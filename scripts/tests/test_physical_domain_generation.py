from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GEN = load("physical_domain_generation_test", "physical_domain_generation.py")
CONTROL = load("control_state_machine_generation_integration", "control_state_machine.py")

Intent = GEN.MutationIntentEvidence
D = CONTROL.FactDependency
OF = CONTROL.ObservedFact


class PhysicalDomainGenerationTests(unittest.TestCase):
    def intent(
        self,
        transaction_id: str,
        run_id: int,
        *,
        attempt: int = 1,
        resolved: bool = True,
        result_state: str = "ACCEPTED",
    ):
        return Intent(
            operation_transaction_id=transaction_id,
            workflow_run_id=run_id,
            workflow_run_attempt=attempt,
            affected_domain_generations={"domain/filesystem": transaction_id},
            result_persisted=resolved,
            result_state=result_state if resolved else "",
            authority="CONTROL",
            lifecycle="CURRENT",
            persisted=True,
        )

    def test_bootstrap_generation_is_used_only_when_no_intent_exists(self) -> None:
        result = GEN.resolve_filesystem_generation(())

        self.assertEqual(result.state, GEN.RESOLVED)
        self.assertEqual(result.source, GEN.BOOTSTRAP)
        self.assertEqual(result.generation, GEN.FILESYSTEM_BOOTSTRAP_GENERATION)
        self.assertIsNone(result.latest_transaction_id)

    def test_latest_persisted_intent_owns_filesystem_generation(self) -> None:
        result = GEN.resolve_filesystem_generation(
            (
                self.intent("fs-100-1", 100),
                self.intent("fs-101-1", 101),
                self.intent("fs-101-2", 101, attempt=2),
            )
        )

        self.assertEqual(result.state, GEN.RESOLVED)
        self.assertEqual(result.source, GEN.MUTATION_INTENT)
        self.assertEqual(result.generation, "fs-101-2")
        self.assertEqual(result.latest_transaction_id, "fs-101-2")

    def test_any_unresolved_persisted_intent_blocks_reuse(self) -> None:
        result = GEN.resolve_filesystem_generation(
            (
                self.intent("fs-100-1", 100, resolved=False),
                self.intent("fs-101-1", 101, resolved=True),
            )
        )

        self.assertEqual(result.state, GEN.UNKNOWN_EXECUTION_OUTCOME)
        self.assertEqual(result.generation, "fs-101-1")
        self.assertEqual(result.latest_transaction_id, "fs-101-1")
        self.assertEqual(result.unresolved_transaction_ids, ("fs-100-1",))
        self.assertIn("unresolved_mutation_intent=fs-100-1", result.reasons)

    def test_generation_must_equal_exact_operation_transaction(self) -> None:
        bad = Intent(
            operation_transaction_id="fs-100-1",
            workflow_run_id=100,
            workflow_run_attempt=1,
            affected_domain_generations={"domain/filesystem": "different"},
            result_persisted=True,
            result_state="ACCEPTED",
            persisted=True,
        )

        result = GEN.resolve_filesystem_generation((bad,))

        self.assertEqual(result.state, GEN.INVALID_EVIDENCE)
        self.assertTrue(any("exact operation transaction" in item for item in result.reasons))

    def test_unpersisted_or_non_control_intent_is_fail_closed(self) -> None:
        unpersisted = Intent(
            operation_transaction_id="fs-100-1",
            workflow_run_id=100,
            workflow_run_attempt=1,
            affected_domain_generations={"domain/filesystem": "fs-100-1"},
            result_persisted=False,
            persisted=False,
        )
        diagnostic = Intent(
            operation_transaction_id="fs-101-1",
            workflow_run_id=101,
            workflow_run_attempt=1,
            affected_domain_generations={"domain/filesystem": "fs-101-1"},
            result_persisted=True,
            result_state="ACCEPTED",
            authority="DIAGNOSTIC",
            persisted=True,
        )

        self.assertEqual(
            GEN.resolve_filesystem_generation((unpersisted,)).state,
            GEN.INVALID_EVIDENCE,
        )
        self.assertEqual(
            GEN.resolve_filesystem_generation((diagnostic,)).state,
            GEN.INVALID_EVIDENCE,
        )

    def test_duplicate_run_attempt_is_conflict(self) -> None:
        result = GEN.resolve_filesystem_generation(
            (
                self.intent("fs-a", 100),
                self.intent("fs-b", 100),
            )
        )

        self.assertEqual(result.state, GEN.INVALID_EVIDENCE)
        self.assertTrue(any("one workflow run attempt" in item for item in result.reasons))

    def test_resolved_generation_allows_git_independent_fact_reuse(self) -> None:
        resolution = GEN.resolve_filesystem_generation((self.intent("fs-200-1", 200),))
        fact = OF(
            subject="filesystem-quarantine",
            predicate="transactions_absent",
            value=True,
            target="android-production",
            observation_ref="private-run:300:1:quarantine-observation",
            source_ref="old-public-sha",
            dependencies=(
                D("target/android-production", "target-binding-v1"),
                D(
                    "observer/filesystem-quarantine",
                    "android.filesystem-quarantine-observer.v2",
                ),
                D("domain/filesystem", resolution.generation),
                D("transaction/fs-200-1", "fs-200-1"),
            ),
            persisted=True,
        )
        context = {
            "target/android-production": "target-binding-v1",
            "observer/filesystem-quarantine": "android.filesystem-quarantine-observer.v2",
            "domain/filesystem": resolution.generation,
            "transaction/fs-200-1": "fs-200-1",
            "source/canonical": "new-unrelated-public-sha",
        }

        result = CONTROL.classify_observed_fact(fact, context)

        self.assertEqual(result.state, CONTROL.FACT_VALID)

    def test_target_observer_or_domain_change_invalidates_fact(self) -> None:
        resolution = GEN.resolve_filesystem_generation((self.intent("fs-200-1", 200),))
        fact = OF(
            subject="filesystem-quarantine",
            predicate="transactions_absent",
            value=True,
            target="android-production",
            observation_ref="private-run:300:1:quarantine-observation",
            source_ref="public-sha",
            dependencies=(
                D("target/android-production", "target-binding-v1"),
                D(
                    "observer/filesystem-quarantine",
                    "android.filesystem-quarantine-observer.v2",
                ),
                D("domain/filesystem", resolution.generation),
            ),
            persisted=True,
        )
        base = {
            "target/android-production": "target-binding-v1",
            "observer/filesystem-quarantine": "android.filesystem-quarantine-observer.v2",
            "domain/filesystem": resolution.generation,
        }

        for scope, changed in (
            ("target/android-production", "target-binding-v2"),
            (
                "observer/filesystem-quarantine",
                "android.filesystem-quarantine-observer.v3",
            ),
            ("domain/filesystem", "fs-201-1"),
        ):
            with self.subTest(scope=scope):
                context = dict(base)
                context[scope] = changed
                result = CONTROL.classify_observed_fact(fact, context)
                self.assertEqual(result.state, CONTROL.FACT_STALE)


if __name__ == "__main__":
    unittest.main()
