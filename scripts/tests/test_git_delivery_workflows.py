import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class GitDeliveryWorkflowTests(unittest.TestCase):
    def test_release_explicitly_dispatches_the_exact_tag_to_production(self) -> None:
        release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

        self.assertIn("actions: write", release)
        self.assertIn("gh workflow run deploy-production.yml", release)
        self.assertIn('--ref "$RELEASE_TAG"', release)
        self.assertIn('-f release_tag="$RELEASE_TAG"', release)
        self.assertIn("-f deploy_vm=true", release)
        self.assertIn("-f deploy_device=true", release)

    def test_manually_published_releases_remain_a_supported_trigger(self) -> None:
        deployment = (ROOT / ".github/workflows/deploy-production.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("release:\n    types:\n      - published", deployment)


if __name__ == "__main__":
    unittest.main()
