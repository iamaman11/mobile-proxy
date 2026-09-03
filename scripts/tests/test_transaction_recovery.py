from __future__ import annotations

from pathlib import Path
import sys
import unittest


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import operation_state_machine as OP
from operations import filesystem as FS
import transaction_runner as RUNNER


REQUEST_ID = "req-sha256:" + "1" * 64
GENERATION = "gen-sha256:" + "2" * 64
CURSOR = "issue179-comment-5532765929"
PRIOR_TERMINAL = "issue-comment:5532752064"
SCRATCH = "/data/local/tmp/mobile-proxy-kernel-" + "1" * 32
PAYLOAD = "payload/" + GENERATION


def semantic() -> RUNNER.SemanticRequestIdentity:
    return RUNNER.routed_semantic_request_identity(
        request_id=REQUEST_ID,
        operation="phone-filesystem-certification",
        arguments=("3" * 40,),
        authority_cursor=CURSOR,
        desired_generation=GENERATION,
    )


def request() -> FS.FilesystemScratchRoundtripRequest:
    return FS.FilesystemScratchRoundtripRequest(
        semantic_request=semantic(),
        scratch_ref=SCRATCH,
        payload_ref=PAYLOAD,
    )


def unknown_evidence(tx: str) -> tuple[OP.PhaseEvidence, ...]:
    ref = "durable-original-evidence"
    return (
        OP.PhaseEvidence("resolve_authority", OP.PASSED, tx, ref),
        OP.PhaseEvidence("mutation_scope", OP.PASSED, tx, ref),
        OP.PhaseEvidence("phone_access_boundary", OP.PASSED, tx, ref),
        OP.PhaseEvidence("mutation_intent", OP.PASSED, tx, ref),
        OP.PhaseEvidence("scratch_roundtrip", OP.DISPATCHED, tx, ref),
    )


class FakeFilesystemEdge:
    def __init__(self) -> None:
        self.dispatch_calls = 0

    def scratch_roundtrip_once(self, value):
        self.dispatch_calls += 1
        raise AssertionError("primary dispatch must never run during recovery")


class FakeObserver:
    def __init__(self, *, absent: bool) -> None:
        self.absent = absent
        self.calls = 0

    def observe_scratch_roundtrip(self, value):
        self.calls += 1
        return RUNNER.PostconditionProof(
            self.absent,
            "bounded-recovery-observation",
        )


class DirectRecoveryExecutor:
    def __init__(self, disposition: str) -> None:
        self.disposition = disposition
        self.dispatch_calls = 0
        self.observe_calls = 0

    def dispatch_once(self, value):
        self.dispatch_calls += 1
        raise AssertionError("primary dispatch must never run during recovery")

    def verify_postcondition(self, value):
        raise AssertionError("primary postcondition must never run during recovery")

    def observe_recovery(self, value):
        self.observe_calls += 1
        return RUNNER.RecoveryObservation(
            self.disposition,
            "bounded-recovery-observation",
        )


class FakeRecoveryPorts:
    def __init__(self, *, authorized: bool = True) -> None:
        self.authorized = authorized
        self.authority_calls = 0
        self.records: list[RUNNER.RecoveryRecord] = []

    def resolve_recovery_authority(
        self,
        value,
        contract,
        transaction_id,
        mutation_subject_ref,
        prior_terminal_ref,
    ):
        self.authority_calls += 1
        if mutation_subject_ref != SCRATCH:
            return RUNNER.AuthorityProof(False, "recovery-authority")
        if prior_terminal_ref != PRIOR_TERMINAL:
            return RUNNER.AuthorityProof(False, "recovery-authority")
        return RUNNER.AuthorityProof(self.authorized, "recovery-authority")

    def persist_recovery(self, record):
        self.records.append(record)
        return "issue-comment:recovery-record"


class TransactionRecoveryTests(unittest.TestCase):
    def binding(self, executor):
        return FS.FilesystemScratchRoundtripBinding(executor)

    def tx(self) -> str:
        return RUNNER.derive_physical_transaction_id(
            semantic(),
            "android.filesystem-scratch-roundtrip.v1",
        )

    def recover(self, executor, *, ports=None, evidence=None, terminal=PRIOR_TERMINAL):
        ports = ports or FakeRecoveryPorts()
        binding = self.binding(executor)
        result = RUNNER.TransactionRunner().recover(
            request(),
            ports=ports,
            binding=binding,
            existing_evidence=evidence or unknown_evidence(self.tx()),
            prior_terminal_ref=terminal,
        )
        return result, ports

    def test_absent_scratch_recovers_safe_state_without_accepting_original(self) -> None:
        filesystem = FakeFilesystemEdge()
        observer = FakeObserver(absent=True)
        executor = FS.FilesystemScratchRoundtripExecutor(filesystem, observer)

        result, ports = self.recover(executor)

        self.assertEqual(result.derived["state"], "RECOVERED")
        self.assertNotEqual(result.derived["state"], "ACCEPTED")
        self.assertEqual(result.recovery_disposition, RUNNER.RECOVERY_PROVEN_ABSENT)
        self.assertEqual(filesystem.dispatch_calls, 0)
        self.assertEqual(observer.calls, 1)
        self.assertEqual(len(ports.records), 1)
        record = ports.records[0]
        self.assertEqual(record.prior_terminal_ref, PRIOR_TERMINAL)
        self.assertEqual(record.mutation_subject_ref, SCRATCH)
        self.assertEqual(record.recovery_step_id, "recovery_observe")
        self.assertEqual(record.disposition, RUNNER.RECOVERY_PROVEN_ABSENT)
        self.assertEqual(record.derived["state"], "RECOVERED")
        self.assertEqual(record.lifecycle_state, RUNNER.TERMINAL_QUARANTINED)
        self.assertFalse(any(item.step_id == "accept" for item in record.evidence))

    def test_present_scratch_is_quarantined_without_cleanup_or_redispatch(self) -> None:
        filesystem = FakeFilesystemEdge()
        observer = FakeObserver(absent=False)
        executor = FS.FilesystemScratchRoundtripExecutor(filesystem, observer)

        result, ports = self.recover(executor)

        self.assertEqual(result.derived["state"], "QUARANTINED")
        self.assertEqual(result.recovery_disposition, RUNNER.RECOVERY_RESIDUAL_PRESENT)
        self.assertEqual(filesystem.dispatch_calls, 0)
        self.assertEqual(observer.calls, 1)
        self.assertEqual(ports.records[0].disposition, RUNNER.RECOVERY_RESIDUAL_PRESENT)

    def test_indeterminate_observation_remains_unknown(self) -> None:
        executor = DirectRecoveryExecutor(RUNNER.RECOVERY_INDETERMINATE)
        result, ports = self.recover(executor)

        self.assertEqual(result.derived["state"], "UNKNOWN_EXECUTION_OUTCOME")
        self.assertEqual(result.lifecycle_state, RUNNER.TERMINAL_UNKNOWN)
        self.assertEqual(result.recovery_disposition, RUNNER.RECOVERY_INDETERMINATE)
        self.assertEqual(executor.dispatch_calls, 0)
        self.assertEqual(executor.observe_calls, 1)
        self.assertEqual(ports.records[0].derived["state"], "UNKNOWN_EXECUTION_OUTCOME")

    def test_proven_complete_recovery_still_does_not_accept_original(self) -> None:
        executor = DirectRecoveryExecutor(RUNNER.RECOVERY_PROVEN_COMPLETE)
        result, _ = self.recover(executor)

        self.assertEqual(result.derived["state"], "RECOVERED")
        self.assertNotEqual(result.derived["state"], "ACCEPTED")
        self.assertEqual(executor.dispatch_calls, 0)

    def test_wrong_prior_terminal_ref_refuses_before_observation(self) -> None:
        executor = DirectRecoveryExecutor(RUNNER.RECOVERY_PROVEN_ABSENT)
        ports = FakeRecoveryPorts()
        with self.assertRaisesRegex(RUNNER.TransactionRefusal, "authority refused"):
            self.recover(executor, ports=ports, terminal="issue-comment:wrong")

        self.assertEqual(executor.observe_calls, 0)
        self.assertEqual(executor.dispatch_calls, 0)
        self.assertEqual(ports.records, [])

    def test_recovery_rejects_mixed_transaction_evidence_before_observation(self) -> None:
        executor = DirectRecoveryExecutor(RUNNER.RECOVERY_PROVEN_ABSENT)
        evidence = unknown_evidence(self.tx()) + (
            OP.PhaseEvidence("recovery_observe", OP.PASSED, "other-tx", "other-ref"),
        )
        ports = FakeRecoveryPorts()
        with self.assertRaisesRegex(RUNNER.TransactionRefusal, "mixes transaction"):
            self.recover(executor, ports=ports, evidence=evidence)

        self.assertEqual(ports.authority_calls, 0)
        self.assertEqual(executor.observe_calls, 0)

    def test_existing_unknown_primary_run_remains_blind_retry_forbidden(self) -> None:
        filesystem = FakeFilesystemEdge()
        observer = FakeObserver(absent=True)
        executor = FS.FilesystemScratchRoundtripExecutor(filesystem, observer)
        binding = self.binding(executor)
        with self.assertRaisesRegex(RUNNER.BlindRetryForbidden, "blind retry"):
            RUNNER.TransactionRunner().run(
                request(),
                ports=object(),
                binding=binding,
                existing_evidence=unknown_evidence(self.tx()),
            )
        self.assertEqual(filesystem.dispatch_calls, 0)

    def test_recovery_api_has_no_mutation_port_surface(self) -> None:
        names = set(getattr(RUNNER.RecoveryPorts, "__annotations__", {}))
        body = (SCRIPT_DIR / "transaction_runner.py").read_text(encoding="utf-8")
        recover_body = body.split("    def recover(", 1)[1]
        for forbidden in (
            "acquire_mutation_scope(",
            "persist_mutation_intent(",
            "affected_domain_generation_updates(",
            "binding.dispatch_once(",
        ):
            self.assertNotIn(forbidden, recover_body)
        self.assertEqual(names, set())

    def test_recovery_dispositions_are_bounded(self) -> None:
        executor = DirectRecoveryExecutor("UNBOUNDED_RAW_OUTPUT")
        with self.assertRaisesRegex(RUNNER.TransactionRefusal, "unsupported disposition"):
            self.recover(executor)
        self.assertEqual(executor.dispatch_calls, 0)


if __name__ == "__main__":
    unittest.main()
