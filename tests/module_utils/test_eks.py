from types import MappingProxyType

import pytest

from plugins.module_utils.eks import (
    Resolution,
    Version,
    VersionCandidates,
    nodegroup_skip_reason,
    resolve_target,
    ssm_release_version_path,
    summarize,
)
from plugins.module_utils.eks_aws import UpdateFailed, wait_for_update


class TestVersion:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("v1.19.2-eksbuild.3", (1, 19, 2, 3)),
            ("v1.11.4", (1, 11, 4, 0)),
            ("1.31.2-20241121", (1, 31, 2, 20241121)),
        ],
    )
    def test_parse(self, raw, expected):
        v = Version.parse(raw)
        assert (v.major, v.minor, v.patch, v.build) == expected
        assert v.raw == raw

    @pytest.mark.parametrize("raw", ["", None, "latest", "1.31", "v1.2.3-rc1"])
    def test_parse_invalid(self, raw):
        assert Version.parse(raw) is None

    def test_ordering_ignores_raw_and_default(self):
        assert Version.parse("v1.19.2-eksbuild.3") > Version.parse("1.19.2-eksbuild.1")
        assert Version.parse("v1.2.3") == Version.parse("1.2.3", is_default=True)


class TestVersionCandidates:
    def test_from_strings_tracks_rejected(self):
        candidates = VersionCandidates.from_strings(["v1.19.2-eksbuild.3", "weird"])
        assert list(candidates) == ["v1.19.2-eksbuild.3"]
        assert candidates.rejected == ("weird",)

    def test_from_addon_versions_marks_default(self):
        candidates = VersionCandidates.from_addon_versions(
            [
                {
                    "addonVersion": "v1.19.2-eksbuild.3",
                    "compatibilities": [{"defaultVersion": False}],
                },
                {
                    "addonVersion": "v1.19.0-eksbuild.1",
                    "compatibilities": [{"defaultVersion": True}],
                },
            ]
        )
        assert candidates.default().raw == "v1.19.0-eksbuild.1"
        assert candidates.latest().raw == "v1.19.2-eksbuild.3"

    def test_empty(self):
        assert VersionCandidates().latest() is None
        assert VersionCandidates().default() is None

    def test_within_minor_step_keeps_rejected(self):
        candidates = VersionCandidates.from_strings(
            ["v1.18.5-eksbuild.1", "v1.19.2-eksbuild.3", "v1.20.0-eksbuild.1", "weird"]
        )
        limited = candidates.within_minor_step(Version.parse("v1.18.0-eksbuild.1"))
        assert list(limited) == ["v1.18.5-eksbuild.1", "v1.19.2-eksbuild.3"]
        assert limited.rejected == ("weird",)


CANDIDATES = VersionCandidates.from_strings(
    ["v1.18.0-eksbuild.1", "v1.19.2-eksbuild.3", "v1.19.2-eksbuild.1"]
)


class TestResolveTarget:
    def test_latest(self):
        assert resolve_target("v1.18.0-eksbuild.1", CANDIDATES) == Resolution(
            "v1.19.2-eksbuild.3", True, "update available"
        )

    def test_latest_already_current(self):
        result = resolve_target("v1.19.2-eksbuild.3", CANDIDATES)
        assert result == Resolution("v1.19.2-eksbuild.3", False, "already at target")

    def test_explicit(self):
        result = resolve_target("v1.18.0-eksbuild.1", CANDIDATES, "v1.19.2-eksbuild.1")
        assert result == Resolution("v1.19.2-eksbuild.1", True, "update available")

    def test_explicit_not_available(self):
        result = resolve_target("v1.18.0-eksbuild.1", CANDIDATES, "v9.9.9-eksbuild.1")
        assert result.changed is False
        assert "not compatible" in result.reason

    def test_refuses_downgrade(self):
        result = resolve_target("v1.20.0-eksbuild.1", CANDIDATES)
        assert result == Resolution(
            "v1.20.0-eksbuild.1", False, "already at or past target"
        )

    def test_unparseable_current(self):
        result = resolve_target("weird", CANDIDATES)
        assert result.changed is False
        assert "cannot compare" in result.reason

    def test_no_candidates(self):
        assert (
            resolve_target("v1.18.0-eksbuild.1", VersionCandidates()).changed is False
        )

    def test_ami_release(self):
        candidates = VersionCandidates.from_strings(["1.35.0-20260915"])
        result = resolve_target("1.35.0-20260801", candidates, "1.35.0-20260915")
        assert result == Resolution("1.35.0-20260915", True, "update available")


def test_ssm_release_version_path():
    assert ssm_release_version_path("AL2023_x86_64_STANDARD", "1.35") == (
        "/aws/service/eks/optimized-ami/1.35/amazon-linux-2023/x86_64/standard"
        "/recommended/release_version"
    )
    assert ssm_release_version_path("BOTTLEROCKET_x86_64", "1.35") is None


class TestNodegroupSkipReason:
    ng = MappingProxyType(
        {"amiType": "AL2023_x86_64_STANDARD", "status": "ACTIVE", "version": "1.35"}
    )

    def test_ok(self):
        assert nodegroup_skip_reason(dict(self.ng), "1.35") is None

    def test_custom(self):
        assert "custom" in nodegroup_skip_reason(
            {**self.ng, "amiType": "CUSTOM"}, "1.35"
        )

    def test_not_active(self):
        assert "UPDATING" in nodegroup_skip_reason(
            {**self.ng, "status": "UPDATING"}, "1.35"
        )

    def test_version_mismatch(self):
        assert "differs" in nodegroup_skip_reason(dict(self.ng), "1.36")


def test_summarize():
    results = [
        {"name": "a", "current_version": "1", "target_version": "2", "changed": True},
        {"name": "b", "current_version": "1", "target_version": "1", "changed": False},
    ]
    summary = summarize(results)
    assert summary["changed"] is True
    assert summary["diff"] == {
        "before": {"a": "1", "b": "1"},
        "after": {"a": "2", "b": "1"},
    }


class TestWaitForUpdate:
    params = MappingProxyType({"name": "c", "updateId": "u1", "addonName": "vpc-cni"})

    def _add(self, stubber, status, errors=None):
        update = {"id": "u1", "status": status}
        if errors:
            update["errors"] = errors
        stubber.add_response("describe_update", {"update": update}, dict(self.params))

    def test_success(self, eks):
        client, stubber = eks
        self._add(stubber, "InProgress")
        self._add(stubber, "Successful")
        update = wait_for_update(
            client, "c", "u1", 60, sleep=lambda s: None, addonName="vpc-cni"
        )
        assert update["status"] == "Successful"

    def test_failed(self, eks):
        client, stubber = eks
        self._add(
            stubber,
            "Failed",
            [{"errorCode": "PodEvictionFailure", "errorMessage": "PDB blocked drain"}],
        )
        with pytest.raises(UpdateFailed, match="PodEvictionFailure: PDB blocked drain"):
            wait_for_update(
                client, "c", "u1", 60, sleep=lambda s: None, addonName="vpc-cni"
            )

    def test_timeout(self, eks):
        client, stubber = eks
        self._add(stubber, "InProgress")
        with pytest.raises(UpdateFailed, match="timed out"):
            wait_for_update(
                client, "c", "u1", 0, sleep=lambda s: None, addonName="vpc-cni"
            )
