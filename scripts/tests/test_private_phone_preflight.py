import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "run_private_phone_preflight.py"
SPEC = importlib.util.spec_from_file_location("private_phone_preflight", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class PrivatePhonePreflightTests(unittest.TestCase):
    def setUp(self):
        self.environment = mock.patch.dict(
            os.environ,
            {"ANDROID_PRODUCTION_SERIAL": "registered-device"},
            clear=False,
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    @mock.patch.object(MODULE.shutil, "which", return_value="/usr/bin/tool")
    @mock.patch.object(MODULE.subprocess, "run")
    def test_exact_registered_device_passes_without_recording_identifier(
        self, run, _which
    ):
        run.side_effect = [
            SimpleNamespace(
                stdout="List of devices attached\nregistered-device\tdevice\n"
            ),
            SimpleNamespace(stdout="device\n"),
            SimpleNamespace(stdout=""),
            SimpleNamespace(stdout="boot-identity-raw\n"),
        ]

        report = MODULE.build_report("a" * 40)

        self.assertTrue(report["accepted"])
        self.assertFalse(report["mutation_performed"])
        self.assertFalse(report["raw_device_identifier_recorded"])
        self.assertFalse(report["raw_boot_identifier_recorded"])
        self.assertNotIn("registered-device", str(report))
        self.assertNotIn("boot-identity-raw", str(report))
        self.assertEqual(report["device"]["device_count"], 1)
        self.assertEqual(
            run.call_args_list[-2].args[0],
            ["adb", "-s", "registered-device", "shell", "true"],
        )
        self.assertEqual(
            run.call_args_list[-1].args[0],
            [
                "adb",
                "-s",
                "registered-device",
                "shell",
                "cat",
                "/proc/sys/kernel/random/boot_id",
            ],
        )

        self.assertEqual(report["format_version"], 2)
        self.assertFalse(report["fact_reuse_eligible"])
        self.assertEqual(len(report["observed_facts"]), 1)
        fact = report["observed_facts"][0]
        self.assertFalse(fact["persisted"])
        self.assertEqual(fact["subject"], "phone")
        self.assertEqual(fact["predicate"], "phone_access_proven")
        scopes = {item["scope"] for item in fact["dependencies"]}
        self.assertEqual(
            scopes,
            {
                "target/android-production",
                "observer/phone-access",
                "boot/android-production",
            },
        )

    @mock.patch.object(MODULE.shutil, "which", return_value="/usr/bin/tool")
    @mock.patch.object(MODULE.subprocess, "run")
    def test_transaction_bound_preflight_emits_same_transaction_dependency(
        self, run, _which
    ):
        run.side_effect = [
            SimpleNamespace(
                stdout="List of devices attached\nregistered-device\tdevice\n"
            ),
            SimpleNamespace(stdout="device\n"),
            SimpleNamespace(stdout=""),
            SimpleNamespace(stdout="boot-2\n"),
        ]

        report = MODULE.build_report("b" * 40, transaction_id="tx-boundary")
        dependencies = {
            item["scope"]: item["identity"]
            for item in report["observed_facts"][0]["dependencies"]
        }
        self.assertEqual(dependencies["transaction/operation"], "tx-boundary")
        self.assertNotIn("b" * 40, dependencies.values())

    @mock.patch.object(MODULE.shutil, "which", return_value="/usr/bin/tool")
    @mock.patch.object(MODULE.subprocess, "run")
    def test_multiple_devices_fail_closed(self, run, _which):
        run.return_value = SimpleNamespace(
            stdout=(
                "List of devices attached\n"
                "registered-device\tdevice\n"
                "other-device\tdevice\n"
            )
        )

        with self.assertRaisesRegex(MODULE.PreflightFailure, "exactly one"):
            MODULE.build_report("a" * 40)

    @mock.patch.object(MODULE.shutil, "which", return_value="/usr/bin/tool")
    @mock.patch.object(MODULE.subprocess, "run")
    def test_wrong_device_fails_without_exposing_identifier(self, run, _which):
        run.return_value = SimpleNamespace(
            stdout="List of devices attached\nwrong-device\tdevice\n"
        )

        with self.assertRaises(MODULE.PreflightFailure) as caught:
            MODULE.build_report("a" * 40)

        self.assertNotIn("wrong-device", str(caught.exception))
        self.assertNotIn("registered-device", str(caught.exception))

    @mock.patch.object(MODULE.shutil, "which")
    def test_missing_required_tool_fails_before_adb(self, which):
        which.side_effect = lambda tool: None if tool == "git" else f"/usr/bin/{tool}"

        with mock.patch.object(MODULE.subprocess, "run") as run:
            with self.assertRaisesRegex(MODULE.PreflightFailure, "git"):
                MODULE.build_report("a" * 40)
        run.assert_not_called()

    def test_invalid_serial_binding_fails_closed(self):
        with mock.patch.dict(
            os.environ,
            {"ANDROID_PRODUCTION_SERIAL": "bad serial"},
            clear=False,
        ):
            with self.assertRaisesRegex(
                MODULE.PreflightFailure,
                "binding is invalid",
            ):
                MODULE.require_expected_serial()

    def test_invalid_canonical_sha_is_rejected(self):
        with self.assertRaisesRegex(MODULE.PreflightFailure, "canonical SHA"):
            MODULE.require_canonical_sha("main")


if __name__ == "__main__":
    unittest.main()
