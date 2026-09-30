from __future__ import annotations

DOCUMENTATION = r"""
module: eks_addon_update
short_description: Update installed EKS addons to a newer compatible version
description:
  - Updates EKS-managed addons (e.g. vpc-cni, coredns, kube-proxy, aws-ebs-csi-driver)
    to the latest, default, or an explicit version compatible with the cluster's
    Kubernetes version. Never downgrades.
  - C(vpc-cni) is limited to one minor version per run when I(version=latest).
options:
  cluster_name:
    description: EKS cluster name.
    required: true
    type: str
  addons:
    description: Addons to update. Defaults to all installed addons.
    type: list
    elements: str
  version:
    description: C(latest), C(default), or an explicit addon version.
    type: str
    default: latest
  resolve_conflicts:
    description: How to resolve field conflicts during the update.
    type: str
    choices: [NONE, PRESERVE, OVERWRITE]
    default: PRESERVE
  wait:
    description: Wait for each update to finish.
    type: bool
    default: true
  wait_timeout:
    description: Seconds to wait for each update.
    type: int
    default: 600
extends_documentation_fragment:
  - amazon.aws.common.modules
  - amazon.aws.region.modules
  - amazon.aws.boto3
"""

EXAMPLES = r"""
- name: Update all addons to latest
  caktus.hosting_services.eks_addon_update:
    cluster_name: my-cluster
"""

RETURN = r"""
updates:
  description: One entry per addon.
  returned: always
  type: list
  elements: dict
"""

from typing import Any

try:
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:
    pass  # AnsibleAWSModule reports missing botocore

from ansible_collections.amazon.aws.plugins.module_utils.botocore import (
    is_boto3_error_code,
)
from ansible_collections.amazon.aws.plugins.module_utils.modules import AnsibleAWSModule
from ansible_collections.amazon.aws.plugins.module_utils.retries import AWSRetry
from ansible_collections.caktus.hosting_services.plugins.module_utils.eks import (
    Version,
    VersionCandidates,
    planned,
    resolve_target,
    skipped,
    summarize,
)
from ansible_collections.caktus.hosting_services.plugins.module_utils.eks_aws import (
    UpdateFailed,
    wait_for_update,
)


def list_addons(client: Any, cluster_name: str) -> list[str]:
    names = []
    for page in client.get_paginator("list_addons").paginate(clusterName=cluster_name):
        names.extend(page["addons"])
    return names


def compatible_versions(
    client: Any, addon_name: str, k8s_version: str
) -> list[dict[str, Any]]:
    versions = []
    paginator = client.get_paginator("describe_addon_versions")
    for page in paginator.paginate(addonName=addon_name, kubernetesVersion=k8s_version):
        for addon in page["addons"]:
            versions.extend(addon["addonVersions"])
    return versions


def run(module: AnsibleAWSModule, client: Any, results: list[dict[str, Any]]) -> None:
    params = module.params
    cluster_name = params["cluster_name"]
    k8s_version = client.describe_cluster(name=cluster_name, aws_retry=True)["cluster"][
        "version"
    ]

    for name in params["addons"] or list_addons(client, cluster_name):
        try:
            addon = client.describe_addon(
                clusterName=cluster_name, addonName=name, aws_retry=True
            )["addon"]
        except is_boto3_error_code("ResourceNotFoundException"):
            results.append(skipped(name, None, "not installed on this cluster"))
            continue

        current = addon["addonVersion"]
        if addon["status"] != "ACTIVE":
            results.append(skipped(name, current, f"addon status is {addon['status']}"))
            continue

        versions = compatible_versions(client, name, k8s_version)
        candidates = VersionCandidates.from_addon_versions(versions)
        if candidates.rejected:
            module.warn(
                f"{name}: ignoring unparseable versions {', '.join(candidates.rejected)}"
            )

        requested = params["version"]
        current_v = Version.parse(current)
        if requested == "default":
            default = candidates.default()
            requested = default.raw if default else current
        elif requested == "latest" and name == "vpc-cni" and current_v:
            candidates = candidates.within_minor_step(current_v)

        resolution = resolve_target(current, candidates, requested)
        entry = planned(name, current, resolution)
        results.append(entry)
        if not resolution.changed or module.check_mode:
            continue

        kwargs = {
            "clusterName": cluster_name,
            "addonName": name,
            "addonVersion": resolution.target,
            "resolveConflicts": params["resolve_conflicts"],
        }
        if addon.get("serviceAccountRoleArn"):
            kwargs["serviceAccountRoleArn"] = addon["serviceAccountRoleArn"]
        update = client.update_addon(aws_retry=True, **kwargs)["update"]
        entry["update_id"] = update["id"]
        if params["wait"]:
            wait_for_update(
                client,
                cluster_name,
                update["id"],
                params["wait_timeout"],
                addonName=name,
            )


def main() -> None:
    module = AnsibleAWSModule(
        argument_spec={
            "cluster_name": {"required": True, "type": "str"},
            "addons": {"type": "list", "elements": "str"},
            "version": {"type": "str", "default": "latest"},
            "resolve_conflicts": {
                "type": "str",
                "choices": ["NONE", "PRESERVE", "OVERWRITE"],
                "default": "PRESERVE",
            },
            "wait": {"type": "bool", "default": True},
            "wait_timeout": {"type": "int", "default": 600},
        },
        supports_check_mode=True,
    )
    client = module.client("eks", retry_decorator=AWSRetry.jittered_backoff())
    results = []
    try:
        run(module, client, results)
    except UpdateFailed as e:
        module.fail_json(msg=str(e), **summarize(results))
    except (BotoCoreError, ClientError) as e:
        module.fail_json_aws(e, msg="EKS API call failed", **summarize(results))
    module.exit_json(**summarize(results))


if __name__ == "__main__":
    main()
