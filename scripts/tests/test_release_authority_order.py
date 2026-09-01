import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "check_release_authority_order.py"
SPEC = importlib.util.spec_from_file_location("release_authority_order", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
ROOT = Path(__file__).resolve().parents[2]


def copy_surface(root: Path) -> None:
    paths = (
        "contracts/operations/final-release-authority-v1.json",
        ".github/workflows/release-tag.yml",
        "docs/operations/final-release-authority-order.md",
        "docs/PRODUCTION_BASELINE_PLAN.md",
        "docs/operations/phone-gitops-runtime.md",
    )
    for relative in paths:
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


class FinalReleaseAuthorityOrderTests(unittest.TestCase):
    def test_repository_passes(self):
        self.assertEqual(MODULE.check_repository(ROOT), [])

    def test_release_command_cannot_move_back_to_issue_162(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surface(root)
            path = root / "contracts/operations/final-release-authority-v1.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["command"]["issue"] = 162
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("canonical tracker #90" in error for error in errors))

    def test_release_workflow_cannot_be_triggered_from_issue_162(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surface(root)
            path = root / ".github/workflows/release-tag.yml"
            body = path.read_text(encoding="utf-8").replace(
                "github.event.issue.number == 90",
                "github.event.issue.number == 162",
            )
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("forbidden pre-Item20 authority token" in error for error in errors))

    def test_release_workflow_must_match_item20_closeout_sha(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surface(root)
            path = root / ".github/workflows/release-tag.yml"
            body = path.read_text(encoding="utf-8").replace(
                "target SHA does not match Item 20 final release marker",
                "target mismatch",
            )
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("missing protected ordering token" in error for error in errors))

    def test_phone_migration_cannot_depend_on_final_v_tag(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surface(root)
            path = root / "docs/operations/phone-gitops-runtime.md"
            body = path.read_text(encoding="utf-8").replace(
                "No final `v0.1.4` tag or GitHub Release is an input to the signing-generation migration.",
                "The signing-generation migration requires final v0.1.4.",
            )
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("phone GitOps document" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
