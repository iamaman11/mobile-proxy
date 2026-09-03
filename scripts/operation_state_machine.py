from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, NamedTuple


CONTROL = "CONTROL"
DIAGNOSTIC = "DIAGNOSTIC"
AUDIT = "AUDIT"
CURRENT = "CURRENT"
STALE = "STALE"

PASSED = "PASSED"
FAILED = "FAILED"
SKIPPED = "SKIPPED"
DISPATCHED = "DISPATCHED"

CAUSAL_REUSE_ALLOWED = "CAUSAL_REUSE_ALLOWED"
SAME_TRANSACTION = "SAME_TRANSACTION"


@dataclass(frozen=True)
class StepContract:
    step_id: str
    kind: str
    failure_stage: str
    destructive: bool = False
    mutation_boundary: bool = False
    acceptance: bool = False


@dataclass(frozen=True)
class FactRequirement:
    """Physical fact requirement declared by an operation contract.

    ``freshness`` is deliberately semantic rather than wall-clock based:
    reusable durable facts are admitted through control_state_machine causal
    dependency equality, while SAME_TRANSACTION facts must be freshly produced
    for the exact operation transaction.
    """

    subject: str
    predicate: str
    freshness: str
    required_dependency_kinds: tuple[str, ...] = ()


@dataclass(frozen=True)
class OperationContract:
    operation_id: str
    target: str
    steps: tuple[StepContract, ...]
    recovery_steps: tuple[StepContract, ...] = ()
    fact_requirements: tuple[FactRequirement, ...] = ()
    affected_physical_domains: tuple[str, ...] = ()
    retryable: bool = False
    rollback_to_legacy_allowed: bool = False


class PhaseEvidence(NamedTuple):
    step_id: str
    status: str
    transaction_id: str
    source_ref: str
    authority: str = CONTROL
    lifecycle: str = CURRENT


class EvidenceConflict(RuntimeError):
    pass


_PHONE_ACCESS_BOUNDARY_FACT = FactRequirement(
    "phone",
    "registered_phone_access_proven",
    SAME_TRANSACTION,
    ("target", "observer", "transaction"),
)


ANDROID_PHONE_ACCESS_CERTIFICATION = OperationContract(
    operation_id="android.phone-access-certification.v1",
    target="android-production",
    steps=(
        StepContract("source_quality", "VERIFY", "SOURCE_AUTHORITY"),
        StepContract("runner_assignment", "OBSERVE", "RUNNER_ASSIGNMENT"),
        StepContract("source_delivery", "VERIFY", "SOURCE_FETCH"),
        StepContract("phone_access", "VERIFY", "ADB_SHELL", acceptance=True),
    ),
)


ANDROID_CAPABILITY_CERTIFICATION = OperationContract(
    operation_id="android.capability-certification.v1",
    target="android-production",
    steps=(
        StepContract("source_quality", "VERIFY", "SOURCE_AUTHORITY"),
        StepContract("runner_assignment", "OBSERVE", "RUNNER_ASSIGNMENT"),
        StepContract("source_delivery", "VERIFY", "SOURCE_FETCH"),
        StepContract("phone_access", "VERIFY", "ADB_SHELL"),
        StepContract("capability_inventory", "OBSERVE", "CAPABILITY", acceptance=True),
    ),
)


ANDROID_FILESYSTEM_CERTIFICATION = OperationContract(
    operation_id="android.filesystem-certification.v1",
    target="android-production",
    steps=(
        StepContract("source_quality", "VERIFY", "SOURCE_AUTHORITY"),
        StepContract("runner_assignment", "OBSERVE", "RUNNER_ASSIGNMENT"),
        StepContract("source_delivery", "VERIFY", "SOURCE_FETCH"),
        StepContract("phone_access_initial", "VERIFY", "ADB_SHELL"),
        StepContract("capability_inventory", "VERIFY", "CAPABILITY"),
        StepContract("mutation_lock", "VERIFY", "MUTATION_LOCK"),
        StepContract(
            "phone_access_boundary",
            "VERIFY",
            "MUTATION_BOUNDARY",
            mutation_boundary=True,
        ),
        StepContract("scratch_roundtrip", "MUTATE", "MUTATION_EXECUTION", destructive=True),
        StepContract("scratch_atomic_replace", "MUTATE", "MUTATION_EXECUTION", destructive=True),
        StepContract("managed_root_write", "MUTATE", "MUTATION_EXECUTION", destructive=True),
        StepContract("managed_atomic_replace", "MUTATE", "MUTATION_EXECUTION", destructive=True),
        StepContract("cleanup_verify", "VERIFY", "POSTCONDITION"),
        StepContract("accept", "ACCEPT", "POSTCONDITION", acceptance=True),
    ),
    recovery_steps=(
        StepContract("recovery_cleanup_scratch", "RECOVER", "RECOVERY", destructive=True),
        StepContract("recovery_cleanup_managed", "RECOVER", "RECOVERY", destructive=True),
        StepContract("recovery_verify_absent", "VERIFY", "RECOVERY", acceptance=True),
    ),
    fact_requirements=(_PHONE_ACCESS_BOUNDARY_FACT,),
    affected_physical_domains=("filesystem",),
    retryable=False,
    rollback_to_legacy_allowed=False,
)


ANDROID_CURRENT_SOURCE_CLEAN_INSTALL = OperationContract(
    operation_id="android.current-source-clean-install.v1",
    target="android-production",
    steps=(
        StepContract("source_quality", "VERIFY", "SOURCE_AUTHORITY"),
        StepContract("artifact_signed", "VERIFY", "ARTIFACT"),
        StepContract("runner_assignment", "OBSERVE", "RUNNER_ASSIGNMENT"),
        StepContract("source_delivery", "VERIFY", "SOURCE_FETCH"),
        StepContract("phone_access_initial", "VERIFY", "ADB_SHELL"),
        StepContract("capability_inventory", "VERIFY", "CAPABILITY"),
        StepContract("mutation_lock", "VERIFY", "MUTATION_LOCK"),
        StepContract(
            "phone_access_boundary",
            "VERIFY",
            "MUTATION_BOUNDARY",
            mutation_boundary=True,
        ),
        StepContract("stop_owned_runtime", "MUTATE", "MUTATION_EXECUTION", destructive=True),
        StepContract("remove_owned_runtime", "MUTATE", "MUTATION_EXECUTION", destructive=True),
        StepContract("uninstall_legacy_apk", "MUTATE", "MUTATION_EXECUTION", destructive=True),
        StepContract("install_new_apk", "MUTATE", "MUTATION_EXECUTION", destructive=True),
        StepContract("verify_new_apk", "VERIFY", "POSTCONDITION"),
        StepContract("materialize_runtime", "MUTATE", "MUTATION_EXECUTION", destructive=True),
        StepContract("verify_runtime", "VERIFY", "POSTCONDITION"),
        StepContract("start_runtime", "MUTATE", "MUTATION_EXECUTION", destructive=True),
        StepContract("structural_health", "ACCEPT", "STRUCTURAL_ACCEPTANCE"),
        StepContract("functional_probe", "ACCEPT", "FUNCTIONAL_ACCEPTANCE"),
        StepContract("accept", "ACCEPT", "FUNCTIONAL_ACCEPTANCE", acceptance=True),
    ),
    recovery_steps=(
        StepContract("recovery_classify", "RECOVER", "RECOVERY"),
        StepContract("recovery_stop_owned_runtime", "RECOVER", "RECOVERY", destructive=True),
        StepContract("recovery_remove_incomplete_runtime", "RECOVER", "RECOVERY", destructive=True),
        StepContract("recovery_normalize_package", "RECOVER", "RECOVERY", destructive=True),
        StepContract("recovery_verify_clean_baseline", "VERIFY", "RECOVERY", acceptance=True),
    ),
    fact_requirements=(_PHONE_ACCESS_BOUNDARY_FACT,),
    affected_physical_domains=("filesystem", "package", "runtime", "process"),
    retryable=False,
    rollback_to_legacy_allowed=False,
)


_OPERATION_CONTRACTS = {
    contract.operation_id: contract
    for contract in (
        ANDROID_PHONE_ACCESS_CERTIFICATION,
        ANDROID_CAPABILITY_CERTIFICATION,
        ANDROID_FILESYSTEM_CERTIFICATION,
        ANDROID_CURRENT_SOURCE_CLEAN_INSTALL,
    )
}


def operation_contract(operation_id: str) -> OperationContract:
    try:
        return _OPERATION_CONTRACTS[operation_id]
    except KeyError as error:
        raise ValueError(f"unknown operation contract: {operation_id}") from error


def affected_domain_generation_updates(
    contract: OperationContract,
    transaction_id: str,
) -> dict[str, str]:
    """Return the exact causal-generation transition required before dispatch.

    Adapters must durably persist this transition before a destructive command is
    allowed to reach the target. Persisting it and then crashing before dispatch is
    conservative (facts become stale unnecessarily) but safe. Dispatching before it
    is persisted is forbidden because an ambiguous result could otherwise leave
    pre-mutation facts reusable.
    """

    transaction_id = transaction_id.strip()
    if not transaction_id:
        raise ValueError("transaction_id must be non-empty")
    if any(character.isspace() for character in transaction_id):
        raise ValueError("transaction_id must not contain whitespace")

    updates: dict[str, str] = {}
    for domain in contract.affected_physical_domains:
        normalized = domain.strip()
        if (
            not normalized
            or "/" in normalized
            or any(character.isspace() for character in normalized)
        ):
            raise ValueError(f"invalid physical domain: {domain}")
        scope = f"domain/{normalized}"
        if scope in updates:
            raise ValueError(f"duplicate physical domain: {normalized}")
        updates[scope] = transaction_id

    if any(step.destructive for step in contract.steps) and not updates:
        raise ValueError("destructive operation must declare affected physical domains")
    return updates


def _current_control_evidence(
    evidence: Iterable[PhaseEvidence], transaction_id: str
) -> tuple[PhaseEvidence, ...]:
    return tuple(
        item
        for item in evidence
        if item.transaction_id == transaction_id
        and item.authority == CONTROL
        and item.lifecycle == CURRENT
    )


def _status_by_step(
    evidence: Iterable[PhaseEvidence], transaction_id: str
) -> dict[str, str]:
    statuses: dict[str, set[str]] = {}
    refs: dict[tuple[str, str], str] = {}
    allowed = {PASSED, FAILED, SKIPPED, DISPATCHED}

    for item in _current_control_evidence(evidence, transaction_id):
        if not item.source_ref:
            raise EvidenceConflict(f"missing source_ref for {item.step_id}")
        if item.status not in allowed:
            raise EvidenceConflict(f"invalid status for {item.step_id}: {item.status}")

        key = (item.step_id, item.status)
        previous_ref = refs.get(key)
        if previous_ref is not None and previous_ref != item.source_ref:
            raise EvidenceConflict(
                f"multiple current probe scopes for {item.step_id}:{item.status}"
            )
        refs[key] = item.source_ref
        statuses.setdefault(item.step_id, set()).add(item.status)

    result: dict[str, str] = {}
    for step_id, observed in statuses.items():
        terminal = observed & {PASSED, FAILED, SKIPPED}
        if len(terminal) > 1:
            raise EvidenceConflict(f"conflicting evidence for {step_id}")
        if DISPATCHED in observed and SKIPPED in terminal:
            raise EvidenceConflict(f"dispatched step cannot be skipped: {step_id}")
        if terminal:
            # DISPATCHED is a monotonic pre-result marker. The eventual PASSED or
            # FAILED result supersedes only the unknown outcome, not the fact that
            # the destructive boundary was crossed.
            result[step_id] = next(iter(terminal))
        else:
            result[step_id] = DISPATCHED
    return result


def _first_non_passed(
    steps: tuple[StepContract, ...], statuses: dict[str, str]
) -> StepContract | None:
    for step in steps:
        if statuses.get(step.step_id) != PASSED:
            return step
    return None


def _first_failed(
    steps: tuple[StepContract, ...], statuses: dict[str, str]
) -> StepContract | None:
    for step in steps:
        if statuses.get(step.step_id) == FAILED:
            return step
    return None


def _first_dispatched(
    steps: tuple[StepContract, ...], statuses: dict[str, str]
) -> StepContract | None:
    for step in steps:
        if statuses.get(step.step_id) == DISPATCHED:
            return step
    return None


def _destructive_started(
    steps: tuple[StepContract, ...], statuses: dict[str, str]
) -> bool:
    # DISPATCHED is a durable may-have-reached marker. A lost result is therefore
    # already across the recovery boundary even when no success/failure result exists.
    return any(
        step.destructive and statuses.get(step.step_id) in {PASSED, FAILED, DISPATCHED}
        for step in steps
    )


def _passed_later_step_before_required_predecessor(
    steps: tuple[StepContract, ...], statuses: dict[str, str]
) -> str | None:
    predecessor_open = False
    for step in steps:
        status = statuses.get(step.step_id)
        if status != PASSED:
            predecessor_open = True
            continue
        if predecessor_open:
            return step.step_id
    return None


def _boundary_passed(
    steps: tuple[StepContract, ...], statuses: dict[str, str]
) -> bool:
    return any(
        step.mutation_boundary and statuses.get(step.step_id) == PASSED
        for step in steps
    )


def _invalid_dispatch_step(
    steps: tuple[StepContract, ...], statuses: dict[str, str]
) -> str | None:
    for step in steps:
        if statuses.get(step.step_id) == DISPATCHED and not step.destructive:
            return step.step_id
    return None


def derive_operation_state(
    contract: OperationContract,
    evidence: Iterable[PhaseEvidence],
    *,
    transaction_id: str,
) -> dict[str, object]:
    evidence = tuple(evidence)
    known_steps = {step.step_id for step in contract.steps + contract.recovery_steps}

    try:
        statuses = _status_by_step(evidence, transaction_id)
    except EvidenceConflict as error:
        return {
            "operation_id": contract.operation_id,
            "transaction_id": transaction_id,
            "state": "CONFLICT",
            "current_step": None,
            "next_step": None,
            "failure_stage": None,
            "destructive_started": None,
            "recovery_required": True,
            "blocking_predicates": [str(error)],
        }

    unknown_steps = sorted(set(statuses) - known_steps)
    if unknown_steps:
        return {
            "operation_id": contract.operation_id,
            "transaction_id": transaction_id,
            "state": "INVALID_TRACE",
            "current_step": None,
            "next_step": None,
            "failure_stage": None,
            "destructive_started": None,
            "recovery_required": True,
            "blocking_predicates": [f"unknown_step={step}" for step in unknown_steps],
        }

    invalid_dispatch = _invalid_dispatch_step(
        contract.steps + contract.recovery_steps, statuses
    )
    if invalid_dispatch is not None:
        return {
            "operation_id": contract.operation_id,
            "transaction_id": transaction_id,
            "state": "INVALID_TRACE",
            "current_step": invalid_dispatch,
            "next_step": None,
            "failure_stage": "MUTATION_EXECUTION",
            "destructive_started": False,
            "recovery_required": True,
            "blocking_predicates": [f"dispatched_non_destructive_step={invalid_dispatch}"],
        }

    out_of_order = _passed_later_step_before_required_predecessor(
        contract.steps, statuses
    )
    if out_of_order is not None:
        return {
            "operation_id": contract.operation_id,
            "transaction_id": transaction_id,
            "state": "INVALID_TRACE",
            "current_step": out_of_order,
            "next_step": None,
            "failure_stage": None,
            "destructive_started": _destructive_started(contract.steps, statuses),
            "recovery_required": True,
            "blocking_predicates": [f"out_of_order_step={out_of_order}"],
        }

    destructive_started = _destructive_started(contract.steps, statuses)
    boundary_passed = _boundary_passed(contract.steps, statuses)
    if destructive_started and not boundary_passed:
        return {
            "operation_id": contract.operation_id,
            "transaction_id": transaction_id,
            "state": "INVALID_TRACE",
            "current_step": None,
            "next_step": None,
            "failure_stage": "MUTATION_BOUNDARY",
            "destructive_started": True,
            "recovery_required": True,
            "blocking_predicates": ["mutation_boundary=PASSED"],
        }

    dispatched = _first_dispatched(contract.steps, statuses)
    if dispatched is not None:
        recovery = _derive_recovery_state(contract, statuses)
        if recovery["state"] == "RECOVERED":
            state = "RECOVERED"
        elif recovery["state"] == "RECOVERING":
            state = "RECOVERING"
        elif recovery["state"] == "QUARANTINED":
            state = "QUARANTINED"
        else:
            state = "UNKNOWN_EXECUTION_OUTCOME"
        return {
            "operation_id": contract.operation_id,
            "transaction_id": transaction_id,
            "state": state,
            "current_step": dispatched.step_id,
            "next_step": recovery["next_step"],
            "failure_stage": "MUTATION_EXECUTION",
            "destructive_started": True,
            "recovery_required": state != "RECOVERED",
            "blocking_predicates": recovery["blocking_predicates"]
            if state != "UNKNOWN_EXECUTION_OUTCOME"
            else [
                f"execution_result_known={dispatched.step_id}",
                "blind_retry=FORBIDDEN",
            ],
        }

    failed = _first_failed(contract.steps, statuses)
    if failed is not None:
        if destructive_started:
            recovery = _derive_recovery_state(contract, statuses)
            return {
                "operation_id": contract.operation_id,
                "transaction_id": transaction_id,
                "state": recovery["state"],
                "current_step": failed.step_id,
                "next_step": recovery["next_step"],
                "failure_stage": failed.failure_stage,
                "destructive_started": True,
                "recovery_required": recovery["state"] != "RECOVERED",
                "blocking_predicates": recovery["blocking_predicates"],
            }
        return {
            "operation_id": contract.operation_id,
            "transaction_id": transaction_id,
            "state": "REFUSED",
            "current_step": failed.step_id,
            "next_step": None,
            "failure_stage": failed.failure_stage,
            "destructive_started": False,
            "recovery_required": False,
            "blocking_predicates": [f"{failed.step_id}=PASSED"],
        }

    first_open = _first_non_passed(contract.steps, statuses)
    if first_open is None:
        return {
            "operation_id": contract.operation_id,
            "transaction_id": transaction_id,
            "state": "ACCEPTED",
            "current_step": contract.steps[-1].step_id if contract.steps else None,
            "next_step": None,
            "failure_stage": None,
            "destructive_started": destructive_started,
            "recovery_required": False,
            "blocking_predicates": [],
        }

    if statuses.get(first_open.step_id) == SKIPPED:
        return {
            "operation_id": contract.operation_id,
            "transaction_id": transaction_id,
            "state": "REFUSED",
            "current_step": first_open.step_id,
            "next_step": None,
            "failure_stage": first_open.failure_stage,
            "destructive_started": destructive_started,
            "recovery_required": destructive_started,
            "blocking_predicates": [f"{first_open.step_id}=PASSED"],
        }

    if destructive_started:
        state = "TRANSACTION_ACTIVE"
    elif boundary_passed:
        state = "READY_TO_MUTATE"
    elif first_open.mutation_boundary:
        state = "READY_FOR_BOUNDARY_REPROOF"
    else:
        state = "PREPARING"

    return {
        "operation_id": contract.operation_id,
        "transaction_id": transaction_id,
        "state": state,
        "current_step": first_open.step_id,
        "next_step": first_open.step_id,
        "failure_stage": None,
        "destructive_started": destructive_started,
        "recovery_required": False,
        "blocking_predicates": [f"{first_open.step_id}=PASSED"],
    }


def _derive_recovery_state(
    contract: OperationContract, statuses: dict[str, str]
) -> dict[str, object]:
    if not contract.recovery_steps:
        return {
            "state": "QUARANTINED",
            "next_step": None,
            "blocking_predicates": ["recovery_contract=DEFINED"],
        }

    failed = _first_failed(contract.recovery_steps, statuses)
    if failed is not None:
        return {
            "state": "QUARANTINED",
            "next_step": None,
            "blocking_predicates": [f"{failed.step_id}=PASSED"],
        }

    dispatched = _first_dispatched(contract.recovery_steps, statuses)
    if dispatched is not None:
        return {
            "state": "UNKNOWN_EXECUTION_OUTCOME",
            "next_step": None,
            "blocking_predicates": [
                f"execution_result_known={dispatched.step_id}",
                "blind_retry=FORBIDDEN",
            ],
        }

    first_open = _first_non_passed(contract.recovery_steps, statuses)
    if first_open is None:
        return {
            "state": "RECOVERED",
            "next_step": None,
            "blocking_predicates": [],
        }

    if statuses.get(first_open.step_id) == SKIPPED:
        return {
            "state": "QUARANTINED",
            "next_step": None,
            "blocking_predicates": [f"{first_open.step_id}=PASSED"],
        }

    completed = any(
        statuses.get(step.step_id) == PASSED for step in contract.recovery_steps
    )
    return {
        "state": "RECOVERING" if completed else "RECOVERY_REQUIRED",
        "next_step": first_open.step_id,
        "blocking_predicates": [f"{first_open.step_id}=PASSED"],
    }


def expected_step_ids(contract: OperationContract) -> tuple[str, ...]:
    return tuple(step.step_id for step in contract.steps)


def recovery_step_ids(contract: OperationContract) -> tuple[str, ...]:
    return tuple(step.step_id for step in contract.recovery_steps)