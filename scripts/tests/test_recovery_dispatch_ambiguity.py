from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "operation_state_machine.py"
SPEC = importlib.util.spec_from_file_location(
    "operation_state_machine_recovery_dispatch_ambiguity",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


TX = "tx-recovery-dispatch-ambiguity"


def evidence(step_id: str, status: str, source_ref: str | None = None):
    return MODULE.PhaseEvidence(
        step_id,
        status,
        TX,
        source_ref or f"evidence:{step_id}:{status}",
    )


class RecoveryDispatchAmbiguityTests(unittest.TestCase):
    def test_lost_recovery_result_forbids_retry_of_same_recovery_step(self) -> None:
        contract = MODULE.ANDROID_FILESYSTEM_CERTIFICATION
        steps = MODULE.expected_step_ids(contract)
        first_destructive = next(step.step_id for step in contract.steps if step.destructive)
        destructive_index = steps.index(first_destructive)

        trace = [
            evidence(step_id, MODULE.PASSED)
            for step_id in steps[:destructive_index]
        ]
        trace.append(evidence(first_destructive, MODULE.FAILED, "device-result"))
        recovery_step = MODULE.recovery_step_ids(contract)[0]
        trace.append(
            evidence(recovery_step, MODULE.DISPATCHED, "durable-recovery-dispatch-intent")
        )

        state = MODULE.derive_operation_state(contract, trace, transaction_id=TX)

        self.assertEqual(state["state"], "UNKNOWN_EXECUTION_OUTCOME")
        self.assertTrue(state["destructive_started"])
        self.assertTrue(state["recovery_required"])
        self.assertIsNone(state["next_step"])
        self.assertIn(
            f"execution_result_known={recovery_step}",
            state["blocking_predicates"],
        )
        self.assertIn("blind_retry=FORBIDDEN", state["blocking_predicates"])

    def test_terminal_recovery_failure_still_quarantines(self) -> None:
        contract = MODULE.ANDROID_FILESYSTEM_CERTIFICATION
        steps = MODULE.expected_step_ids(contract)
        first_destructive = next(step.step_id for step in contract.steps if step.destructive)
        destructive_index = steps.index(first_destructive)

        trace = [
            evidence(step_id, MODULE.PASSED)
            for step_id in steps[:destructive_index]
        ]
        trace.append(evidence(first_destructive, MODULE.FAILED, "device-result"))
        recovery_step = MODULE.recovery_step_ids(contract)[0]
        trace.extend(
            (
                evidence(recovery_step, MODULE.DISPATCHED, "durable-recovery-dispatch-intent"),
                evidence(recovery_step, MODULE.FAILED, "recovery-device-result"),
            )
        )

        state = MODULE.derive_operation_state(contract, trace, transaction_id=TX)

        self.assertEqual(state["state"], "QUARANTINED")
        self.assertTrue(state["recovery_required"])
        self.assertIsNone(state["next_step"])


if __name__ == "__main__":
    unittest.main()
