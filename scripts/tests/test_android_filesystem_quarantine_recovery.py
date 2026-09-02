from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "run_android_filesystem_quarantine_recovery.py"
SPEC = importlib.util.spec_from_file_location("android_filesystem_quarantine_recovery", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class AndroidFilesystemQuarantineRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = mock.patch.dict(
            os.environ,
            {"ANDROID_PRODUCTION_SERIAL": "registered-device"},
            clear=False,
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def _complete_observation(
        self,
        transaction_ids=("fs-1-1",),
        *,
        scratch_nodes=None,
        managed_nodes=None,
        scratch_base=MODULE.DIRECTORY,
        managed_base=MODULE.DIRECTORY,
    ):
        scratch_nodes = scratch_nodes or {
            transaction_id: MODULE.DIRECTORY for transaction_id in transaction_ids
        }
        managed_nodes = managed_nodes or {
            transaction_id: MODULE.ABSENT for transaction_id in transaction_ids
        }
        report = {
            "scratch_base": {
                "node_state": scratch_base,
                "writable": MODULE.SUPPORTED,
                "executable": MODULE.SUPPORTED,
            },
            "managed_base": {
                "node_state": managed_base,
                "writable": MODULE.SUPPORTED,
                "executable": MODULE.SUPPORTED,
            },
            "transactions": [
                {
                    "transaction_id": transaction_id,
                    "scratch": {"node_state": scratch_nodes[transaction_id]},
                    "managed_root": {"node_state": managed_nodes[transaction_id]},
                }
                for transaction_id in transaction_ids
            ],
        }
        report["observation_complete"] = MODULE._observation_complete(report)
        report["cleanup_admissible"] = MODULE._cleanup_admissible(report)
        return report

    def test_transaction_ids_are_validated_and_deduplicated(self) -> None:
        self.assertEqual(
            MODULE._require_transaction_ids(["fs-123-1", "fs-456-1"]),
            ("fs-123-1", "fs-456-1"),
        )
        for invalid in ("../escape", "a/b", "", "/absolute"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(MODULE.QuarantineRecoveryFailure):
                    MODULE._require_transaction_ids([invalid])
        with self.assertRaises(MODULE.QuarantineRecoveryFailure):
            MODULE._require_transaction_ids(["fs-1-1", "fs-1-1"])

    def test_cleanup_admission_rejects_symlink_other_and_unknown(self) -> None:
        for unsafe in (MODULE.SYMLINK, MODULE.OTHER, MODULE.UNKNOWN):
            with self.subTest(unsafe=unsafe):
                report = self._complete_observation(
                    scratch_nodes={"fs-1-1": unsafe},
                )
                self.assertFalse(MODULE._cleanup_admissible(report))

    @mock.patch.object(MODULE._PREFLIGHT, "prove_registered_device")
    @mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True})
    @mock.patch.object(MODULE, "_scope_observation")
    @mock.patch.object(MODULE, "_transaction_observation")
    def test_observe_is_read_only_and_records_no_raw_identity_or_contents(
        self,
        transaction_observation,
        scope_observation,
        _tools,
        prove_device,
    ) -> None:
        scope_observation.return_value = {
            "node_state": MODULE.DIRECTORY,
            "writable": MODULE.SUPPORTED,
            "executable": MODULE.SUPPORTED,
        }
        transaction_observation.side_effect = lambda _serial, transaction_id: {
            "transaction_id": transaction_id,
            "scratch": {"node_state": MODULE.DIRECTORY},
            "managed_root": {"node_state": MODULE.ABSENT},
        }

        report = MODULE.observe("a" * 40, ["fs-1-1", "fs-2-1"])

        self.assertTrue(report["observation_complete"])
        self.assertTrue(report["cleanup_admissible"])
        self.assertFalse(report["phone_mutation_performed"])
        self.assertFalse(report["raw_directory_contents_recorded"])
        self.assertFalse(report["raw_command_output_recorded"])
        self.assertFalse(report["raw_device_identifier_recorded"])
        self.assertNotIn("registered-device", str(report))
        self.assertEqual(prove_device.call_count, 1)

    @mock.patch.object(MODULE, "_remove_exact")
    @mock.patch.object(MODULE, "observe")
    @mock.patch.object(MODULE._PREFLIGHT, "prove_registered_device")
    @mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True})
    def test_cleanup_refuses_unsafe_observation_before_mutation(
        self,
        _tools,
        prove_device,
        observe,
        remove_exact,
    ) -> None:
        unsafe = self._complete_observation(
            scratch_nodes={"fs-1-1": MODULE.SYMLINK},
        )
        observe.return_value = unsafe

        report = MODULE.cleanup("b" * 40, ["fs-1-1"])

        self.assertEqual(report["state"], "REFUSED")
        self.assertFalse(report["accepted"])
        self.assertFalse(report["phone_mutation_performed"])
        self.assertFalse(report["cleanup_attempted"])
        self.assertEqual(report["failure_stage"], "cleanup_admission")
        self.assertEqual(prove_device.call_count, 1)
        remove_exact.assert_not_called()

    @mock.patch.object(MODULE, "_remove_exact")
    @mock.patch.object(MODULE, "observe")
    @mock.patch.object(MODULE._PREFLIGHT, "prove_registered_device")
    @mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True})
    def test_cleanup_removes_only_explicit_transaction_paths_and_proves_absence(
        self,
        _tools,
        prove_device,
        observe,
        remove_exact,
    ) -> None:
        transaction_ids = ("fs-10-1", "fs-20-1")
        pre = self._complete_observation(
            transaction_ids,
            scratch_nodes={
                "fs-10-1": MODULE.DIRECTORY,
                "fs-20-1": MODULE.ABSENT,
            },
            managed_nodes={
                "fs-10-1": MODULE.ABSENT,
                "fs-20-1": MODULE.DIRECTORY,
            },
        )
        post = self._complete_observation(
            transaction_ids,
            scratch_nodes={
                "fs-10-1": MODULE.ABSENT,
                "fs-20-1": MODULE.ABSENT,
            },
            managed_nodes={
                "fs-10-1": MODULE.ABSENT,
                "fs-20-1": MODULE.ABSENT,
            },
        )
        observe.side_effect = [pre, post]

        report = MODULE.cleanup("c" * 40, transaction_ids)

        self.assertEqual(report["state"], "CLEANED")
        self.assertTrue(report["accepted"])
        self.assertTrue(report["cleanup_attempted"])
        self.assertTrue(report["cleanup_verified"])
        self.assertTrue(report["phone_mutation_performed"])
        self.assertEqual(prove_device.call_count, 2)
        expected_scratch = MODULE._CERT.transaction_paths("fs-10-1")["scratch"]
        expected_managed = MODULE._CERT.transaction_paths("fs-20-1")["managed"]
        self.assertEqual(
            remove_exact.call_args_list,
            [
                mock.call("registered-device", expected_scratch, root=False),
                mock.call("registered-device", expected_managed, root=True),
            ],
        )

    @mock.patch.object(MODULE, "_remove_exact")
    @mock.patch.object(MODULE, "observe")
    @mock.patch.object(MODULE._PREFLIGHT, "prove_registered_device")
    @mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True})
    def test_cleanup_failure_remains_quarantined_with_exact_substep(
        self,
        _tools,
        _prove_device,
        observe,
        remove_exact,
    ) -> None:
        pre = self._complete_observation()
        post = self._complete_observation()
        observe.side_effect = [pre, post]
        remove_exact.side_effect = MODULE._CERT.CertificationFailure(
            "device command returned nonzero status"
        )

        report = MODULE.cleanup("d" * 40, ["fs-1-1"])

        self.assertEqual(report["state"], "QUARANTINED")
        self.assertFalse(report["accepted"])
        self.assertTrue(report["phone_mutation_performed"])
        self.assertTrue(report["cleanup_attempted"])
        self.assertFalse(report["cleanup_verified"])
        self.assertEqual(report["failure_stage"], "cleanup_execution")
        self.assertEqual(report["failure_substep"], "fs-1-1.scratch.remove")

    @mock.patch.object(MODULE, "_remove_exact")
    @mock.patch.object(MODULE, "observe")
    @mock.patch.object(MODULE._PREFLIGHT, "prove_registered_device")
    @mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True})
    def test_cleanup_of_already_absent_transactions_is_accepted_without_mutation(
        self,
        _tools,
        _prove_device,
        observe,
        remove_exact,
    ) -> None:
        clean = self._complete_observation(
            scratch_nodes={"fs-1-1": MODULE.ABSENT},
            managed_nodes={"fs-1-1": MODULE.ABSENT},
        )
        observe.side_effect = [clean, clean]

        report = MODULE.cleanup("e" * 40, ["fs-1-1"])

        self.assertEqual(report["state"], "ALREADY_CLEAN")
        self.assertTrue(report["accepted"])
        self.assertFalse(report["cleanup_attempted"])
        self.assertTrue(report["cleanup_verified"])
        self.assertFalse(report["phone_mutation_performed"])
        remove_exact.assert_not_called()


if __name__ == "__main__":
    unittest.main()
