"""Expose IAM Identity Center template generation to Ansible."""

from collections.abc import Mapping

from ansible.errors import AnsibleFilterError
from ansible_collections.caktus.hosting_services.plugins.module_utils.aws_identity_center_template import (
    AbsentAccessRecord,
    PresentAccessRecord,
    TemplateInput,
    render_template,
)


def _present_access(value: Mapping) -> PresentAccessRecord:
    """Convert a present access mapping."""
    return PresentAccessRecord(
        logical_id=value["logical_id"],
        name=value["name"],
        state="present",
        description=value["description"],
        session_duration=value["session_duration"],
        users=tuple(value["users"]),
        managed_policies=(
            tuple(value["managed_policies"]) if "managed_policies" in value else None
        ),
        role_arn=value.get("role_arn"),
        target_account_id=value.get("target_account_id"),
    )


def _access_record(value: Mapping) -> PresentAccessRecord | AbsentAccessRecord:
    """Convert an access mapping."""
    if value["state"] == "present":
        return _present_access(value)
    if value["state"] == "absent":
        return AbsentAccessRecord(
            logical_id=value["logical_id"],
            state="absent",
        )
    raise ValueError(f"invalid access state: {value['state']}")


def _template_input(value: Mapping) -> TemplateInput:
    """Convert Ansible data into typed template input."""
    if not isinstance(value, Mapping):
        raise AnsibleFilterError("aws_identity_center_template expects a mapping")

    access_records = []
    for item in value["access"]:
        if not isinstance(item, Mapping):
            raise AnsibleFilterError(
                "aws_identity_center_template access entries must be mappings"
            )
        access_records.append(_access_record(item))

    return TemplateInput(
        instance_arn=value["instance_arn"],
        identity_store_id=value["identity_store_id"],
        management_account_id=value["management_account_id"],
        access=tuple(access_records),
        user_ids=dict(value["user_ids"]),
    )


def aws_identity_center_template(value: Mapping) -> str:
    """Render IAM Identity Center CloudFormation JSON."""
    try:
        return render_template(_template_input(value))
    except (KeyError, TypeError, ValueError) as error:
        raise AnsibleFilterError(
            f"Unable to render IAM Identity Center template: {error}"
        ) from error


class FilterModule:
    """Register IAM Identity Center filters."""

    def filters(self) -> dict:
        """Return filters provided by this plugin."""
        return {
            "aws_identity_center_template": aws_identity_center_template,
        }
