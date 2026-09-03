from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "control_state_machine.py"
SPEC = importlib.util.spec_from_file_location("control_state_machine_fact_validity", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


D = MODULE.FactDependency
OF = MODULE.ObservedFact


class CausalFactValidityTests(unittest.TestCase):
    def filesystem_fact(self, *, persisted: bool = True, authority: str = "CONTROL") -> object:
        return OF(
            subject="phone",
            predicate="quarantine_path_absent",
            value=True,
            target="android-production",
            observation_ref="run-33692515684",
            source_ref="cb949904edd562ff021d71e42e84f6df4bb1bfa0",
            dependencies=(
                D("target/android-production", "target-binding-v1"),
                D("observer/filesystem-quarantine", "observer-v1"),
                D("domain/filesystem", "fs-generation-17"),
            ),
            authority=authority,
            persisted=persisted,
        )

    def filesystem_context(self) -> dict[str, str]:
        return {
            "target/android-production": "target-binding-v1",
            "observer/filesystem-quarantine": "observer-v1",
            "domain/filesystem": "fs-generation-17",
            "source/canonical": "0f2b32969ab6273c557993d4ac4d770148f30e09",
        }

    def test_unrelated_source_advance_does_not_stale_source_independent_fact(self) -> None:
        fact = self.filesystem_fact()
        result = MODULE.classify_observed_fact(fact, self.filesystem_context())

        self.assertEqual(result.state, MODULE.FACT_VALID)
        self.assertEqual(result.reasons, ())

    def test_source_bound_fact_stales_when_source_identity_changes(self) -> None:
        base = self.filesystem_fact()
        fact = OF(
            **{
                **base._asdict(),
                "dependencies": base.dependencies
                + (D("source/canonical", "cb949904edd562ff021d71e42e84f6df4bb1bfa0"),),
            }
        )

        result = MODULE.classify_observed_fact(fact, self.filesystem_context())

        self.assertEqual(result.state, MODULE.FACT_STALE)
        self.assertTrue(any("source/canonical" in reason for reason in result.reasons))

    def test_domain_mutation_stales_only_domain_dependent_fact(self) -> None:
        context = self.filesystem_context()
        context["domain/filesystem"] = "tx-new-filesystem-mutation"

        result = MODULE.classify_observed_fact(self.filesystem_fact(), context)

        self.assertEqual(result.state, MODULE.FACT_STALE)
        self.assertEqual(len(result.reasons), 1)
        self.assertIn("domain/filesystem", result.reasons[0])

    def test_target_binding_change_stales_target_fact(self) -> None:
        context = self.filesystem_context()
        context["target/android-production"] = "target-binding-v2"

        result = MODULE.classify_observed_fact(self.filesystem_fact(), context)

        self.assertEqual(result.state, MODULE.FACT_STALE)
        self.assertIn("target/android-production", result.reasons[0])

    def test_observer_semantic_version_change_stales_only_dependent_fact(self) -> None:
        context = self.filesystem_context()
        context["observer/filesystem-quarantine"] = "observer-v2"

        result = MODULE.classify_observed_fact(self.filesystem_fact(), context)

        self.assertEqual(result.state, MODULE.FACT_STALE)
        self.assertIn("observer/filesystem-quarantine", result.reasons[0])

    def test_missing_dependency_context_is_unknown_not_guessed(self) -> None:
        context = self.filesystem_context()
        del context["domain/filesystem"]

        result = MODULE.classify_observed_fact(self.filesystem_fact(), context)

        self.assertEqual(result.state, MODULE.FACT_UNKNOWN)
        self.assertEqual(result.reasons, ("missing_current_context=domain/filesystem",))

    def test_unpersisted_observation_cannot_satisfy_durable_guard(self) -> None:
        result = MODULE.classify_observed_fact(
            self.filesystem_fact(persisted=False),
            self.filesystem_context(),
        )

        self.assertEqual(result.state, MODULE.FACT_UNPERSISTED)
        self.assertEqual(result.reasons, ("evidence_persisted=false",))

    def test_diagnostic_observation_cannot_authorize_control_reuse(self) -> None:
        result = MODULE.classify_observed_fact(
            self.filesystem_fact(authority="DIAGNOSTIC"),
            self.filesystem_context(),
        )

        self.assertEqual(result.state, MODULE.FACT_UNUSABLE)

    def test_required_dependency_missing_from_fact_is_invalid(self) -> None:
        result = MODULE.classify_observed_fact(
            self.filesystem_fact(),
            self.filesystem_context(),
            required_scopes=("boot/android-production",),
        )

        self.assertEqual(result.state, MODULE.FACT_INVALID)
        self.assertEqual(
            result.reasons,
            ("missing_required_dependency=boot/android-production",),
        )

    def test_duplicate_dependency_scope_is_invalid(self) -> None:
        base = self.filesystem_fact()
        fact = OF(
            **{
                **base._asdict(),
                "dependencies": base.dependencies
                + (D("domain/filesystem", "other-generation"),),
            }
        )

        result = MODULE.classify_observed_fact(fact, self.filesystem_context())

        self.assertEqual(result.state, MODULE.FACT_INVALID)
        self.assertIn("duplicate_dependency_scope=domain/filesystem", result.reasons)

    def test_projection_preserves_existing_reducer_surface(self) -> None:
        projected = MODULE.project_observed_fact(
            self.filesystem_fact(),
            self.filesystem_context(),
        )

        assert projected is not None
        self.assertEqual(projected.lifecycle, MODULE.CURRENT)
        self.assertEqual(projected.source_ref, "run-33692515684")
        self.assertEqual(projected.authority, MODULE.CONTROL)

    def test_stale_projection_is_explicit_and_unpersisted_fact_is_not_projected(self) -> None:
        changed = self.filesystem_context()
        changed["domain/filesystem"] = "new-generation"

        stale = MODULE.project_observed_fact(self.filesystem_fact(), changed)
        unpersisted = MODULE.project_observed_fact(
            self.filesystem_fact(persisted=False),
            self.filesystem_context(),
        )

        assert stale is not None
        self.assertEqual(stale.lifecycle, MODULE.STALE)
        self.assertIsNone(unpersisted)


if __name__ == "__main__":
    unittest.main()
