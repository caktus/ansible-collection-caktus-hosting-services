"""Boto helpers shared by the EKS update modules."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


class UpdateFailed(Exception):
    pass


def wait_for_update(
    client: Any,
    cluster_name: str,
    update_id: str,
    timeout: int,
    delay: float = 15,
    sleep: Callable[[float], None] = time.sleep,
    **resource: str,
) -> dict[str, Any]:
    """Poll describe_update until it succeeds.

    ``resource`` is ``addonName=...`` or ``nodegroupName=...``, as describe_update requires.
    """
    deadline = time.monotonic() + timeout
    while True:
        update = client.describe_update(
            name=cluster_name, updateId=update_id, aws_retry=True, **resource
        )["update"]
        if update["status"] == "Successful":
            return update
        if update["status"] in ("Failed", "Cancelled"):
            errors = "; ".join(
                f"{e.get('errorCode')}: {e.get('errorMessage')}"
                for e in update.get("errors", [])
            )
            raise UpdateFailed(
                f"update {update_id} {update['status'].lower()}: {errors}"
            )
        if time.monotonic() >= deadline:
            raise UpdateFailed(
                f"timed out after {timeout}s waiting for update {update_id}"
            )
        sleep(delay)
