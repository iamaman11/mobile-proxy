from __future__ import annotations

from dataclasses import replace
import inspect
from pathlib import Path
import sys
import unittest


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import operation_state_machine as OP
from operations import filesystem as FILESYSTEM
import transaction_runner as RUNNER


REQUEST_ID = "req-sha256:" + ("1" * 64)
GENERATION = "gen-sha256:" + ("2" * 64)
AUTHORITY_CURSOR = "issue179-comment-5531491187"
SCRATCH = "/data/local/tmp/mobile-proxy-kernel-0123456789abcdef0123456789abcdef"
PAYLOAD = "payload/gen-sha256:" + ("2" * 64)
PRIOR_REF = "issue-comment:5532752064"


class ForbiddenFilesystemEdge:
    def __init__(self) -> None:
        self.dispatch_calls = 0

    def scratch_roundtrip_once(self, request):
        self.dispatch_calls += 1
        raise AssertionError("recovery observation must never dispatch")


class RecoveryObserver:
    def __init__(self, *, passed: bool = True, error: bool = False) -> None:
        self.passed = passed
        self.error = error
        self.calls = 0

    def observe_scratch_roundtrip(self, request):
        self.calls += 1
        if self.error:
            raise RuntimeError("recovery observation transport lost")
        return RUNNER.PostconditionProof(
            self.passed,
            "recovery-observation:filesystem-scratch-absent"
            if self.passed
            else "recovery-observation:filesystem-scratch-present",
        )


class RecoveryOnlyPorts:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.recovery_terminals: list[tuple[RUNNER.TerminalRecord, str, str | None]] = []

    def _forbidden(self, name: str):
        self.events.append(f"FORBIDDEN:{name}")
        raise AssertionError(f"recovery path called mutation port {name}")

    def resolve_authority(self, request, contract):
        return self._forbidden("resolve_authority")

    def acquire_mutation_scope(self, target, transaction_id):
        return self._forbidden("acquire_mutation_scope")

    def prove_same_transaction_boundary(self, contract, transaction_id):
        return self._forbidden("prove_same_transaction_boundary")

    def prove_preflight_requirements(self, contract, transaction_id):
        return self._forbidden("prove_preflight_requirements")

    def persist_mutation_intent(self, intent):
        return self._forbidden("persist_mutation_intent")

    def persist_terminal(self, record):
        return self._forbidden("persist_terminal")

    def persist_recovery_terminal(
        self,
        record,
        *,
        prior_terminal_ref,
        recovery_error,
    ):
        self.events.append("recovery_terminal")
        self.recovery_terminals.append(
            (record, prior_terminal_ref, recovery_error)
        )
        return f"recovery-terminal-{len(self.recovery_terminals)}"


def semantic() -> RUNNER.SemanticRequestIdentity:
    return RUNNER.routed_semantic_request_identity(
        request_id=REQUEST_ID,
        operation="phone-filesystem-certification",
        arguments=("374073b4e666d71981d5ccf9169c30e0979845e6",),
        authority_cursor=AUTHORITY_CURSOR,
        desired_generation=GENERATION,
    )


def request() -> FILESYSTEM.FilesystemScratchRoundtripRequest:
    return FILESYSTEM.FilesystemScratchRoundtripRequest(
        semantic_request=semantic(),
        scratch_ref=SCRATCH,
        payload_ref=PAYLOAD,
    )


def binding(*, passed: bool = True, error: bool = False):
    filesystem = ForbiddenFilesystemEdge()
    observer = RecoveryObserver(passed=passed, error=error)
    executor = FILESYSTEM.FilesystemScratchRoundtripExecutor(filesystem, observer)
    return (
        FILESYSTEM.FilesystemScratchRoundtripBinding(executor),
        filesystem,
        observer,
    )


def unknown_terminal(bound: FILESYSTEM.FilesystemScratchRoundtripBinding):
    req = request()
    tx = bound.transaction_id(req)
    roles = bound.kernel_steps
    evidence = (
        OP.PhaseEvidence(roles.authority_step_id, OP.PASSED, tx, "authority-1"),
        OP.PhaseEvidence(roles.mutation_scope_step_id, OP.PASSED, tx, "scope-1"),
        OP.PhaseEvidence(roles.preflight_step_id, OP.PASSED, tx, "phone-fact-1"),
        OP.PhaseEvidence(roles.intent_step_id, OP.PASSED, tx, "intent-1"),
        OP.PhaseEvidence(roles.dispatch_step_id, OP.DISPATCHED, tx, "intent-1"),
    )
    derived = OP.derive_operation_state(bound.contract, evidence, transaction_id=tx)
    assert derived["state"] == "UNKNOWN_EXECUTION_OUTCOME"
    assert derived["next_step"] == "recovery_observe"
    return RUNNER.TerminalRecord(
        operation_id=bound.contract.operation_id,
        target=bound.contract.target,
        transaction_id=tx,
        affected_domain_generations={"domain/filesystem": tx},
        evidence=evidence,
        derived=derived,
        lifecycle_state=RUNNER.TERMINAL_UNKNOWN,
        control_request_id=REQUEST_ID,
        authority_cursor=AUTHORITY_CURSOR,
        desired_generation=GENERATION,
    )


class RecoveryObserveKernelTests(unittest.TestCase):
    def test_absent_observation_recovers_environment_without_accepting_or_retrying(self) -> None:
        bound, filesystem, observer = binding(passed=True)
        prior = unknown_terminal(bound)
        ports = RecoveryOnlyPorts()
        runner = RUNNER.TransactionRunner()

        result = runner.recover_observe(
            request(),
            ports=ports,
            binding=bound,
            prior_terminal=prior,
            prior_terminal_ref=PRIOR_REF,
        )

        self.assertEqual(result.derived["state"], "RECOVERED")
        self.assertEqual(result.lifecycle_state, RUNNER.TERMINAL_QUARANTINED)
        self.assertNotEqual(result.lifecycle_state, RUNNER.TERMINAL_ACCEPTED)
        self.assertEqual(result.prior_terminal_ref, PRIOR_REF)
        self.assertIsNone(result.recovery_error)
        self.assertEqual(filesystem.dispatch_calls, 0)
        self.assertEqual(observer.calls, 1)
        self.assertEqual(ports.events, ["recovery_terminal"])
        self.assertEqual(len(ports.recovery_terminals), 1)
        record, prior_ref, recovery_error = ports.recovery_terminals[0]
        self.assertEqual(prior_ref, PRIOR_REF)
        self.assertIsNone(recovery_error)
        self.assertEqual(record.derived["state"], "RECOVERED")
        self.assertEqual(record.lifecycle_state, RUNNER.TERMINAL_QUARANTINED)
        self.assertEqual(prior.lifecycle_state, RUNNER.TERMINAL_UNKNOWN)
        self.assertEqual(prior.derived["state"], "UNKNOWN_EXECUTION_OUTCOME")
        self.assertEqual(
            (result.evidence[-1].step_id, result.evidence[-1].status),
            ("recovery_observe", OP.PASSED),
        )

        retry_ports = RecoveryOnlyPorts()
        retry_bound, retry_filesystem, retry_observer = binding(passed=True)
        with self.assertRaisesRegex(RUNNER.BlindRetryForbidden, "blind retry"):
            runner.run(
                request(),
                ports=retry_ports,
                binding=retry_bound,
                existing_evidence=result.evidence,
            )
        self.assertEqual(retry_ports.events, [])
        self.assertEqual(retry_filesystem.dispatch_calls, 0)
        self.assertEqual(retry_observer.calls, 0)

    def test_present_observation_quarantines_without_cleanup_or_dispatch(self) -> None:
        bound, filesystem, observer = binding(passed=False)
        prior = unknown_terminal(bound)
        ports = RecoveryOnlyPorts()

        result = RUNNER.TransactionRunner().recover_observe(
            request(),
            ports=ports,
            binding=bound,
            prior_terminal=prior,
            prior_terminal_ref=PRIOR_REF,
        )

        self.assertEqual(result.derived["state"], "QUARANTINED")
        self.assertEqual(result.lifecycle_state, RUNNER.TERMINAL_QUARANTINED)
        self.assertEqual(filesystem.dispatch_calls, 0)
        self.assertEqual(observer.calls, 1)
        self.assertEqual(ports.events, ["recovery_terminal"])
        self.assertEqual(
            (result.evidence[-1].step_id, result.evidence[-1].status),
            ("recovery_observe", OP.FAILED),
        )

    def test_lost_recovery_observation_preserves_unknown_and_persists_error(self) -> None:
        bound, filesystem, observer = binding(error=True)
        prior = unknown_terminal(bound)
        ports = RecoveryOnlyPorts()

        result = RUNNER.TransactionRunner().recover_observe(
            request(),
            ports=ports,
            binding=bound,
            prior_terminal=prior,
            prior_terminal_ref=PRIOR_REF,
        )

        self.assertEqual(result.derived["state"], "UNKNOWN_EXECUTION_OUTCOME")
        self.assertEqual(result.lifecycle_state, RUNNER.TERMINAL_UNKNOWN)
        self.assertEqual(result.evidence, prior.evidence)
        self.assertIn("recovery observation transport lost", result.recovery_error or "")
        self.assertEqual(filesystem.dispatch_calls, 0)
        self.assertEqual(observer.calls, 1)
        self.assertEqual(ports.events, ["recovery_terminal"])
        _, prior_ref, recovery_error = ports.recovery_terminals[0]
        self.assertEqual(prior_ref, PRIOR_REF)
        self.assertIn("recovery observation transport lost", recovery_error or "")

    def test_prior_terminal_semantic_mismatch_refuses_before_observer_or_ports(self) -> None:
        bound, filesystem, observer = binding()
        prior = replace(unknown_terminal(bound), control_request_id="req-sha256:" + ("f" * 64))
        ports = RecoveryOnlyPorts()

        with self.assertRaisesRegex(RUNNER.TransactionRefusal, "semantic identity"):
            RUNNER.TransactionRunner().recover_observe(
                request(),
                ports=ports,
                binding=bound,
                prior_terminal=prior,
                prior_terminal_ref=PRIOR_REF,
            )

        self.assertEqual(filesystem.dispatch_calls, 0)
        self.assertEqual(observer.calls, 0)
        self.assertEqual(ports.events, [])

    def test_prior_terminal_must_be_canonical_unknown_at_dispatch_boundary(self) -> None:
        bound, filesystem, observer = binding()
        prior = unknown_terminal(bound)
        forged = replace(prior, lifecycle_state=RUNNER.TERMINAL_QUARANTINED)
        ports = RecoveryOnlyPorts()

        with self.assertRaisesRegex(RUNNER.TransactionRefusal, "canonical UNKNOWN"):
            RUNNER.TransactionRunner().recover_observe(
                request(),
                ports=ports,
                binding=bound,
                prior_terminal=forged,
                prior_terminal_ref=PRIOR_REF,
            )

        self.assertEqual(filesystem.dispatch_calls, 0)
        self.assertEqual(observer.calls, 0)
        self.assertEqual(ports.events, [])

    def test_recovery_method_has_no_mutation_port_or_dispatch_call_surface(self) -> None:
        body = inspect.getsource(RUNNER.TransactionRunner.recover_observe)
        for forbidden in (
            ".dispatch_once(",
            "resolve_authority(",
            "acquire_mutation_scope(",
            "prove_same_transaction_boundary(",
            "prove_preflight_requirements(",
            "persist_mutation_intent(",
            "persist_terminal(",
        ):
            self.assertNotIn(forbidden, body)
        self.assertIn("persist_recovery_terminal(", body)
        self.assertIn("observe_recovery", body)


if __name__ == "__main__":
    unittest.main()
