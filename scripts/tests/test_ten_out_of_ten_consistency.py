from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_ten_out_of_ten_consistency.py"
SPEC = importlib.util.spec_from_file_location("ten_out_of_ten_consistency", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

SURFACES = (
    "TEN_OUT_OF_TEN_VALIDATION_PLAN.md",
    "README.md",
    "RUNTIME_LAYOUT.md",
    "docs/PRODUCTION_BASELINE_PLAN.md",
    "docs/FUTURE_PLATFORM_ARCHITECTURE_ROADMAP.md",
    "docs/operations/project-authority.md",
    "docs/operations/phone-gitops-runtime.md",
    "docs/operations/final-release-authority-order.md",
    "docs/operations/item19-provider-proof-closeout.md",
    "contracts/operations/item20-acceptance-v1.json",
    "contracts/operations/item20-admission-readiness-v1.json",
    "contracts/operations/item20-private-handoff-v1.json",
    "contracts/operations/final-release-authority-v1.json",
    "contracts/operations/production-topology-v1.json",
    ".github/workflows/release-tag.yml",
    ".github/workflows/release.yml",
    ".github/workflows/item20-admission-readiness.yml",
)


def copy_surfaces(root: Path) -> None:
    for relative in SURFACES:
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


class TenOutOfTenConsistencyTests(unittest.TestCase):
    def test_repository_passes(self) -> None:
        self.assertEqual(MODULE.check_repository(ROOT), [])

    def test_distinct_item20_candidate_and_control_plane_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "contracts/operations/item20-acceptance-v1.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["identity"]["exact_equality_required"] = False
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("one-SHA acceptance model" in error for error in errors))

    def test_release_marker_cannot_revert_to_control_plane_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "contracts/operations/final-release-authority-v1.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["preconditions"]["item20_release_sha_marker"] = "final_release_control_plane_sha"
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("final release authority" in error or "retired two-SHA" in error for error in errors))

    def test_release_workflow_cannot_accept_stale_protected_main(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / ".github/workflows/release-tag.yml"
            body = path.read_text(encoding="utf-8").replace(
                "protected main advanced or differs from the accepted candidate; acceptance is stale",
                "ancestor accepted",
            )
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("release-tag.yml" in error for error in errors))

    def test_android_role_cannot_claim_production_apk_is_globally_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "TEN_OUT_OF_TEN_VALIDATION_PLAN.md"
            body = path.read_text(encoding="utf-8") + "\nThe optional Android app is not installed by the production stack.\n"
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("globally never installed" in error for error in errors))

    def test_android_managed_auxiliary_role_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "RUNTIME_LAYOUT.md"
            body = path.read_text(encoding="utf-8").replace(
                "managed production auxiliary component",
                "optional development helper",
            )
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("RUNTIME_LAYOUT.md" in error for error in errors))

    def test_private_repository_cannot_become_policy_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "contracts/operations/production-topology-v1.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["control_planes"]["phone"]["authority"] = "canonical"
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("execution-only" in error for error in errors))

    def test_future_roadmap_cannot_gain_stale_current_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "docs/FUTURE_PLATFORM_ARCHITECTURE_ROADMAP.md"
            body = path.read_text(encoding="utf-8") + f"\nCurrent SHA = {MODULE.STALE_FUTURE_SHA}\n"
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("stale operational candidate" in error for error in errors))

    def test_historical_item19_sha_cannot_be_active_item20_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "contracts/operations/item20-acceptance-v1.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["identity"]["candidate_sha"] = MODULE.HISTORICAL_ITEM19_SHA
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("historical Item 19 SHA" in error or "one-SHA acceptance model" in error for error in errors))

    def test_retired_two_sha_semantic_fails_on_active_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "docs/operations/project-authority.md"
            path.write_text(
                path.read_text(encoding="utf-8") + "\ncontrol_plane_may_advance_without_redefining_candidate\n",
                encoding="utf-8",
            )
            errors = MODULE.check_repository(root)
        self.assertTrue(any("retired two-SHA semantic" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
