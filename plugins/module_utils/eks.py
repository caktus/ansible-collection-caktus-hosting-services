"""Pure version-resolution logic for the EKS update modules (no boto imports)."""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from typing import Any

_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-(?:eksbuild\.(\d+)|(\d{8})))?$")

_SSM_AMI_PATHS = {
    "AL2_x86_64": "amazon-linux-2",
    "AL2_x86_64_GPU": "amazon-linux-2-gpu",
    "AL2_ARM_64": "amazon-linux-2-arm64",
    "AL2023_x86_64_STANDARD": "amazon-linux-2023/x86_64/standard",
    "AL2023_ARM_64_STANDARD": "amazon-linux-2023/arm64/standard",
    "AL2023_x86_64_NVIDIA": "amazon-linux-2023/x86_64/nvidia",
    "AL2023_x86_64_NEURON": "amazon-linux-2023/x86_64/neuron",
}


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int
    build: int = 0  # eksbuild number or AMI release date
    raw: str = field(default="", compare=False)
    is_default: bool = field(default=False, compare=False)

    @classmethod
    def parse(cls, raw: str | None, is_default: bool = False) -> Version | None:
        m = _VERSION_RE.match(raw or "")
        if not m:
            return None
        major, minor, patch, build, date = m.groups()
        return cls(
            int(major), int(minor), int(patch), int(build or date or 0), raw, is_default
        )

    def within_minor_step(self, other: Version) -> bool:
        return (self.major, self.minor) <= (other.major, other.minor + 1)


class VersionCandidates(dict[str, Version]):
    """Raw version string -> Version. Strings that don't parse go in ``rejected``."""

    def __init__(
        self, versions: Iterable[Version] = (), rejected: Iterable[str] = ()
    ) -> None:
        super().__init__((v.raw, v) for v in versions)
        self.rejected = tuple(rejected)

    @classmethod
    def from_strings(
        cls, raws: Iterable[str], defaults: Collection[str] = frozenset()
    ) -> VersionCandidates:
        parsed, rejected = [], []
        for raw in raws:
            version = Version.parse(raw, is_default=raw in defaults)
            if version:
                parsed.append(version)
            else:
                rejected.append(raw)
        return cls(parsed, rejected)

    @classmethod
    def from_addon_versions(
        cls, addon_versions: list[dict[str, Any]]
    ) -> VersionCandidates:
        defaults = {
            v["addonVersion"]
            for v in addon_versions
            if any(c.get("defaultVersion") for c in v.get("compatibilities", []))
        }
        return cls.from_strings((v["addonVersion"] for v in addon_versions), defaults)

    def latest(self) -> Version | None:
        return max(self.values(), default=None)

    def default(self) -> Version | None:
        return next((v for v in self.values() if v.is_default), None)

    def within_minor_step(self, current: Version) -> VersionCandidates:
        """AWS recommends vpc-cni move one minor version at a time."""
        return VersionCandidates(
            (v for v in self.values() if v.within_minor_step(current)), self.rejected
        )


@dataclass
class Resolution:
    target: str
    changed: bool
    reason: str


def resolve_target(
    current: str, candidates: VersionCandidates, requested: str = "latest"
) -> Resolution:
    """Pick the version to move to. Never returns a downgrade."""
    target = candidates.latest() if requested == "latest" else candidates.get(requested)
    if target is None:
        return Resolution(
            current, False, "requested version not compatible with this cluster"
        )
    if target.raw == current:
        return Resolution(current, False, "already at target")

    current_v = Version.parse(current)
    if current_v is None:
        return Resolution(
            current, False, f"cannot compare {current!r} to {target.raw!r}"
        )
    if target <= current_v:
        return Resolution(current, False, "already at or past target")
    return Resolution(target.raw, True, "update available")


def ssm_release_version_path(ami_type: str, k8s_version: str) -> str | None:
    subpath = _SSM_AMI_PATHS.get(ami_type)
    if subpath is None:
        return None
    return f"/aws/service/eks/optimized-ami/{k8s_version}/{subpath}/recommended/release_version"


def nodegroup_skip_reason(
    nodegroup: dict[str, Any], cluster_version: str
) -> str | None:
    if nodegroup.get("amiType") == "CUSTOM":
        return "custom AMI nodegroups are not supported"
    if nodegroup.get("status") != "ACTIVE":
        return f"nodegroup status is {nodegroup.get('status')}"
    if nodegroup.get("version") != cluster_version:
        return (
            f"nodegroup Kubernetes version {nodegroup.get('version')} "
            f"differs from cluster version {cluster_version}"
        )
    return None


def planned(name: str, current: str, resolution: Resolution) -> dict[str, Any]:
    return {
        "name": name,
        "current_version": current,
        "target_version": resolution.target,
        "changed": resolution.changed,
        "skipped": False,
        "reason": resolution.reason,
        "update_id": None,
    }


def skipped(name: str, current: str | None, reason: str) -> dict[str, Any]:
    return {
        "name": name,
        "current_version": current,
        "target_version": current,
        "changed": False,
        "skipped": True,
        "reason": reason,
        "update_id": None,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "changed": any(r["changed"] for r in results),
        "updates": results,
        "diff": {
            "before": {r["name"]: r["current_version"] for r in results},
            "after": {r["name"]: r["target_version"] for r in results},
        },
    }
