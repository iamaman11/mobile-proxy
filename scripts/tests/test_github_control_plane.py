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


def copy_policy_tree(root: Path, workflows: bool = False) -> None:
    shutil.copytree(ROOT / "contracts", root / "contracts")
    shutil.copytree(ROOT / "docs", root / "docs")
    target = root / ".github/workflows"
    target.mkdir(parents=True)
    if workflows:
        for workflow in (ROOT / ".github/workflows").glob("*.yml"):
            shutil.copy2(workflow, target / workflow.name)
    else:
        shutil.copy2(ROOT / ".github/workflows/deploy-production.yml", target / "deploy-production.yml")


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
            copy_policy_tree(root)
            path = root / "contracts/operations/github-control-plane-v1.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["vultr_environment"]["allowed_ref_type"] = "branch"
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("production-vultr boundary" in error for error in errors))

    def test_phone_binding_contract_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root)
            path = root / "contracts/operations/github-control-plane-v1.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["phone_control_repository"]["required_device_binding_secret"] = (
                "UNREGISTERED_DEVICE"
            )
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("registered-device binding" in error for error in errors))

    def test_phone_signing_secret_contract_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root)
            path = root / "contracts/operations/github-control-plane-v1.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["phone_control_repository"]["reserved_android_signing_secret_names"] = []
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("signing-secret" in error for error in errors))

    def test_phone_preflight_checkpoint_is_rejected_if_stale(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root)
            path = root / "contracts/operations/production-topology-v1.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["migration_status"]["phone_live_preflight"] = "not_proven"
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("GitOps checkpoint" in error for error in errors))

    def test_satellite_cannot_become_a_second_source_of_truth(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root)
            path = root / "contracts/operations/project-authority-v1.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["execution_satellites"][0]["authority"] = "canonical"
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("execution satellite authority" in error for error in errors))

    def test_mutable_release_authority_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root)
            path = root / "contracts/operations/project-authority-v1.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["release_identity"]["mutable_branch_authority"] = "allowed"
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("release identity" in error for error in errors))

    def test_acceptance_candidate_must_remain_full_sha_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root, workflows=True)
            path = root / "contracts/operations/acceptance-authority-v1.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["candidate_identity"]["kind"] = "branch"
            contract["candidate_identity"]["pattern"] = "main"
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("full-SHA only" in error for error in errors))

    def test_acceptance_cannot_become_final_production_authority(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root, workflows=True)
            path = root / "contracts/operations/acceptance-authority-v1.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["authority_separation"]["final_production_authority"] = True
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("distinct from final production authority" in error for error in errors))

    def test_acceptance_workflow_cannot_use_production_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root, workflows=True)
            path = root / ".github/workflows/acceptance-authority.yml"
            content = path.read_text(encoding="utf-8")
            path.write_text(content + "\n# environment: production-vultr\n", encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(
            any("attempts to use final production authority or secrets" in error for error in errors)
        )

    def test_production_preflight_must_remain_tag_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root, workflows=True)
            path = root / ".github/workflows/production-preflight.yml"
            content = path.read_text(encoding="utf-8")
            content = content.replace(
                '[[ "$GITHUB_REF_TYPE" == "tag" ]]',
                '[[ "$GITHUB_REF_TYPE" == "branch" ]]',
            )
            path.write_text(content, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("no longer protected v*-tag only" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
