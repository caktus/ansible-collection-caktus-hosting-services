from types import SimpleNamespace

import pytest
from ansible_collections.caktus.hosting_services.plugins.modules.eks_addon_update import (
    run,
)

CLUSTER = "c"


def module(check_mode=False, **params):
    defaults = {
        "cluster_name": CLUSTER,
        "addons": ["vpc-cni"],
        "version": "latest",
        "resolve_conflicts": "PRESERVE",
        "wait": False,
        "wait_timeout": 600,
    }
    warnings = []
    return SimpleNamespace(
        params={**defaults, **params},
        check_mode=check_mode,
        warnings=warnings,
        warn=warnings.append,
    )


def addon(version="v1.19.0-eksbuild.1", status="ACTIVE", **extra):
    return {
        "addon": {
            "addonName": "vpc-cni",
            "clusterName": CLUSTER,
            "status": status,
            "addonVersion": version,
            **extra,
        }
    }


def versions(*vs, default=None):
    return {
        "addons": [
            {
                "addonName": "vpc-cni",
                "addonVersions": [
                    {
                        "addonVersion": v,
                        "compatibilities": [
                            {"clusterVersion": "1.35", "defaultVersion": v == default}
                        ],
                    }
                    for v in vs
                ],
            }
        ]
    }


@pytest.fixture
def stubber(eks):
    client, stubber = eks
    stubber.add_response(
        "describe_cluster",
        {"cluster": {"name": CLUSTER, "version": "1.35"}},
        {"name": CLUSTER},
    )
    return client, stubber


def expect_lookup(stubber, addon_response, versions_response):
    stubber.add_response(
        "describe_addon",
        addon_response,
        {"clusterName": CLUSTER, "addonName": "vpc-cni"},
    )
    stubber.add_response(
        "describe_addon_versions",
        versions_response,
        {"addonName": "vpc-cni", "kubernetesVersion": "1.35"},
    )


def test_check_mode_makes_no_update_call(stubber):
    client, stub = stubber
    expect_lookup(stub, addon(), versions("v1.19.0-eksbuild.1", "v1.19.2-eksbuild.3"))
    results = []
    run(module(check_mode=True), client, results)
    assert results[0]["changed"] is True
    assert results[0]["target_version"] == "v1.19.2-eksbuild.3"
    assert results[0]["update_id"] is None


def test_already_current(stubber):
    client, stub = stubber
    expect_lookup(
        stub,
        addon("v1.19.2-eksbuild.3"),
        versions("v1.19.0-eksbuild.1", "v1.19.2-eksbuild.3"),
    )
    results = []
    run(module(), client, results)
    assert results[0]["changed"] is False


def test_update_omits_empty_role_arn_and_waits(stubber):
    client, stub = stubber
    expect_lookup(stub, addon(), versions("v1.19.2-eksbuild.3"))
    stub.add_response(
        "update_addon",
        {"update": {"id": "u1", "status": "InProgress"}},
        {
            "clusterName": CLUSTER,
            "addonName": "vpc-cni",
            "addonVersion": "v1.19.2-eksbuild.3",
            "resolveConflicts": "PRESERVE",
        },
    )
    stub.add_response(
        "describe_update",
        {"update": {"id": "u1", "status": "Successful"}},
        {"name": CLUSTER, "updateId": "u1", "addonName": "vpc-cni"},
    )
    results = []
    run(module(wait=True), client, results)
    assert results[0]["update_id"] == "u1"


def test_update_passes_existing_role_arn(stubber):
    client, stub = stubber
    arn = "arn:aws:iam::123456789012:role/cni"
    expect_lookup(
        stub, addon(serviceAccountRoleArn=arn), versions("v1.19.2-eksbuild.3")
    )
    stub.add_response(
        "update_addon",
        {"update": {"id": "u1", "status": "InProgress"}},
        {
            "clusterName": CLUSTER,
            "addonName": "vpc-cni",
            "addonVersion": "v1.19.2-eksbuild.3",
            "resolveConflicts": "PRESERVE",
            "serviceAccountRoleArn": arn,
        },
    )
    run(module(), client, [])


def test_default_version(stubber):
    client, stub = stubber
    expect_lookup(
        stub,
        addon(),
        versions(
            "v1.19.1-eksbuild.1", "v1.19.2-eksbuild.3", default="v1.19.1-eksbuild.1"
        ),
    )
    results = []
    run(module(check_mode=True, version="default"), client, results)
    assert results[0]["target_version"] == "v1.19.1-eksbuild.1"


def test_vpc_cni_limited_to_one_minor(stubber):
    client, stub = stubber
    expect_lookup(stub, addon(), versions("v1.20.0-eksbuild.1", "v1.21.0-eksbuild.1"))
    results = []
    run(module(check_mode=True), client, results)
    assert results[0]["target_version"] == "v1.20.0-eksbuild.1"


def test_warns_on_unparseable_versions(stubber):
    client, stub = stubber
    expect_lookup(stub, addon(), versions("v1.19.2-eksbuild.3", "weird"))
    mod = module(check_mode=True)
    results = []
    run(mod, client, results)
    assert results[0]["target_version"] == "v1.19.2-eksbuild.3"
    assert mod.warnings == ["vpc-cni: ignoring unparseable versions weird"]


def test_not_installed_is_skipped(stubber):
    client, stub = stubber
    stub.add_client_error(
        "describe_addon",
        service_error_code="ResourceNotFoundException",
        expected_params={"clusterName": CLUSTER, "addonName": "vpc-cni"},
    )
    results = []
    run(module(), client, results)
    assert results[0]["skipped"] is True


def test_not_active_is_skipped(stubber):
    client, stub = stubber
    stub.add_response(
        "describe_addon",
        addon(status="DEGRADED"),
        {"clusterName": CLUSTER, "addonName": "vpc-cni"},
    )
    results = []
    run(module(), client, results)
    assert results[0]["skipped"] is True
    assert "DEGRADED" in results[0]["reason"]


def test_defaults_to_all_installed(stubber):
    client, stub = stubber
    stub.add_response("list_addons", {"addons": ["vpc-cni"]}, {"clusterName": CLUSTER})
    expect_lookup(stub, addon("v1.19.2-eksbuild.3"), versions("v1.19.2-eksbuild.3"))
    results = []
    run(module(addons=None), client, results)
    assert [r["name"] for r in results] == ["vpc-cni"]
