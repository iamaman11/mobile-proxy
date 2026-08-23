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
