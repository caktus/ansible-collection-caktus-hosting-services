"""Expose IAM Identity Center template generation to Ansible."""

from collections.abc import Mapping
from dataclasses import MISSING, fields

from ansible.errors import AnsibleFilterError
from ansible_collections.caktus.hosting_services.plugins.module_utils.aws_identity_center_template import (
    AbsentAccessRecord,
    PresentAccessRecord,
    TemplateInput,
    render_template,
)


def _require_dataclass_fields(value: Mapping, model: type, context: str) -> None:
    """Reject input that cannot populate a dataclass."""
    missing = [
        field.name
        for field in fields(model)
        if field.default is MISSING
        and field.default_factory is MISSING
        and field.name not in value
    ]
    if missing:
        missing_fields = ", ".join(missing)
        raise AnsibleFilterError(
            f"{context} is missing required fields: {missing_fields}"
        )


def _template_input(value: Mapping) -> TemplateInput:
    """Convert Ansible data into typed template input."""
    if not isinstance(value, Mapping):
        raise AnsibleFilterError("aws_identity_center_template expects a mapping")

    _require_dataclass_fields(value, TemplateInput, "template input")
    access_records = []
    for item in value["access"]:
        if not isinstance(item, Mapping):
            raise AnsibleFilterError(
                "aws_identity_center_template access entries must be mappings"
            )
        state = item.get("state")
        if state not in ("present", "absent"):
            raise AnsibleFilterError(
                "access record "
                f"{item.get('logical_id', '<unknown>')} has invalid state: "
                f"{state}"
            )
        model = PresentAccessRecord if state == "present" else AbsentAccessRecord
        context = f"access record {item.get('logical_id', '<unknown>')}"
        _require_dataclass_fields(item, model, context)
        if state == "absent":
            access_records.append(
                AbsentAccessRecord(
                    logical_id=item["logical_id"],
                    state="absent",
                )
            )
            continue

        managed_policies = (
            tuple(item["managed_policies"]) if "managed_policies" in item else None
        )
        access_records.append(
            PresentAccessRecord(
                logical_id=item["logical_id"],
                state="present",
                name=item["name"],
                description=item["description"],
                session_duration=item["session_duration"],
                users=tuple(item["users"]),
                managed_policies=managed_policies,
                role_arn=item.get("role_arn"),
                target_account_id=item.get("target_account_id"),
            )
        )

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
