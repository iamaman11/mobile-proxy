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
        self.assertEqual(context["format_version"], 3)
        self.assertEqual(context["quality"]["required_check"], "Quality Gate")
        self.assertEqual(
            context["source_metadata"]["expected_tag_from_source_version"],
            f"v{context['source_metadata']['workspace_version']}",
        )
        self.assertIn("crates/reverse-tunnel", context["workspace"]["members"])
        self.assertLess(len(MODULE.to_markdown(context)), 1800)

    def test_context_declares_one_source_of_truth_per_concern(self):
        context = MODULE.build_context()
        authority = context["project_authority"]
        truth = context["source_of_truth_by_concern"]
        recovery = context["context_recovery"]

        self.assertEqual(authority["stage_cursor"], "iamaman11/mobile-proxy#179")
        self.assertEqual(authority["planning_backlog"], "iamaman11/mobile-proxy#249")
        self.assertEqual(
            authority["deployment_controller_repository"],
            "iamaman11/mobile-proxy-production",
        )
        self.assertEqual(
            truth["cross_project_working_method"],
            "STAGE_WORKFLOW.md",
        )
        self.assertIn("project-authority.md", truth["cross_plane_ownership"])
        self.assertIn("mobile-proxy-production#1", truth["controller_runtime_transaction_truth"])
        self.assertIn("mobile-proxy-production#97", truth["reusable_phone_diagnostic_mechanics"])
        self.assertEqual(
            recovery["spine"],
            [
                "AGENTS.md",
                "STAGE_WORKFLOW.md",
                "newest authoritative PRODUCT #179 checkpoint",
                "current subordinate Stage Issue",
            ],
        )
        self.assertIn("last owner-authored", recovery["issue_179_access"])
        self.assertIn("exact causal", recovery["controller_issue_1_access"])
        self.assertFalse(recovery["dynamic_state_embedded_here"])

    def test_context_does_not_restore_superseded_or_ambiguous_execution_model(self):
        context = MODULE.build_context()
        rendered = repr(context)
        for token in (
            "canonical_gitops_issue",
            "temporary_checkpoint",
            "active_roadmap",
            "execution satellite only",
            "blocked until split GitOps workflows",
            "release_immutability",
            "authoritative_docs",
        ):
            self.assertNotIn(token, rendered)

        references = set(context["reference_docs_on_demand"])
        self.assertIn("QUICK_REFERENCE.md", references)
        self.assertIn("IMPLEMENTATION_PLAN.md", references)
        self.assertNotIn("STAGE_WORKFLOW.md", references)
        self.assertNotIn("contracts/operations/project-authority-v1.json", references)

    def test_runtime_ownership_and_deployment_identity_remain_explicit(self):
        architecture = MODULE.build_context()["architecture"]
        self.assertEqual(
            architecture["primary_runtime"],
            "first_party_reverse_tunnel",
        )
        self.assertEqual(
            architecture["carrier_specific_egress_owner"],
            "first_party_android_egress",
        )
        self.assertEqual(
            architecture["deployment_identity"],
            "exact immutable Product Release + exact admitted Deployment Controller revision",
        )


if __name__ == "__main__":
    unittest.main()
