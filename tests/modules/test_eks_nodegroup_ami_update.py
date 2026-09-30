from types import SimpleNamespace

import pytest
from ansible_collections.caktus.hosting_services.plugins.module_utils.eks_aws import (
    UpdateFailed,
)
from ansible_collections.caktus.hosting_services.plugins.modules.eks_nodegroup_ami_update import (
    run,
)

CLUSTER = "c"
NG = "ng-1"
SSM_PATH = "/aws/service/eks/optimized-ami/1.35/amazon-linux-2023/x86_64/standard/recommended/release_version"


def module(check_mode=False, **params):
    defaults = {
        "cluster_name": CLUSTER,
        "nodegroups": [NG],
        "release_version": "latest",
        "force": False,
        "wait": False,
        "wait_timeout": 3600,
    }
    return SimpleNamespace(params={**defaults, **params}, check_mode=check_mode)


def nodegroup(release="1.35.0-20260801", **extra):
    return {
        "nodegroup": {
            "nodegroupName": NG,
            "clusterName": CLUSTER,
            "version": "1.35",
            "releaseVersion": release,
            "status": "ACTIVE",
            "amiType": "AL2023_x86_64_STANDARD",
            **extra,
        }
    }


@pytest.fixture
def clients(eks, ssm):
    eks_client, eks_stub = eks
    eks_stub.add_response(
        "describe_cluster",
        {"cluster": {"name": CLUSTER, "version": "1.35"}},
        {"name": CLUSTER},
    )
    return eks_client, eks_stub, ssm[0], ssm[1]


def expect_describe(stub, response):
    stub.add_response(
        "describe_nodegroup", response, {"clusterName": CLUSTER, "nodegroupName": NG}
    )


def expect_ssm(stub, value="1.35.0-20260915"):
    stub.add_response(
        "get_parameter",
        {"Parameter": {"Name": SSM_PATH, "Value": value}},
        {"Name": SSM_PATH},
    )


def test_check_mode_makes_no_update_call(clients):
    eks, eks_stub, ssm, ssm_stub = clients
    expect_describe(eks_stub, nodegroup())
    expect_ssm(ssm_stub)
    results = []
    run(module(check_mode=True), eks, ssm, results)
    assert results[0]["changed"] is True
    assert results[0]["target_version"] == "1.35.0-20260915"


def test_already_current(clients):
    eks, eks_stub, ssm, ssm_stub = clients
    expect_describe(eks_stub, nodegroup("1.35.0-20260915"))
    expect_ssm(ssm_stub)
    results = []
    run(module(), eks, ssm, results)
    assert results[0]["changed"] is False


def test_update_sends_launch_template_id_only(clients):
    eks, eks_stub, ssm, ssm_stub = clients
    lt = {"name": "lt", "version": "3", "id": "lt-0123"}
    expect_describe(eks_stub, nodegroup(launchTemplate=lt))
    expect_ssm(ssm_stub)
    eks_stub.add_response(
        "update_nodegroup_version",
        {"update": {"id": "u1", "status": "InProgress"}},
        {
            "clusterName": CLUSTER,
            "nodegroupName": NG,
            "releaseVersion": "1.35.0-20260915",
            "force": False,
            "launchTemplate": {"id": "lt-0123", "version": "3"},
        },
    )
    eks_stub.add_response(
        "describe_update",
        {"update": {"id": "u1", "status": "Successful"}},
        {"name": CLUSTER, "updateId": "u1", "nodegroupName": NG},
    )
    results = []
    run(module(wait=True), eks, ssm, results)
    assert results[0]["update_id"] == "u1"


def test_explicit_release_skips_ssm(clients):
    eks, eks_stub, ssm, _ = clients
    expect_describe(eks_stub, nodegroup())
    results = []
    run(module(check_mode=True, release_version="1.35.0-20260901"), eks, ssm, results)
    assert results[0]["target_version"] == "1.35.0-20260901"


def test_explicit_downgrade_refused(clients):
    eks, eks_stub, ssm, _ = clients
    expect_describe(eks_stub, nodegroup())
    results = []
    run(module(release_version="1.35.0-20260701"), eks, ssm, results)
    assert results[0]["changed"] is False


def test_custom_ami_skipped(clients):
    eks, eks_stub, ssm, _ = clients
    expect_describe(eks_stub, nodegroup(amiType="CUSTOM"))
    results = []
    run(module(), eks, ssm, results)
    assert results[0]["skipped"] is True


def test_missing_ssm_parameter_fails(clients):
    eks, eks_stub, ssm, ssm_stub = clients
    expect_describe(eks_stub, nodegroup())
    ssm_stub.add_client_error(
        "get_parameter",
        service_error_code="ParameterNotFound",
        expected_params={"Name": SSM_PATH},
    )
    with pytest.raises(UpdateFailed, match="no SSM release_version parameter"):
        run(module(), eks, ssm, [])
