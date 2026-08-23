import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).parents[1] / "write_ci_summary.py"
SPEC = importlib.util.spec_from_file_location("ci_summary", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class CiSummaryTests(unittest.TestCase):
    def test_success_is_compact_and_sorted(self):
        checks = MODULE.parse_checks(["rust=success", "policy=success"])
        summary = MODULE.build_summary(
            "a" * 40,
            checks,
            {"GITHUB_REPOSITORY": "o/r", "GITHUB_RUN_ID": "42"},
        )
        self.assertEqual(summary["overall"], "success")
        self.assertEqual(list(summary["checks"]), ["policy", "rust"])
        self.assertEqual(
            summary["workflow_run"],
            "https://github.com/o/r/actions/runs/42",
        )

    def test_non_success_result_fails_summary(self):
        summary = MODULE.build_summary(
            "b" * 40,
            MODULE.parse_checks(["rust=cancelled"]),
            {},
        )
        self.assertEqual(summary["overall"], "failure")

    def test_invalid_or_duplicate_checks_are_rejected(self):
        for value in ("rust=unknown", "../rust=success", "rust"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                MODULE.parse_checks([value])
        with self.assertRaises(ValueError):
            MODULE.parse_checks(["rust=success", "rust=failure"])
