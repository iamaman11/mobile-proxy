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
    def _evidence(self, step_id: str, status: str, tx: str = "tx-fs", *, ref: str | None = None):
        return MODULE.PhaseEvidence(step_id, status, tx, ref or f"run:{step_id}:{status}")

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

    def test_contract_declares_causal_reuse_fresh_boundary_and_affected_domain(self) -> None:
        contract = MODULE.ANDROID_FILESYSTEM_CERTIFICATION

        self.assertEqual(contract.affected_domains, ("filesystem",))
        self.assertTrue(
            any(item.freshness == MODULE.CAUSAL_REUSE_ALLOWED for item in contract.reusable_facts)
        )
        self.assertEqual(len(contract.freshness_requirements), 1)
        boundary = contract.freshness_requirements[0]
        self.assertEqual(boundary.freshness, MODULE.SAME_TRANSACTION)
        self.assertIn("transaction/operation", boundary.required_scopes)
        self.assertFalse(contract.retryable)

    def test_dispatch_generation_transition_is_exact_transaction_identity(self) -> None:
        contract = MODULE.ANDROID_FILESYSTEM_CERTIFICATION
        self.assertEqual(
            MODULE.dispatch_generation_updates(contract, "tx-fs"),
            {"domain/filesystem": "tx-fs"},
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

    def test_dispatch_without_terminal_result_is_unknown_execution_outcome(self) -> None:
        contract = MODULE.ANDROID_FILESYSTEM_CERTIFICATION
        before = MODULE.expected_step_ids(contract)[:7]
        evidence = [self._evidence(step, MODULE.PASSED) for step in before]
        evidence.append(self._evidence("scratch_roundtrip", MODULE.DISPATCHED))

        state = MODULE.derive_operation_state(contract, evidence, transaction_id="tx-fs")

        self.assertEqual(state["state"], "UNKNOWN_EXECUTION_OUTCOME")
        self.assertEqual(state["current_step"], "scratch_roundtrip")
        self.assertEqual(state["next_step"], "recovery_cleanup_scratch")
        self.assertTrue(state["destructive_started"])
        self.assertTrue(state["recovery_required"])
        self.assertIn("blind_retry=FORBIDDEN", state["blocking_predicates"])

    def test_dispatch_marker_can_be_followed_by_terminal_result_without_conflict(self) -> None:
        contract = MODULE.ANDROID_FILESYSTEM_CERTIFICATION
        before = MODULE.expected_step_ids(contract)[:7]
        evidence = [self._evidence(step, MODULE.PASSED) for step in before]
        evidence.extend(
            (
                self._evidence("scratch_roundtrip", MODULE.DISPATCHED, ref="dispatch:tx-fs"),
                self._evidence("scratch_roundtrip", MODULE.PASSED, ref="result:tx-fs"),
            )
        )

        state = MODULE.derive_operation_state(contract, evidence, transaction_id="tx-fs")

        self.assertEqual(state["state"], "TRANSACTION_ACTIVE")
        self.assertEqual(state["next_step"], "scratch_atomic_replace")
        self.assertTrue(state["destructive_started"])

    def test_terminal_result_cannot_regress_back_to_dispatched(self) -> None:
        contract = MODULE.ANDROID_FILESYSTEM_CERTIFICATION
        before = MODULE.expected_step_ids(contract)[:7]
        evidence = [self._evidence(step, MODULE.PASSED) for step in before]
        evidence.extend(
            (
                self._evidence("scratch_roundtrip", MODULE.PASSED, ref="result:tx-fs"),
                self._evidence("scratch_roundtrip", MODULE.DISPATCHED, ref="dispatch:late"),
            )
        )

        state = MODULE.derive_operation_state(contract, evidence, transaction_id="tx-fs")

        self.assertEqual(state["state"], "CONFLICT")
        self.assertTrue(state["recovery_required"])

    def test_recovery_can_resolve_unknown_execution_outcome_without_fabricating_result(self) -> None:
        contract = MODULE.ANDROID_FILESYSTEM_CERTIFICATION
        before = MODULE.expected_step_ids(contract)[:7]
        evidence = [self._evidence(step, MODULE.PASSED) for step in before]
        evidence.append(self._evidence("scratch_roundtrip", MODULE.DISPATCHED))
        evidence.extend(
            self._evidence(step, MODULE.PASSED)
            for step in MODULE.recovery_step_ids(contract)
        )

        state = MODULE.derive_operation_state(contract, evidence, transaction_id="tx-fs")

        self.assertEqual(state["state"], "RECOVERED")
        self.assertEqual(state["current_step"], "scratch_roundtrip")
        self.assertFalse(state["recovery_required"])
        self.assertNotEqual(state["state"], "ACCEPTED")

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
            self._evidence("scratch_roundtrip", MODULE.DISPATCHED),
        ]

        state = MODULE.derive_operation_state(contract, evidence, transaction_id="tx-fs")

        self.assertEqual(state["state"], "INVALID_TRACE")
        self.assertTrue(state["recovery_required"])

    def test_quarantine_cleanup_is_a_real_filesystem_domain_transaction(self) -> None:
        contract = MODULE.ANDROID_FILESYSTEM_QUARANTINE_CLEANUP
        self.assertEqual(contract.affected_domains, ("filesystem",))
        self.assertFalse(contract.retryable)
        self.assertEqual(
            MODULE.dispatch_generation_updates(contract, "tx-cleanup"),
            {"domain/filesystem": "tx-cleanup"},
        )
        reusable = contract.reusable_facts[0]
        self.assertEqual(reusable.predicate, "quarantine_transactions_absent")
        self.assertIn("domain/filesystem", reusable.required_scopes)


if __name__ == "__main__":
    unittest.main()
