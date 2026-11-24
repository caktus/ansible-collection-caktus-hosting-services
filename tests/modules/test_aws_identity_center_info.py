import pytest
from ansible_collections.caktus.hosting_services.plugins.modules.aws_identity_center_info import (
    DiscoveryError,
    discover,
)

INSTANCE_ARN = "arn:aws:sso:::instance/ssoins-example"
IDENTITY_STORE_ID = "d-1234567890"


def access(*users, state="present"):
    return [
        {
            "logical_id": "ProjectAlphaAdmin",
            "state": state,
            "users": list(users),
        }
    ]


def expect_identity(stub, caller_account="111122223333"):
    stub.add_response(
        "get_caller_identity",
        {
            "Account": caller_account,
            "Arn": "arn:aws:iam::111122223333:user/test",
            "UserId": "AIDATEST",
        },
        {},
    )


def expect_instances(stub, instances):
    stub.add_response("list_instances", {"Instances": instances}, {})


def expect_user(stub, username, user_id):
    stub.add_response(
        "get_user_id",
        {
            "UserId": user_id,
            "UserArn": f"arn:aws:identitystore:::user/{user_id}",
            "IdentityStoreId": IDENTITY_STORE_ID,
        },
        {
            "IdentityStoreId": IDENTITY_STORE_ID,
            "AlternateIdentifier": {
                "UniqueAttribute": {
                    "AttributePath": "userName",
                    "AttributeValue": f"{username}@example.com",
                }
            },
        },
    )


def test_discovers_identity_center_and_unique_users(sts, sso_admin, identitystore):
    sts_client, sts_stub = sts
    sso_client, sso_stub = sso_admin
    identity_client, identity_stub = identitystore
    expect_identity(sts_stub)
    expect_instances(
        sso_stub,
        [{"InstanceArn": INSTANCE_ARN, "IdentityStoreId": IDENTITY_STORE_ID}],
    )
    expect_user(
        identity_stub,
        "userone",
        "11111111-1111-1111-1111-111111111111",
    )
    expect_user(
        identity_stub,
        "usertwo",
        "22222222-2222-2222-2222-222222222222",
    )

    result = discover(
        sts_client,
        sso_client,
        identity_client,
        access("userone", "usertwo") + access("userone"),
        "example.com",
    )

    assert result == {
        "account_id": "111122223333",
        "instance_arn": INSTANCE_ARN,
        "identity_store_id": IDENTITY_STORE_ID,
        "user_ids": {
            "userone": "11111111-1111-1111-1111-111111111111",
            "usertwo": "22222222-2222-2222-2222-222222222222",
        },
    }


@pytest.mark.parametrize("instance_count", [0, 2])
def test_requires_exactly_one_instance(sts, sso_admin, identitystore, instance_count):
    sts_client, sts_stub = sts
    sso_client, sso_stub = sso_admin
    identity_client, _ = identitystore
    expect_identity(sts_stub)
    instances = [
        {
            "InstanceArn": f"{INSTANCE_ARN}-{index}",
            "IdentityStoreId": f"{IDENTITY_STORE_ID}-{index}",
        }
        for index in range(instance_count)
    ]
    expect_instances(sso_stub, instances)

    with pytest.raises(DiscoveryError, match=rf"found {instance_count}"):
        discover(
            sts_client,
            sso_client,
            identity_client,
            access("userone"),
            "example.com",
        )


def test_names_missing_identity_store_user(sts, sso_admin, identitystore):
    sts_client, sts_stub = sts
    sso_client, sso_stub = sso_admin
    identity_client, identity_stub = identitystore
    expect_identity(sts_stub)
    expect_instances(
        sso_stub,
        [{"InstanceArn": INSTANCE_ARN, "IdentityStoreId": IDENTITY_STORE_ID}],
    )
    identity_stub.add_client_error(
        "get_user_id",
        service_error_code="ResourceNotFoundException",
        service_message="user not found",
        expected_params={
            "IdentityStoreId": IDENTITY_STORE_ID,
            "AlternateIdentifier": {
                "UniqueAttribute": {
                    "AttributePath": "userName",
                    "AttributeValue": "missing@example.com",
                }
            },
        },
    )

    with pytest.raises(DiscoveryError, match="missing@example.com"):
        discover(
            sts_client,
            sso_client,
            identity_client,
            access("missing"),
            "example.com",
        )
