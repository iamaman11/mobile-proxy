from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "run_android_filesystem_tooling_diagnostic.py"
SPEC = importlib.util.spec_from_file_location("android_filesystem_tooling_diagnostic", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class AndroidFilesystemToolingDiagnosticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = mock.patch.dict(
            os.environ,
            {"ANDROID_PRODUCTION_SERIAL": "registered-device"},
            clear=False,
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def _run_diagnostic(self, command_status: dict[str, str]):
        seen: list[str] = []

        def probe(_serial: str, command: str, *, timeout: int = 10) -> str:
            self.assertEqual(timeout, 10)
            seen.append(command)
            return command_status.get(command, MODULE.SUPPORTED)

        device = {
            "device_count": 1,
            "registered_device_match": True,
            "adb_state": "device",
            "shell_probe": True,
        }
        with (
            mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True}),
            mock.patch.object(MODULE._PREFLIGHT, "prove_registered_device", return_value=device),
            mock.patch.object(MODULE, "_probe_shell", side_effect=probe),
        ):
            report = MODULE.diagnose("a" * 40)
        return report, seen

    def test_compatible_when_exact_canonical_comparator_and_scratch_prerequisites_work(self) -> None:
        report, _seen = self._run_diagnostic({})

        self.assertEqual(report["classification"], "FILESYSTEM_TOOLING_COMPATIBLE")
        self.assertTrue(report["diagnostic_complete"])
        self.assertEqual(report["canonical_comparator"], "cmp")
        self.assertEqual(
            report["canonical_comparator_invocation_supported"], MODULE.SUPPORTED
        )
        self.assertFalse(report["phone_mutation_performed"])
        self.assertTrue(report["phone_access_performed"])
        self.assertFalse(report["raw_command_output_recorded"])
        self.assertFalse(report["raw_device_identifier_recorded"])
        self.assertNotIn("registered-device", str(report))

    def test_plain_cmp_double_dash_incompatibility_is_not_hidden_by_working_fallbacks(self) -> None:
        report, _seen = self._run_diagnostic(
            {
                "cmp -s -- /dev/null /dev/null": MODULE.UNSUPPORTED,
                "cmp -s /dev/null /dev/null": MODULE.SUPPORTED,
                "toybox cmp -s /dev/null /dev/null": MODULE.SUPPORTED,
                "busybox cmp -s /dev/null /dev/null": MODULE.SUPPORTED,
            }
        )

        self.assertEqual(report["classification"], "FILESYSTEM_TOOLING_INCOMPATIBLE")
        self.assertTrue(report["diagnostic_complete"])
        self.assertEqual(report["canonical_comparator"], "cmp")
        self.assertEqual(
            report["comparator_invocations"]["cmp_with_double_dash"],
            MODULE.UNSUPPORTED,
        )
        self.assertEqual(
            report["comparator_invocations"]["cmp_without_double_dash"],
            MODULE.SUPPORTED,
        )
        self.assertEqual(
            report["canonical_comparator_invocation_supported"], MODULE.UNSUPPORTED
        )

    def test_toybox_is_selected_only_when_plain_cmp_is_absent(self) -> None:
        report, _seen = self._run_diagnostic(
            {
                "command -v cmp >/dev/null 2>&1": MODULE.UNSUPPORTED,
                "command -v toybox >/dev/null 2>&1": MODULE.SUPPORTED,
                "toybox cmp -s /dev/null /dev/null": MODULE.SUPPORTED,
            }
        )

        self.assertEqual(report["classification"], "FILESYSTEM_TOOLING_COMPATIBLE")
        self.assertEqual(report["canonical_comparator"], "toybox_cmp")
        self.assertEqual(
            report["canonical_comparator_invocation_supported"], MODULE.SUPPORTED
        )

    def test_unknown_higher_priority_comparator_is_unobserved_not_fallback(self) -> None:
        report, _seen = self._run_diagnostic(
            {"command -v cmp >/dev/null 2>&1": MODULE.UNKNOWN}
        )

        self.assertEqual(report["classification"], "UNOBSERVED")
        self.assertFalse(report["diagnostic_complete"])
        self.assertIsNone(report["canonical_comparator"])
        self.assertEqual(
            report["canonical_comparator_invocation_supported"], MODULE.UNKNOWN
        )

    def test_probe_surface_is_strictly_observational(self) -> None:
        _report, seen = self._run_diagnostic({})

        allowed_exact = {
            "cmp -s -- /dev/null /dev/null",
            "cmp -s /dev/null /dev/null",
            "toybox cmp -s /dev/null /dev/null",
            "busybox cmp -s /dev/null /dev/null",
            "test -d /data/local/tmp",
            "test -w /data/local/tmp",
            "test -x /data/local/tmp",
        }
        expected_tools = {
            "cmp",
            "toybox",
            "busybox",
            "cp",
            "mv",
            "ln",
            "readlink",
            "mkdir",
            "rm",
        }
        expected_presence = {
            f"command -v {tool} >/dev/null 2>&1" for tool in expected_tools
        }
        self.assertEqual(set(seen), allowed_exact | expected_presence)
        self.assertEqual(len(seen), len(allowed_exact | expected_presence))

    def test_access_failure_stops_before_android_tool_probes(self) -> None:
        with (
            mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True}),
            mock.patch.object(
                MODULE._PREFLIGHT,
                "prove_registered_device",
                side_effect=MODULE._PREFLIGHT.PreflightFailure("device mismatch"),
            ),
            mock.patch.object(MODULE, "_probe_shell") as probe,
        ):
            with self.assertRaisesRegex(MODULE._PREFLIGHT.PreflightFailure, "device mismatch"):
                MODULE.diagnose("b" * 40)
            probe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
