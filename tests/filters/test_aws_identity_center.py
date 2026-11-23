import json

import pytest
from ansible.errors import AnsibleFilterError
from ansible_collections.caktus.hosting_services.plugins.filter.aws_identity_center import (
    FilterModule,
)


def filter_module():
    return FilterModule().filters()["aws_identity_center_template"]


def template_data():
    return {
        "instance_arn": "arn:aws:sso:::instance/ssoins-example",
        "identity_store_id": "d-example",
        "management_account_id": "111122223333",
        "user_ids": {
            "userone": "11111111-1111-1111-1111-111111111111",
        },
        "access": [
            {
                "logical_id": "ProjectAlphaAdmin",
                "name": "ProjectAlpha-Admin",
                "state": "present",
                "description": "Access ProjectAlpha",
                "session_duration": "PT4H",
                "role_arn": ("arn:aws:iam::777788889999:role/ProjectAccountAccessRole"),
                "users": ["userone"],
            }
        ],
    }


def test_filter_renders_template():
    rendered = json.loads(filter_module()(template_data()))

    assert rendered["Resources"]["ProjectAlphaAdminAssignment"]["Type"] == (
        "AWS::SSO::Assignment"
    )


def test_filter_names_missing_top_level_input():
    data = template_data()
    del data["identity_store_id"]

    with pytest.raises(AnsibleFilterError, match="identity_store_id"):
        filter_module()(data)


def test_filter_names_missing_access_input():
    data = template_data()
    del data["access"][0]["session_duration"]

    with pytest.raises(
        AnsibleFilterError,
        match="ProjectAlphaAdmin.*session_duration",
    ):
        filter_module()(data)


def test_filter_names_missing_user_id():
    data = template_data()
    data["access"][0]["users"] = ["userthree"]

    with pytest.raises(
        AnsibleFilterError,
        match="Unable to render IAM Identity Center template.*userthree",
    ):
        filter_module()(data)


def test_filter_accepts_minimal_absent_record():
    data = template_data()
    data["access"] = [{"logical_id": "ProjectAlphaAdmin", "state": "absent"}]

    resources = json.loads(filter_module()(data))["Resources"]

    assert resources == {
        "EmptyStackAnchor": {"Type": "AWS::CloudFormation::WaitConditionHandle"}
    }
