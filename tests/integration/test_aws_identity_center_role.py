import json
import os
import stat
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PLAYBOOK = ROOT / "tests/integration/aws_identity_center.yml"

AWS_STUB = """#!/usr/bin/env python3
import json
import os
import sys

arguments = sys.argv[1:]
with open(os.environ["AWS_STUB_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(arguments) + "\\n")

if arguments == ["--version"]:
    print("aws-cli/2.34.45 Python/3.14 Linux/unknown source/unknown")
elif arguments[:2] == ["sso-admin", "list-instances"]:
    print(json.dumps({"Instances": [{
        "InstanceArn": "arn:aws:sso:::instance/ssoins-example",
        "IdentityStoreId": "d-example"
    }]}))
elif arguments[:2] == ["identitystore", "get-user-id"]:
    alternate_identifier = json.loads(
        arguments[arguments.index("--alternate-identifier") + 1]
    )
    username = alternate_identifier["UniqueAttribute"]["AttributeValue"]
    user_ids = {
        "userone@example.com": "11111111-1111-1111-1111-111111111111",
        "usertwo@example.com": "22222222-2222-2222-2222-222222222222",
    }
    if username not in user_ids:
        print(f"ResourceNotFoundException: {username} does not exist", file=sys.stderr)
        raise SystemExit(254)
    print(json.dumps({"UserId": user_ids[username]}))
elif arguments[:2] == ["cloudformation", "validate-template"]:
    print("{}")
elif arguments[:2] == ["cloudformation", "describe-change-set"]:
    print("Add ExampleGroup AWS::IdentityStore::Group")
else:
    print(f"unexpected aws arguments: {arguments}", file=sys.stderr)
    raise SystemExit(2)
"""


def access_record(**overrides):
    record = {
        "logical_id": "ProjectAlphaAdmin",
        "name": "ProjectAlpha-Admin",
        "state": "present",
        "description": "Access ProjectAlpha",
        "role_arn": (
            "arn:aws:iam::111122223333:role/ProjectAccountAccessRole"
        ),
        "session_duration": "PT4H",
        "users": ["userone", "usertwo"],
    }
    record.update(overrides)
    return record


@pytest.fixture
def aws_stub(tmp_path):
    log_path = tmp_path / "aws.log"
    aws_path = tmp_path / "aws"
    aws_path.write_text(AWS_STUB)
    aws_path.chmod(aws_path.stat().st_mode | stat.S_IXUSR)

    collection_root = tmp_path / "collections/ansible_collections/caktus"
    collection_root.mkdir(parents=True)
    (collection_root / "hosting_services").symlink_to(ROOT)

    return tmp_path, log_path, tmp_path / "collections"


def run_role(aws_stub, access):
    bin_directory, log_path, collection_path = aws_stub
    extra_vars = {
        "aws_sso_access": access,
        "aws_sso_email_domain": "example.com",
        "aws_sso_management_account_id": "111122223333",
        "aws_region": "us-east-1",
    }
    environment = os.environ.copy()
    environment["PATH"] = (
        f"{bin_directory}{os.pathsep}{environment.get('PATH', '')}"
    )
    environment["AWS_STUB_LOG"] = str(log_path)
    environment["ANSIBLE_COLLECTIONS_PATH"] = str(collection_path)
    environment["ANSIBLE_NOCOLOR"] = "1"
    return subprocess.run(
        [
            "uv",
            "run",
            "ansible-playbook",
            str(PLAYBOOK),
            "-e",
            json.dumps(extra_vars),
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def aws_calls(aws_stub):
    log_path = aws_stub[1]
    if not log_path.exists():
        return []
    return [
        json.loads(line)
        for line in log_path.read_text().splitlines()
    ]


def output(result):
    return result.stdout + result.stderr


def test_duplicate_logical_id_fails_before_aws(aws_stub):
    result = run_role(
        aws_stub,
        [access_record(), access_record(name="ProjectBeta-Admin")],
    )

    assert result.returncode != 0
    assert "ProjectAlphaAdmin" in output(result)
    assert all(
        "sso-admin" not in call
        and "identitystore" not in call
        and "cloudformation" not in call
        for call in aws_calls(aws_stub)
    )


def test_missing_scim_user_fails_before_template_validation(aws_stub):
    result = run_role(
        aws_stub,
        [access_record(users=["userone", "missing-user"])],
    )

    assert result.returncode != 0
    assert "Look up IAM Identity Center user IDs" in output(result)
    assert not any(
        call[:2] == ["cloudformation", "validate-template"]
        for call in aws_calls(aws_stub)
    )


def test_valid_access_validates_without_deploying(aws_stub):
    result = run_role(aws_stub, [access_record()])

    assert result.returncode == 0, output(result)
    assert ["cloudformation", "validate-template"] in [
        call[:2] for call in aws_calls(aws_stub)
    ]
    assert "Create or update the IAM Identity Center stack" in output(result)
    assert "skipping: [localhost]" in output(result)
