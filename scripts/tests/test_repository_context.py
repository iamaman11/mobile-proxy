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
        self.assertEqual(context["format_version"], 1)
        self.assertEqual(context["quality"]["required_check"], "Quality Gate")
        self.assertEqual(
            context["release"]["expected_tag"],
            f"v{context['release']['version']}",
        )
        self.assertIn(
            "crates/reverse-tunnel",
            context["workspace"]["members"],
        )
        self.assertLess(len(MODULE.to_markdown(context)), 1200)

    def test_context_points_to_current_recovery_surface(self):
        context = MODULE.build_context()
        current = context["current_execution"]
        self.assertEqual(current["context_entrypoint"], "QUICK_REFERENCE.md")
        self.assertEqual(
            current["temporary_checkpoint"],
            "IMPLEMENTATION_PLAN.md#current-execution-checkpoint",
        )
        self.assertEqual(
            current["active_roadmap"],
            "docs/PRODUCTION_BASELINE_PLAN.md",
        )
        self.assertEqual(
            current["acceptance_matrix"],
            "TEN_OUT_OF_TEN_VALIDATION_PLAN.md",
        )
        self.assertEqual(
            current["architecture_standard"],
            "docs/architecture/ARCHITECTURE_STANDARD.md",
        )

        docs = set(context["authoritative_docs"])
        self.assertTrue(
            {
                "QUICK_REFERENCE.md",
                "REPOSITORY_MAP.md",
                "docs/architecture/ARCHITECTURE_STANDARD.md",
                "contracts/governance/module-boundaries-v1.json",
                "contracts/governance/state-ownership-v1.json",
            }.issubset(docs)
        )

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
