import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).parents[1] / "repository_context.py"
SPEC = importlib.util.spec_from_file_location("repository_context", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class RepositoryContextTests(unittest.TestCase):
    def test_context_is_bounded_and_identifies_delivery_contract(self):
        context = MODULE.build_context()
        self.assertEqual(context["format_version"], 2)
        self.assertEqual(context["quality"]["required_check"], "Quality Gate")
        self.assertEqual(
            context["source_metadata"]["expected_tag_from_source_version"],
            f"v{context['source_metadata']['workspace_version']}",
        )
        self.assertIn("crates/reverse-tunnel", context["workspace"]["members"])
        self.assertLess(len(MODULE.to_markdown(context)), 1600)

    def test_context_points_to_single_execution_spine(self):
        context = MODULE.build_context()
        authority = context["project_authority"]
        current = context["current_execution"]

        self.assertEqual(authority["stage_cursor"], "iamaman11/mobile-proxy#179")
        self.assertEqual(authority["planning_backlog"], "iamaman11/mobile-proxy#249")
        self.assertEqual(
            authority["deployment_controller_repository"],
            "iamaman11/mobile-proxy-production",
        )
        self.assertEqual(
            current["context_recovery_spine"],
            [
                "AGENTS.md",
                "STAGE_WORKFLOW.md",
                "newest authoritative PRODUCT #179 checkpoint",
                "current subordinate Stage Issue",
            ],
        )
        self.assertEqual(
            current["stage_roadmap"],
            "docs/PRODUCTION_STAGE_ROADMAP.md",
        )
        self.assertEqual(
            current["baseline_invariants"],
            "docs/PRODUCTION_BASELINE_PLAN.md",
        )
        self.assertFalse(current["dynamic_state_embedded_here"])

    def test_context_does_not_restore_superseded_execution_model(self):
        context = MODULE.build_context()
        rendered = repr(context)
        self.assertNotIn("canonical_gitops_issue", rendered)
        self.assertNotIn("temporary_checkpoint", rendered)
        self.assertNotIn("active_roadmap", rendered)
        self.assertNotIn("execution satellite only", rendered)
        self.assertNotIn("blocked until split GitOps workflows", rendered)
        self.assertNotIn("release_immutability", rendered)

        docs = set(context["authoritative_docs"])
        self.assertTrue(
            {
                "AGENTS.md",
                "STAGE_WORKFLOW.md",
                "docs/PRODUCTION_STAGE_ROADMAP.md",
                "docs/architecture/ARCHITECTURE_STANDARD.md",
                "contracts/operations/project-authority-v2.json",
                "contracts/operations/github-control-plane-v2.json",
                "contracts/operations/production-topology-v2.json",
                "contracts/operations/product-release-authority-v2.json",
            }.issubset(docs)
        )
        self.assertNotIn("contracts/operations/project-authority-v1.json", docs)
        self.assertNotIn("contracts/operations/github-control-plane-v1.json", docs)
        self.assertNotIn("contracts/operations/production-topology-v1.json", docs)

    def test_runtime_ownership_distinguishes_default_from_carrier_egress(self):
        architecture = MODULE.build_context()["architecture"]
        self.assertEqual(
            architecture["default_tunnel_owner"],
            "first_party_reverse_tunnel",
        )
        self.assertEqual(
            architecture["production_phone_owner"],
            architecture["default_tunnel_owner"],
        )
        self.assertEqual(
            architecture["carrier_specific_egress_owner"],
            "first_party_android_egress",
        )
        self.assertEqual(
            architecture["deployment_identity"],
            "exact immutable Product Release + exact admitted Deployment Controller revision",
        )
