from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "operation_state_machine.py"
SPEC = importlib.util.spec_from_file_location(
    "operation_state_machine_quarantine_cleanup_contract", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

TX = "cleanup-tx-1"


def evidence(step_id: str, status: str) -> object:
    return MODULE.PhaseEvidence(step_id, status, TX, f"ev-{step_id}-{status.lower()}")


class QuarantineCleanupOperationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = MODULE.operation_contract(
            "android.filesystem-quarantine-cleanup.v1"
        )
        self.steps = MODULE.expected_step_ids(self.contract)

    def test_cleanup_is_canonical_non_retryable_filesystem_operation(self) -> None:
        self.assertEqual(self.contract.affected_physical_domains, ("filesystem",))
        self.assertFalse(self.contract.retryable)
        self.assertFalse(self.contract.rollback_to_legacy_allowed)
        self.assertEqual(
            MODULE.affected_domain_generation_updates(self.contract, TX),
            {"domain/filesystem": TX},
        )

    def test_cleanup_requires_causal_observation_and_fresh_boundary(self) -> None:
        requirements = {
            (item.subject, item.predicate): item
            for item in self.contract.fact_requirements
        }
        cleanup = requirements[("filesystem-quarantine", "cleanup_admissible")]
        self.assertEqual(cleanup.freshness, MODULE.CAUSAL_REUSE_ALLOWED)
        self.assertEqual(
            cleanup.required_dependency_kinds,
            ("target", "observer", "domain", "transaction"),
        )
        boundary = requirements[("phone", "registered_phone_access_proven")]
        self.assertEqual(boundary.freshness, MODULE.SAME_TRANSACTION)
        self.assertEqual(
            boundary.required_dependency_kinds,
            ("target", "observer", "transaction"),
        )

    def test_boundary_precedes_only_destructive_cleanup_dispatch(self) -> None:
        boundary_index = self.steps.index("phone_access_boundary")
        cleanup_index = self.steps.index("cleanup_exact_paths")
        destructive = [
            index for index, step in enumerate(self.contract.steps) if step.destructive
        ]
        self.assertEqual(destructive, [cleanup_index])
        self.assertLess(boundary_index, cleanup_index)

    def test_lost_cleanup_result_is_unknown_and_forbids_retry(self) -> None:
        cleanup_index = self.steps.index("cleanup_exact_paths")
        trace = [evidence(step, MODULE.PASSED) for step in self.steps[:cleanup_index]]
        trace.append(evidence("cleanup_exact_paths", MODULE.DISPATCHED))

        state = MODULE.derive_operation_state(
            self.contract, trace, transaction_id=TX
        )

        self.assertEqual(state["state"], "UNKNOWN_EXECUTION_OUTCOME")
        self.assertTrue(state["destructive_started"])
        self.assertTrue(state["recovery_required"])
        self.assertEqual(state["next_step"], "recovery_post_cleanup_observation")
        self.assertIn("blind_retry=FORBIDDEN", state["blocking_predicates"])
        self.assertNotEqual(state["next_step"], "cleanup_exact_paths")

    def test_unknown_cleanup_can_only_resolve_through_observation_recovery(self) -> None:
        cleanup_index = self.steps.index("cleanup_exact_paths")
        trace = [evidence(step, MODULE.PASSED) for step in self.steps[:cleanup_index]]
        trace.append(evidence("cleanup_exact_paths", MODULE.DISPATCHED))
        trace.extend(
            evidence(step, MODULE.PASSED)
            for step in MODULE.recovery_step_ids(self.contract)
        )

        state = MODULE.derive_operation_state(
            self.contract, trace, transaction_id=TX
        )

        self.assertEqual(state["state"], "RECOVERED")
        self.assertFalse(state["recovery_required"])
        self.assertNotEqual(state["state"], "ACCEPTED")

    def test_cleanup_dispatch_without_fresh_boundary_is_invalid(self) -> None:
        trace = [
            evidence("source_quality", MODULE.PASSED),
            evidence("runner_assignment", MODULE.PASSED),
            evidence("source_delivery", MODULE.PASSED),
            evidence("quarantine_observation", MODULE.PASSED),
            evidence("mutation_lock", MODULE.PASSED),
            evidence("cleanup_exact_paths", MODULE.DISPATCHED),
        ]
        state = MODULE.derive_operation_state(
            self.contract, trace, transaction_id=TX
        )
        self.assertEqual(state["state"], "INVALID_TRACE")
        self.assertEqual(state["failure_stage"], "MUTATION_BOUNDARY")

    def test_success_requires_independent_post_cleanup_observation(self) -> None:
        cleanup_index = self.steps.index("cleanup_exact_paths")
        trace = [evidence(step, MODULE.PASSED) for step in self.steps[:cleanup_index]]
        trace.extend(
            (
                evidence("cleanup_exact_paths", MODULE.DISPATCHED),
                evidence("cleanup_exact_paths", MODULE.PASSED),
            )
        )
        active = MODULE.derive_operation_state(
            self.contract, trace, transaction_id=TX
        )
        self.assertEqual(active["state"], "TRANSACTION_ACTIVE")
        self.assertEqual(active["next_step"], "post_cleanup_observation")

        trace.extend(
            (
                evidence("post_cleanup_observation", MODULE.PASSED),
                evidence("accept", MODULE.PASSED),
            )
        )
        accepted = MODULE.derive_operation_state(
            self.contract, trace, transaction_id=TX
        )
        self.assertEqual(accepted["state"], "ACCEPTED")

    def test_operation_evidence_schema_admits_cleanup(self) -> None:
        schema_path = (
            Path(__file__).resolve().parents[2]
            / "docs"
            / "operation-state-evidence-v1.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        operations = schema["properties"]["operation_id"]["enum"]
        self.assertIn("android.filesystem-quarantine-cleanup.v1", operations)


if __name__ == "__main__":
    unittest.main()
