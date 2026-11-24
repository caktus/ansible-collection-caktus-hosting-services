from __future__ import annotations

DOCUMENTATION = r"""
module: aws_identity_center_info
short_description: Discover IAM Identity Center authorization inputs
description:
  - Read the caller account and the active IAM Identity Center instance.
  - Resolve unique users from present access records in the Identity Store.
options:
  access:
    description: IAM Identity Center access records.
    required: true
    type: list
    elements: dict
  email_domain:
    description: Domain appended to local usernames for Identity Store lookup.
    required: true
    type: str
extends_documentation_fragment:
  - amazon.aws.common.modules
  - amazon.aws.region.modules
  - amazon.aws.boto3
"""

EXAMPLES = r"""
- name: Discover IAM Identity Center inputs
  caktus.hosting_services.aws_identity_center_info:
    access: "{{ aws_sso_access }}"
    email_domain: caktusgroup.com
"""

RETURN = r"""
account_id:
  description: AWS account that owns the credentials.
  returned: always
  type: str
instance_arn:
  description: IAM Identity Center instance ARN.
  returned: always
  type: str
identity_store_id:
  description: Identity Store ID.
  returned: always
  type: str
user_ids:
  description: Identity Store user IDs keyed by local username.
  returned: always
  type: dict
"""

from typing import Any

try:
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:
    pass

from ansible_collections.amazon.aws.plugins.module_utils.botocore import (
    is_boto3_error_code,
)
from ansible_collections.amazon.aws.plugins.module_utils.modules import AnsibleAWSModule
from ansible_collections.amazon.aws.plugins.module_utils.retries import AWSRetry


class DiscoveryError(Exception):
    """Report invalid IAM Identity Center discovery state."""


def unique_present_users(access: list[dict[str, Any]]) -> list[str]:
    """Return unique usernames from present access records."""
    return list(
        dict.fromkeys(
            username
            for item in access
            if item.get("state") == "present"
            for username in item["users"]
        )
    )


def discover(
    sts_client: Any,
    sso_admin_client: Any,
    identitystore_client: Any,
    access: list[dict[str, Any]],
    email_domain: str,
) -> dict[str, Any]:
    """Discover Identity Center facts and present user IDs."""
    account_id = sts_client.get_caller_identity(aws_retry=True)["Account"]
    instances = sso_admin_client.list_instances(aws_retry=True)["Instances"]
    if len(instances) != 1:
        raise DiscoveryError(
            f"Expected one IAM Identity Center instance, found {len(instances)}"
        )

    instance = instances[0]
    identity_store_id = instance["IdentityStoreId"]
    user_ids = {}
    for username in unique_present_users(access):
        email = f"{username}@{email_domain}"
        try:
            response = identitystore_client.get_user_id(
                IdentityStoreId=identity_store_id,
                AlternateIdentifier={
                    "UniqueAttribute": {
                        "AttributePath": "userName",
                        "AttributeValue": email,
                    }
                },
                aws_retry=True,
            )
        except is_boto3_error_code("ResourceNotFoundException") as error:
            raise DiscoveryError(
                f"IAM Identity Center user not found: {email}"
            ) from error
        user_ids[username] = response["UserId"]

    return {
        "account_id": account_id,
        "instance_arn": instance["InstanceArn"],
        "identity_store_id": identity_store_id,
        "user_ids": user_ids,
    }


def main() -> None:
    module = AnsibleAWSModule(
        argument_spec={
            "access": {"required": True, "type": "list", "elements": "dict"},
            "email_domain": {"required": True, "type": "str"},
        },
        supports_check_mode=True,
    )
    retry = AWSRetry.jittered_backoff()
    try:
        result = discover(
            module.client("sts", retry_decorator=retry),
            module.client("sso-admin", retry_decorator=retry),
            module.client("identitystore", retry_decorator=retry),
            module.params["access"],
            module.params["email_domain"],
        )
    except DiscoveryError as error:
        module.fail_json(msg=str(error))
    except (BotoCoreError, ClientError) as error:
        module.fail_json_aws(error, msg="IAM Identity Center discovery failed")
    module.exit_json(changed=False, **result)


if __name__ == "__main__":
    main()
