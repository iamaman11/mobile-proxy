from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "run_android_filesystem_quarantine_recovery.py"
SPEC = importlib.util.spec_from_file_location(
    "android_filesystem_quarantine_recovery_evidence",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class AndroidFilesystemQuarantineEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = mock.patch.dict(
            os.environ,
            {"ANDROID_PRODUCTION_SERIAL": "registered-device"},
            clear=False,
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    @staticmethod
    def _observation(node_state: str) -> dict[str, object]:
        report: dict[str, object] = {
            "scratch_base": {
                "node_state": MODULE.DIRECTORY,
                "writable": MODULE.SUPPORTED,
                "executable": MODULE.SUPPORTED,
            },
            "managed_base": {
                "node_state": MODULE.DIRECTORY,
                "writable": MODULE.SUPPORTED,
                "executable": MODULE.SUPPORTED,
            },
            "transactions": [
                {
                    "transaction_id": "fs-1-1",
                    "scratch": {"node_state": node_state},
                    "managed_root": {"node_state": MODULE.ABSENT},
                }
            ],
        }
        report["observation_complete"] = MODULE._observation_complete(report)
        report["cleanup_admissible"] = MODULE._cleanup_admissible(report)
        return report

    @mock.patch.object(MODULE, "_remove_exact")
    @mock.patch.object(MODULE, "observe")
    @mock.patch.object(MODULE._PREFLIGHT, "prove_registered_device")
    @mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True})
    def test_post_cleanup_observation_failure_is_quarantined_after_mutation(
        self,
        _tools,
        _prove_device,
        observe,
        remove_exact,
    ) -> None:
        pre = self._observation(MODULE.DIRECTORY)
        observe.side_effect = [
            pre,
            MODULE._PREFLIGHT.PreflightFailure("registered device became unreachable"),
        ]

        report = MODULE.cleanup("a" * 40, ["fs-1-1"])

        self.assertEqual(report["state"], "QUARANTINED")
        self.assertFalse(report["accepted"])
        self.assertTrue(report["cleanup_attempted"])
        self.assertTrue(report["phone_mutation_performed"])
        self.assertFalse(report["cleanup_verified"])
        self.assertEqual(report["failure_stage"], "cleanup_execution")
        self.assertEqual(report["failure_substep"], "post_cleanup_observation")
        self.assertIsNone(report["post_cleanup_observation"])
        remove_exact.assert_called_once()

    @mock.patch.object(MODULE, "_remove_exact")
    @mock.patch.object(MODULE, "observe")
    @mock.patch.object(MODULE._PREFLIGHT, "prove_registered_device")
    @mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True})
    def test_already_clean_uses_proven_prestate_without_second_device_dependency(
        self,
        _tools,
        prove_device,
        observe,
        remove_exact,
    ) -> None:
        pre = self._observation(MODULE.ABSENT)
        observe.return_value = pre

        report = MODULE.cleanup("b" * 40, ["fs-1-1"])

        self.assertEqual(report["state"], "ALREADY_CLEAN")
        self.assertTrue(report["accepted"])
        self.assertTrue(report["cleanup_verified"])
        self.assertFalse(report["cleanup_attempted"])
        self.assertFalse(report["phone_mutation_performed"])
        self.assertIs(report["post_cleanup_observation"], pre)
        observe.assert_called_once()
        self.assertEqual(prove_device.call_count, 1)
        remove_exact.assert_not_called()


if __name__ == "__main__":
    unittest.main()
