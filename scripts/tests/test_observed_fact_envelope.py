from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = SCRIPT_DIR / "observed_fact_envelope.py"
SPEC = importlib.util.spec_from_file_location("observed_fact_envelope_tests", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
CONTROL = MODULE._CONTROL


class ObservedFactEnvelopeTests(unittest.TestCase):
    def dependencies(self):
        return (
            ("target/android-production", "target-binding-v1"),
            ("observer/filesystem-quarantine", "observer-v2"),
            ("domain/filesystem", "fs-generation-17"),
        )

    def envelope(self):
        return MODULE.make_envelope(
            subject="filesystem",
            predicate="quarantine_transactions_absent",
            value=True,
            target="android-production",
            observation_ref="run:33692515684",
            source_ref="a" * 40,
            dependencies=self.dependencies(),
            persisted=False,
        )

    def test_adapter_envelope_is_unpersisted_and_cannot_authorize_reuse(self):
        payload = self.envelope()
        fact = MODULE.to_observed_fact(payload)
        context = {item.scope: item.identity for item in fact.dependencies}

        validity = CONTROL.classify_observed_fact(fact, context)

        self.assertEqual(validity.state, CONTROL.FACT_UNPERSISTED)
        self.assertFalse(payload["persisted"])

    def test_independent_persistence_transition_makes_same_dependencies_reusable(self):
        payload = MODULE.mark_persisted(
            self.envelope(),
            observation_ref="artifact:run-33692515684:quarantine-observation",
        )
        fact = MODULE.to_observed_fact(payload)
        context = {item.scope: item.identity for item in fact.dependencies}

        validity = CONTROL.classify_observed_fact(fact, context)

        self.assertEqual(validity.state, CONTROL.FACT_VALID)
        self.assertTrue(payload["persisted"])

    def test_unrelated_source_change_does_not_stale_source_independent_fact(self):
        payload = MODULE.mark_persisted(
            self.envelope(),
            observation_ref="artifact:durable",
        )
        fact = MODULE.to_observed_fact(payload)
        context = {item.scope: item.identity for item in fact.dependencies}
        context["source/canonical"] = "b" * 40

        validity = CONTROL.classify_observed_fact(fact, context)

        self.assertEqual(validity.state, CONTROL.FACT_VALID)

    def test_affected_domain_generation_change_stales_fact(self):
        payload = MODULE.mark_persisted(
            self.envelope(),
            observation_ref="artifact:durable",
        )
        fact = MODULE.to_observed_fact(payload)
        context = {item.scope: item.identity for item in fact.dependencies}
        context["domain/filesystem"] = "tx-new"

        validity = CONTROL.classify_observed_fact(fact, context)

        self.assertEqual(validity.state, CONTROL.FACT_STALE)
        self.assertIn("domain/filesystem", validity.reasons[0])

    def test_bounded_identity_never_records_raw_identifier(self):
        raw = "registered-production-device-secretish-id"
        identity = MODULE.bounded_identity("target/android-production", raw)

        self.assertTrue(identity.startswith("sha256:"))
        self.assertNotIn(raw, identity)

    def test_duplicate_dependency_scope_fails_closed_at_envelope_boundary(self):
        with self.assertRaises(MODULE.ObservedFactEnvelopeError):
            MODULE.make_envelope(
                subject="filesystem",
                predicate="x",
                value=True,
                target="android-production",
                observation_ref="run:1",
                source_ref="a" * 40,
                dependencies=(
                    ("domain/filesystem", "one"),
                    ("domain/filesystem", "two"),
                ),
                persisted=False,
            )


if __name__ == "__main__":
    unittest.main()
