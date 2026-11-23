import json

from ansible_collections.caktus.hosting_services.plugins.modules.aws_identity_center_template import (
    build,
)


def access_records():
    return [
        {
            "logical_id": "ControlPlaneAdmin",
            "name": "ControlPlane-Admin",
            "state": "present",
            "description": "Manage the control plane",
            "target_account_id": "444455556666",
            "managed_policies": [
                "arn:aws:iam::aws:policy/AdministratorAccess"
            ],
            "session_duration": "PT1H",
            "users": ["userone", "usertwo"],
        },
        {
            "logical_id": "ProjectAlphaAdmin",
            "name": "ProjectAlpha-Admin",
            "state": "present",
            "description": "Access ProjectAlpha",
            "role_arn": (
                "arn:aws:iam::777788889999:"
                "role/ProjectAccountAccessRole"
            ),
            "session_duration": "PT4H",
            "users": ["userone"],
        },
        {
            "logical_id": "ProjectBetaAdmin",
            "name": "ProjectBeta-Admin",
            "state": "absent",
        },
    ]


def user_ids():
    return {
        "userone": "11111111-1111-1111-1111-111111111111",
        "usertwo": "22222222-2222-2222-2222-222222222222",
    }


def test_builds_template_summary():
    result = build(
        access=access_records(),
        instance_arn="arn:aws:sso:::instance/ssoins-example",
        identity_store_id="d-1234567890",
        management_account_id="111122223333",
        user_ids=user_ids(),
    )
    resources = json.loads(result["template_body"])["Resources"]

    assert result["resource_count"] == 9
    assert result["resource_types"] == {
        "AWS::IdentityStore::Group": 2,
        "AWS::IdentityStore::GroupMembership": 3,
        "AWS::SSO::Assignment": 2,
        "AWS::SSO::PermissionSet": 2,
    }
    assert "ProjectBetaAdminPermissionSet" not in resources
    assert resources["ControlPlaneAdminAssignment"]["Properties"]["TargetId"] == (
        "444455556666"
    )
    assert resources["ProjectAlphaAdminAssignment"]["Properties"]["TargetId"] == (
        "111122223333"
    )


def test_builds_anchor_for_minimal_absent_record():
    result = build(
        access=[{"logical_id": "ProjectBetaAdmin", "state": "absent"}],
        instance_arn="arn:aws:sso:::instance/ssoins-example",
        identity_store_id="d-1234567890",
        management_account_id="111122223333",
        user_ids={},
    )

    assert json.loads(result["template_body"])["Resources"] == {
        "EmptyStackAnchor": {
            "Type": "AWS::CloudFormation::WaitConditionHandle"
        }
    }
