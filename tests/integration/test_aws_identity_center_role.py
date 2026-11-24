import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PLAYBOOK = ROOT / "tests/integration/aws_identity_center.yml"
TASKS = ROOT / "roles/aws_identity_center/tasks/main.yml"


def test_role_syntax_and_collection_resolution(tmp_path):
    collection_root = tmp_path / "collections/ansible_collections/caktus"
    collection_root.mkdir(parents=True)
    (collection_root / "hosting_services").symlink_to(ROOT)
    environment = os.environ.copy()
    environment["ANSIBLE_COLLECTIONS_PATH"] = str(tmp_path / "collections")
    environment["ANSIBLE_NOCOLOR"] = "1"

    result = subprocess.run(
        [
            "uv",
            "run",
            "ansible-playbook",
            str(PLAYBOOK),
            "--syntax-check",
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_role_uses_collection_modules_without_aws_cli():
    tasks = yaml.safe_load(TASKS.read_text())
    module_tasks = {
        key
        for task in tasks
        for key in task
        if key.startswith("caktus.hosting_services.")
    }
    aws_commands = [
        task
        for task in tasks
        if task.get("ansible.builtin.command", {}).get("argv", [None])[0] == "aws"
    ]

    assert module_tasks == {
        "caktus.hosting_services.aws_identity_center_info",
        "caktus.hosting_services.aws_identity_center_template",
        "caktus.hosting_services.cloudformation_validate",
    }
    assert aws_commands == []
