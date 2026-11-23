"""Expose IAM Identity Center template generation to Ansible."""

from collections.abc import Mapping, Sequence

from ansible.errors import AnsibleFilterError
from ansible_collections.caktus.hosting_services.plugins.module_utils.aws_identity_center_template import (
    AccessRecord,
    TemplateInput,
    render_template,
)

_TOP_LEVEL_FIELDS = (
    "instance_arn",
    "identity_store_id",
    "management_account_id",
    "access",
    "user_ids",
)
_ACCESS_FIELDS = (
    "logical_id",
    "name",
    "state",
    "description",
    "session_duration",
    "users",
)


def _require_fields(value: Mapping, fields: Sequence[str], context: str) -> None:
    """Reject input that cannot satisfy the collection contract."""
    missing = [field for field in fields if field not in value]
    if missing:
        missing_fields = ", ".join(missing)
        raise AnsibleFilterError(
            f"{context} is missing required fields: {missing_fields}"
        )


def _template_input(value: Mapping) -> TemplateInput:
    """Convert Ansible data into typed template input."""
    if not isinstance(value, Mapping):
        raise AnsibleFilterError("aws_identity_center_template expects a mapping")

    _require_fields(value, _TOP_LEVEL_FIELDS, "template input")
    access_records = []
    for item in value["access"]:
        if not isinstance(item, Mapping):
            raise AnsibleFilterError(
                "aws_identity_center_template access entries must be mappings"
            )
        _require_fields(
            item,
            _ACCESS_FIELDS,
            f"access record {item.get('logical_id', '<unknown>')}",
        )
        access_records.append(
            AccessRecord(
                logical_id=item["logical_id"],
                name=item["name"],
                state=item["state"],
                description=item["description"],
                session_duration=item["session_duration"],
                users=tuple(item["users"]),
                managed_policies=tuple(item.get("managed_policies", ())),
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
