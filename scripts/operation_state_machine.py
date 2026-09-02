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


@dataclass(frozen=True)
class StepContract:
    step_id: str
    kind: str
    failure_stage: str
    destructive: bool = False
    mutation_boundary: bool = False
    acceptance: bool = False


@dataclass(frozen=True)
class OperationContract:
    operation_id: str
    target: str
    steps: tuple[StepContract, ...]
    recovery_steps: tuple[StepContract, ...] = ()
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
    retryable=False,
    rollback_to_legacy_allowed=False,
)


_OPERATION_CONTRACTS = {
    contract.operation_id: contract
    for contract in (
        ANDROID_PHONE_ACCESS_CERTIFICATION,
        ANDROID_CAPABILITY_CERTIFICATION,
        ANDROID_CURRENT_SOURCE_CLEAN_INSTALL,
    )
}


def operation_contract(operation_id: str) -> OperationContract:
    try:
        return _OPERATION_CONTRACTS[operation_id]
    except KeyError as error:
        raise ValueError(f"unknown operation contract: {operation_id}") from error


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
    result: dict[str, str] = {}
    refs: dict[str, str] = {}
    for item in _current_control_evidence(evidence, transaction_id):
        if not item.source_ref:
            raise EvidenceConflict(f"missing source_ref for {item.step_id}")
        if item.status not in {PASSED, FAILED, SKIPPED}:
            raise EvidenceConflict(f"invalid status for {item.step_id}: {item.status}")
        previous = result.get(item.step_id)
        if previous is not None and previous != item.status:
            raise EvidenceConflict(f"conflicting evidence for {item.step_id}")
        previous_ref = refs.get(item.step_id)
        if previous_ref is not None and previous_ref != item.source_ref:
            raise EvidenceConflict(f"multiple current probe scopes for {item.step_id}")
        result[item.step_id] = item.status
        refs[item.step_id] = item.source_ref
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


def _destructive_started(
    steps: tuple[StepContract, ...], statuses: dict[str, str]
) -> bool:
    return any(step.destructive and statuses.get(step.step_id) == PASSED for step in steps)


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

    out_of_order = _passed_later_step_before_required_predecessor(contract.steps, statuses)
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
            "current_step": "accept",
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
