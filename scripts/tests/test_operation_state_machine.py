from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "operation_state_machine.py"
SPEC = importlib.util.spec_from_file_location("operation_state_machine", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


E = MODULE.PhaseEvidence
TX = "txn-1"


def passed(step_id: str, *, source_ref: str | None = None) -> object:
    return E(step_id, MODULE.PASSED, TX, source_ref or f"ev-{step_id}")


def failed(step_id: str, *, source_ref: str | None = None) -> object:
    return E(step_id, MODULE.FAILED, TX, source_ref or f"ev-{step_id}")


class OperationStateMachineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = MODULE.ANDROID_CURRENT_SOURCE_CLEAN_INSTALL
        self.steps = MODULE.expected_step_ids(self.contract)

    def test_contract_covers_full_android_lifecycle(self) -> None:
        self.assertEqual(
            self.steps,
            (
                "source_quality",
                "artifact_signed",
                "runner_assignment",
                "source_delivery",
                "phone_access_initial",
                "capability_inventory",
                "mutation_lock",
                "phone_access_boundary",
                "stop_owned_runtime",
                "remove_owned_runtime",
                "uninstall_legacy_apk",
                "install_new_apk",
                "verify_new_apk",
                "materialize_runtime",
                "verify_runtime",
                "start_runtime",
                "structural_health",
                "functional_probe",
                "accept",
            ),
        )
        self.assertFalse(self.contract.rollback_to_legacy_allowed)
        self.assertFalse(self.contract.retryable)

    def test_empty_trace_starts_at_source_quality(self) -> None:
        state = MODULE.derive_operation_state(self.contract, [], transaction_id=TX)
        self.assertEqual(state["state"], "PREPARING")
        self.assertEqual(state["next_step"], "source_quality")
        self.assertFalse(state["destructive_started"])

    def test_no_destructive_phase_before_same_transaction_boundary_reproof(self) -> None:
        evidence = [passed(step) for step in self.steps[:7]]
        state = MODULE.derive_operation_state(self.contract, evidence, transaction_id=TX)
        self.assertEqual(state["state"], "READY_FOR_BOUNDARY_REPROOF")
        self.assertEqual(state["next_step"], "phone_access_boundary")
        self.assertFalse(state["destructive_started"])

    def test_boundary_reproof_opens_mutation_but_does_not_claim_mutation(self) -> None:
        evidence = [passed(step) for step in self.steps[:8]]
        state = MODULE.derive_operation_state(self.contract, evidence, transaction_id=TX)
        self.assertEqual(state["state"], "READY_TO_MUTATE")
        self.assertEqual(state["next_step"], "stop_owned_runtime")
        self.assertFalse(state["destructive_started"])

    def test_uninstall_and_install_are_explicit_separate_phases(self) -> None:
        uninstall_index = self.steps.index("uninstall_legacy_apk")
        install_index = self.steps.index("install_new_apk")
        verify_index = self.steps.index("verify_new_apk")
        self.assertLess(uninstall_index, install_index)
        self.assertLess(install_index, verify_index)

    def test_mutation_command_success_never_implies_postcondition(self) -> None:
        verify_index = self.steps.index("verify_new_apk")
        evidence = [passed(step) for step in self.steps[:verify_index]]
        state = MODULE.derive_operation_state(self.contract, evidence, transaction_id=TX)
        self.assertEqual(state["state"], "TRANSACTION_ACTIVE")
        self.assertEqual(state["next_step"], "verify_new_apk")
        self.assertNotEqual(state["state"], "ACCEPTED")

    def test_runtime_materialization_and_runtime_verification_are_separate(self) -> None:
        materialize = self.steps.index("materialize_runtime")
        verify = self.steps.index("verify_runtime")
        self.assertLess(materialize, verify)

    def test_structural_health_never_substitutes_for_functional_probe(self) -> None:
        functional_index = self.steps.index("functional_probe")
        evidence = [passed(step) for step in self.steps[:functional_index]]
        state = MODULE.derive_operation_state(self.contract, evidence, transaction_id=TX)
        self.assertEqual(state["next_step"], "functional_probe")
        self.assertNotEqual(state["state"], "ACCEPTED")

    def test_full_success_is_accepted_only_after_explicit_acceptance(self) -> None:
        evidence = [passed(step) for step in self.steps]
        state = MODULE.derive_operation_state(self.contract, evidence, transaction_id=TX)
        self.assertEqual(state["state"], "ACCEPTED")
        self.assertEqual(state["blocking_predicates"], [])
        self.assertTrue(state["destructive_started"])

    def test_pre_boundary_failure_refuses_without_recovery_requirement(self) -> None:
        evidence = [passed("source_quality"), failed("artifact_signed")]
        state = MODULE.derive_operation_state(self.contract, evidence, transaction_id=TX)
        self.assertEqual(state["state"], "REFUSED")
        self.assertEqual(state["failure_stage"], "ARTIFACT")
        self.assertFalse(state["recovery_required"])

    def test_failed_first_destructive_command_enters_recovery(self) -> None:
        stop_index = self.steps.index("stop_owned_runtime")
        evidence = [passed(step) for step in self.steps[:stop_index]]
        evidence.append(failed("stop_owned_runtime"))
        state = MODULE.derive_operation_state(self.contract, evidence, transaction_id=TX)
        self.assertEqual(state["state"], "RECOVERY_REQUIRED")
        self.assertEqual(state["next_step"], "recovery_classify")
        self.assertEqual(state["failure_stage"], "MUTATION_EXECUTION")
        self.assertTrue(state["destructive_started"])
        self.assertTrue(state["recovery_required"])

    def test_post_boundary_failure_requires_recovery(self) -> None:
        install_index = self.steps.index("install_new_apk")
        evidence = [passed(step) for step in self.steps[:install_index]]
        evidence.append(failed("install_new_apk"))
        state = MODULE.derive_operation_state(self.contract, evidence, transaction_id=TX)
        self.assertEqual(state["state"], "RECOVERY_REQUIRED")
        self.assertEqual(state["next_step"], "recovery_classify")
        self.assertEqual(state["failure_stage"], "MUTATION_EXECUTION")
        self.assertTrue(state["destructive_started"])
        self.assertTrue(state["recovery_required"])

    def test_recovery_progress_is_explicit_and_forward_only(self) -> None:
        install_index = self.steps.index("install_new_apk")
        evidence = [passed(step) for step in self.steps[:install_index]]
        evidence.append(failed("install_new_apk"))
        evidence.append(passed("recovery_classify"))
        state = MODULE.derive_operation_state(self.contract, evidence, transaction_id=TX)
        self.assertEqual(state["state"], "RECOVERING")
        self.assertEqual(state["next_step"], "recovery_stop_owned_runtime")
        self.assertFalse(self.contract.rollback_to_legacy_allowed)

    def test_completed_recovery_yields_clean_recovered_state_not_accepted(self) -> None:
        install_index = self.steps.index("install_new_apk")
        evidence = [passed(step) for step in self.steps[:install_index]]
        evidence.append(failed("install_new_apk"))
        evidence.extend(passed(step) for step in MODULE.recovery_step_ids(self.contract))
        state = MODULE.derive_operation_state(self.contract, evidence, transaction_id=TX)
        self.assertEqual(state["state"], "RECOVERED")
        self.assertFalse(state["recovery_required"])
        self.assertNotEqual(state["state"], "ACCEPTED")

    def test_recovery_failure_quarantines(self) -> None:
        install_index = self.steps.index("install_new_apk")
        evidence = [passed(step) for step in self.steps[:install_index]]
        evidence.append(failed("install_new_apk"))
        evidence.append(failed("recovery_classify"))
        state = MODULE.derive_operation_state(self.contract, evidence, transaction_id=TX)
        self.assertEqual(state["state"], "QUARANTINED")
        self.assertTrue(state["recovery_required"])

    def test_out_of_order_success_is_invalid_trace(self) -> None:
        state = MODULE.derive_operation_state(
            self.contract,
            [passed("source_quality"), passed("install_new_apk")],
            transaction_id=TX,
        )
        self.assertEqual(state["state"], "INVALID_TRACE")
        self.assertEqual(state["current_step"], "install_new_apk")

    def test_conflicting_current_evidence_fails_closed(self) -> None:
        evidence = [
            passed("source_quality", source_ref="same-probe"),
            E("source_quality", MODULE.FAILED, TX, "same-probe"),
        ]
        state = MODULE.derive_operation_state(self.contract, evidence, transaction_id=TX)
        self.assertEqual(state["state"], "CONFLICT")
        self.assertTrue(state["recovery_required"])

    def test_diagnostic_or_stale_evidence_cannot_advance_control_transaction(self) -> None:
        evidence = [
            E("source_quality", MODULE.PASSED, TX, "diag", authority=MODULE.DIAGNOSTIC),
            E("artifact_signed", MODULE.PASSED, TX, "stale", lifecycle=MODULE.STALE),
        ]
        state = MODULE.derive_operation_state(self.contract, evidence, transaction_id=TX)
        self.assertEqual(state["state"], "PREPARING")
        self.assertEqual(state["next_step"], "source_quality")

    def test_evidence_from_another_transaction_cannot_advance_current_transaction(self) -> None:
        evidence = [E("source_quality", MODULE.PASSED, "other-txn", "other")]
        state = MODULE.derive_operation_state(self.contract, evidence, transaction_id=TX)
        self.assertEqual(state["next_step"], "source_quality")

    def test_phone_access_and_capability_certification_are_independent_operations(self) -> None:
        access = MODULE.ANDROID_PHONE_ACCESS_CERTIFICATION
        capability = MODULE.ANDROID_CAPABILITY_CERTIFICATION
        self.assertNotEqual(access.operation_id, capability.operation_id)
        self.assertEqual(MODULE.expected_step_ids(access)[-1], "phone_access")
        self.assertEqual(MODULE.expected_step_ids(capability)[-1], "capability_inventory")


if __name__ == "__main__":
    unittest.main()
