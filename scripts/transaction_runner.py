from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

import control_state_machine as control
import operation_state_machine as operation


class TransactionRefusal(RuntimeError):
    """Fail-closed admission error before a physical dispatch is allowed."""


class BlindRetryForbidden(TransactionRefusal):
    """The transaction already crossed a durable dispatch boundary."""


class DispatchOutcomeUnknown(RuntimeError):
    """An operation binding cannot prove whether dispatch reached the target."""


@dataclass(frozen=True)
class AuthorityProof:
    authorized: bool
    source_ref: str


@dataclass(frozen=True)
class BoundaryProof:
    fact: control.ObservedFact
    current_context: Mapping[str, str]


@dataclass(frozen=True)
class MutationIntent:
    operation_id: str
    target: str
    transaction_id: str
    dispatch_step_id: str
    mutation_subject_ref: str
    affected_domain_generations: Mapping[str, str]


@dataclass(frozen=True)
class DispatchReceipt:
    source_ref: str


@dataclass(frozen=True)
class PostconditionProof:
    passed: bool
    source_ref: str


@dataclass(frozen=True)
class TerminalRecord:
    operation_id: str
    target: str
    transaction_id: str
    affected_domain_generations: Mapping[str, str]
    evidence: tuple[operation.PhaseEvidence, ...]
    derived: Mapping[str, object]


@dataclass(frozen=True)
class TransactionResult:
    evidence: tuple[operation.PhaseEvidence, ...]
    derived: Mapping[str, object]
    terminal_ref: str | None
    dispatch_error: str | None = None


class TransactionPorts(Protocol):
    def resolve_authority(
        self,
        request: object,
        contract: operation.OperationContract,
    ) -> AuthorityProof: ...

    def acquire_mutation_scope(
        self,
        target: str,
        transaction_id: str,
    ) -> AbstractContextManager[str]: ...

    def prove_same_transaction_boundary(
        self,
        contract: operation.OperationContract,
        transaction_id: str,
    ) -> BoundaryProof: ...

    def persist_mutation_intent(self, intent: MutationIntent) -> str: ...

    def persist_terminal(self, record: TerminalRecord) -> str: ...


class OperationBinding(Protocol):
    """Operation-specific edge consumed by the generic transaction kernel.

    The binding supplies request interpretation plus one physical dispatch and one
    postcondition observation. It does not own transaction ordering or state.
    """

    contract: operation.OperationContract
    dispatch_step_id: str
    postcondition_step_id: str
    acceptance_step_id: str

    def transaction_id(self, request: object) -> str: ...

    def mutation_subject_ref(self, request: object) -> str: ...

    def dispatch_once(self, request: object) -> DispatchReceipt: ...

    def verify_postcondition(self, request: object) -> PostconditionProof: ...


def _non_empty(value: str, *, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise TransactionRefusal(f"{field} must be non-empty")
    if any(character.isspace() for character in normalized):
        raise TransactionRefusal(f"{field} must not contain whitespace")
    return normalized


def _phase(
    step_id: str,
    status: str,
    transaction_id: str,
    source_ref: str,
) -> operation.PhaseEvidence:
    return operation.PhaseEvidence(
        step_id,
        status,
        transaction_id,
        _non_empty(source_ref, field=f"{step_id}.source_ref"),
    )


def _derive(
    contract: operation.OperationContract,
    evidence: Sequence[operation.PhaseEvidence],
    transaction_id: str,
) -> dict[str, object]:
    return operation.derive_operation_state(
        contract,
        evidence,
        transaction_id=transaction_id,
    )


def _validate_binding(binding: OperationBinding) -> None:
    contract = binding.contract
    steps = tuple(contract.steps)
    by_id = {step.step_id: (index, step) for index, step in enumerate(steps)}
    if len(by_id) != len(steps):
        raise TransactionRefusal("operation contract has duplicate step ids")

    required_kernel_steps = (
        "resolve_authority",
        "mutation_scope",
        "phone_access_boundary",
        "mutation_intent",
    )
    binding_steps = (
        binding.dispatch_step_id,
        binding.postcondition_step_id,
        binding.acceptance_step_id,
    )
    all_steps = (*required_kernel_steps, *binding_steps)
    if len(set(all_steps)) != len(all_steps):
        raise TransactionRefusal("operation binding step ids must be distinct")
    if any(step_id not in by_id for step_id in all_steps):
        raise TransactionRefusal("operation binding does not match operation contract")

    indexes = [by_id[step_id][0] for step_id in all_steps]
    if indexes != sorted(indexes):
        raise TransactionRefusal("operation binding steps are out of contract order")

    boundary = by_id["phone_access_boundary"][1]
    dispatch = by_id[binding.dispatch_step_id][1]
    postcondition = by_id[binding.postcondition_step_id][1]
    acceptance = by_id[binding.acceptance_step_id][1]
    if not boundary.mutation_boundary:
        raise TransactionRefusal("operation binding lacks mutation boundary")
    if not dispatch.destructive:
        raise TransactionRefusal("operation dispatch step must be destructive")
    if postcondition.destructive:
        raise TransactionRefusal("postcondition step must be non-destructive")
    if not acceptance.acceptance:
        raise TransactionRefusal("acceptance step must be an acceptance step")


def _validate_boundary(
    contract: operation.OperationContract,
    proof: BoundaryProof,
    transaction_id: str,
) -> str:
    requirements = tuple(
        item
        for item in contract.fact_requirements
        if item.freshness == operation.SAME_TRANSACTION
    )
    if len(requirements) != 1:
        raise TransactionRefusal(
            "transaction operation requires exactly one SAME_TRANSACTION fact"
        )

    requirement = requirements[0]
    fact = proof.fact
    if fact.subject != requirement.subject or fact.predicate != requirement.predicate:
        raise TransactionRefusal("boundary fact does not match operation contract")
    if fact.value is not True:
        raise TransactionRefusal("boundary fact value is not true")
    if fact.target != contract.target:
        raise TransactionRefusal("boundary fact target does not match operation target")

    dependency_scopes: list[str] = []
    dependencies = tuple(fact.dependencies)
    for kind in requirement.required_dependency_kinds:
        matches = [item for item in dependencies if item.scope.startswith(f"{kind}/")]
        if len(matches) != 1:
            raise TransactionRefusal(
                f"boundary fact requires exactly one {kind} dependency"
            )
        dependency_scopes.append(matches[0].scope)
        if kind == "transaction":
            expected_scope = f"transaction/{transaction_id}"
            if matches[0].scope != expected_scope or matches[0].identity != transaction_id:
                raise TransactionRefusal("boundary fact is not from this transaction")

    validity = control.classify_observed_fact(
        fact,
        proof.current_context,
        required_scopes=dependency_scopes,
    )
    if validity.state != control.FACT_VALID:
        details = ",".join(validity.reasons) or validity.state
        raise TransactionRefusal(f"boundary fact is not CURRENT: {details}")
    return _non_empty(fact.observation_ref, field="boundary.observation_ref")


def _terminal_record(
    contract: operation.OperationContract,
    transaction_id: str,
    generations: Mapping[str, str],
    evidence: Sequence[operation.PhaseEvidence],
) -> TerminalRecord:
    derived = _derive(contract, evidence, transaction_id)
    return TerminalRecord(
        operation_id=contract.operation_id,
        target=contract.target,
        transaction_id=transaction_id,
        affected_domain_generations=dict(generations),
        evidence=tuple(evidence),
        derived=derived,
    )


class TransactionRunner:
    """Single imperative transaction kernel around the canonical reducers.

    This class owns invariant ordering only. Operation-specific request, dispatch and
    postcondition behavior arrives through ``OperationBinding``. All operation-state
    classification stays in ``operation_state_machine.py`` and physical-fact
    admission stays in ``control_state_machine.py``.
    """

    def run(
        self,
        request: object,
        *,
        ports: TransactionPorts,
        binding: OperationBinding,
        existing_evidence: Sequence[operation.PhaseEvidence] = (),
    ) -> TransactionResult:
        _validate_binding(binding)
        contract = binding.contract
        transaction_id = _non_empty(
            binding.transaction_id(request),
            field="transaction_id",
        )
        mutation_subject_ref = _non_empty(
            binding.mutation_subject_ref(request),
            field="mutation_subject_ref",
        )

        prior_evidence = tuple(existing_evidence)
        if prior_evidence:
            prior = _derive(contract, prior_evidence, transaction_id)
            if prior["state"] == "UNKNOWN_EXECUTION_OUTCOME":
                raise BlindRetryForbidden("blind retry forbidden after persisted dispatch")
            raise TransactionRefusal("transaction resume is not implemented")

        evidence: list[operation.PhaseEvidence] = []
        authority = ports.resolve_authority(request, contract)
        authority_ref = _non_empty(authority.source_ref, field="authority.source_ref")
        if not authority.authorized:
            evidence.append(
                _phase(
                    "resolve_authority",
                    operation.FAILED,
                    transaction_id,
                    authority_ref,
                )
            )
            record = _terminal_record(contract, transaction_id, {}, evidence)
            terminal_ref = _non_empty(
                ports.persist_terminal(record),
                field="terminal_ref",
            )
            return TransactionResult(tuple(evidence), record.derived, terminal_ref)

        evidence.append(
            _phase(
                "resolve_authority",
                operation.PASSED,
                transaction_id,
                authority_ref,
            )
        )

        with ports.acquire_mutation_scope(
            contract.target,
            transaction_id,
        ) as scope_ref:
            evidence.append(
                _phase(
                    "mutation_scope",
                    operation.PASSED,
                    transaction_id,
                    scope_ref,
                )
            )

            boundary = ports.prove_same_transaction_boundary(
                contract,
                transaction_id,
            )
            boundary_ref = _validate_boundary(
                contract,
                boundary,
                transaction_id,
            )
            evidence.append(
                _phase(
                    "phone_access_boundary",
                    operation.PASSED,
                    transaction_id,
                    boundary_ref,
                )
            )

            generations = operation.affected_domain_generation_updates(
                contract,
                transaction_id,
            )
            intent = MutationIntent(
                operation_id=contract.operation_id,
                target=contract.target,
                transaction_id=transaction_id,
                dispatch_step_id=binding.dispatch_step_id,
                mutation_subject_ref=mutation_subject_ref,
                affected_domain_generations=generations,
            )
            intent_ref = _non_empty(
                ports.persist_mutation_intent(intent),
                field="mutation_intent.source_ref",
            )
            evidence.append(
                _phase(
                    "mutation_intent",
                    operation.PASSED,
                    transaction_id,
                    intent_ref,
                )
            )
            evidence.append(
                _phase(
                    binding.dispatch_step_id,
                    operation.DISPATCHED,
                    transaction_id,
                    intent_ref,
                )
            )

            dispatched = _derive(contract, evidence, transaction_id)
            if dispatched["state"] != "UNKNOWN_EXECUTION_OUTCOME":
                raise RuntimeError("persisted dispatch must classify as unknown before result")

            try:
                receipt = binding.dispatch_once(request)
                receipt_ref = _non_empty(
                    receipt.source_ref,
                    field="dispatch_receipt.source_ref",
                )
            except Exception as error:
                unknown = _derive(contract, evidence, transaction_id)
                return TransactionResult(
                    tuple(evidence),
                    unknown,
                    None,
                    dispatch_error=f"{type(error).__name__}: {error}",
                )

            evidence.append(
                _phase(
                    binding.dispatch_step_id,
                    operation.PASSED,
                    transaction_id,
                    receipt_ref,
                )
            )

            postcondition = binding.verify_postcondition(request)
            post_ref = _non_empty(
                postcondition.source_ref,
                field="postcondition.source_ref",
            )
            evidence.append(
                _phase(
                    binding.postcondition_step_id,
                    operation.PASSED if postcondition.passed else operation.FAILED,
                    transaction_id,
                    post_ref,
                )
            )

            if postcondition.passed:
                evidence.append(
                    _phase(
                        binding.acceptance_step_id,
                        operation.PASSED,
                        transaction_id,
                        post_ref,
                    )
                )

            record = _terminal_record(
                contract,
                transaction_id,
                generations,
                evidence,
            )
            terminal_ref = _non_empty(
                ports.persist_terminal(record),
                field="terminal_ref",
            )
            return TransactionResult(tuple(evidence), record.derived, terminal_ref)
