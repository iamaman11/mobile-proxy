from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "physical_state_evidence.py"
SPEC = importlib.util.spec_from_file_location("physical_state_evidence_tested", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


Record = MODULE.OrderedPhysicalEvidence


class PhysicalStateEvidenceTests(unittest.TestCase):
    def raw_fact(
        self,
        *,
        generation: str = "fs-generation-17",
        source_ref: str = "c3df0d742398ea0a6dc04e1c409d153bd531566f",
        persisted: bool = False,
    ) -> dict[str, object]:
        return {
            "subject": "filesystem-quarantine",
            "predicate": "transactions_absent",
            "value": True,
            "target": "android-production",
            "observation_ref": "run-33710000000",
            "source_ref": source_ref,
            "dependencies": [
                {
                    "scope": "target/android-production",
                    "identity": "tb-hmac-sha256:opaque-target-v1",
                },
                {
                    "scope": "observer/filesystem-quarantine",
                    "identity": "android.filesystem-quarantine-observer.v2",
                },
                {"scope": "domain/filesystem", "identity": generation},
            ],
            "authority": "CONTROL",
            "persisted": persisted,
        }

    def intent(
        self,
        transaction_id: str,
        *,
        source_ref: str = "c3df0d742398ea0a6dc04e1c409d153bd531566f",
    ) -> dict[str, object]:
        return MODULE.build_dispatch_intent_evidence(
            source_ref=source_ref,
            operation_id="android.filesystem-certification.v1",
            transaction_id=transaction_id,
            step_id="scratch_roundtrip",
            affected_domain_generations={"domain/filesystem": transaction_id},
        )

    def test_promotes_producer_fact_only_at_outer_persistence_boundary(self) -> None:
        evidence = MODULE.promote_observed_fact(self.raw_fact())
        self.assertEqual(evidence["evidence_type"], "OBSERVED_FACT")
        self.assertTrue(evidence["observed_fact"]["persisted"])
        self.assertEqual(
            evidence["observed_fact"]["dependencies"][2],
            {"scope": "domain/filesystem", "identity": "fs-generation-17"},
        )

    def test_rejects_producer_that_claims_outer_persistence(self) -> None:
        with self.assertRaises(MODULE.PhysicalEvidenceFailure):
            MODULE.promote_observed_fact(self.raw_fact(persisted=True))

    def test_rejects_duplicate_fact_dependency_scope(self) -> None:
        raw = self.raw_fact()
        raw["dependencies"] = list(raw["dependencies"]) + [
            {"scope": "domain/filesystem", "identity": "other"}
        ]
        with self.assertRaises(MODULE.PhysicalEvidenceFailure):
            MODULE.promote_observed_fact(raw)

    def test_dispatch_generation_must_equal_transaction_identity(self) -> None:
        with self.assertRaises(MODULE.PhysicalEvidenceFailure):
            MODULE.build_dispatch_intent_evidence(
                source_ref="source-ref",
                operation_id="android.filesystem-certification.v1",
                transaction_id="fs-1-1",
                step_id="scratch_roundtrip",
                affected_domain_generations={"domain/filesystem": "different"},
            )

    def test_no_intent_uses_explicit_bootstrap_generation(self) -> None:
        resolved = MODULE.resolve_domain_generation("filesystem", ())
        self.assertEqual(resolved.scope, "domain/filesystem")
        self.assertEqual(resolved.identity, "bootstrap:filesystem:v1")
        self.assertEqual(resolved.state, MODULE.GENERATION_BOOTSTRAP)
        self.assertIsNone(resolved.transaction_id)

    def test_latest_intent_owns_generation_and_is_unknown_until_observed(self) -> None:
        records = (
            Record(10, self.intent("fs-10-1")),
            Record(20, self.intent("fs-20-1")),
        )
        resolved = MODULE.resolve_domain_generation("filesystem", records)
        self.assertEqual(resolved.identity, "fs-20-1")
        self.assertEqual(resolved.transaction_id, "fs-20-1")
        self.assertEqual(
            resolved.state,
            MODULE.GENERATION_UNKNOWN_EXECUTION_OUTCOME,
        )
        self.assertIn("blind_retry=FORBIDDEN", resolved.blocking_predicates)

    def test_observation_before_latest_intent_does_not_resolve_it(self) -> None:
        records = (
            Record(10, MODULE.promote_observed_fact(self.raw_fact(generation="fs-20-1"))),
            Record(20, self.intent("fs-20-1")),
        )
        resolved = MODULE.resolve_domain_generation("filesystem", records)
        self.assertEqual(
            resolved.state,
            MODULE.GENERATION_UNKNOWN_EXECUTION_OUTCOME,
        )

    def test_later_matching_domain_observation_resolves_latest_intent(self) -> None:
        records = (
            Record(20, self.intent("fs-20-1")),
            Record(30, MODULE.promote_observed_fact(self.raw_fact(generation="fs-20-1"))),
        )
        resolved = MODULE.resolve_domain_generation("filesystem", records)
        self.assertEqual(resolved.identity, "fs-20-1")
        self.assertEqual(resolved.state, MODULE.GENERATION_OBSERVED)
        self.assertEqual(resolved.blocking_predicates, ())

    def test_unrelated_git_source_change_does_not_change_physical_generation(self) -> None:
        records = (
            Record(20, self.intent("fs-20-1", source_ref="a" * 40)),
            Record(
                30,
                MODULE.promote_observed_fact(
                    self.raw_fact(generation="fs-20-1", source_ref="b" * 40)
                ),
            ),
        )
        resolved = MODULE.resolve_domain_generation("filesystem", records)
        self.assertEqual(resolved.identity, "fs-20-1")
        self.assertEqual(resolved.state, MODULE.GENERATION_OBSERVED)

    def test_other_domain_observation_does_not_resolve_filesystem(self) -> None:
        raw = self.raw_fact(generation="fs-20-1")
        raw["dependencies"] = [
            dependency
            for dependency in raw["dependencies"]
            if dependency["scope"] != "domain/filesystem"
        ] + [{"scope": "domain/runtime", "identity": "fs-20-1"}]
        records = (
            Record(20, self.intent("fs-20-1")),
            Record(30, MODULE.promote_observed_fact(raw)),
        )
        resolved = MODULE.resolve_domain_generation("filesystem", records)
        self.assertEqual(
            resolved.state,
            MODULE.GENERATION_UNKNOWN_EXECUTION_OUTCOME,
        )

    def test_duplicate_transport_sequence_is_conflict(self) -> None:
        records = (
            Record(20, self.intent("fs-20-1")),
            Record(20, self.intent("fs-20-2")),
        )
        resolved = MODULE.resolve_domain_generation("filesystem", records)
        self.assertEqual(resolved.state, MODULE.GENERATION_CONFLICT)

    def test_malformed_dispatch_intent_fails_closed(self) -> None:
        intent = self.intent("fs-20-1")
        intent["dispatch_intent"]["blind_retry_allowed"] = True
        resolved = MODULE.resolve_domain_generation(
            "filesystem",
            (Record(20, intent),),
        )
        self.assertEqual(resolved.state, MODULE.GENERATION_INVALID)
        self.assertTrue(resolved.blocking_predicates)

    def test_latest_intent_in_other_domain_does_not_change_filesystem(self) -> None:
        runtime = MODULE.build_dispatch_intent_evidence(
            source_ref="source-ref",
            operation_id="runtime.test.v1",
            transaction_id="runtime-30-1",
            step_id="runtime_write",
            affected_domain_generations={"domain/runtime": "runtime-30-1"},
        )
        records = (
            Record(20, self.intent("fs-20-1")),
            Record(30, runtime),
            Record(40, MODULE.promote_observed_fact(self.raw_fact(generation="fs-20-1"))),
        )
        resolved = MODULE.resolve_domain_generation("filesystem", records)
        self.assertEqual(resolved.identity, "fs-20-1")
        self.assertEqual(resolved.state, MODULE.GENERATION_OBSERVED)


if __name__ == "__main__":
    unittest.main()
