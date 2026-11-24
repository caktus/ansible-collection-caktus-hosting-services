from __future__ import annotations

DOCUMENTATION = r"""
module: aws_identity_center_template
short_description: Build an IAM Identity Center CloudFormation template
description:
  - Convert resolved IAM Identity Center facts into a CloudFormation template.
  - Generate the template with Troposphere.
options:
  access:
    description: IAM Identity Center access records.
    required: true
    type: list
    elements: dict
  instance_arn:
    description: IAM Identity Center instance ARN.
    required: true
    type: str
  identity_store_id:
    description: Identity Store ID.
    required: true
    type: str
  management_account_id:
    description: Default account ID for assignments.
    required: true
    type: str
  user_ids:
    description: Identity Store user IDs keyed by local username.
    required: true
    type: dict
"""

EXAMPLES = r"""
- name: Build IAM Identity Center template
  caktus.hosting_services.aws_identity_center_template:
    access: "{{ aws_sso_access }}"
    instance_arn: "{{ aws_sso_info.instance_arn }}"
    identity_store_id: "{{ aws_sso_info.identity_store_id }}"
    management_account_id: "{{ aws_sso_info.account_id }}"
    user_ids: "{{ aws_sso_info.user_ids }}"
"""

RETURN = r"""
template_body:
  description: Generated CloudFormation JSON template.
  returned: always
  type: str
resource_count:
  description: Number of generated CloudFormation resources.
  returned: always
  type: int
resource_types:
  description: Resource count grouped by CloudFormation type.
  returned: always
  type: dict
"""

from collections import Counter
from collections.abc import Mapping

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.caktus.hosting_services.plugins.module_utils.aws_identity_center_template import (
    AbsentAccessRecord,
    PresentAccessRecord,
    TemplateInput,
    load_template,
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


def build(
    *,
    access: list[dict],
    instance_arn: str,
    identity_store_id: str,
    management_account_id: str,
    user_ids: dict[str, str],
) -> dict:
    """Build an IAM Identity Center CloudFormation template."""
    template_body = render_template(
        TemplateInput(
            instance_arn=instance_arn,
            identity_store_id=identity_store_id,
            management_account_id=management_account_id,
            access=tuple(_access_record(item) for item in access),
            user_ids=user_ids,
        )
    )
    resources = load_template(template_body)["Resources"]
    return {
        "template_body": template_body,
        "resource_count": len(resources),
        "resource_types": dict(
            sorted(Counter(resource["Type"] for resource in resources.values()).items())
        ),
    }


def main() -> None:
    module = AnsibleModule(
        argument_spec={
            "access": {
                "required": True,
                "type": "list",
                "elements": "dict",
            },
            "instance_arn": {"required": True, "type": "str"},
            "identity_store_id": {"required": True, "type": "str"},
            "management_account_id": {"required": True, "type": "str"},
            "user_ids": {"required": True, "type": "dict"},
        },
        supports_check_mode=True,
    )
    try:
        result = build(**module.params)
    except (KeyError, TypeError, ValueError) as error:
        module.fail_json(msg=f"Unable to build IAM Identity Center template: {error}")
    module.exit_json(changed=False, **result)


if __name__ == "__main__":
    main()
