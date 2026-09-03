from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
import json
import re
from typing import Iterable, Mapping, Protocol, Sequence

import control_state_machine as control
import operation_state_machine as operation


SEMANTIC_REQUEST_SCHEMA = "production-control-request.v1"

REQUESTED = "REQUESTED"
AUTHORIZED = "AUTHORIZED"
OBSERVED_PREFLIGHT = "OBSERVED/PREFLIGHT"
INTENT_PERSISTED = "INTENT_PERSISTED"
LIFECYCLE_DISPATCHED = "DISPATCHED"
POSTCONDITION_VERIFIED = "POSTCONDITION_VERIFIED"

TERMINAL_ACCEPTED = "ACCEPTED"
TERMINAL_REFUSED = "REFUSED"
TERMINAL_UNKNOWN = "UNKNOWN"
TERMINAL_QUARANTINED = "QUARANTINED"

TERMINAL_STATES = frozenset(
    {
        TERMINAL_ACCEPTED,
        TERMINAL_REFUSED,
        TERMINAL_UNKNOWN,
        TERMINAL_QUARANTINED,
    }
)

_OPERATION_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}")
_CURSOR_RE = re.compile(r"issue179-comment-[1-9][0-9]*")
_REQUEST_ID_RE = re.compile(r"req-sha256:[0-9a-f]{64}")
_GENERATION_RE = re.compile(r"gen-sha256:[0-9a-f]{64}")


class TransactionRefusal(RuntimeError):
    """Fail-closed admission error before a physical dispatch is allowed."""


class BlindRetryForbidden(TransactionRefusal):
    """The transaction already crossed a durable dispatch boundary."""


class DispatchOutcomeUnknown(RuntimeError):
    """An operation binding cannot prove whether dispatch reached the target."""


class SemanticRequestError(TransactionRefusal):
    """The routed semantic request does not match the canonical request contract."""


@dataclass(frozen=True)
class SemanticRequestIdentity:
    """Typed semantic identity produced by the private Issue #1 router.

    The private router owns the accepted request digest construction. This public
    kernel owns the canonical envelope shape and validates routed identity before
    it can participate in physical transaction identity. GitHub comment/run/attempt
    identifiers are intentionally absent because they are provenance, not semantic
    mutation identity.
    """

    schema: str
    request_id: str
    operation: str
    arguments: tuple[str, ...]
    authority_cursor: str
    desired_generation: str

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "operation": self.operation,
            "arguments": list(self.arguments),
            "authority_cursor": self.authority_cursor,
            "desired_generation": self.desired_generation,
        }


@dataclass(frozen=True)
class KernelStepRoles:
    """Map an operation's declarative steps onto the universal lifecycle."""

    authority_step_id: str
    mutation_scope_step_id: str
    preflight_step_id: str
    intent_step_id: str
    dispatch_step_id: str
    postcondition_step_id: str
    acceptance_step_id: str


@dataclass(frozen=True)
class AuthorityProof:
    authorized: bool
    source_ref: str


@dataclass(frozen=True)
class BoundaryProof:
    """One observed fact plus the exact causal context used to validate it."""

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
    control_request_id: str = ""
    authority_cursor: str = ""
    desired_generation: str = ""
    preflight_observation_refs: tuple[str, ...] = ()


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
    lifecycle_state: str = REQUESTED
    control_request_id: str = ""
    authority_cursor: str = ""
    desired_generation: str = ""


@dataclass(frozen=True)
class TransactionResult:
    evidence: tuple[operation.PhaseEvidence, ...]
    derived: Mapping[str, object]
    terminal_ref: str | None
    dispatch_error: str | None = None
    lifecycle_state: str = REQUESTED
    control_request_id: str = ""


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
    """Operation-specific edge consumed by the universal physical kernel.

    The binding supplies request interpretation plus one physical dispatch and one
    postcondition observation. It does not own authority ordering, locking, causal
    preflight admission, generation invalidation, intent durability, dispatch
    classification, terminal classification, or retry policy.
    """

    contract: operation.OperationContract
    kernel_steps: KernelStepRoles

    def transaction_id(self, request: object) -> str: ...

    def mutation_subject_ref(self, request: object) -> str: ...

    def dispatch_once(self, request: object) -> DispatchReceipt: ...

    def verify_postcondition(self, request: object) -> PostconditionProof: ...


def normalize_semantic_arguments(arguments: Iterable[str]) -> tuple[str, ...]:
    result = tuple(str(value).strip() for value in arguments)
    if any(not value for value in result):
        raise SemanticRequestError("empty semantic argument")
    if any("\n" in value or "\r" in value or "\x00" in value for value in result):
        raise SemanticRequestError("multiline/NUL semantic argument")
    return result


def validate_semantic_request_identity(
    identity: SemanticRequestIdentity,
) -> SemanticRequestIdentity:
    """Validate one routed semantic envelope without inventing a digest contract.

    Request-id and desired-generation digests are produced at the already accepted
    private router boundary. Public code validates exact schema/shape and owns all
    downstream semantic use. This deliberately avoids introducing a second raw
    digest implementation in first-party Python, which repository policy forbids.
    """

    if not isinstance(identity, SemanticRequestIdentity):
        raise SemanticRequestError("invalid semantic request identity type")
    if identity.schema != SEMANTIC_REQUEST_SCHEMA:
        raise SemanticRequestError("invalid semantic request schema")

    operation_id = identity.operation.strip()
    authority_cursor = identity.authority_cursor.strip()
    request_id = identity.request_id.strip()
    generation = identity.desired_generation.strip()
    arguments = normalize_semantic_arguments(identity.arguments)

    if _OPERATION_RE.fullmatch(operation_id) is None:
        raise SemanticRequestError("invalid operation name")
    if _CURSOR_RE.fullmatch(authority_cursor) is None:
        raise SemanticRequestError("invalid authority cursor")
    if _REQUEST_ID_RE.fullmatch(request_id) is None:
        raise SemanticRequestError("invalid semantic request id")
    if _GENERATION_RE.fullmatch(generation) is None:
        raise SemanticRequestError("invalid desired generation")
    if arguments != identity.arguments:
        raise SemanticRequestError("semantic arguments are not normalized")
    if operation_id != identity.operation:
        raise SemanticRequestError("operation name is not normalized")
    if authority_cursor != identity.authority_cursor:
        raise SemanticRequestError("authority cursor is not normalized")
    if request_id != identity.request_id or generation != identity.desired_generation:
        raise SemanticRequestError("semantic digest fields are not normalized")
    return identity


def routed_semantic_request_identity(
    *,
    request_id: str,
    operation: str,
    arguments: Iterable[str],
    authority_cursor: str,
    desired_generation: str,
) -> SemanticRequestIdentity:
    """Construct the public typed view of an already routed semantic request."""

    identity = SemanticRequestIdentity(
        schema=SEMANTIC_REQUEST_SCHEMA,
        request_id=request_id,
        operation=operation,
        arguments=tuple(arguments),
        authority_cursor=authority_cursor,
        desired_generation=desired_generation,
    )
    return validate_semantic_request_identity(identity)


def derive_physical_transaction_id(
    semantic: SemanticRequestIdentity,
    physical_operation_id: str,
) -> str:
    """Derive one stable physical transaction identity without provenance inputs.

    The semantic request id already commits to normalized arguments, authority
    cursor and desired generation at the router boundary. The physical operation id
    disambiguates subtransactions when one semantic control request orchestrates
    more than one physical effect. No new digest primitive is introduced here.
    """

    semantic = validate_semantic_request_identity(semantic)
    physical_operation_id = physical_operation_id.strip()
    if _OPERATION_RE.fullmatch(physical_operation_id) is None:
        raise SemanticRequestError("invalid physical operation name")

    request_digest = semantic.request_id.removeprefix("req-sha256:")
    generation_digest = semantic.desired_generation.removeprefix("gen-sha256:")
    return (
        "physical-tx-v1:"
        f"{request_digest}:{physical_operation_id}:{generation_digest}"
    )


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


def _roles(binding: OperationBinding) -> KernelStepRoles:
    roles = getattr(binding, "kernel_steps", None)
    if isinstance(roles, KernelStepRoles):
        return roles

    # Compatibility bridge for the already accepted first physical vertical
    # slice. It is intentionally expressed in one place so existing bindings move
    # through this universal kernel without creating a second transaction engine.
    dispatch_step_id = getattr(binding, "dispatch_step_id", None)
    postcondition_step_id = getattr(binding, "postcondition_step_id", None)
    acceptance_step_id = getattr(binding, "acceptance_step_id", None)
    if all(
        isinstance(value, str) and value.strip()
        for value in (dispatch_step_id, postcondition_step_id, acceptance_step_id)
    ):
        return KernelStepRoles(
            authority_step_id="resolve_authority",
            mutation_scope_step_id="mutation_scope",
            preflight_step_id="phone_access_boundary",
            intent_step_id="mutation_intent",
            dispatch_step_id=dispatch_step_id,
            postcondition_step_id=postcondition_step_id,
            acceptance_step_id=acceptance_step_id,
        )
    raise TransactionRefusal("operation binding must declare universal kernel step roles")


def _validate_binding(binding: OperationBinding) -> KernelStepRoles:
    contract = binding.contract
    roles = _roles(binding)
    steps = tuple(contract.steps)
    by_id = {step.step_id: (index, step) for index, step in enumerate(steps)}
    if len(by_id) != len(steps):
        raise TransactionRefusal("operation contract has duplicate step ids")

    role_steps = (
        roles.authority_step_id,
        roles.mutation_scope_step_id,
        roles.preflight_step_id,
        roles.intent_step_id,
        roles.dispatch_step_id,
        roles.postcondition_step_id,
        roles.acceptance_step_id,
    )
    if len(set(role_steps)) != len(role_steps):
        raise TransactionRefusal("universal kernel step roles must be distinct")
    if any(step_id not in by_id for step_id in role_steps):
        raise TransactionRefusal("operation binding does not match operation contract")

    indexes = [by_id[step_id][0] for step_id in role_steps]
    if indexes != sorted(indexes):
        raise TransactionRefusal("universal kernel steps are out of contract order")

    boundary = by_id[roles.preflight_step_id][1]
    dispatch = by_id[roles.dispatch_step_id][1]
    postcondition = by_id[roles.postcondition_step_id][1]
    acceptance = by_id[roles.acceptance_step_id][1]
    if not boundary.mutation_boundary:
        raise TransactionRefusal("operation binding lacks mutation boundary")
    if not dispatch.destructive:
        raise TransactionRefusal("operation dispatch step must be destructive")
    if postcondition.destructive:
        raise TransactionRefusal("postcondition step must be non-destructive")
    if not acceptance.acceptance:
        raise TransactionRefusal("acceptance step must be an acceptance step")
    if contract.retryable:
        raise TransactionRefusal(
            "physical mutation binding cannot opt into blind retry at the kernel layer"
        )

    operation.affected_domain_generation_updates(contract, "kernel-validation")
    return roles


def _validate_one_fact_requirement(
    requirement: operation.FactRequirement,
    proof: BoundaryProof,
    transaction_id: str,
) -> str:
    fact = proof.fact
    if fact.subject != requirement.subject or fact.predicate != requirement.predicate:
        raise TransactionRefusal("preflight fact does not match operation contract")
    if fact.value is not True:
        raise TransactionRefusal("preflight fact value is not true")
    if fact.target.strip() == "":
        raise TransactionRefusal("preflight fact target is empty")

    dependencies = tuple(fact.dependencies)
    dependency_scopes: list[str] = []
    for kind in requirement.required_dependency_kinds:
        matches = [item for item in dependencies if item.scope.startswith(f"{kind}/")]
        if len(matches) != 1:
            raise TransactionRefusal(
                f"preflight fact requires exactly one {kind} dependency"
            )
        dependency_scopes.append(matches[0].scope)
        if kind == "transaction" and requirement.freshness == operation.SAME_TRANSACTION:
            expected_scope = f"transaction/{transaction_id}"
            if matches[0].scope != expected_scope or matches[0].identity != transaction_id:
                raise TransactionRefusal("preflight fact is not from this transaction")

    if requirement.freshness == operation.SAME_TRANSACTION:
        transaction_dependencies = [
            item for item in dependencies if item.scope.startswith("transaction/")
        ]
        if len(transaction_dependencies) != 1:
            raise TransactionRefusal(
                "SAME_TRANSACTION preflight fact requires one transaction dependency"
            )
        item = transaction_dependencies[0]
        if item.scope != f"transaction/{transaction_id}" or item.identity != transaction_id:
            raise TransactionRefusal("preflight fact is not from this transaction")
    elif requirement.freshness != operation.CAUSAL_REUSE_ALLOWED:
        raise TransactionRefusal(
            f"unsupported fact freshness requirement: {requirement.freshness}"
        )

    validity = control.classify_observed_fact(
        fact,
        proof.current_context,
        required_scopes=dependency_scopes,
    )
    if validity.state != control.FACT_VALID:
        details = ",".join(validity.reasons) or validity.state
        raise TransactionRefusal(f"preflight fact is not CURRENT: {details}")
    return _non_empty(fact.observation_ref, field="preflight.observation_ref")


def _preflight_proofs(
    ports: TransactionPorts,
    contract: operation.OperationContract,
    transaction_id: str,
) -> tuple[BoundaryProof, ...]:
    provider = getattr(ports, "prove_preflight_requirements", None)
    if callable(provider):
        proofs = tuple(provider(contract, transaction_id))
    else:
        # Backward-compatible adapter surface for the first physical vertical.
        # Multi-fact operations must implement prove_preflight_requirements.
        proofs = (ports.prove_same_transaction_boundary(contract, transaction_id),)
    return proofs


def _validate_preflight(
    contract: operation.OperationContract,
    proofs: Sequence[BoundaryProof],
    transaction_id: str,
) -> tuple[str, ...]:
    requirements = tuple(contract.fact_requirements)
    if not requirements:
        raise TransactionRefusal(
            "physical mutation operation must declare at least one preflight fact requirement"
        )
    if len(proofs) != len(requirements):
        raise TransactionRefusal(
            "preflight proof count does not match operation fact requirements"
        )

    unused = list(proofs)
    refs: list[str] = []
    for requirement in requirements:
        matches = [
            item
            for item in unused
            if item.fact.subject == requirement.subject
            and item.fact.predicate == requirement.predicate
        ]
        if len(matches) != 1:
            raise TransactionRefusal(
                f"preflight requirement is missing or ambiguous: "
                f"{requirement.subject}.{requirement.predicate}"
            )
        proof = matches[0]
        unused.remove(proof)
        if proof.fact.target != contract.target:
            raise TransactionRefusal("preflight fact target does not match operation target")
        refs.append(_validate_one_fact_requirement(requirement, proof, transaction_id))

    if unused:
        raise TransactionRefusal("unexpected preflight proof")
    return tuple(refs)


def _combined_preflight_ref(refs: Sequence[str]) -> str:
    if not refs:
        raise TransactionRefusal("preflight observation refs are empty")
    if len(refs) == 1:
        return _non_empty(refs[0], field="preflight.source_ref")
    for ref in refs:
        _non_empty(ref, field="preflight.source_ref")
    canonical = json.dumps(sorted(refs), separators=(",", ":"), ensure_ascii=True)
    return f"preflight-set-v1:{canonical}"


def _semantic_identity(
    binding: OperationBinding,
    request: object,
) -> SemanticRequestIdentity | None:
    provider = getattr(binding, "semantic_request_identity", None)
    if not callable(provider):
        return None
    identity = provider(request)
    if identity is None:
        return None
    return validate_semantic_request_identity(identity)


def _lifecycle_state(
    contract: operation.OperationContract,
    evidence: Sequence[operation.PhaseEvidence],
    transaction_id: str,
    roles: KernelStepRoles,
) -> str:
    derived = _derive(contract, evidence, transaction_id)
    reducer_state = str(derived.get("state", ""))

    if reducer_state == "ACCEPTED":
        return TERMINAL_ACCEPTED
    if reducer_state == "REFUSED":
        return TERMINAL_REFUSED
    if reducer_state == "UNKNOWN_EXECUTION_OUTCOME":
        return TERMINAL_UNKNOWN
    if reducer_state in {
        "QUARANTINED",
        "RECOVERY_REQUIRED",
        "RECOVERING",
        "RECOVERED",
        "CONFLICT",
        "INVALID_TRACE",
    }:
        return TERMINAL_QUARANTINED

    statuses = {
        (item.step_id, item.status)
        for item in evidence
        if item.transaction_id == transaction_id
        and item.authority == operation.CONTROL
        and item.lifecycle == operation.CURRENT
    }
    if (
        (roles.postcondition_step_id, operation.PASSED) in statuses
        or (roles.postcondition_step_id, operation.FAILED) in statuses
    ):
        return POSTCONDITION_VERIFIED
    if (
        (roles.dispatch_step_id, operation.DISPATCHED) in statuses
        or (roles.dispatch_step_id, operation.PASSED) in statuses
        or (roles.dispatch_step_id, operation.FAILED) in statuses
    ):
        return LIFECYCLE_DISPATCHED
    if (roles.intent_step_id, operation.PASSED) in statuses:
        return INTENT_PERSISTED
    if (roles.preflight_step_id, operation.PASSED) in statuses:
        return OBSERVED_PREFLIGHT
    if (roles.authority_step_id, operation.PASSED) in statuses:
        return AUTHORIZED
    return REQUESTED


def _terminal_record(
    contract: operation.OperationContract,
    transaction_id: str,
    generations: Mapping[str, str],
    evidence: Sequence[operation.PhaseEvidence],
    roles: KernelStepRoles,
    semantic: SemanticRequestIdentity | None,
) -> TerminalRecord:
    derived = _derive(contract, evidence, transaction_id)
    return TerminalRecord(
        operation_id=contract.operation_id,
        target=contract.target,
        transaction_id=transaction_id,
        affected_domain_generations=dict(generations),
        evidence=tuple(evidence),
        derived=derived,
        lifecycle_state=_lifecycle_state(
            contract,
            evidence,
            transaction_id,
            roles,
        ),
        control_request_id="" if semantic is None else semantic.request_id,
        authority_cursor="" if semantic is None else semantic.authority_cursor,
        desired_generation="" if semantic is None else semantic.desired_generation,
    )


class TransactionRunner:
    """Universal imperative physical transaction kernel around canonical reducers.

    Invariant order:

      semantic request -> authority -> global mutation scope -> causal preflight
      -> durable intent/generation invalidation -> exactly-once dispatch
      -> independent postcondition -> durable terminal classification

    The kernel never owns operation-specific device commands. Bindings own only
    request interpretation, one physical dispatch, and one postcondition observer.
    """

    def run(
        self,
        request: object,
        *,
        ports: TransactionPorts,
        binding: OperationBinding,
        existing_evidence: Sequence[operation.PhaseEvidence] = (),
    ) -> TransactionResult:
        roles = _validate_binding(binding)
        contract = binding.contract
        transaction_id = _non_empty(
            binding.transaction_id(request),
            field="transaction_id",
        )
        mutation_subject_ref = _non_empty(
            binding.mutation_subject_ref(request),
            field="mutation_subject_ref",
        )
        semantic = _semantic_identity(binding, request)
        if semantic is not None:
            expected_transaction_id = derive_physical_transaction_id(
                semantic,
                contract.operation_id,
            )
            if transaction_id != expected_transaction_id:
                raise SemanticRequestError(
                    "transaction_id does not match semantic physical transaction identity"
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
                    roles.authority_step_id,
                    operation.FAILED,
                    transaction_id,
                    authority_ref,
                )
            )
            record = _terminal_record(
                contract,
                transaction_id,
                {},
                evidence,
                roles,
                semantic,
            )
            terminal_ref = _non_empty(
                ports.persist_terminal(record),
                field="terminal_ref",
            )
            return TransactionResult(
                tuple(evidence),
                record.derived,
                terminal_ref,
                lifecycle_state=record.lifecycle_state,
                control_request_id=record.control_request_id,
            )

        evidence.append(
            _phase(
                roles.authority_step_id,
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
                    roles.mutation_scope_step_id,
                    operation.PASSED,
                    transaction_id,
                    scope_ref,
                )
            )

            proofs = _preflight_proofs(ports, contract, transaction_id)
            preflight_refs = _validate_preflight(
                contract,
                proofs,
                transaction_id,
            )
            evidence.append(
                _phase(
                    roles.preflight_step_id,
                    operation.PASSED,
                    transaction_id,
                    _combined_preflight_ref(preflight_refs),
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
                dispatch_step_id=roles.dispatch_step_id,
                mutation_subject_ref=mutation_subject_ref,
                affected_domain_generations=generations,
                control_request_id="" if semantic is None else semantic.request_id,
                authority_cursor="" if semantic is None else semantic.authority_cursor,
                desired_generation="" if semantic is None else semantic.desired_generation,
                preflight_observation_refs=preflight_refs,
            )
            intent_ref = _non_empty(
                ports.persist_mutation_intent(intent),
                field="mutation_intent.source_ref",
            )
            evidence.append(
                _phase(
                    roles.intent_step_id,
                    operation.PASSED,
                    transaction_id,
                    intent_ref,
                )
            )
            evidence.append(
                _phase(
                    roles.dispatch_step_id,
                    operation.DISPATCHED,
                    transaction_id,
                    intent_ref,
                )
            )

            dispatched = _derive(contract, evidence, transaction_id)
            if dispatched["state"] != "UNKNOWN_EXECUTION_OUTCOME":
                raise RuntimeError(
                    "persisted dispatch must classify as unknown before result"
                )

            try:
                receipt = binding.dispatch_once(request)
                receipt_ref = _non_empty(
                    receipt.source_ref,
                    field="dispatch_receipt.source_ref",
                )
            except Exception as error:
                unknown = _derive(contract, evidence, transaction_id)
                lifecycle = _lifecycle_state(
                    contract,
                    evidence,
                    transaction_id,
                    roles,
                )
                if lifecycle != TERMINAL_UNKNOWN:
                    raise RuntimeError("post-dispatch ambiguity must classify as UNKNOWN")
                return TransactionResult(
                    tuple(evidence),
                    unknown,
                    None,
                    dispatch_error=f"{type(error).__name__}: {error}",
                    lifecycle_state=lifecycle,
                    control_request_id="" if semantic is None else semantic.request_id,
                )

            evidence.append(
                _phase(
                    roles.dispatch_step_id,
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
                    roles.postcondition_step_id,
                    operation.PASSED
                    if postcondition.passed
                    else operation.FAILED,
                    transaction_id,
                    post_ref,
                )
            )

            if postcondition.passed:
                evidence.append(
                    _phase(
                        roles.acceptance_step_id,
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
                roles,
                semantic,
            )
            terminal_ref = _non_empty(
                ports.persist_terminal(record),
                field="terminal_ref",
            )
            return TransactionResult(
                tuple(evidence),
                record.derived,
                terminal_ref,
                lifecycle_state=record.lifecycle_state,
                control_request_id=record.control_request_id,
            )
