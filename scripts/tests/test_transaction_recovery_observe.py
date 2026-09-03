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


class ForbiddenPostconditionObserver:
    def __init__(self) -> None:
        self.calls = 0

    def observe_scratch_roundtrip(self, request):
        self.calls += 1
        raise AssertionError("recovery must not reuse normal postcondition observer")


class TypedRecoveryObserver:
    def __init__(
        self,
        disposition: str,
        *,
        source_ref: str = "recovery-observation:filesystem-scratch",
        error: bool = False,
    ) -> None:
        self.disposition = disposition
        self.source_ref = source_ref
        self.error = error
        self.calls = 0

    def observe_recovery(self, request):
        self.calls += 1
        if self.error:
            raise RuntimeError("recovery observation transport lost")
        return RUNNER.RecoveryObservation(self.disposition, self.source_ref)


class RecoveryOnlyPorts:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.recovery_terminals: list[
            tuple[
                RUNNER.TerminalRecord,
                str,
                RUNNER.RecoveryObservation | None,
                str | None,
            ]
        ] = []

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
        recovery_observation,
        recovery_error,
    ):
        self.events.append("recovery_terminal")
        self.recovery_terminals.append(
            (record, prior_terminal_ref, recovery_observation, recovery_error)
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


def binding(
    disposition: str = RUNNER.RECOVERY_PROVEN_ABSENT,
    *,
    source_ref: str = "recovery-observation:filesystem-scratch",
    error: bool = False,
):
    filesystem = ForbiddenFilesystemEdge()
    postcondition = ForbiddenPostconditionObserver()
    recovery = TypedRecoveryObserver(
        disposition,
        source_ref=source_ref,
        error=error,
    )
    executor = FILESYSTEM.FilesystemScratchRoundtripExecutor(filesystem, postcondition)
    return (
        FILESYSTEM.FilesystemScratchRoundtripBinding(executor, recovery),
        filesystem,
        postcondition,
        recovery,
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


def recover(
    bound: FILESYSTEM.FilesystemScratchRoundtripBinding,
    ports: RecoveryOnlyPorts,
    prior: RUNNER.TerminalRecord,
):
    return RUNNER.TransactionRunner().recover(
        request(),
        ports=ports,
        binding=bound,
        prior_terminal=prior,
        prior_terminal_ref=PRIOR_REF,
        prior_mutation_subject_ref=SCRATCH,
    )


class RecoveryObserveKernelTests(unittest.TestCase):
    def test_proven_absent_recovers_baseline_without_accepting_or_retrying(self) -> None:
        bound, filesystem, postcondition, observer = binding(
            RUNNER.RECOVERY_PROVEN_ABSENT,
            source_ref="recovery-observation:filesystem-scratch-absent",
        )
        prior = unknown_terminal(bound)
        ports = RecoveryOnlyPorts()

        result = recover(bound, ports, prior)

        self.assertEqual(result.derived["state"], "RECOVERED")
        self.assertEqual(result.lifecycle_state, RUNNER.TERMINAL_QUARANTINED)
        self.assertNotEqual(result.lifecycle_state, RUNNER.TERMINAL_ACCEPTED)
        self.assertEqual(result.recovery_disposition, RUNNER.RECOVERY_PROVEN_ABSENT)
        self.assertEqual(result.prior_terminal_ref, PRIOR_REF)
        self.assertIsNone(result.recovery_error)
        self.assertEqual(filesystem.dispatch_calls, 0)
        self.assertEqual(postcondition.calls, 0)
        self.assertEqual(observer.calls, 1)
        self.assertEqual(ports.events, ["recovery_terminal"])
        record, prior_ref, observation, recovery_error = ports.recovery_terminals[0]
        self.assertEqual(prior_ref, PRIOR_REF)
        self.assertEqual(observation.disposition, RUNNER.RECOVERY_PROVEN_ABSENT)
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
        retry_bound, retry_filesystem, retry_postcondition, retry_observer = binding()
        with self.assertRaisesRegex(RUNNER.BlindRetryForbidden, "blind retry"):
            RUNNER.TransactionRunner().run(
                request(),
                ports=retry_ports,
                binding=retry_bound,
                existing_evidence=result.evidence,
            )
        self.assertEqual(retry_ports.events, [])
        self.assertEqual(retry_filesystem.dispatch_calls, 0)
        self.assertEqual(retry_postcondition.calls, 0)
        self.assertEqual(retry_observer.calls, 0)

    def test_residual_present_quarantines_without_cleanup_or_dispatch(self) -> None:
        bound, filesystem, postcondition, observer = binding(
            RUNNER.RECOVERY_RESIDUAL_PRESENT,
            source_ref="recovery-observation:filesystem-scratch-present",
        )
        prior = unknown_terminal(bound)
        ports = RecoveryOnlyPorts()

        result = recover(bound, ports, prior)

        self.assertEqual(result.derived["state"], "QUARANTINED")
        self.assertEqual(result.lifecycle_state, RUNNER.TERMINAL_QUARANTINED)
        self.assertEqual(result.recovery_disposition, RUNNER.RECOVERY_RESIDUAL_PRESENT)
        self.assertEqual(filesystem.dispatch_calls, 0)
        self.assertEqual(postcondition.calls, 0)
        self.assertEqual(observer.calls, 1)
        self.assertEqual(ports.events, ["recovery_terminal"])
        self.assertEqual(
            (result.evidence[-1].step_id, result.evidence[-1].status),
            ("recovery_observe", OP.FAILED),
        )

    def test_indeterminate_observation_preserves_unknown_without_recovery_phase(self) -> None:
        bound, filesystem, postcondition, observer = binding(
            RUNNER.RECOVERY_INDETERMINATE,
            source_ref="recovery-observation:filesystem-scratch-indeterminate",
        )
        prior = unknown_terminal(bound)
        ports = RecoveryOnlyPorts()

        result = recover(bound, ports, prior)

        self.assertEqual(result.derived["state"], "UNKNOWN_EXECUTION_OUTCOME")
        self.assertEqual(result.lifecycle_state, RUNNER.TERMINAL_UNKNOWN)
        self.assertEqual(result.evidence, prior.evidence)
        self.assertEqual(result.recovery_disposition, RUNNER.RECOVERY_INDETERMINATE)
        self.assertEqual(filesystem.dispatch_calls, 0)
        self.assertEqual(postcondition.calls, 0)
        self.assertEqual(observer.calls, 1)
        record, _, observation, recovery_error = ports.recovery_terminals[0]
        self.assertEqual(record.evidence, prior.evidence)
        self.assertEqual(observation.disposition, RUNNER.RECOVERY_INDETERMINATE)
        self.assertIsNone(recovery_error)

    def test_transport_loss_preserves_unknown_and_persists_bounded_error(self) -> None:
        bound, filesystem, postcondition, observer = binding(error=True)
        prior = unknown_terminal(bound)
        ports = RecoveryOnlyPorts()

        result = recover(bound, ports, prior)

        self.assertEqual(result.derived["state"], "UNKNOWN_EXECUTION_OUTCOME")
        self.assertEqual(result.lifecycle_state, RUNNER.TERMINAL_UNKNOWN)
        self.assertEqual(result.evidence, prior.evidence)
        self.assertIsNone(result.recovery_disposition)
        self.assertIn("recovery observation transport lost", result.recovery_error or "")
        self.assertEqual(filesystem.dispatch_calls, 0)
        self.assertEqual(postcondition.calls, 0)
        self.assertEqual(observer.calls, 1)
        _, prior_ref, observation, recovery_error = ports.recovery_terminals[0]
        self.assertEqual(prior_ref, PRIOR_REF)
        self.assertIsNone(observation)
        self.assertIn("recovery observation transport lost", recovery_error or "")

    def test_scratch_binding_never_converts_late_absence_to_proven_complete(self) -> None:
        bound, filesystem, postcondition, observer = binding(
            RUNNER.RECOVERY_PROVEN_COMPLETE,
            source_ref="recovery-observation:filesystem-scratch-absent",
        )
        prior = unknown_terminal(bound)
        ports = RecoveryOnlyPorts()

        result = recover(bound, ports, prior)

        self.assertEqual(result.derived["state"], "UNKNOWN_EXECUTION_OUTCOME")
        self.assertEqual(result.lifecycle_state, RUNNER.TERMINAL_UNKNOWN)
        self.assertIsNone(result.recovery_disposition)
        self.assertIn("cannot prove historical completion", result.recovery_error or "")
        self.assertEqual(filesystem.dispatch_calls, 0)
        self.assertEqual(postcondition.calls, 0)
        self.assertEqual(observer.calls, 1)
        self.assertFalse(
            any(
                item.step_id == "recovery_observe" and item.status == OP.PASSED
                for item in result.evidence
            )
        )

    def test_unbounded_recovery_source_ref_is_not_admitted_as_evidence(self) -> None:
        bound, filesystem, postcondition, observer = binding(
            RUNNER.RECOVERY_PROVEN_ABSENT,
            source_ref="raw adb stdout contains spaces and device data",
        )
        prior = unknown_terminal(bound)
        ports = RecoveryOnlyPorts()

        result = recover(bound, ports, prior)

        self.assertEqual(result.derived["state"], "UNKNOWN_EXECUTION_OUTCOME")
        self.assertEqual(result.evidence, prior.evidence)
        self.assertIsNone(result.recovery_disposition)
        self.assertIn("source_ref is not bounded", result.recovery_error or "")
        self.assertEqual(filesystem.dispatch_calls, 0)
        self.assertEqual(postcondition.calls, 0)
        self.assertEqual(observer.calls, 1)

    def test_prior_terminal_semantic_mismatch_refuses_before_observer_or_ports(self) -> None:
        bound, filesystem, postcondition, observer = binding()
        prior = replace(
            unknown_terminal(bound),
            control_request_id="req-sha256:" + ("f" * 64),
        )
        ports = RecoveryOnlyPorts()

        with self.assertRaisesRegex(RUNNER.TransactionRefusal, "semantic identity"):
            recover(bound, ports, prior)

        self.assertEqual(filesystem.dispatch_calls, 0)
        self.assertEqual(postcondition.calls, 0)
        self.assertEqual(observer.calls, 0)
        self.assertEqual(ports.events, [])

    def test_mutation_subject_mismatch_refuses_before_observer_or_ports(self) -> None:
        bound, filesystem, postcondition, observer = binding()
        prior = unknown_terminal(bound)
        ports = RecoveryOnlyPorts()

        with self.assertRaisesRegex(RUNNER.TransactionRefusal, "mutation subject"):
            RUNNER.TransactionRunner().recover(
                request(),
                ports=ports,
                binding=bound,
                prior_terminal=prior,
                prior_terminal_ref=PRIOR_REF,
                prior_mutation_subject_ref=SCRATCH + "-other",
            )

        self.assertEqual(filesystem.dispatch_calls, 0)
        self.assertEqual(postcondition.calls, 0)
        self.assertEqual(observer.calls, 0)
        self.assertEqual(ports.events, [])

    def test_prior_terminal_must_be_canonical_unknown_at_dispatch_boundary(self) -> None:
        bound, filesystem, postcondition, observer = binding()
        prior = unknown_terminal(bound)
        forged = replace(prior, lifecycle_state=RUNNER.TERMINAL_QUARANTINED)
        ports = RecoveryOnlyPorts()

        with self.assertRaisesRegex(RUNNER.TransactionRefusal, "canonical UNKNOWN"):
            recover(bound, ports, forged)

        self.assertEqual(filesystem.dispatch_calls, 0)
        self.assertEqual(postcondition.calls, 0)
        self.assertEqual(observer.calls, 0)
        self.assertEqual(ports.events, [])

    def test_recovery_entrypoint_has_no_primary_mutation_surface(self) -> None:
        body = inspect.getsource(RUNNER.TransactionRunner.recover)
        for forbidden in (
            ".dispatch_once(",
            "resolve_authority(",
            "acquire_mutation_scope(",
            "prove_same_transaction_boundary(",
            "prove_preflight_requirements(",
            "persist_mutation_intent(",
            "persist_terminal(",
            "affected_domain_generation_updates(",
        ):
            self.assertNotIn(forbidden, body)
        self.assertIn("persist_recovery_terminal(", body)
        self.assertIn("observe_recovery", body)
        self.assertIn("RECOVERY_INDETERMINATE", body)

    def test_disposition_set_is_exactly_bounded(self) -> None:
        self.assertEqual(
            RUNNER.RECOVERY_DISPOSITIONS,
            {
                "PROVEN_COMPLETE",
                "PROVEN_ABSENT",
                "RESIDUAL_PRESENT",
                "INDETERMINATE",
            },
        )


if __name__ == "__main__":
    unittest.main()
