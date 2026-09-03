from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1]


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CERT = load("filesystem_cert_envelope_tests", "run_android_filesystem_certification.py")
QUARANTINE = load(
    "filesystem_quarantine_envelope_tests",
    "run_android_filesystem_quarantine_recovery.py",
)


class ObserverDependencyEnvelopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = mock.patch.dict(
            os.environ,
            {"ANDROID_PRODUCTION_SERIAL": "registered-device"},
            clear=False,
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def _inventory(self):
        return {
            "read_only_capabilities_proven": True,
            "capabilities": {
                "adb_push_pull_roundtrip": "UNKNOWN",
                "managed_root_write": "UNKNOWN",
                "managed_atomic_replace": "UNKNOWN",
            },
        }

    def test_filesystem_certification_emits_domain_bound_unpersisted_facts(self) -> None:
        with (
            mock.patch.object(CERT, "_probe_comparator", return_value=CERT.SUPPORTED),
            mock.patch.object(CERT, "cleanup_paths", return_value=True),
            mock.patch.object(CERT, "run_managed_certification"),
            mock.patch.object(CERT, "run_scratch_certification"),
            mock.patch.object(CERT, "verify_prestate"),
            mock.patch.object(CERT._CAPABILITIES, "inventory", return_value=self._inventory()),
            mock.patch.object(CERT._PREFLIGHT, "require_tools", return_value={"adb": True}),
            mock.patch.object(CERT._PREFLIGHT, "prove_registered_device"),
        ):
            report = CERT.certify(
                "a" * 40,
                "tx-cert",
                filesystem_domain_generation="tx-cert",
                observation_ref="run:cert",
            )

        self.assertTrue(report["accepted"])
        self.assertTrue(report["fact_dependency_envelope_complete"])
        self.assertFalse(report["fact_reuse_eligible"])
        self.assertEqual(len(report["observed_facts"]), 2)
        for fact in report["observed_facts"]:
            self.assertFalse(fact["persisted"])
            deps = {item["scope"]: item["identity"] for item in fact["dependencies"]}
            self.assertEqual(deps["domain/filesystem"], "tx-cert")
            self.assertEqual(
                deps["observer/filesystem-certification"],
                CERT._FILESYSTEM_OBSERVER_ID,
            )
            self.assertNotIn("registered-device", str(fact))

    def test_quarantine_observer_emits_reusable_physical_fact_only_when_complete(self) -> None:
        base = {
            "node_state": QUARANTINE.DIRECTORY,
            "writable": QUARANTINE.SUPPORTED,
            "executable": QUARANTINE.SUPPORTED,
        }
        transaction = {
            "transaction_id": "old-tx",
            "scratch": {"node_state": QUARANTINE.ABSENT},
            "managed_root": {"node_state": QUARANTINE.ABSENT},
        }
        with (
            mock.patch.object(QUARANTINE._PREFLIGHT, "require_tools", return_value={"adb": True}),
            mock.patch.object(QUARANTINE._PREFLIGHT, "prove_registered_device"),
            mock.patch.object(QUARANTINE, "_scope_observation", side_effect=[base, base]),
            mock.patch.object(QUARANTINE, "_transaction_observation", return_value=transaction),
        ):
            report = QUARANTINE.observe(
                "b" * 40,
                ["old-tx"],
                filesystem_domain_generation="fs-generation-22",
                observation_ref="run:quarantine",
            )

        self.assertTrue(report["observation_complete"])
        self.assertTrue(report["cleanup_admissible"])
        self.assertEqual(len(report["observed_facts"]), 1)
        fact = report["observed_facts"][0]
        self.assertEqual(fact["predicate"], "quarantine_transactions_absent")
        self.assertTrue(fact["value"])
        deps = {item["scope"]: item["identity"] for item in fact["dependencies"]}
        self.assertEqual(deps["domain/filesystem"], "fs-generation-22")
        self.assertNotIn("source/canonical", deps)
        self.assertFalse(fact["persisted"])


if __name__ == "__main__":
    unittest.main()
