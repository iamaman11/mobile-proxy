from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "run_android_scratch_certification.py"
SPEC = importlib.util.spec_from_file_location("android_scratch_certification", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def ok() -> object:
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def fail() -> object:
    return SimpleNamespace(returncode=1, stdout="", stderr="failure")


DEVICE = {
    "device_count": 1,
    "registered_device_match": True,
    "adb_state": "device",
    "shell_probe": True,
}


class AndroidScratchCertificationTests(unittest.TestCase):
    def common(self):
        return mock.patch.multiple(
            MODULE.PREFLIGHT,
            require_expected_serial=mock.DEFAULT,
            require_tools=mock.DEFAULT,
            prove_registered_device=mock.DEFAULT,
        )

    def test_success_proves_roundtrip_replace_cleanup_and_acceptance(self) -> None:
        with self.common() as patches, mock.patch.object(MODULE, "_shell", return_value=ok()) as shell, mock.patch.object(
            MODULE, "_push"
        ) as push, mock.patch.object(MODULE, "_pull") as pull, mock.patch.object(
            MODULE, "_sha256", side_effect=["first", "second", "first", "second"]
        ):
            patches["require_expected_serial"].return_value = "registered"
            patches["require_tools"].return_value = {"adb": True}
            patches["prove_registered_device"].return_value = DEVICE

            report, accepted = MODULE.certify("a" * 40, "txn-1")

        self.assertTrue(accepted)
        self.assertEqual(report["state"], "ACCEPTED")
        self.assertTrue(report["phone_mutation_performed"])
        self.assertFalse(report["recovery_attempted"])
        self.assertFalse(report["raw_device_identifier_recorded"])
        self.assertEqual(push.call_count, 2)
        self.assertEqual(pull.call_count, 2)
        phases = [item["step_id"] for item in report["phase_evidence"]]
        self.assertEqual(
            phases,
            [
                "scratch_absent_initial",
                "phone_access_boundary",
                "scratch_create",
                "scratch_push",
                "scratch_roundtrip_verify",
                "scratch_stage_replacement",
                "scratch_atomic_replace",
                "scratch_replacement_verify",
                "scratch_cleanup",
                "scratch_absent_final",
            ],
        )
        commands = "\n".join(call.args[1] for call in shell.call_args_list)
        self.assertIn("/data/local/tmp/mobile-proxy-adapter-test/txn-1", commands)
        self.assertNotIn("/data/adb/", commands)

    def test_boundary_failure_refuses_before_mutation(self) -> None:
        with self.common() as patches, mock.patch.object(MODULE, "_shell", return_value=ok()), mock.patch.object(
            MODULE, "_push"
        ) as push:
            patches["require_expected_serial"].return_value = "registered"
            patches["require_tools"].return_value = {"adb": True}
            patches["prove_registered_device"].side_effect = [
                DEVICE,
                MODULE.PREFLIGHT.PreflightFailure("boundary mismatch"),
            ]

            report, accepted = MODULE.certify("b" * 40, "txn-2")

        self.assertFalse(accepted)
        self.assertEqual(report["state"], "REFUSED")
        self.assertFalse(report["phone_mutation_performed"])
        self.assertFalse(report["recovery_attempted"])
        push.assert_not_called()

    def test_failed_first_mutation_recovers_to_absent_baseline(self) -> None:
        with self.common() as patches, mock.patch.object(
            MODULE, "_shell", side_effect=[ok(), fail(), ok(), ok()]
        ), mock.patch.object(MODULE, "_push") as push:
            patches["require_expected_serial"].return_value = "registered"
            patches["require_tools"].return_value = {"adb": True}
            patches["prove_registered_device"].return_value = DEVICE

            report, accepted = MODULE.certify("c" * 40, "txn-3")

        self.assertFalse(accepted)
        self.assertEqual(report["state"], "RECOVERED")
        self.assertTrue(report["phone_mutation_performed"])
        self.assertTrue(report["recovery_attempted"])
        self.assertTrue(report["recovery_succeeded"])
        push.assert_not_called()
        phases = {item["step_id"]: item["status"] for item in report["phase_evidence"]}
        self.assertEqual(phases["recovery_cleanup"], "PASSED")
        self.assertEqual(phases["recovery_absence_verify"], "PASSED")

    def test_failed_recovery_quarantines(self) -> None:
        with self.common() as patches, mock.patch.object(
            MODULE, "_shell", side_effect=[ok(), fail(), fail()]
        ):
            patches["require_expected_serial"].return_value = "registered"
            patches["require_tools"].return_value = {"adb": True}
            patches["prove_registered_device"].return_value = DEVICE

            report, accepted = MODULE.certify("d" * 40, "txn-4")

        self.assertFalse(accepted)
        self.assertEqual(report["state"], "QUARANTINED")
        self.assertTrue(report["recovery_attempted"])
        self.assertFalse(report["recovery_succeeded"])

    def test_invalid_transaction_id_is_rejected_before_device_access(self) -> None:
        with mock.patch.object(MODULE.PREFLIGHT, "require_expected_serial") as serial:
            with self.assertRaisesRegex(MODULE.CertificationFailure, "invalid transaction id"):
                MODULE.certify("e" * 40, "../escape")
            serial.assert_not_called()


if __name__ == "__main__":
    unittest.main()
