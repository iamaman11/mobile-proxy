from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "run_android_capability_inventory.py"
SPEC = importlib.util.spec_from_file_location("android_capability_inventory", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class AndroidCapabilityInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = mock.patch.dict(
            os.environ,
            {"ANDROID_PRODUCTION_SERIAL": "registered-device"},
            clear=False,
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

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
    def test_read_only_capabilities_supported_but_mutation_remains_unknown(
        self, run, _device, _tools
    ) -> None:
        run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")

        report = MODULE.inventory("a" * 40)

        self.assertTrue(report["read_only_capabilities_proven"])
        self.assertFalse(report["full_clean_install_capability_proven"])
        self.assertFalse(report["phone_mutation_performed"])
        self.assertFalse(report["raw_device_identifier_recorded"])
        for capability in MODULE.READ_ONLY_CAPABILITIES:
            self.assertEqual(report["capabilities"][capability], MODULE.SUPPORTED)
        for capability in MODULE.MUTATION_CAPABILITIES:
            self.assertEqual(report["capabilities"][capability], MODULE.UNKNOWN)
            self.assertIn(capability, report["unresolved_capabilities"])

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
    def test_nonzero_probe_is_unsupported_without_aborting_inventory(
        self, run, _device, _tools
    ) -> None:
        run.side_effect = [
            SimpleNamespace(returncode=0, stdout="", stderr=""),
            SimpleNamespace(returncode=1, stdout="", stderr="permission denied"),
            SimpleNamespace(returncode=1, stdout="", stderr="permission denied"),
            SimpleNamespace(returncode=1, stdout="", stderr="permission denied"),
            SimpleNamespace(returncode=1, stdout="", stderr="permission denied"),
            SimpleNamespace(returncode=0, stdout="", stderr=""),
        ]

        report = MODULE.inventory("b" * 40)

        self.assertEqual(report["capabilities"]["package_query"], MODULE.SUPPORTED)
        self.assertEqual(report["capabilities"]["root_shell"], MODULE.UNSUPPORTED)
        self.assertFalse(report["read_only_capabilities_proven"])
        self.assertIn("root_shell", report["unresolved_capabilities"])

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
    def test_transport_failure_is_unknown(self, run, _device, _tools) -> None:
        run.side_effect = subprocess_timeout = __import__("subprocess").TimeoutExpired(
            cmd=["adb"], timeout=10
        )

        report = MODULE.inventory("c" * 40)

        self.assertEqual(report["capabilities"]["package_query"], MODULE.UNKNOWN)
        self.assertEqual(report["capabilities"]["root_shell"], MODULE.UNKNOWN)
        self.assertFalse(report["read_only_capabilities_proven"])
        self.assertIsNotNone(subprocess_timeout)

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
    def test_probe_commands_are_observational_only(self, run, _device, _tools) -> None:
        run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")

        MODULE.inventory("d" * 40)

        commands = [" ".join(call.args[0]) for call in run.call_args_list]
        text = "\n".join(commands)
        forbidden = (
            " push ",
            " pull ",
            " pm install",
            " pm uninstall",
            " mkdir ",
            " rm ",
            " mv ",
            " cp ",
            " chmod ",
            " chown ",
            " am start",
            " force-stop",
        )
        for token in forbidden:
            self.assertNotIn(token, text)

    def test_access_failure_stops_before_capability_probes(self) -> None:
        with mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True}), mock.patch.object(
            MODULE._PREFLIGHT,
            "prove_registered_device",
            side_effect=MODULE._PREFLIGHT.PreflightFailure("device mismatch"),
        ), mock.patch.object(MODULE.subprocess, "run") as run:
            with self.assertRaisesRegex(MODULE._PREFLIGHT.PreflightFailure, "device mismatch"):
                MODULE.inventory("e" * 40)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
