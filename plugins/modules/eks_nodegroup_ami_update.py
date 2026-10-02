from __future__ import annotations

DOCUMENTATION = r"""
module: eks_nodegroup_ami_update
short_description: Refresh EKS managed nodegroups to a newer AMI release
description:
  - Updates managed nodegroups to the latest (or an explicit) AMI release for
    their current Kubernetes version. Never downgrades.
  - C(latest) is resolved from the EKS-optimized AMI SSM parameters.
  - Skips custom-AMI nodegroups, nodegroups that aren't C(ACTIVE), and
    nodegroups whose Kubernetes version differs from the cluster's.
options:
  cluster_name:
    description: EKS cluster name.
    required: true
    type: str
  nodegroups:
    description: Nodegroups to update. Defaults to all nodegroups in the cluster.
    type: list
    elements: str
  release_version:
    description: C(latest) or an explicit AMI release version.
    type: str
    default: latest
  force:
    description: Force the update even if pods can't be drained due to a PodDisruptionBudget.
    type: bool
    default: false
  wait:
    description: Wait for each update to finish.
    type: bool
    default: true
  wait_timeout:
    description: Seconds to wait for each update.
    type: int
    default: 3600
extends_documentation_fragment:
  - amazon.aws.common.modules
  - amazon.aws.region.modules
  - amazon.aws.boto3
"""

EXAMPLES = r"""
- name: Update all nodegroups to the latest AMI release
  caktus.hosting_services.eks_nodegroup_ami_update:
    cluster_name: my-cluster
"""

RETURN = r"""
updates:
  description: One entry per nodegroup.
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
    VersionCandidates,
    nodegroup_skip_reason,
    planned,
    resolve_target,
    skipped,
    ssm_release_version_path,
    summarize,
)
from ansible_collections.caktus.hosting_services.plugins.module_utils.eks_aws import (
    UpdateFailed,
    wait_for_update,
)


def list_nodegroups(client: Any, cluster_name: str) -> list[str]:
    """Return the names of all managed nodegroups in the cluster."""
    names = []
    for page in client.get_paginator("list_nodegroups").paginate(
        clusterName=cluster_name
    ):
        names.extend(page["nodegroups"])
    return names


def run(
    module: AnsibleAWSModule, client: Any, ssm: Any, results: list[dict[str, Any]]
) -> None:
    """Resolve and apply AMI updates, appending one entry per nodegroup to ``results``."""
    params = module.params
    cluster_name = params["cluster_name"]
    cluster_version = client.describe_cluster(name=cluster_name, aws_retry=True)[
        "cluster"
    ]["version"]

    for name in params["nodegroups"] or list_nodegroups(client, cluster_name):
        ng = client.describe_nodegroup(
            clusterName=cluster_name, nodegroupName=name, aws_retry=True
        )["nodegroup"]
        current = ng.get("releaseVersion")
        reason = nodegroup_skip_reason(ng, cluster_version)
        if reason:
            results.append(skipped(name, current, reason))
            continue

        candidate = params["release_version"]
        if candidate == "latest":
            path = ssm_release_version_path(ng["amiType"], cluster_version)
            if path is None:
                results.append(
                    skipped(name, current, f"unsupported AMI type {ng['amiType']}")
                )
                continue
            try:
                candidate = ssm.get_parameter(Name=path, aws_retry=True)["Parameter"][
                    "Value"
                ]
            except is_boto3_error_code("ParameterNotFound"):
                raise UpdateFailed(f"no SSM release_version parameter at {path}")

        candidates = VersionCandidates.from_strings([candidate])
        if candidates.rejected:
            module.warn(f"{name}: ignoring unparseable release version {candidate}")
        resolution = resolve_target(current, candidates, candidate)
        entry = planned(name, current, resolution)
        results.append(entry)
        if not resolution.changed or module.check_mode:
            continue

        kwargs = {
            "clusterName": cluster_name,
            "nodegroupName": name,
            "releaseVersion": resolution.target,
            "force": params["force"],
        }
        if lt := ng.get("launchTemplate"):
            # The API rejects id and name together.
            ref = {"id": lt["id"]} if lt.get("id") else {"name": lt["name"]}
            kwargs["launchTemplate"] = {**ref, "version": lt["version"]}
        update = client.update_nodegroup_version(aws_retry=True, **kwargs)["update"]
        entry["update_id"] = update["id"]
        if params["wait"]:
            wait_for_update(
                client,
                cluster_name,
                update["id"],
                params["wait_timeout"],
                nodegroupName=name,
            )


def main() -> None:
    module = AnsibleAWSModule(
        argument_spec={
            "cluster_name": {"required": True, "type": "str"},
            "nodegroups": {"type": "list", "elements": "str"},
            "release_version": {"type": "str", "default": "latest"},
            "force": {"type": "bool", "default": False},
            "wait": {"type": "bool", "default": True},
            "wait_timeout": {"type": "int", "default": 3600},
        },
        supports_check_mode=True,
    )
    retry = AWSRetry.jittered_backoff()
    client = module.client("eks", retry_decorator=retry)
    ssm = module.client("ssm", retry_decorator=retry)
    results = []
    try:
        run(module, client, ssm, results)
    except UpdateFailed as e:
        module.fail_json(msg=str(e), **summarize(results))
    except (BotoCoreError, ClientError) as e:
        module.fail_json_aws(e, msg="EKS API call failed", **summarize(results))
    module.exit_json(**summarize(results))


if __name__ == "__main__":
    main()
