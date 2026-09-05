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

    def test_controller_confidentiality_boundary_cannot_disappear(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "contracts/operations/project-authority-v2.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["deployment_controller_authority"]["confidentiality_boundary"] = "repository_visibility"
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("confidentiality boundary differs" in error for error in errors))

    def test_runtime_identity_requires_product_release_plus_controller_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "contracts/operations/project-authority-v2.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["runtime_identity"]["identity"] = "public_main_sha"
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("runtime identity is not Product Release + controller revision" in error for error in errors))

    def test_product_release_must_exist_before_physical_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "contracts/operations/production-topology-v2.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["release_link"]["physical_acceptance_before_product_release"] = True
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("Product Release before deployment" in error for error in errors))

    def test_vm_target_remains_fail_closed_until_proven(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "contracts/operations/production-topology-v2.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["targets"]["vm-production"]["destructive_dispatch"] = "allowed"
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("VM target is not fail-closed" in error for error in errors))

    def test_blind_retry_after_dispatch_cannot_be_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "contracts/operations/production-topology-v2.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["execution_rules"]["blind_retry_after_dispatch_boundary"] = True
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("transaction/recovery semantics differ" in error for error in errors))

    def test_controller_ingress_must_remain_deploy_target_tag(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "contracts/operations/github-control-plane-v2.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["deployment_controller_repository"]["command"] = "/deploy-latest"
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("Deployment Controller ingress" in error for error in errors))

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

    def test_release_digest_domain_cannot_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "contracts/operations/product-release-authority-v2.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["manifest"]["content_digest_domain"] = "mobile-proxy/wrong/v1"
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("typed digest identity differs" in error for error in errors))

    def test_release_tag_cannot_restore_item20_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / ".github/workflows/release-tag.yml"
            path.write_text(path.read_text(encoding="utf-8") + "\n# ITEM20_ISSUE\n", encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("old physical-before-product authority" in error for error in errors))

    def test_release_workflow_requires_exact_draft_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / ".github/workflows/release.yml"
            body = path.read_text(encoding="utf-8").replace("cmp -s --", "test -e")
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("release.yml is missing controller-v2 invariant 'cmp -s --'" in error for error in errors))

    def test_active_release_doc_cannot_restore_item20_before_release(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "docs/operations/final-release-authority-order.md"
            path.write_text(
                path.read_text(encoding="utf-8") + "\nOnly after Item 20 physical acceptance may release proceed.\n",
                encoding="utf-8",
            )
            errors = MODULE.check_repository(root)
        self.assertTrue(any("superseded active authority wording" in error for error in errors))

    def test_phone_doc_must_keep_controller_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "docs/operations/phone-gitops-runtime.md"
            body = path.read_text(encoding="utf-8").replace(
                "Both repositories are public",
                "The controller is only a thin execution satellite",
            )
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("phone-gitops-runtime.md is missing controller-v2 invariant" in error for error in errors))

    def test_android_auxiliary_role_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "RUNTIME_LAYOUT.md"
            body = path.read_text(encoding="utf-8").replace(
                "not the primary reverse-tunnel owner",
                "the primary reverse-tunnel owner",
            )
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("RUNTIME_LAYOUT.md lost Android auxiliary-role invariant" in error for error in errors))

    def test_historical_item19_proof_sha_remains_audit_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surfaces(root)
            path = root / "docs/operations/item19-provider-proof-closeout.md"
            body = path.read_text(encoding="utf-8").replace(MODULE.HISTORICAL_ITEM19_SHA, "0" * 40)
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("historical Item 19 closeout lost its immutable proof SHA" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
