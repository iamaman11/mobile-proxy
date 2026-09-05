import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class GitDeliveryWorkflowTests(unittest.TestCase):
    def test_release_is_product_publication_only(self) -> None:
        release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

        self.assertIn("actions: read", release)
        self.assertIn("contents: write", release)
        self.assertIn("environment: product-release", release)
        self.assertIn("scripts/build_signed_android_release.py", release)
        self.assertIn("scripts/prepare_phone_release_runtime.py", release)
        self.assertIn(
            "contracts/operations/phone-production-release-components-v1.json",
            release,
        )
        self.assertIn("mobile-proxy-phone-production-runtime-", release)
        self.assertIn("repos/$GITHUB_REPOSITORY/immutable-releases", release)
        self.assertIn("gh release create", release)
        self.assertIn("--draft", release)
        self.assertNotIn("gh workflow run deploy-production.yml", release)
        self.assertNotIn("/deploy ", release)
        self.assertNotIn("adb ", release)
        self.assertNotIn("runs-on: self-hosted", release)
        self.assertNotIn("mobile-proxy-production", release)

    def test_quality_gate_owns_immutable_release_candidate_evidence(self) -> None:
        quality = (ROOT / ".github/workflows/quality.yml").read_text(encoding="utf-8")

        self.assertFalse(
            (ROOT / ".github/workflows/software-release-candidate.yml").exists()
        )
        self.assertIn("release-candidate-evidence:", quality)
        self.assertIn("Immutable release-candidate evidence", quality)
        self.assertIn("github.event_name != 'merge_group'", quality)
        self.assertIn("scripts/write_release_candidate_evidence.py", quality)
        self.assertIn("software-release-candidate-${{ env.CANDIDATE_SHA }}", quality)
        self.assertIn("release_candidate=$RELEASE_CANDIDATE_RESULT", quality)
        self.assertIn("test \"$RELEASE_CANDIDATE_RESULT\" = success", quality)


if __name__ == "__main__":
    unittest.main()
