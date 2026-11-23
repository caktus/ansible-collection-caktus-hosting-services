"""Build CloudFormation resources for IAM Identity Center authorization."""

import hashlib
from dataclasses import dataclass
from typing import Literal

from troposphere import GetAtt, Template
from troposphere.cloudformation import WaitConditionHandle
from troposphere.identitystore import Group, GroupMembership, MemberId
from troposphere.sso import Assignment, PermissionSet


@dataclass(frozen=True)
class PresentAccessRecord:
    logical_id: str
    name: str
    state: Literal["present"]
    description: str
    session_duration: str
    users: tuple[str, ...]
    managed_policies: tuple[str, ...] | None = None
    role_arn: str | None = None
    target_account_id: str | None = None


@dataclass(frozen=True)
class AbsentAccessRecord:
    logical_id: str
    state: Literal["absent"]


AccessRecord = PresentAccessRecord | AbsentAccessRecord


@dataclass(frozen=True)
class TemplateInput:
    instance_arn: str
    identity_store_id: str
    management_account_id: str
    access: tuple[AccessRecord, ...]
    user_ids: dict[str, str]


def _user_logical_id(username: str) -> str:
    """Build a stable CloudFormation membership identifier."""
    digest = hashlib.sha1(username.encode()).hexdigest()
    return f"User{digest}"


def _assume_role_policy(role_arn: str) -> dict:
    """Build an inline policy for one role ARN."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "sts:AssumeRole",
                "Resource": role_arn,
            }
        ],
    }


def render_template(template_input: TemplateInput) -> str:
    """Render an IAM Identity Center CloudFormation template.

    Args:
        template_input: Access records and AWS discovery values.

    Returns:
        A CloudFormation JSON template.
    """
    template = Template(Description="IAM Identity Center authorization")
    present_access = [item for item in template_input.access if item.state == "present"]

    if not present_access:
        template.add_resource(WaitConditionHandle("EmptyStackAnchor"))
        return template.to_json()

    for item in present_access:
        logical_id = item.logical_id
        group = template.add_resource(
            Group(
                f"{logical_id}Group",
                IdentityStoreId=template_input.identity_store_id,
                DisplayName=item.name,
                Description=item.description,
            )
        )

        for username in item.users:
            template.add_resource(
                GroupMembership(
                    f"{logical_id}{_user_logical_id(username)}Membership",
                    IdentityStoreId=template_input.identity_store_id,
                    GroupId=GetAtt(group, "GroupId"),
                    MemberId=MemberId(UserId=template_input.user_ids[username]),
                )
            )

        permission_set_properties = {
            "InstanceArn": template_input.instance_arn,
            "Name": item.name,
            "Description": item.description,
            "SessionDuration": item.session_duration,
        }
        if item.managed_policies is not None:
            permission_set_properties["ManagedPolicies"] = list(item.managed_policies)
        else:
            permission_set_properties["InlinePolicy"] = _assume_role_policy(
                item.role_arn
            )

        permission_set = template.add_resource(
            PermissionSet(
                f"{logical_id}PermissionSet",
                **permission_set_properties,
            )
        )

        template.add_resource(
            Assignment(
                f"{logical_id}Assignment",
                InstanceArn=template_input.instance_arn,
                PermissionSetArn=GetAtt(permission_set, "PermissionSetArn"),
                PrincipalId=GetAtt(group, "GroupId"),
                PrincipalType="GROUP",
                TargetId=(
                    item.target_account_id or template_input.management_account_id
                ),
                TargetType="AWS_ACCOUNT",
            )
        )

    return template.to_json()
