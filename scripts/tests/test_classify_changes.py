import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).parents[1] / "classify_changes.py"
SPEC = importlib.util.spec_from_file_location("classify_changes", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ClassifyChangesTests(unittest.TestCase):
    def test_markdown_only_is_documentation_scope(self):
        self.assertFalse(
            MODULE.requires_code_gate(
                ["README.md", "docs/GIT_DELIVERY.md", "AGENTS.md"]
            )
        )

    def test_every_executable_or_configuration_path_requires_full_gate(self):
        for path in (
            ".github/workflows/quality.yml",
            "Cargo.toml",
            "scripts/tool.py",
            "deploy/profile.json",
            "apps/android-app/README.txt",
        ):
            with self.subTest(path=path):
                self.assertTrue(MODULE.requires_code_gate([path]))

    def test_missing_comparison_fails_safe(self):
        self.assertEqual(
            MODULE.changed_paths("invalid", "also-invalid"),
            ["unknown-input"],
        )
        self.assertTrue(MODULE.requires_code_gate(["unknown-input"]))
