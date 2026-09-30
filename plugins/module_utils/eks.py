"""Pure version-resolution logic for the EKS update modules (no boto imports)."""

import re
from dataclasses import dataclass

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


def parse_version(version):
    m = _VERSION_RE.match(version or "")
    if not m:
        return None
    major, minor, patch, build, date = m.groups()
    return (int(major), int(minor), int(patch), int(build or date or 0))


@dataclass
class Resolution:
    target: str
    changed: bool
    reason: str


def resolve_target(current, available, requested="latest"):
    """Pick the version to move to. Never returns a downgrade."""
    if requested == "latest":
        parsed = sorted((v for v in available if parse_version(v)), key=parse_version)
        target = parsed[-1] if parsed else None
    else:
        target = requested if requested in available else None

    if target is None:
        return Resolution(
            current, False, "requested version not compatible with this cluster"
        )
    if target == current:
        return Resolution(current, False, "already at target")

    current_v, target_v = parse_version(current), parse_version(target)
    if current_v is None or target_v is None:
        return Resolution(current, False, f"cannot compare {current!r} to {target!r}")
    if target_v <= current_v:
        return Resolution(current, False, "already at or past target")
    return Resolution(target, True, "update available")


def default_version(addon_versions):
    """Return the addonVersion flagged defaultVersion for this cluster, if any."""
    for v in addon_versions:
        if any(c.get("defaultVersion") for c in v.get("compatibilities", [])):
            return v["addonVersion"]
    return None


def limit_minor_step(current, available):
    """Drop versions more than one minor ahead of current (AWS guidance for vpc-cni)."""
    current_v = parse_version(current)
    if current_v is None:
        return available
    return [
        v
        for v in available
        if (p := parse_version(v)) and (p[0], p[1]) <= (current_v[0], current_v[1] + 1)
    ]


def ssm_release_version_path(ami_type, k8s_version):
    subpath = _SSM_AMI_PATHS.get(ami_type)
    if subpath is None:
        return None
    return f"/aws/service/eks/optimized-ami/{k8s_version}/{subpath}/recommended/release_version"


def nodegroup_skip_reason(nodegroup, cluster_version):
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


def planned(name, current, resolution):
    return {
        "name": name,
        "current_version": current,
        "target_version": resolution.target,
        "changed": resolution.changed,
        "skipped": False,
        "reason": resolution.reason,
        "update_id": None,
    }


def skipped(name, current, reason):
    return {
        "name": name,
        "current_version": current,
        "target_version": current,
        "changed": False,
        "skipped": True,
        "reason": reason,
        "update_id": None,
    }


def summarize(results):
    return {
        "changed": any(r["changed"] for r in results),
        "updates": results,
        "diff": {
            "before": {r["name"]: r["current_version"] for r in results},
            "after": {r["name"]: r["target_version"] for r in results},
        },
    }
