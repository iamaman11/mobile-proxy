from __future__ import annotations

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
    "QUICK_REFERENCE.md",
    "AGENTS.md",
    "STAGE_WORKFLOW.md",
    "IMPLEMENTATION_PLAN.md",
    "docs/PRODUCTION_STAGE_ROADMAP.md",
    "docs/PRODUCTION_BASELINE_PLAN.md",
    "scripts/repository_context.py",
    "RUNTIME_LAYOUT.md",
    "docs/operations/project-authority.md",
    "docs/operations/phone-gitops-runtime.md",
    "docs/operations/final-release-authority-order.md",
    "docs/operations/item19-provider-proof-closeout.md",
    "contracts/operations/project-authority-v2.json",
    "contracts/operations/production-topology-v2.json",
    "contracts/operations/github-control-plane-v2.json",
    "contracts/operations/product-release-authority-v2.json",
    ".github/workflows/release-tag.yml",
    ".github/workflows/release.yml",
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

    def _mutate(self, relative: str, transform) -> list[str]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / relative
            body = path.read_text(encoding="utf-8")
            path.write_text(transform(body), encoding="utf-8")
            return MODULE.check_repository(root)

    def test_controller_repository_must_remain_deployment_controller(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "contracts/operations/project-authority-v2.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["deployment_controller_authority"]["authority"] = "execution_satellite"
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("Deployment Controller authority" in error for error in errors))

    def test_runtime_identity_requires_release_plus_controller_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "contracts/operations/project-authority-v2.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["runtime_identity"]["identity"] = "public_main_sha"
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("runtime identity" in error for error in errors))

    def test_vm_target_remains_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "contracts/operations/production-topology-v2.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["targets"]["vm-production"]["destructive_dispatch"] = "allowed"
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("VM target is not fail-closed" in error for error in errors))

    def test_blind_retry_cannot_be_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "contracts/operations/production-topology-v2.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["execution_rules"]["blind_retry_after_dispatch_boundary"] = True
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("transaction/recovery semantics differ" in error for error in errors))

    def test_release_asset_set_cannot_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "contracts/operations/product-release-authority-v2.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["required_release_assets"] = ["release-manifest.json"]
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("exact asset set differs" in error for error in errors))

    def test_release_tag_cannot_restore_item20_authority(self) -> None:
        errors = self._mutate(
            ".github/workflows/release-tag.yml",
            lambda body: body + "\n# ITEM20_ISSUE\n",
        )
        self.assertTrue(any("old physical-before-product authority" in error for error in errors))

    def test_release_workflow_requires_exact_draft_bytes(self) -> None:
        errors = self._mutate(
            ".github/workflows/release.yml",
            lambda body: body.replace("cmp -s --", "test -e"),
        )
        self.assertTrue(any("cmp -s --" in error for error in errors))

    def test_static_stage_roadmap_cannot_restore_dynamic_current(self) -> None:
        errors = self._mutate(
            "docs/PRODUCTION_STAGE_ROADMAP.md",
            lambda body: body + "\n## Stage 4 — CURRENT\n",
        )
        self.assertTrue(any("must not embed dynamic CURRENT" in error for error in errors))

    def test_baseline_cannot_restore_checkpoint_after_every_merge(self) -> None:
        errors = self._mutate(
            "docs/PRODUCTION_BASELINE_PLAN.md",
            lambda body: body + "\nAfter each accepted merge or separately authorized production operation, record a bounded #179 checkpoint\n",
        )
        self.assertTrue(any("superseded execution wording" in error for error in errors))

    def test_product_agents_must_keep_one_source_per_concern(self) -> None:
        errors = self._mutate(
            "AGENTS.md",
            lambda body: body.replace("One source of truth per concern", "Several equivalent sources"),
        )
        self.assertTrue(any("AGENTS.md is missing invariant 'One source of truth per concern'" in error for error in errors))

    def test_stage_workflow_requires_capability_gap_classification(self) -> None:
        errors = self._mutate(
            "STAGE_WORKFLOW.md",
            lambda body: body.replace("controller_capability_gap", "manual_gap"),
        )
        self.assertTrue(any("controller_capability_gap" in error for error in errors))

    def test_repository_context_must_not_restore_flat_authoritative_docs(self) -> None:
        errors = self._mutate(
            "scripts/repository_context.py",
            lambda body: body + '\n# "authoritative_docs"\n',
        )
        self.assertTrue(any("flat authoritative_docs" in error for error in errors))

    def test_repository_context_must_identify_controller_ledger_and_diagnostics(self) -> None:
        errors = self._mutate(
            "scripts/repository_context.py",
            lambda body: body.replace("controller_runtime_transaction_truth", "runtime_hint"),
        )
        self.assertTrue(any("controller_runtime_transaction_truth" in error for error in errors))

    def test_context_budget_prevents_agents_becoming_parallel_handbook(self) -> None:
        errors = self._mutate(
            "AGENTS.md",
            lambda body: body + ("\nextra duplicated governance" * 1000),
        )
        self.assertTrue(any("exceeds bounded context budget" in error for error in errors))

    def test_historical_item19_proof_sha_remains_audit_evidence(self) -> None:
        errors = self._mutate(
            "docs/operations/item19-provider-proof-closeout.md",
            lambda body: body.replace(MODULE.HISTORICAL_ITEM19_SHA, "0" * 40),
        )
        self.assertTrue(any("historical Item 19 closeout" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
