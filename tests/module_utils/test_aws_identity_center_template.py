import json
from dataclasses import asdict
from hashlib import sha1
from pathlib import Path

import yaml
from ansible_collections.caktus.hosting_services.plugins.module_utils.aws_identity_center_template import (
    AccessRecord,
    TemplateInput,
    render_template,
)
from jinja2 import Environment, FileSystemLoader, StrictUndefined

FIXTURES = Path(__file__).parent / "fixtures"


class CloudFormationLoader(yaml.SafeLoader):
    pass


CloudFormationLoader.add_constructor(
    "!GetAtt",
    lambda loader, node: {"Fn::GetAtt": loader.construct_scalar(node).split(".", 1)},
)


def template_input():
    return TemplateInput(
        instance_arn="arn:aws:sso:::instance/ssoins-example",
        identity_store_id="d-example",
        management_account_id="111122223333",
        user_ids={
            "userone": "11111111-1111-1111-1111-111111111111",
            "usertwo": "22222222-2222-2222-2222-222222222222",
        },
        access=(
            AccessRecord(
                logical_id="ControlPlaneAdmin",
                name="ControlPlane-Admin",
                state="present",
                description="Manage the control plane",
                target_account_id="444455556666",
                managed_policies=("arn:aws:iam::aws:policy/AdministratorAccess",),
                session_duration="PT1H",
                users=("userone", "usertwo"),
            ),
            AccessRecord(
                logical_id="ProjectAlphaProdAdmin",
                name="ProjectAlpha-Prod-Admin",
                state="present",
                description="Access ProjectAlpha production",
                role_arn=("arn:aws:iam::777788889999:role/ProjectAccountAccessRole"),
                session_duration="PT1H",
                users=("userone", "usertwo"),
            ),
            AccessRecord(
                logical_id="ProjectBetaDevAdmin",
                name="ProjectBeta-Dev-Admin",
                state="present",
                description="Access ProjectBeta development",
                role_arn=("arn:aws:iam::777788889999:role/ProjectAccountAccessRole"),
                session_duration="PT4H",
                users=("userone", "usertwo"),
            ),
            AccessRecord(
                logical_id="OtherProjectAdmin",
                name="Other-Project-Admin",
                state="absent",
                description="Access another project",
                role_arn=("arn:aws:iam::777788889999:role/ProjectAccountAccessRole"),
                session_duration="PT4H",
                users=(),
            ),
        ),
    )


def render():
    return json.loads(render_template(template_input()))


def test_renders_present_access_records():
    resources = render()["Resources"]

    assert "ControlPlaneAdminPermissionSet" in resources
    assert "ProjectAlphaProdAdminPermissionSet" in resources
    assert "ProjectBetaDevAdminPermissionSet" in resources
    assert "OtherProjectAdminPermissionSet" not in resources
    assert (
        sum(
            resource["Type"] == "AWS::IdentityStore::Group"
            for resource in resources.values()
        )
        == 3
    )
    assert (
        sum(
            resource["Type"] == "AWS::IdentityStore::GroupMembership"
            for resource in resources.values()
        )
        == 6
    )


def test_renders_managed_and_inline_policies():
    resources = render()["Resources"]
    control_plane = resources["ControlPlaneAdminPermissionSet"]["Properties"]
    project = resources["ProjectAlphaProdAdminPermissionSet"]["Properties"]

    assert control_plane["ManagedPolicies"] == [
        "arn:aws:iam::aws:policy/AdministratorAccess"
    ]
    assert project["InlinePolicy"]["Statement"] == [
        {
            "Effect": "Allow",
            "Action": "sts:AssumeRole",
            "Resource": ("arn:aws:iam::777788889999:role/ProjectAccountAccessRole"),
        }
    ]


def test_preserves_explicit_empty_managed_policy_list():
    data = template_input()
    record = data.access[1]
    explicit_empty = AccessRecord(
        logical_id=record.logical_id,
        name=record.name,
        state=record.state,
        description=record.description,
        session_duration=record.session_duration,
        users=record.users,
        managed_policies=(),
        role_arn=record.role_arn,
    )
    data = TemplateInput(
        instance_arn=data.instance_arn,
        identity_store_id=data.identity_store_id,
        management_account_id=data.management_account_id,
        user_ids=data.user_ids,
        access=(explicit_empty,),
    )

    properties = json.loads(render_template(data))["Resources"][
        "ProjectAlphaProdAdminPermissionSet"
    ]["Properties"]

    assert properties["ManagedPolicies"] == []
    assert "InlinePolicy" not in properties


def test_renders_assignments_with_stable_references():
    resources = render()["Resources"]
    control_plane = resources["ControlPlaneAdminAssignment"]["Properties"]
    project = resources["ProjectAlphaProdAdminAssignment"]["Properties"]

    assert control_plane["TargetId"] == "444455556666"
    assert project["TargetId"] == "111122223333"
    assert control_plane["PrincipalType"] == "GROUP"
    assert control_plane["PrincipalId"] == {
        "Fn::GetAtt": [
            "ControlPlaneAdminGroup",
            "GroupId",
        ]
    }
    assert (
        "ControlPlaneAdminUser"
        "73ca4a1db058ed915e07b5716e0c9463c359fd88Membership" in resources
    )


def test_renders_memberships_for_all_users():
    resources = render()["Resources"]
    memberships = [
        resource
        for resource in resources.values()
        if resource["Type"] == "AWS::IdentityStore::GroupMembership"
    ]

    assert len(memberships) == 6
    assert {
        membership["Properties"]["MemberId"]["UserId"] for membership in memberships
    } == {
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
    }


def test_renders_anchor_when_all_records_are_absent():
    data = template_input()
    data = TemplateInput(
        instance_arn=data.instance_arn,
        identity_store_id=data.identity_store_id,
        management_account_id=data.management_account_id,
        user_ids=data.user_ids,
        access=(data.access[-1],),
    )

    resources = json.loads(render_template(data))["Resources"]

    assert resources == {
        "EmptyStackAnchor": {"Type": "AWS::CloudFormation::WaitConditionHandle"}
    }


def test_matches_legacy_template_resources():
    data = template_input()
    access = []
    for item in data.access:
        record = asdict(item)
        if record["managed_policies"]:
            record.pop("role_arn")
        else:
            record.pop("managed_policies")
        if record["target_account_id"] is None:
            record.pop("target_account_id")
        access.append(record)

    environment = Environment(
        loader=FileSystemLoader(FIXTURES),
        undefined=StrictUndefined,
        trim_blocks=True,
    )
    environment.filters["to_json"] = json.dumps
    legacy = environment.get_template("legacy_identity_center.yml.j2").render(
        aws_sso_access=access,
        aws_sso_identity_store_id=data.identity_store_id,
        aws_sso_instance_arn=data.instance_arn,
        aws_sso_management_account_id=data.management_account_id,
        aws_sso_user_ids=data.user_ids,
        aws_sso_user_logical_ids={
            username: f"User{sha1(username.encode()).hexdigest()}"
            for username in data.user_ids
        },
    )

    legacy_resources = yaml.load(legacy, Loader=CloudFormationLoader)["Resources"]
    troposphere_resources = json.loads(render_template(data))["Resources"]

    assert troposphere_resources == legacy_resources
