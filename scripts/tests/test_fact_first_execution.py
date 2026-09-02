from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_fact_first_execution.py"
SPEC = importlib.util.spec_from_file_location("fact_first_execution", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

SURFACES = tuple(str(path) for path in MODULE.REQUIRED)


def copy_surfaces(root: Path) -> None:
    for relative in SURFACES:
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


class FactFirstExecutionTests(unittest.TestCase):
    def test_repository_passes(self) -> None:
        self.assertEqual(MODULE.check_repository(ROOT), [])

    def test_workflow_success_cannot_replace_fact_first_control(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "docs/PRODUCTION_BASELINE_PLAN.md"
            body = path.read_text(encoding="utf-8").replace(
                "Operation execution result, independent postcondition verification and evidence persistence are separate dimensions.",
                "A successful workflow is sufficient evidence of production state.",
            )
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("separate dimensions" in error for error in errors))

    def test_unpersisted_evidence_cannot_fail_open(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "docs/PRODUCTION_BASELINE_PLAN.md"
            body = path.read_text(encoding="utf-8").replace(
                "required-but-unpersisted evidence fail closed",
                "required-but-unpersisted evidence may advance",
            )
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("unpersisted" in error for error in errors))

    def test_android_must_remain_first_proven_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "IMPLEMENTATION_PLAN.md"
            body = path.read_text(encoding="utf-8").replace(
                "Android is the first adapter to be proven end to end",
                "VM is generalized before Android acceptance",
            )
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("Android is the first adapter" in error for error in errors))

    def test_real_phone_must_remain_android_reality_oracle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "docs/PRODUCTION_BASELINE_PLAN.md"
            body = path.read_text(encoding="utf-8").replace(
                "For Android physical state, the real registered production phone is the authoritative observation oracle.",
                "Hosted CI is the authoritative source of Android physical state.",
            )
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("authoritative observation oracle" in error for error in errors))

    def test_hosted_evidence_cannot_complete_device_verifiable_android_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "docs/PRODUCTION_BASELINE_PLAN.md"
            body = path.read_text(encoding="utf-8").replace(
                "Unit/integration/hosted-Actions evidence alone cannot complete that Android state.",
                "Hosted evidence alone may complete Android state.",
            )
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("hosted-Actions" in error for error in errors))

    def test_blocker_fix_must_return_to_real_phone_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "IMPLEMENTATION_PLAN.md"
            body = path.read_text(encoding="utf-8").replace(
                "Infrastructure or control-plane hardening may run ahead of the phone only to remove a demonstrated blocker",
                "Infrastructure and orchestration hardening may continue independently of the phone",
            )
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("demonstrated blocker" in error for error in errors))

    def test_fact_first_delivery_order_cannot_be_reversed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "docs/PRODUCTION_BASELINE_PLAN.md"
            body = path.read_text(encoding="utf-8")
            body = body.replace("**Evidence reliability**", "__FACT_FIRST_EVIDENCE__", 1)
            body = body.replace("**Current-SHA phone admission**", "**Evidence reliability**", 1)
            body = body.replace("__FACT_FIRST_EVIDENCE__", "**Current-SHA phone admission**", 1)
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("delivery sequence is out of order" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
