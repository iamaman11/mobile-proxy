from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "operation_state_machine.py"
SPEC = importlib.util.spec_from_file_location("operation_state_machine_filesystem_tests", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FilesystemOperationContractTests(unittest.TestCase):
    def _evidence(self, step_id: str, status: str, tx: str = "tx-fs"):
        return MODULE.PhaseEvidence(step_id, status, tx, f"run:{step_id}")

    def test_contract_has_boundary_before_all_destructive_steps(self) -> None:
        contract = MODULE.operation_contract("android.filesystem-certification.v1")
        ids = MODULE.expected_step_ids(contract)
        boundary = ids.index("phone_access_boundary")
        destructive = [
            index for index, step in enumerate(contract.steps) if step.destructive
        ]
        self.assertTrue(destructive)
        self.assertTrue(all(index > boundary for index in destructive))
        self.assertEqual(
            ids,
            (
                "source_quality",
                "runner_assignment",
                "source_delivery",
                "phone_access_initial",
                "capability_inventory",
                "mutation_lock",
                "phone_access_boundary",
                "scratch_roundtrip",
                "scratch_atomic_replace",
                "managed_root_write",
                "managed_atomic_replace",
                "cleanup_verify",
                "accept",
            ),
        )

    def test_complete_filesystem_trace_is_accepted(self) -> None:
        contract = MODULE.ANDROID_FILESYSTEM_CERTIFICATION
        evidence = [self._evidence(step, MODULE.PASSED) for step in MODULE.expected_step_ids(contract)]

        state = MODULE.derive_operation_state(contract, evidence, transaction_id="tx-fs")

        self.assertEqual(state["state"], "ACCEPTED")
        self.assertTrue(state["destructive_started"])
        self.assertFalse(state["recovery_required"])

    def test_failed_first_mutation_requires_recovery(self) -> None:
        contract = MODULE.ANDROID_FILESYSTEM_CERTIFICATION
        before = MODULE.expected_step_ids(contract)[:7]
        evidence = [self._evidence(step, MODULE.PASSED) for step in before]
        evidence.append(self._evidence("scratch_roundtrip", MODULE.FAILED))

        state = MODULE.derive_operation_state(contract, evidence, transaction_id="tx-fs")

        self.assertEqual(state["state"], "RECOVERY_REQUIRED")
        self.assertEqual(state["current_step"], "scratch_roundtrip")
        self.assertEqual(state["next_step"], "recovery_cleanup_scratch")
        self.assertTrue(state["destructive_started"])
        self.assertTrue(state["recovery_required"])

    def test_recovered_failure_never_becomes_accepted(self) -> None:
        contract = MODULE.ANDROID_FILESYSTEM_CERTIFICATION
        before = MODULE.expected_step_ids(contract)[:7]
        evidence = [self._evidence(step, MODULE.PASSED) for step in before]
        evidence.append(self._evidence("scratch_roundtrip", MODULE.FAILED))
        evidence.extend(
            self._evidence(step, MODULE.PASSED)
            for step in MODULE.recovery_step_ids(contract)
        )

        state = MODULE.derive_operation_state(contract, evidence, transaction_id="tx-fs")

        self.assertEqual(state["state"], "RECOVERED")
        self.assertFalse(state["recovery_required"])
        self.assertNotEqual(state["state"], "ACCEPTED")

    def test_destructive_trace_without_boundary_is_invalid(self) -> None:
        contract = MODULE.ANDROID_FILESYSTEM_CERTIFICATION
        evidence = [
            self._evidence("source_quality", MODULE.PASSED),
            self._evidence("runner_assignment", MODULE.PASSED),
            self._evidence("source_delivery", MODULE.PASSED),
            self._evidence("phone_access_initial", MODULE.PASSED),
            self._evidence("capability_inventory", MODULE.PASSED),
            self._evidence("mutation_lock", MODULE.PASSED),
            self._evidence("scratch_roundtrip", MODULE.FAILED),
        ]

        state = MODULE.derive_operation_state(contract, evidence, transaction_id="tx-fs")

        self.assertEqual(state["state"], "INVALID_TRACE")
        self.assertTrue(state["recovery_required"])


if __name__ == "__main__":
    unittest.main()
