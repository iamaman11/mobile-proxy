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


POLICY_SURFACE = (
    "contracts/operations/project-authority-v2.json",
    "contracts/operations/github-control-plane-v2.json",
    "contracts/operations/production-topology-v2.json",
    "contracts/operations/product-release-authority-v2.json",
    "contracts/operations/historical-public-acceptance-retirement-v1.json",
    "docs/operations/final-release-authority-order.md",
)


def copy_policy_tree(root: Path) -> None:
    for relative in POLICY_SURFACE:
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for relative in MODULE.EXPECTED_PUBLIC_WORKFLOWS:
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


class GithubControlPlaneTests(unittest.TestCase):
    def test_repository_passes(self) -> None:
        self.assertEqual(MODULE.check_repository(ROOT), [])

    def test_public_product_repository_cannot_gain_self_hosted_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root)
            path = root / "contracts/operations/github-control-plane-v2.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["public_product_repository"]["self_hosted_runners"] = "allowed"
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(
            any("public PRODUCT repository boundary differs" in error for error in errors)
        )

    def test_product_release_environment_cannot_gain_target_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root)
            path = root / "contracts/operations/github-control-plane-v2.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["product_release_environment"]["phone_or_target_access"] = "allowed"
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(
            any("product-release environment boundary differs" in error for error in errors)
        )

    def test_product_release_environment_requires_exact_secret_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root)
            path = root / "contracts/operations/github-control-plane-v2.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["product_release_environment"]["required_secret_names"] = []
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(
            any("product-release environment boundary differs" in error for error in errors)
        )

    def test_public_controller_repository_must_remain_deployment_controller(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root)
            path = root / "contracts/operations/github-control-plane-v2.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["deployment_controller_repository"]["authority"] = "execution_satellite"
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(
            any("deployment controller GitHub boundary differs" in error for error in errors)
        )

    def test_controller_repository_cannot_publish_sensitive_runtime_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root)
            path = root / "contracts/operations/project-authority-v2.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            controller = contract["deployment_controller_authority"]
            controller["forbidden"].remove(
                "secret_or_raw_device_data_in_public_git_or_issue_evidence"
            )
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(
            any("PRODUCT/confidentiality ownership" in error for error in errors)
        )

    def test_runtime_identity_must_bind_product_release_and_controller_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root)
            path = root / "contracts/operations/project-authority-v2.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["runtime_identity"]["identity"] = "public_main_sha"
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(
            any(
                "runtime identity is not Product Release plus controller revision" in error
                for error in errors
            )
        )

    def test_residual_production_preflight_is_historical_and_absent(self) -> None:
        self.assertFalse((ROOT / MODULE.RETIRED_PRODUCTION_PREFLIGHT).exists())
        retirement = json.loads(
            (ROOT / MODULE.RETIREMENT).read_text(encoding="utf-8")
        )
        residual = retirement["residual_provider_access_retirement"]
        self.assertEqual(
            residual,
            {
                "workflow": ".github/workflows/production-preflight.yml",
                "status": "historical_only_non_executable",
                "former_environment": "production-vultr",
                "former_provider": "vultr",
                "former_capability": "read_only_provider_account_probe",
                "execution_authority": False,
                "current_runtime_owner": "iamaman11/mobile-proxy-production",
                "credential_cleanup": "separate_read_only_ownership_audit_required_before_mutation",
            },
        )

    def test_residual_provider_retirement_cannot_regain_execution_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root)
            path = root / MODULE.RETIREMENT
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["residual_provider_access_retirement"]["execution_authority"] = True
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(
            any(
                "residual public production provider-access retirement differs" in error
                for error in errors
            )
        )

    def test_unclassified_public_workflow_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root)
            path = root / ".github/workflows/unclassified.yml"
            path.write_text(
                "name: Unclassified\non: workflow_dispatch\njobs: {}\n",
                encoding="utf-8",
            )
            errors = MODULE.check_repository(root)
        self.assertTrue(
            any(
                "public executable workflow classification differs" in error
                for error in errors
            )
        )

    def test_any_public_workflow_cannot_gain_target_secret(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root)
            path = root / MODULE.QUALITY_WORKFLOW
            path.write_text(
                path.read_text(encoding="utf-8")
                + "\n# ${{ secrets.NEW_PRIVATE_TARGET_TOKEN }}\n",
                encoding="utf-8",
            )
            errors = MODULE.check_repository(root)
        self.assertTrue(
            any(
                "references non-PRODUCT workflow secrets" in error
                and "NEW_PRIVATE_TARGET_TOKEN" in error
                for error in errors
            )
        )

    def test_any_public_workflow_cannot_gain_target_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root)
            path = root / MODULE.QUALITY_WORKFLOW
            path.write_text(
                path.read_text(encoding="utf-8") + "\nenvironment: production-target\n",
                encoding="utf-8",
            )
            errors = MODULE.check_repository(root)
        self.assertTrue(
            any(
                "references non-PRODUCT GitHub environments" in error
                and "production-target" in error
                for error in errors
            )
        )

    def test_any_public_workflow_cannot_gain_direct_vultr_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root)
            path = root / MODULE.QUALITY_WORKFLOW
            path.write_text(
                path.read_text(encoding="utf-8")
                + "\n# curl https://api.vultr.com/v2/account\n",
                encoding="utf-8",
            )
            errors = MODULE.check_repository(root)
        self.assertTrue(
            any(
                "wrong-owner authority token 'api.vultr.com'" in error
                for error in errors
            )
        )

    def test_non_release_public_workflow_cannot_gain_phone_production_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root)
            path = root / MODULE.QUALITY_WORKFLOW
            path.write_text(
                path.read_text(encoding="utf-8") + "\n# phone-production\n",
                encoding="utf-8",
            )
            errors = MODULE.check_repository(root)
        self.assertTrue(
            any(
                "wrong-owner authority token 'phone-production'" in error
                for error in errors
            )
        )

    def test_release_workflow_cannot_gain_phone_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root)
            path = root / ".github/workflows/release.yml"
            path.write_text(
                path.read_text(encoding="utf-8") + "\n# adb shell true\n",
                encoding="utf-8",
            )
            errors = MODULE.check_repository(root)
        self.assertTrue(
            any("wrong-owner authority token 'adb '" in error for error in errors)
        )

    def test_release_workflow_cannot_gain_deploy_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root)
            path = root / ".github/workflows/release.yml"
            path.write_text(
                path.read_text(encoding="utf-8")
                + "\n# /deploy phone-production v0.1.5\n",
                encoding="utf-8",
            )
            errors = MODULE.check_repository(root)
        self.assertTrue(
            any("wrong-owner authority token '/deploy '" in error for error in errors)
        )

    def test_release_tag_workflow_cannot_restore_item20_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root)
            path = root / ".github/workflows/release-tag.yml"
            path.write_text(
                path.read_text(encoding="utf-8") + "\n# ITEM20_ISSUE\n",
                encoding="utf-8",
            )
            errors = MODULE.check_repository(root)
        self.assertTrue(
            any("wrong-owner authority token 'ITEM20_ISSUE'" in error for error in errors)
        )

    def test_release_document_must_keep_product_release_before_deployment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_policy_tree(root)
            path = root / "docs/operations/final-release-authority-order.md"
            body = path.read_text(encoding="utf-8").replace(
                "A Product Release is an **input to deployment**, not an output of prior physical phone acceptance.",
                "Physical acceptance defines the product release.",
            )
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(
            any("missing protected authority token" in error for error in errors)
        )


if __name__ == "__main__":
    unittest.main()
