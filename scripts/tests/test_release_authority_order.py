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


SURFACE = (
    "contracts/operations/product-release-authority-v2.json",
    ".github/workflows/product-release-readiness.yml",
    ".github/workflows/release-tag.yml",
    ".github/workflows/release.yml",
    "docs/operations/final-release-authority-order.md",
)


def copy_surface(root: Path) -> None:
    for relative in SURFACE:
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


class ProductReleaseAuthorityOrderTests(unittest.TestCase):
    def test_repository_passes(self) -> None:
        self.assertEqual(MODULE.check_repository(ROOT), [])

    def test_release_command_cannot_move_back_to_issue_162(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surface(root)
            path = root / "contracts/operations/product-release-authority-v2.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["command"]["issue"] = 162
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("canonical public tracker #90" in error for error in errors))

    def test_readiness_command_must_remain_owner_read_only_on_issue_90(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surface(root)
            path = root / "contracts/operations/product-release-authority-v2.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["readiness_command"]["mutation_authority"] = True
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("readiness command authority differs" in error for error in errors))

    def test_settings_token_must_keep_administration_and_environments_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surface(root)
            path = root / "contracts/operations/product-release-authority-v2.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["preconditions"]["settings_token_permissions"] = [
                "repository_administration_read"
            ]
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("preconditions differ" in error for error in errors))

    def test_product_tag_cannot_restore_physical_acceptance_precondition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surface(root)
            path = root / "contracts/operations/product-release-authority-v2.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["preconditions"]["physical_acceptance_required_before_product_tag"] = True
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("preconditions differ" in error for error in errors))

    def test_readiness_workflow_cannot_receive_android_signing_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surface(root)
            path = root / ".github/workflows/product-release-readiness.yml"
            path.write_text(
                path.read_text(encoding="utf-8")
                + "\n# ANDROID_RELEASE_KEYSTORE_B64: ${{ secrets.ANDROID_RELEASE_KEYSTORE_B64 }}\n",
                encoding="utf-8",
            )
            errors = MODULE.check_repository(root)
        self.assertTrue(any("retired/wrong-owner token" in error for error in errors))

    def test_readiness_workflow_must_list_environment_secret_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surface(root)
            path = root / ".github/workflows/product-release-readiness.yml"
            body = path.read_text(encoding="utf-8").replace(
                "repos/$GITHUB_REPOSITORY/environments/product-release/secrets?per_page=100",
                "repos/$GITHUB_REPOSITORY/actions/secrets",
            )
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("missing protected Product Release v2 token" in error for error in errors))

    def test_readiness_workflow_must_prove_environment_protection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surface(root)
            path = root / ".github/workflows/product-release-readiness.yml"
            body = path.read_text(encoding="utf-8").replace(
                "product-release environment has no protection rules",
                "environment unchecked",
            )
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("missing protected Product Release v2 token" in error for error in errors))

    def test_release_tag_workflow_must_bind_exact_protected_main(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surface(root)
            path = root / ".github/workflows/release-tag.yml"
            body = path.read_text(encoding="utf-8").replace(
                "target SHA does not equal exact protected main",
                "target mismatch",
            )
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("missing protected Product Release v2 token" in error for error in errors))

    def test_release_tag_requires_exact_same_sha_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surface(root)
            path = root / ".github/workflows/release-tag.yml"
            body = path.read_text(encoding="utf-8").replace(
                "exact protected main has no eligible successful Product Release Readiness proof",
                "readiness skipped",
            )
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("missing protected Product Release v2 token" in error for error in errors))

    def test_release_workflow_requires_signed_android_build(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surface(root)
            path = root / ".github/workflows/release.yml"
            body = path.read_text(encoding="utf-8").replace(
                "scripts/build_signed_android_release.py",
                "scripts/build_android.py",
            )
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("missing protected Product Release v2 token" in error for error in errors))

    def test_release_workflow_requires_draft_first_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surface(root)
            path = root / ".github/workflows/release.yml"
            body = path.read_text(encoding="utf-8").replace("            --draft \\\n", "")
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("missing protected Product Release v2 token '--draft'" in error for error in errors))

    def test_release_workflow_requires_immutable_release_setting_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surface(root)
            path = root / ".github/workflows/release.yml"
            body = path.read_text(encoding="utf-8").replace(
                "repos/$GITHUB_REPOSITORY/immutable-releases",
                "repos/$GITHUB_REPOSITORY/releases",
            )
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("missing protected Product Release v2 token" in error for error in errors))

    def test_release_bundle_must_remain_retry_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surface(root)
            path = root / ".github/workflows/release.yml"
            path.write_text(path.read_text(encoding="utf-8") + "\n# $GITHUB_RUN_ID\n", encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("GITHUB_RUN_ID" in error for error in errors))

    def test_release_exact_asset_set_cannot_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surface(root)
            path = root / "contracts/operations/product-release-authority-v2.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["required_release_assets"] = ["release-manifest.json"]
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("exact asset set differs" in error for error in errors))

    def test_release_document_must_keep_product_release_as_deployment_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_surface(root)
            path = root / "docs/operations/final-release-authority-order.md"
            body = path.read_text(encoding="utf-8").replace(
                "A Product Release is an **input to deployment**, not an output of prior physical phone acceptance.",
                "Product Release follows physical acceptance.",
            )
            path.write_text(body, encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("missing protected Product Release v2 token" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
