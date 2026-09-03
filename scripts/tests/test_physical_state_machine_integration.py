from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1]
ROOT = SCRIPT_DIR.parent


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


OP = load("operation_state_machine_physical_integration", SCRIPT_DIR / "operation_state_machine.py")
CONTROL = load("control_state_machine_physical_integration", SCRIPT_DIR / "control_state_machine.py")
PREFLIGHT = load("private_phone_preflight_physical_integration", SCRIPT_DIR / "run_private_phone_preflight.py")
QUARANTINE = load(
    "filesystem_quarantine_physical_integration",
    SCRIPT_DIR / "run_android_filesystem_quarantine_recovery.py",
)


TX = "fs-physical-foundation-1"


def passed(step_id: str):
    return OP.PhaseEvidence(step_id, OP.PASSED, TX, f"ev-{step_id}")


class PhysicalStateMachineIntegrationTests(unittest.TestCase):
    def _control_fact(self, envelope: dict[str, object], *, persisted: bool = True):
        dependencies = tuple(
            CONTROL.FactDependency(item["scope"], item["identity"])
            for item in envelope["dependencies"]
        )
        return CONTROL.ObservedFact(
            subject=envelope["subject"],
            predicate=envelope["predicate"],
            value=envelope["value"],
            target=envelope["target"],
            observation_ref=envelope["observation_ref"],
            source_ref=envelope["source_ref"],
            dependencies=dependencies,
            authority=envelope["authority"],
            persisted=persisted,
        )

    def test_filesystem_contract_declares_same_transaction_boundary_and_domain(self):
        contract = OP.ANDROID_FILESYSTEM_CERTIFICATION
        self.assertEqual(contract.affected_physical_domains, ("filesystem",))
        self.assertFalse(contract.retryable)

        requirements = {
            (item.subject, item.predicate): item
            for item in contract.fact_requirements
        }
        boundary = requirements[("phone", "registered_phone_access_proven")]
        self.assertEqual(boundary.freshness, OP.SAME_TRANSACTION)
        self.assertEqual(
            boundary.required_dependency_kinds,
            ("target", "observer", "transaction"),
        )

    def test_domain_generation_advances_to_exact_transaction_before_dispatch(self):
        updates = OP.affected_domain_generation_updates(
            OP.ANDROID_FILESYSTEM_CERTIFICATION,
            TX,
        )
        self.assertEqual(updates, {"domain/filesystem": TX})

    def test_dispatch_marker_is_unknown_outcome_and_never_blind_retry(self):
        contract = OP.ANDROID_FILESYSTEM_CERTIFICATION
        steps = OP.expected_step_ids(contract)
        first_destructive = next(
            step.step_id for step in contract.steps if step.destructive
        )
        destructive_index = steps.index(first_destructive)
        evidence = [passed(step) for step in steps[:destructive_index]]
        evidence.append(
            OP.PhaseEvidence(
                first_destructive,
                OP.DISPATCHED,
                TX,
                "durable-dispatch-intent",
            )
        )

        state = OP.derive_operation_state(contract, evidence, transaction_id=TX)

        self.assertEqual(state["state"], "UNKNOWN_EXECUTION_OUTCOME")
        self.assertTrue(state["destructive_started"])
        self.assertTrue(state["recovery_required"])
        self.assertEqual(state["next_step"], "recovery_cleanup_scratch")
        self.assertNotEqual(state["next_step"], first_destructive)
        self.assertIn("blind_retry=FORBIDDEN", state["blocking_predicates"])

    def test_dispatch_without_boundary_is_invalid_trace(self):
        contract = OP.ANDROID_FILESYSTEM_CERTIFICATION
        first_destructive = next(
            step.step_id for step in contract.steps if step.destructive
        )
        state = OP.derive_operation_state(
            contract,
            [
                OP.PhaseEvidence(
                    first_destructive,
                    OP.DISPATCHED,
                    TX,
                    "illegal-dispatch",
                )
            ],
            transaction_id=TX,
        )
        self.assertEqual(state["state"], "INVALID_TRACE")
        self.assertEqual(state["failure_stage"], "MUTATION_BOUNDARY")

    def test_recovery_can_resolve_unknown_dispatch_without_retry(self):
        contract = OP.ANDROID_FILESYSTEM_CERTIFICATION
        steps = OP.expected_step_ids(contract)
        first_destructive = next(
            step.step_id for step in contract.steps if step.destructive
        )
        destructive_index = steps.index(first_destructive)
        evidence = [passed(step) for step in steps[:destructive_index]]
        evidence.append(
            OP.PhaseEvidence(
                first_destructive,
                OP.DISPATCHED,
                TX,
                "durable-dispatch-intent",
            )
        )
        evidence.extend(passed(step) for step in OP.recovery_step_ids(contract))

        state = OP.derive_operation_state(contract, evidence, transaction_id=TX)

        self.assertEqual(state["state"], "RECOVERED")
        self.assertFalse(state["recovery_required"])
        self.assertIsNone(state["next_step"])

    def test_preflight_emits_bounded_same_transaction_fact_envelope(self):
        with mock.patch.dict(
            os.environ,
            {"ANDROID_PRODUCTION_SERIAL": "raw-device-serial"},
            clear=False,
        ):
            envelope = PREFLIGHT.build_phone_access_fact_envelope(
                "a" * 40,
                target_binding_id="target-binding-generation-7",
                session_id="adb-session-9",
                observation_ref="private-run-123",
                transaction_id=TX,
            )

        text = json.dumps(envelope, sort_keys=True)
        self.assertNotIn("raw-device-serial", text)
        self.assertFalse(envelope["persisted"])
        dependencies = {
            item["scope"]: item["identity"]
            for item in envelope["dependencies"]
        }
        self.assertEqual(
            dependencies["target/android-production"],
            "target-binding-generation-7",
        )
        self.assertEqual(
            dependencies["observer/phone-access"],
            "android.phone-access-observer.v2",
        )
        self.assertEqual(dependencies[f"transaction/{TX}"], TX)

    def test_raw_device_identifier_cannot_be_used_as_dependency_identity(self):
        with mock.patch.dict(
            os.environ,
            {"ANDROID_PRODUCTION_SERIAL": "raw-device-serial"},
            clear=False,
        ):
            with self.assertRaisesRegex(
                PREFLIGHT.PreflightFailure,
                "raw device identifier",
            ):
                PREFLIGHT.build_phone_access_fact_envelope(
                    "a" * 40,
                    target_binding_id="raw-device-serial",
                    session_id="adb-session-9",
                    observation_ref="private-run-123",
                    transaction_id=TX,
                )

    def test_quarantine_envelope_is_causal_and_source_independent(self):
        report = {
            "observation_complete": True,
            "cleanup_admissible": True,
            "transactions": [
                {
                    "transaction_id": "fs-old-1",
                    "scratch": {"node_state": QUARANTINE.ABSENT},
                    "managed_root": {"node_state": QUARANTINE.ABSENT},
                }
            ],
        }
        with mock.patch.dict(
            os.environ,
            {"ANDROID_PRODUCTION_SERIAL": "raw-device-serial"},
            clear=False,
        ):
            envelopes = QUARANTINE.build_quarantine_fact_envelopes(
                "a" * 40,
                ["fs-old-1"],
                report,
                target_binding_id="target-binding-generation-7",
                filesystem_generation="filesystem-generation-12",
                observation_ref="private-run-456",
            )

        absence = next(
            item for item in envelopes
            if item["predicate"] == "transactions_absent"
        )
        fact = self._control_fact(absence, persisted=True)
        context = {
            item["scope"]: item["identity"]
            for item in absence["dependencies"]
        }
        context["source/canonical"] = "b" * 40

        valid = CONTROL.classify_observed_fact(fact, context)
        self.assertEqual(valid.state, CONTROL.FACT_VALID)

        context.update(
            OP.affected_domain_generation_updates(
                OP.ANDROID_FILESYSTEM_CERTIFICATION,
                TX,
            )
        )
        stale = CONTROL.classify_observed_fact(fact, context)
        self.assertEqual(stale.state, CONTROL.FACT_STALE)
        self.assertTrue(
            any("domain/filesystem" in reason for reason in stale.reasons)
        )

    def test_new_physical_evidence_schema_covers_fact_and_dispatch_contracts(self):
        physical = json.loads(
            (ROOT / "docs" / "physical-state-evidence-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        operation = json.loads(
            (ROOT / "docs" / "operation-state-evidence-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )

        evidence_types = physical["properties"]["evidence_type"]["enum"]
        self.assertEqual(
            set(evidence_types),
            {"OBSERVED_FACT", "MUTATION_DISPATCH_INTENT"},
        )
        self.assertIn("dependencies", physical["$defs"]["observedFact"]["required"])
        dispatch = physical["$defs"]["dispatchIntent"]["properties"]
        self.assertEqual(dispatch["status"]["const"], "DISPATCHED")
        self.assertFalse(dispatch["blind_retry_allowed"]["const"])
        self.assertTrue(dispatch["persistence_precedes_dispatch"]["const"])

        statuses = operation["$defs"]["phaseEvidence"]["properties"]["status"]["enum"]
        states = operation["$defs"]["derived"]["properties"]["state"]["enum"]
        operations = operation["properties"]["operation_id"]["enum"]
        self.assertIn("DISPATCHED", statuses)
        self.assertIn("UNKNOWN_EXECUTION_OUTCOME", states)
        self.assertIn("android.filesystem-certification.v1", operations)


if __name__ == "__main__":
    unittest.main()
