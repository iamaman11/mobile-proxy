from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
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

    def _run_for(self, resolver):
        def fake_run(command, **_kwargs):
            text = " ".join(command)
            return SimpleNamespace(
                returncode=0 if resolver(text) else 1,
                stdout="registered-device should-not-leak",
                stderr="registered-device should-not-leak",
            )

        return fake_run

    def _selector_probes(self, **overrides: str) -> dict[str, str]:
        probes = {
            "cmp_present": MODULE.UNSUPPORTED,
            "cmp_exact_invocation": MODULE.UNSUPPORTED,
            "toybox_present": MODULE.UNSUPPORTED,
            "toybox_cmp_exact_invocation": MODULE.UNSUPPORTED,
            "busybox_present": MODULE.UNSUPPORTED,
            "busybox_cmp_exact_invocation": MODULE.UNSUPPORTED,
        }
        probes.update(overrides)
        return probes

    def test_comparator_selection_truth_table(self) -> None:
        cases = (
            (
                "compatible primary",
                self._selector_probes(
                    cmp_present=MODULE.SUPPORTED,
                    cmp_exact_invocation=MODULE.SUPPORTED,
                ),
                ("cmp", MODULE.SUPPORTED),
            ),
            (
                "incompatible primary compatible fallback",
                self._selector_probes(
                    cmp_present=MODULE.SUPPORTED,
                    cmp_exact_invocation=MODULE.UNSUPPORTED,
                    toybox_present=MODULE.SUPPORTED,
                    toybox_cmp_exact_invocation=MODULE.SUPPORTED,
                ),
                ("toybox_cmp", MODULE.SUPPORTED),
            ),
            (
                "two incompatible candidates compatible final fallback",
                self._selector_probes(
                    cmp_present=MODULE.SUPPORTED,
                    cmp_exact_invocation=MODULE.UNSUPPORTED,
                    toybox_present=MODULE.SUPPORTED,
                    toybox_cmp_exact_invocation=MODULE.UNSUPPORTED,
                    busybox_present=MODULE.SUPPORTED,
                    busybox_cmp_exact_invocation=MODULE.SUPPORTED,
                ),
                ("busybox_cmp", MODULE.SUPPORTED),
            ),
            (
                "all candidate invocations conclusively incompatible",
                self._selector_probes(
                    cmp_present=MODULE.SUPPORTED,
                    toybox_present=MODULE.SUPPORTED,
                    busybox_present=MODULE.SUPPORTED,
                ),
                ("NONE", MODULE.UNSUPPORTED),
            ),
            (
                "unknown primary does not block compatible fallback",
                self._selector_probes(
                    cmp_present=MODULE.SUPPORTED,
                    cmp_exact_invocation=MODULE.UNKNOWN,
                    toybox_present=MODULE.SUPPORTED,
                    toybox_cmp_exact_invocation=MODULE.SUPPORTED,
                ),
                ("toybox_cmp", MODULE.SUPPORTED),
            ),
            (
                "unresolved candidate without compatible fallback",
                self._selector_probes(
                    cmp_present=MODULE.SUPPORTED,
                    cmp_exact_invocation=MODULE.UNKNOWN,
                ),
                ("UNKNOWN", MODULE.UNKNOWN),
            ),
            (
                "absent candidate makes unknown invocation irrelevant",
                self._selector_probes(
                    cmp_present=MODULE.UNSUPPORTED,
                    cmp_exact_invocation=MODULE.UNKNOWN,
                ),
                ("NONE", MODULE.UNSUPPORTED),
            ),
            (
                "exact invocation success outranks inconclusive presence",
                self._selector_probes(
                    cmp_present=MODULE.UNKNOWN,
                    cmp_exact_invocation=MODULE.SUPPORTED,
                ),
                ("cmp", MODULE.SUPPORTED),
            ),
        )

        for name, probes, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(MODULE._select_comparator(probes), expected)

    def test_present_but_incompatible_primary_cannot_block_compatible_fallback(self) -> None:
        probes = self._selector_probes(
            cmp_present=MODULE.SUPPORTED,
            cmp_exact_invocation=MODULE.UNSUPPORTED,
            toybox_present=MODULE.SUPPORTED,
            toybox_cmp_exact_invocation=MODULE.SUPPORTED,
        )

        self.assertEqual(
            MODULE._select_comparator(probes),
            ("toybox_cmp", MODULE.SUPPORTED),
        )

    def test_invalid_comparator_probe_state_is_rejected(self) -> None:
        probes = self._selector_probes(cmp_present="BROKEN")

        with self.assertRaisesRegex(MODULE.ToolingDiagnosticFailure, "invalid comparator probe state"):
            MODULE._select_comparator(probes)

    @mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True})
    @mock.patch.object(
        MODULE._PREFLIGHT,
        "prove_registered_device",
        return_value={
            "device_count": 1,
            "registered_device_match": True,
            "adb_state": "device",
            "shell_probe": True,
        },
    )
    @mock.patch.object(MODULE.subprocess, "run")
    def test_cmp_exact_invocation_supported_in_both_scopes(self, run, _device, _tools) -> None:
        run.side_effect = self._run_for(lambda _text: True)

        report = MODULE.diagnose("a" * 40)

        self.assertTrue(report["diagnostic_complete"])
        self.assertTrue(report["comparator_compatibility_proven"])
        self.assertEqual(report["scratch_scope"]["selected_comparator"], "cmp")
        self.assertEqual(report["managed_root_scope"]["selected_comparator"], "cmp")
        self.assertEqual(
            report["scratch_scope"]["canonical_comparator_path_state"],
            MODULE.SUPPORTED,
        )
        self.assertFalse(report["phone_mutation_performed"])
        self.assertFalse(report["raw_device_identifier_recorded"])
        self.assertFalse(report["raw_command_output_recorded"])
        self.assertNotIn("registered-device", str(report))

    @mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True})
    @mock.patch.object(MODULE._PREFLIGHT, "prove_registered_device", return_value={})
    @mock.patch.object(MODULE.subprocess, "run")
    def test_cmp_exact_incompatibility_falls_back_to_toybox(
        self, run, _device, _tools
    ) -> None:
        def resolver(text: str) -> bool:
            if "cmp -s -- /dev/null /dev/null" in text:
                return False
            return True

        run.side_effect = self._run_for(resolver)

        report = MODULE.diagnose("b" * 40)

        scratch = report["scratch_scope"]
        self.assertEqual(scratch["probes"]["cmp_present"], MODULE.SUPPORTED)
        self.assertEqual(scratch["probes"]["toybox_present"], MODULE.SUPPORTED)
        self.assertEqual(
            scratch["probes"]["toybox_cmp_exact_invocation"],
            MODULE.SUPPORTED,
        )
        self.assertEqual(scratch["selected_comparator"], "toybox_cmp")
        self.assertEqual(
            scratch["canonical_comparator_path_state"],
            MODULE.SUPPORTED,
        )
        self.assertTrue(report["comparator_compatibility_proven"])

    @mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True})
    @mock.patch.object(MODULE._PREFLIGHT, "prove_registered_device", return_value={})
    @mock.patch.object(MODULE.subprocess, "run")
    def test_toybox_is_selected_when_cmp_is_absent(self, run, _device, _tools) -> None:
        def resolver(text: str) -> bool:
            if "command -v cmp " in text:
                return False
            if "cmp -s -- /dev/null /dev/null" in text:
                return False
            return True

        run.side_effect = self._run_for(resolver)

        report = MODULE.diagnose("c" * 40)

        for scope_name in ("scratch_scope", "managed_root_scope"):
            scope = report[scope_name]
            self.assertEqual(scope["selected_comparator"], "toybox_cmp")
            self.assertEqual(
                scope["canonical_comparator_path_state"],
                MODULE.SUPPORTED,
            )
        self.assertTrue(report["comparator_compatibility_proven"])

    @mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True})
    @mock.patch.object(MODULE._PREFLIGHT, "prove_registered_device", return_value={})
    @mock.patch.object(MODULE.subprocess, "run")
    def test_root_scope_is_classified_independently(self, run, _device, _tools) -> None:
        def resolver(text: str) -> bool:
            root = " shell su 0 sh -c " in f" {text} "
            if root and "command -v cmp " in text:
                return False
            if root and "cmp -s -- /dev/null /dev/null" in text:
                return False
            return True

        run.side_effect = self._run_for(resolver)

        report = MODULE.diagnose("d" * 40)

        self.assertEqual(report["scratch_scope"]["selected_comparator"], "cmp")
        self.assertEqual(
            report["managed_root_scope"]["selected_comparator"],
            "toybox_cmp",
        )
        self.assertTrue(report["comparator_compatibility_proven"])

    @mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True})
    @mock.patch.object(MODULE._PREFLIGHT, "prove_registered_device", return_value={})
    @mock.patch.object(MODULE.subprocess, "run")
    def test_transport_failure_is_bounded_as_unknown(self, run, _device, _tools) -> None:
        timeout = __import__("subprocess").TimeoutExpired(cmd=["adb"], timeout=10)
        run.side_effect = timeout

        report = MODULE.diagnose("e" * 40)

        self.assertFalse(report["diagnostic_complete"])
        self.assertFalse(report["comparator_compatibility_proven"])
        self.assertEqual(
            report["scratch_scope"]["canonical_comparator_path_state"],
            MODULE.UNKNOWN,
        )

    @mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True})
    @mock.patch.object(MODULE._PREFLIGHT, "prove_registered_device", return_value={})
    @mock.patch.object(MODULE.subprocess, "run")
    def test_probe_commands_are_read_only_and_comparator_targets_dev_null(
        self, run, _device, _tools
    ) -> None:
        run.side_effect = self._run_for(lambda _text: True)

        MODULE.diagnose("f" * 40)

        commands = [call.args[0] for call in run.call_args_list]
        forbidden_shell_tokens = (
            "mkdir ",
            "rm ",
            "mv ",
            "cp ",
            "chmod ",
            "chown ",
            "ln -s ",
            "pm install",
            "pm uninstall",
            "am start",
            "force-stop",
        )
        for command in commands:
            self.assertNotIn("push", command)
            self.assertNotIn("pull", command)
            shell_command = command[-1]
            if shell_command.startswith("command -v "):
                continue
            for token in forbidden_shell_tokens:
                self.assertNotIn(token, shell_command)

        rendered = [" ".join(command) for command in commands]
        cmp_commands = [command for command in rendered if " cmp " in f" {command} "]
        self.assertTrue(cmp_commands)
        for command in cmp_commands:
            if "command -v" not in command:
                self.assertIn("/dev/null /dev/null", command)

    def test_access_failure_stops_before_tooling_probes(self) -> None:
        with mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True}), mock.patch.object(
            MODULE._PREFLIGHT,
            "prove_registered_device",
            side_effect=MODULE._PREFLIGHT.PreflightFailure("device mismatch"),
        ), mock.patch.object(MODULE.subprocess, "run") as run:
            with self.assertRaisesRegex(MODULE._PREFLIGHT.PreflightFailure, "device mismatch"):
                MODULE.diagnose("1" * 40)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
