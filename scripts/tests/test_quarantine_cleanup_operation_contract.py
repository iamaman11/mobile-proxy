from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
ROOT = SCRIPT_DIR.parent
MODULE_PATH = SCRIPT_DIR / "operation_state_machine.py"
SPEC = importlib.util.spec_from_file_location(
    "operation_state_machine_quarantine_cleanup_contract",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


TX = "tx-quarantine-cleanup-1"


def evidence(step_id: str, status: str, source_ref: str | None = None):
    return MODULE.PhaseEvidence(
        step_id,
        status,
        TX,
        source_ref or f"evidence:{step_id}:{status}",
    )


class QuarantineCleanupOperationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = MODULE.operation_contract(
            "android.filesystem-quarantine-cleanup.v1"
        )
        self.steps = MODULE.expected_step_ids(self.contract)

    def test_contract_is_registered_nonretryable_and_filesystem_scoped(self) -> None:
        self.assertIs(self.contract, MODULE.ANDROID_FILESYSTEM_QUARANTINE_CLEANUP)
        self.assertEqual(self.contract.affected_physical_domains, ("filesystem",))
        self.assertFalse(self.contract.retryable)
        self.assertFalse(self.contract.rollback_to_legacy_allowed)
        self.assertEqual(
            MODULE.affected_domain_generation_updates(self.contract, TX),
            {"domain/filesystem": TX},
        )

    def test_contract_requires_causal_admission_and_same_transaction_boundary(self) -> None:
        requirements = {
            (item.subject, item.predicate): item
            for item in self.contract.fact_requirements
        }

        admission = requirements[("filesystem-quarantine", "cleanup_admissible")]
        self.assertEqual(admission.freshness, MODULE.CAUSAL_REUSE_ALLOWED)
        self.assertEqual(
            admission.required_dependency_kinds,
            ("target", "observer", "domain", "transaction"),
        )

        boundary = requirements[("phone", "registered_phone_access_proven")]
        self.assertEqual(boundary.freshness, MODULE.SAME_TRANSACTION)
        self.assertEqual(
            boundary.required_dependency_kinds,
            ("target", "observer", "transaction"),
        )

    def test_boundary_precedes_the_single_destructive_cleanup_dispatch(self) -> None:
        self.assertEqual(
            self.steps,
            (
                "source_quality",
                "runner_assignment",
                "source_delivery",
                "quarantine_observation_admission",
                "mutation_lock",
                "phone_access_boundary",
                "cleanup_paths",
                "post_cleanup_observation",
                "accept",
            ),
        )
        destructive = [step for step in self.contract.steps if step.destructive]
        self.assertEqual([step.step_id for step in destructive], ["cleanup_paths"])
        self.assertLess(
            self.steps.index("phone_access_boundary"),
            self.steps.index("cleanup_paths"),
        )

    def test_lost_cleanup_result_routes_to_observation_recovery_not_retry(self) -> None:
        cleanup_index = self.steps.index("cleanup_paths")
        trace = [
            evidence(step_id, MODULE.PASSED)
            for step_id in self.steps[:cleanup_index]
        ]
        trace.append(
            evidence("cleanup_paths", MODULE.DISPATCHED, "durable-dispatch-intent")
        )

        state = MODULE.derive_operation_state(self.contract, trace, transaction_id=TX)

        self.assertEqual(state["state"], "UNKNOWN_EXECUTION_OUTCOME")
        self.assertTrue(state["destructive_started"])
        self.assertTrue(state["recovery_required"])
        self.assertEqual(state["current_step"], "cleanup_paths")
        self.assertEqual(state["next_step"], "recovery_post_cleanup_observation")
        self.assertNotEqual(state["next_step"], "cleanup_paths")
        self.assertIn("blind_retry=FORBIDDEN", state["blocking_predicates"])

    def test_post_ambiguity_observation_can_prove_recovered_state(self) -> None:
        cleanup_index = self.steps.index("cleanup_paths")
        trace = [
            evidence(step_id, MODULE.PASSED)
            for step_id in self.steps[:cleanup_index]
        ]
        trace.extend(
            (
                evidence("cleanup_paths", MODULE.DISPATCHED, "durable-dispatch-intent"),
                evidence(
                    "recovery_post_cleanup_observation",
                    MODULE.PASSED,
                    "bounded-postcondition-observation",
                ),
            )
        )

        state = MODULE.derive_operation_state(self.contract, trace, transaction_id=TX)

        self.assertEqual(state["state"], "RECOVERED")
        self.assertFalse(state["recovery_required"])
        self.assertIsNone(state["next_step"])
        self.assertNotEqual(state["state"], "ACCEPTED")

    def test_failed_post_ambiguity_observation_quarantines(self) -> None:
        cleanup_index = self.steps.index("cleanup_paths")
        trace = [
            evidence(step_id, MODULE.PASSED)
            for step_id in self.steps[:cleanup_index]
        ]
        trace.extend(
            (
                evidence("cleanup_paths", MODULE.DISPATCHED, "durable-dispatch-intent"),
                evidence(
                    "recovery_post_cleanup_observation",
                    MODULE.FAILED,
                    "bounded-postcondition-observation",
                ),
            )
        )

        state = MODULE.derive_operation_state(self.contract, trace, transaction_id=TX)

        self.assertEqual(state["state"], "QUARANTINED")
        self.assertTrue(state["recovery_required"])
        self.assertIsNone(state["next_step"])

    def test_complete_mutating_trace_requires_post_cleanup_observation(self) -> None:
        post_index = self.steps.index("post_cleanup_observation")
        trace = [
            evidence(step_id, MODULE.PASSED)
            for step_id in self.steps[:post_index]
        ]

        state = MODULE.derive_operation_state(self.contract, trace, transaction_id=TX)

        self.assertEqual(state["state"], "TRANSACTION_ACTIVE")
        self.assertEqual(state["next_step"], "post_cleanup_observation")
        self.assertNotEqual(state["state"], "ACCEPTED")

    def test_operation_evidence_schema_admits_cleanup_operation(self) -> None:
        schema = json.loads(
            (ROOT / "docs" / "operation-state-evidence-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        operations = schema["properties"]["operation_id"]["enum"]
        self.assertIn("android.filesystem-quarantine-cleanup.v1", operations)


if __name__ == "__main__":
    unittest.main()
