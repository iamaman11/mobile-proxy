from __future__ import annotations

from pathlib import Path
import sys
import unittest


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import atomic_physical_contracts as atomic
import operation_state_machine as operation


class FilesystemBootstrapContractTests(unittest.TestCase):
    def test_scratch_roundtrip_bootstraps_filesystem_mutation_capability(self) -> None:
        contract = atomic.ANDROID_FILESYSTEM_SCRATCH_ROUNDTRIP.contract
        requirements = tuple(
            (item.subject, item.predicate, item.freshness, item.required_dependency_kinds)
            for item in contract.fact_requirements
        )
        self.assertEqual(
            requirements,
            (
                (
                    "phone",
                    "registered_phone_access_proven",
                    operation.SAME_TRANSACTION,
                    ("target", "observer", "transaction"),
                ),
            ),
        )

    def test_later_filesystem_mutations_require_proven_capability(self) -> None:
        for spec in (
            atomic.ANDROID_FILESYSTEM_SCRATCH_ATOMIC_REPLACE,
            atomic.ANDROID_FILESYSTEM_MANAGED_ROOT_WRITE,
            atomic.ANDROID_FILESYSTEM_MANAGED_ATOMIC_REPLACE,
        ):
            with self.subTest(operation_id=spec.contract.operation_id):
                requirements = {
                    (item.subject, item.predicate, item.freshness)
                    for item in spec.contract.fact_requirements
                }
                self.assertIn(
                    (
                        "filesystem",
                        "mutation_capability_proven",
                        operation.CAUSAL_REUSE_ALLOWED,
                    ),
                    requirements,
                )
                self.assertIn(
                    (
                        "phone",
                        "registered_phone_access_proven",
                        operation.SAME_TRANSACTION,
                    ),
                    requirements,
                )

    def test_bootstrap_remains_single_dispatch_nonretryable(self) -> None:
        spec = atomic.ANDROID_FILESYSTEM_SCRATCH_ROUNDTRIP
        self.assertEqual(atomic.validate_atomic_spec(spec), ())
        self.assertEqual(
            atomic.primary_destructive_steps(spec.contract),
            ("scratch_roundtrip",),
        )
        self.assertFalse(spec.contract.retryable)
        self.assertEqual(spec.contract.affected_physical_domains, ("filesystem",))


if __name__ == "__main__":
    unittest.main()
