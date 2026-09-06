from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/product-release-prerequisites.yml"


class ProductReleasePrerequisiteWorkflowTests(unittest.TestCase):
    def test_prerequisite_evidence_is_hosted_and_environment_bounded(self) -> None:
        body = WORKFLOW.read_text(encoding="utf-8")

        for token in (
            "runs-on: ubuntu-latest",
            "environment: product-release",
            "PRODUCT_RELEASE_SETTINGS_TOKEN",
            "ANDROID_RELEASE_KEYSTORE_B64",
            "ANDROID_RELEASE_KEYSTORE_PASSWORD",
            "ANDROID_RELEASE_KEY_ALIAS",
            "ANDROID_RELEASE_KEY_PASSWORD",
            "environments/product-release",
            "deployment-branch-policies?per_page=100",
            "environments/product-release/secrets?per_page=100",
            'expected = {("branch", "main"), ("tag", "v*.*.*")}',
            "if resolved != expected:",
            "Environment deployment ref policy: branch main + tag v*.*.* only",
            "repos/$GITHUB_REPOSITORY/immutable-releases",
            'value.get("enabled") is not True',
            "Exact required environment secret names present: true",
            "Android signing secret values loaded: false",
            "Phone access performed: false",
            "Deployment performed: false",
            "Provider or VM mutation performed: false",
            "Secret values emitted: false",
        ):
            self.assertIn(token, body)

        for forbidden in (
            "self-hosted",
            "adb ",
            "phone-production",
            "/deploy ",
            "mobile-proxy-production",
            "VULTR_API_KEY",
            "VULTR_SSH_PRIVATE_KEY",
            "ANDROID_RELEASE_KEYSTORE_B64: ${{ secrets.ANDROID_RELEASE_KEYSTORE_B64 }}",
            "ANDROID_RELEASE_KEYSTORE_PASSWORD: ${{ secrets.ANDROID_RELEASE_KEYSTORE_PASSWORD }}",
            "ANDROID_RELEASE_KEY_ALIAS: ${{ secrets.ANDROID_RELEASE_KEY_ALIAS }}",
            "ANDROID_RELEASE_KEY_PASSWORD: ${{ secrets.ANDROID_RELEASE_KEY_PASSWORD }}",
            "gh release create",
            "git tag -a",
            'expected = {("branch", "main")}',
            "Environment deployment ref policy: branch main only",
        ):
            self.assertNotIn(forbidden, body)

    def test_metadata_check_precedes_environment_secret_job(self) -> None:
        body = WORKFLOW.read_text(encoding="utf-8")
        metadata = body.index("environment-metadata:")
        bindings = body.index("environment-bindings:")
        self.assertLess(metadata, bindings)
        self.assertIn("needs: environment-metadata", body)

    def test_only_release_and_prerequisite_workflows_can_reference_environment(self) -> None:
        references = set()
        for path in (ROOT / ".github/workflows").glob("*.yml"):
            if "environment: product-release" in path.read_text(encoding="utf-8"):
                references.add(path.name)
        self.assertEqual(references, {"release.yml", "product-release-prerequisites.yml"})


if __name__ == "__main__":
    unittest.main()
