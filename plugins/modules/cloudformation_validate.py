from __future__ import annotations

DOCUMENTATION = r"""
module: cloudformation_validate
short_description: Validate a CloudFormation template
description:
  - Send a CloudFormation template to the AWS validate-template API.
options:
  template_body:
    description: CloudFormation JSON or YAML template text.
    required: true
    type: str
extends_documentation_fragment:
  - amazon.aws.common.modules
  - amazon.aws.region.modules
  - amazon.aws.boto3
"""

EXAMPLES = r"""
- name: Validate a CloudFormation template
  caktus.hosting_services.cloudformation_validate:
    template_body: "{{ cloudformation_template }}"
"""

RETURN = r"""
capabilities:
  description: Required CloudFormation capabilities.
  returned: always
  type: list
  elements: str
capabilities_reason:
  description: AWS explanation for required capabilities.
  returned: when reported by AWS
  type: str
declared_transforms:
  description: Transforms declared by the template.
  returned: always
  type: list
  elements: str
description:
  description: Template description.
  returned: when reported by AWS
  type: str
parameters:
  description: Template parameter declarations.
  returned: always
  type: list
  elements: dict
"""

from typing import Any

try:
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:
    pass

from ansible_collections.amazon.aws.plugins.module_utils.modules import AnsibleAWSModule
from ansible_collections.amazon.aws.plugins.module_utils.retries import AWSRetry


class ValidationError(Exception):
    """Report CloudFormation template validation failure."""


def validate(client: Any, template_body: str) -> dict[str, Any]:
    """Validate a CloudFormation template and return AWS metadata."""
    try:
        response = client.validate_template(
            TemplateBody=template_body,
            aws_retry=True,
        )
    except ClientError as error:
        message = error.response.get("Error", {}).get("Message", str(error))
        raise ValidationError(
            f"CloudFormation template validation failed: {message}"
        ) from error

    return {
        "capabilities": response.get("Capabilities", []),
        "capabilities_reason": response.get("CapabilitiesReason"),
        "declared_transforms": response.get("DeclaredTransforms", []),
        "description": response.get("Description"),
        "parameters": response.get("Parameters", []),
    }


def main() -> None:
    module = AnsibleAWSModule(
        argument_spec={
            "template_body": {"required": True, "type": "str"},
        },
        supports_check_mode=True,
    )
    client = module.client(
        "cloudformation",
        retry_decorator=AWSRetry.jittered_backoff(),
    )
    try:
        result = validate(client, module.params["template_body"])
    except ValidationError as error:
        module.fail_json(msg=str(error))
    except (BotoCoreError, ClientError) as error:
        module.fail_json_aws(
            error,
            msg="CloudFormation validation API call failed",
        )
    module.exit_json(changed=False, **result)


if __name__ == "__main__":
    main()
