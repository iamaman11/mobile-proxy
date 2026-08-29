import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "check_github_control_plane.py"
SPEC = importlib.util.spec_from_file_location("github_control_plane", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
ROOT = Path(__file__).resolve().parents[2]


class GithubControlPlaneTests(unittest.TestCase):
    def test_repository_passes(self):
        self.assertEqual(MODULE.check_repository(ROOT), [])

    def test_public_self_hosted_workflow_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(ROOT / "contracts", root / "contracts")
            shutil.copytree(ROOT / "docs", root / "docs")
            workflow = root / ".github/workflows/deploy-production.yml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text("runs-on: self-hosted\n", encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("self-hosted" in error for error in errors))

    def test_vultr_branch_policy_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(ROOT / "contracts", root / "contracts")
            shutil.copytree(ROOT / "docs", root / "docs")
            (root / ".github/workflows").mkdir(parents=True)
            shutil.copy2(
                ROOT / ".github/workflows/deploy-production.yml",
                root / ".github/workflows/deploy-production.yml",
            )
            path = root / "contracts/operations/github-control-plane-v1.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["vultr_environment"]["allowed_ref_type"] = "branch"
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("production-vultr boundary" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
