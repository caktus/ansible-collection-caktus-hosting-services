import atexit
import shutil
import sys
import tempfile
from pathlib import Path

import boto3
import pytest
from botocore.stub import Stubber

# Expose this repo as ansible_collections.caktus.hosting_services so modules import as in production.
_ROOT = Path(__file__).resolve().parent.parent
_tmp = Path(tempfile.mkdtemp())
atexit.register(shutil.rmtree, _tmp, ignore_errors=True)
(_tmp / "ansible_collections" / "caktus").mkdir(parents=True)
(_tmp / "ansible_collections" / "caktus" / "hosting_services").symlink_to(_ROOT)
sys.path.insert(0, str(_tmp))


def _stubbed(service):
    from ansible_collections.amazon.aws.plugins.module_utils.retries import (
        AWSRetry,
        RetryingBotoClientWrapper,
    )

    client = boto3.client(
        service,
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    stubber = Stubber(client)
    stubber.activate()
    return RetryingBotoClientWrapper(client, AWSRetry.jittered_backoff()), stubber


@pytest.fixture
def eks():
    client, stubber = _stubbed("eks")
    yield client, stubber
    stubber.assert_no_pending_responses()


@pytest.fixture
def ssm():
    client, stubber = _stubbed("ssm")
    yield client, stubber
    stubber.assert_no_pending_responses()
