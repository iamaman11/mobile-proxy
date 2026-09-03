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

CAUSAL_REUSE = "CAUSAL_REUSE"
SAME_SESSION = "SAME_SESSION"
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
    step_id: str
    subject: str
    predicate: str
    required_scopes: tuple[str, ...]
    freshness: str = CAUSAL_REUSE


@dataclass(frozen=True)
class OperationContract:
    operation_id: str
    target: str
    steps: tuple[StepContract, ...]
    recovery_steps: tuple[StepContract, ...] = ()
    fact_requirements: tuple[FactRequirement, ...] = ()
    affected_domains: tuple[str, ...] = ()
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


_PHONE_ACCESS_SCOPES = (
    "target/android-production",
    "observer/phone-access",
    "session/android-production",
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
    fact_requirements=(
        FactRequirement(
            "phone_access",
            "phone",
            "adb_shell_probe",
            _PHONE_ACCESS_SCOPES,
            SAME_SESSION,
        ),
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
    fact_requirements=(
        FactRequirement(
            "phone_access",
            "phone",
            "adb_shell_probe",
            _PHONE_ACCESS_SCOPES,
            SAME_SESSION,
        ),
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
    fact_requirements=(
        FactRequirement(
            "phone_access_initial",
            "phone",
            "adb_shell_probe",
            _PHONE_ACCESS_SCOPES,
            SAME_SESSION,
        ),
        FactRequirement(
            "phone_access_boundary",
            "phone",
            "adb_shell_probe",
            _PHONE_ACCESS_SCOPES + ("transaction/android-production",),
            SAME_TRANSACTION,
        ),
    ),
    affected_domains=("domain/filesystem",),
    retryable=False,
    rollback_to_legacy_allowed=False,
)


ANDROID_FILESYSTEM_QUARANTINE_CLEANUP = OperationContract(
    operation_id="android.filesystem-quarantine-cleanup.v1",
    target="android-production",
    steps=(
        StepContract("source_quality", "VERIFY", "SOURCE_AUTHORITY"),
        StepContract("runner_assignment", "OBSERVE", "RUNNER_ASSIGNMENT"),
        StepContract("source_delivery", "VERIFY", "SOURCE_FETCH"),
        StepContract("phone_access_initial", "VERIFY", "ADB_SHELL"),
        StepContract("quarantine_observation", "VERIFY", "POSTCONDITION"),
        StepContract("mutation_lock", "VERIFY", "MUTATION_LOCK"),
        StepContract(
            "phone_access_boundary",
            "VERIFY",
            "MUTATION_BOUNDARY",
            mutation_boundary=True,
        ),
        StepContract("cleanup_exact_paths", "MUTATE", "MUTATION_EXECUTION", destructive=True),
        StepContract("cleanup_verify", "VERIFY", "POSTCONDITION"),
        StepContract("accept", "ACCEPT", "POSTCONDITION", acceptance=True),
    ),
    recovery_steps=(
        StepContract("recovery_observe_filesystem", "RECOVER", "RECOVERY"),
        StepContract("recovery_verify_absent", "VERIFY", "RECOVERY", acceptance=True),
    ),
    fact_requirements=(
        FactRequirement(
            "quarantine_observation",
            "filesystem-quarantine",
            "cleanup_admissible",
            (
                "target/android-production",
                "observer/filesystem-quarantine",
                "domain/filesystem",
            ),
            CAUSAL_REUSE,
        ),
        FactRequirement(
            "phone_access_boundary",
            "phone",
            "adb_shell_probe",
            _PHONE_ACCESS_SCOPES + ("transaction/android-production",),
            SAME_TRANSACTION,
        ),
    ),
    affected_domains=("domain/filesystem",),
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
    fact_requirements=(
        FactRequirement(
            "phone_access_initial",
            "phone",
            "adb_shell_probe",
            _PHONE_ACCESS_SCOPES,
            SAME_SESSION,
        ),
        FactRequirement(
            "phone_access_boundary",
            "phone",
            "adb_shell_probe",
            _PHONE_ACCESS_SCOPES + ("transaction/android-production",),
            SAME_TRANSACTION,
        ),
    ),
    affected_domains=(
        "domain/filesystem",
        "domain/package",
        "domain/runtime",
        "domain/process",
        "domain/connectivity",
    ),
    retryable=False,
    rollback_to_legacy_allowed=False,
)


_OPERATION_CONTRACTS = {
    contract.operation_id: contract
    for contract in (
        ANDROID_PHONE_ACCESS_CERTIFICATION,
        ANDROID_CAPABILITY_CERTIFICATION,
        ANDROID_FILESYSTEM_CERTIFICATION,
        ANDROID_FILESYSTEM_QUARANTINE_CLEANUP,
        ANDROID_CURRENT_SOURCE_CLEAN_INSTALL,
    )
}


def operation_contract(operation_id: str) -> OperationContract:
    try:
        return _OPERATION_CONTRACTS[operation_id]
    except KeyError as error:
        raise ValueError(f"unknown operation contract: {operation_id}") from error


def fact_requirements_for_step(
    contract: OperationContract, step_id: str
) -> tuple[FactRequirement, ...]:
    return tuple(
        requirement
        for requirement in contract.fact_requirements
        if requirement.step_id == step_id
    )


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
    grouped: dict[str, list[PhaseEvidence]] = {}
    for item in _current_control_evidence(evidence, transaction_id):
        if not item.source_ref:
            raise EvidenceConflict(f"missing source_ref for {item.step_id}")
        if item.status not in {PASSED, FAILED, SKIPPED, DISPATCHED}:
            raise EvidenceConflict(f"invalid status for {item.step_id}: {item.status}")
        grouped.setdefault(item.step_id, []).append(item)

    result: dict[str, str] = {}
    for step_id, items in grouped.items():
        statuses = {item.status for item in items}
        refs_by_status = {
            status: {item.source_ref for item in items if item.status == status}
            for status in statuses
        }
        if any(len(refs) != 1 for refs in refs_by_status.values()):
            raise EvidenceConflict(f"multiple current probe scopes for {step_id}")

        if statuses == {DISPATCHED}:
            result[step_id] = DISPATCHED
            continue
        if statuses == {DISPATCHED, PASSED}:
            result[step_id] = PASSED
            continue
        if statuses == {DISPATCHED, FAILED}:
            result[step_id] = FAILED
            continue
        if len(statuses) == 1:
            result[step_id] = next(iter(statuses))
            continue
        raise EvidenceConflict(f"conflicting evidence for {step_id}")
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


def _first_unknown_execution(
    steps: tuple[StepContract, ...], statuses: dict[str, str]
) -> StepContract | None:
    for step in steps:
        if step.destructive and statuses.get(step.step_id) == DISPATCHED:
            return step
    return None


def _raw_destructive_dispatch_seen(
    contract: OperationContract,
    evidence: Iterable[PhaseEvidence],
    transaction_id: str,
) -> bool:
    destructive_ids = {
        step.step_id
        for step in contract.steps + contract.recovery_steps
        if step.destructive
    }
    return any(
        item.step_id in destructive_ids
        and item.status in {DISPATCHED, PASSED, FAILED}
        for item in _current_control_evidence(evidence, transaction_id)
    )


def derive_affected_domain_generations(
    contract: OperationContract,
    evidence: Iterable[PhaseEvidence],
    *,
    transaction_id: str,
) -> dict[str, str]:
    if not _raw_destructive_dispatch_seen(contract, evidence, transaction_id):
        return {}
    return {scope: transaction_id for scope in contract.affected_domains}


def _destructive_started(
    steps: tuple[StepContract, ...], statuses: dict[str, str]
) -> bool:
    # DISPATCHED means the command may have reached the target even if the result
    # was lost. PASSED and FAILED are terminal observations after the same boundary.
    return any(
        step.destructive and statuses.get(step.step_id) in {DISPATCHED, PASSED, FAILED}
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


def derive_operation_state(
    contract: OperationContract,
    evidence: Iterable[PhaseEvidence],
    *,
    transaction_id: str,
) -> dict[str, object]:
    evidence = tuple(evidence)
    known_steps = {step.step_id for step in contract.steps + contract.recovery_steps}
    affected_domain_generations = derive_affected_domain_generations(
        contract,
        evidence,
        transaction_id=transaction_id,
    )

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
            "destructive_started": bool(affected_domain_generations),
            "recovery_required": True,
            "blocking_predicates": [str(error)],
            "affected_domain_generations": affected_domain_generations,
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
            "destructive_started": bool(affected_domain_generations),
            "recovery_required": True,
            "blocking_predicates": [f"unknown_step={step}" for step in unknown_steps],
            "affected_domain_generations": affected_domain_generations,
        }

    dispatched_non_destructive = sorted(
        step.step_id
        for step in contract.steps + contract.recovery_steps
        if not step.destructive and statuses.get(step.step_id) == DISPATCHED
    )
    if dispatched_non_destructive:
        return {
            "operation_id": contract.operation_id,
            "transaction_id": transaction_id,
            "state": "INVALID_TRACE",
            "current_step": dispatched_non_destructive[0],
            "next_step": None,
            "failure_stage": None,
            "destructive_started": bool(affected_domain_generations),
            "recovery_required": bool(affected_domain_generations),
            "blocking_predicates": [
                f"non_destructive_dispatch_marker={step}"
                for step in dispatched_non_destructive
            ],
            "affected_domain_generations": affected_domain_generations,
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
            "affected_domain_generations": affected_domain_generations,
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
            "affected_domain_generations": affected_domain_generations,
        }

    unknown_execution = _first_unknown_execution(contract.steps, statuses)
    if unknown_execution is not None:
        recovery = _derive_recovery_state(contract, statuses)
        return {
            "operation_id": contract.operation_id,
            "transaction_id": transaction_id,
            "state": recovery["state"],
            "current_step": unknown_execution.step_id,
            "next_step": recovery["next_step"],
            "failure_stage": "MUTATION_EXECUTION",
            "destructive_started": True,
            "recovery_required": recovery["state"] != "RECOVERED",
            "blocking_predicates": recovery["blocking_predicates"],
            "affected_domain_generations": affected_domain_generations,
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
                "affected_domain_generations": affected_domain_generations,
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
            "affected_domain_generations": affected_domain_generations,
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
            "affected_domain_generations": affected_domain_generations,
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
            "affected_domain_generations": affected_domain_generations,
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
        "affected_domain_generations": affected_domain_generations,
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

    unknown_execution = _first_unknown_execution(contract.recovery_steps, statuses)
    if unknown_execution is not None:
        return {
            "state": "QUARANTINED",
            "next_step": None,
            "blocking_predicates": [f"{unknown_execution.step_id}=OUTCOME_KNOWN"],
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
