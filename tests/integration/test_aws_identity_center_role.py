import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAYBOOK = ROOT / "tests/integration/aws_identity_center.yml"


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
