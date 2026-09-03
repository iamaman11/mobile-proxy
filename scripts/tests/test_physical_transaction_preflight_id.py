from __future__ import annotations

from pathlib import Path
import sys
import unittest


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_private_phone_preflight as preflight
import transaction_runner as kernel


class PhysicalTransactionPreflightIdTests(unittest.TestCase):
    def test_real_kernel_physical_transaction_id_is_preflight_admissible(self) -> None:
        semantic = kernel.SemanticRequestIdentity(
            schema=kernel.SEMANTIC_REQUEST_SCHEMA,
            request_id="req-sha256:" + "a" * 64,
            operation="phone-filesystem-certification",
            arguments=("b" * 40,),
            authority_cursor="issue179-comment-5531491187",
            desired_generation="gen-sha256:" + "c" * 64,
        )
        transaction_id = kernel.derive_physical_transaction_id(
            semantic,
            "android.filesystem-scratch-roundtrip.v1",
        )
        self.assertGreater(len(transaction_id), 96)
        self.assertIn(":", transaction_id)
        self.assertEqual(preflight.require_transaction_id(transaction_id), transaction_id)

    def test_transaction_id_remains_bounded_and_single_line(self) -> None:
        for invalid in (
            "",
            "physical tx",
            "physical-tx-v1:abc\ndef",
            "a" * 257,
            "physical-tx-v1:abc/def",
        ):
            with self.subTest(invalid=invalid[:30]):
                with self.assertRaises(preflight.PreflightFailure):
                    preflight.require_transaction_id(invalid)


if __name__ == "__main__":
    unittest.main()
