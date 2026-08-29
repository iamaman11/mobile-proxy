import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class GitDeliveryWorkflowTests(unittest.TestCase):
    def test_release_never_dispatches_legacy_production(self) -> None:
        release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

        self.assertIn("actions: write", release)
        self.assertNotIn("gh workflow run deploy-production.yml", release)

    def test_legacy_deployment_workflow_is_an_explicit_migration_gate(self) -> None:
        deployment = (ROOT / ".github/workflows/deploy-production.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("workflow_dispatch:", deployment)
        self.assertIn("Production deployment is blocked", deployment)
        self.assertNotIn("self-hosted", deployment)


if __name__ == "__main__":
    unittest.main()
