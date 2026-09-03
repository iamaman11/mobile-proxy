from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import atomic_physical_contracts as atomic


PLAN_RUN = "RUN"
PLAN_STOP = "STOP"
PLAN_COMPLETE = "COMPLETE"

ACCEPTED = "ACCEPTED"
REFUSED = "REFUSED"
UNKNOWN = "UNKNOWN"
QUARANTINED = "QUARANTINED"
TERMINAL_STATES = frozenset({ACCEPTED, REFUSED, UNKNOWN, QUARANTINED})
STOP_TERMINALS = frozenset({REFUSED, UNKNOWN, QUARANTINED})

PRIVATE_EXECUTION_SHA = "4842a6455c44e8f549fd5ea37c2fa28349fc72bb"


class PlanValidationError(ValueError):
    """A composite plan or its bounded progress evidence is contradictory."""


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    operation_id: str
    requires_accepted_steps: tuple[str, ...]
    allow_satisfied_skip: bool = False
    satisfied_predicate: str | None = None


@dataclass(frozen=True)
class CompositePlan:
    plan_id: str
    steps: tuple[PlanStep, ...]
    stop_terminals: frozenset[str] = STOP_TERMINALS


@dataclass(frozen=True)
class PlanDecision:
    action: str
    step_id: str | None
    operation_id: str | None
    reason: str


@dataclass(frozen=True)
class PrivateMutatorInventoryEntry:
    workflow: str
    disposition: str
    operation_id: str | None = None
    plan_id: str | None = None
    hard_block_reason: str | None = None


def _linear_plan(
    plan_id: str,
    steps: tuple[tuple[str, str, bool, str | None], ...],
) -> CompositePlan:
    accepted: list[str] = []
    result: list[PlanStep] = []
    for step_id, operation_id, allow_satisfied_skip, satisfied_predicate in steps:
        result.append(
            PlanStep(
                step_id=step_id,
                operation_id=operation_id,
                requires_accepted_steps=tuple(accepted),
                allow_satisfied_skip=allow_satisfied_skip,
                satisfied_predicate=satisfied_predicate,
            )
        )
        accepted.append(step_id)
    return CompositePlan(plan_id=plan_id, steps=tuple(result))


CURRENT_SOURCE_CLEAN_INSTALL_PLAN = _linear_plan(
    "android.current-source-clean-install.plan.v1",
    (
        (
            "stop_runtime",
            "android.runtime-stop.v1",
            True,
            "runtime_stopped",
        ),
        (
            "remove_runtime",
            "android.runtime-remove.v1",
            True,
            "runtime_absent",
        ),
        (
            "remove_package",
            "android.package-remove.v1",
            True,
            "package_absent",
        ),
        (
            "install_package",
            "android.apk-install.v1",
            False,
            None,
        ),
        (
            "materialize_runtime",
            "android.runtime-materialize.v1",
            False,
            None,
        ),
        (
            "start_runtime",
            "android.runtime-start.v1",
            False,
            None,
        ),
    ),
)

FILESYSTEM_CERTIFICATION_PLAN = _linear_plan(
    "android.filesystem-certification.plan.v1",
    (
        (
            "scratch_roundtrip",
            "android.filesystem-scratch-roundtrip.v1",
            False,
            None,
        ),
        (
            "scratch_atomic_replace",
            "android.filesystem-scratch-atomic-replace.v1",
            False,
            None,
        ),
        (
            "managed_root_write",
            "android.filesystem-managed-root-write.v1",
            False,
            None,
        ),
        (
            "managed_atomic_replace",
            "android.filesystem-managed-atomic-replace.v1",
            False,
            None,
        ),
    ),
)

RUNTIME_RECONSTRUCTION_PLAN = _linear_plan(
    "android.runtime-reconstruction.plan.v1",
    (
        (
            "stop_runtime",
            "android.runtime-stop.v1",
            True,
            "runtime_stopped",
        ),
        (
            "materialize_runtime",
            "android.runtime-materialize.v1",
            False,
            None,
        ),
        (
            "start_runtime",
            "android.runtime-start.v1",
            False,
            None,
        ),
    ),
)

RUNTIME_BINARY_REPAIR_PLAN = _linear_plan(
    "android.runtime-binary-repair.plan.v1",
    (
        (
            "replace_runtime_binaries",
            "android.runtime-binary-replace.v1",
            False,
            None,
        ),
        (
            "stop_runtime",
            "android.runtime-stop.v1",
            True,
            "runtime_stopped",
        ),
        (
            "start_runtime",
            "android.runtime-start.v1",
            False,
            None,
        ),
    ),
)

COMPOSITE_PLANS = (
    CURRENT_SOURCE_CLEAN_INSTALL_PLAN,
    FILESYSTEM_CERTIFICATION_PLAN,
    RUNTIME_RECONSTRUCTION_PLAN,
    RUNTIME_BINARY_REPAIR_PLAN,
)

_PLAN_BY_ID = {item.plan_id: item for item in COMPOSITE_PLANS}


def composite_plan(plan_id: str) -> CompositePlan:
    try:
        return _PLAN_BY_ID[plan_id]
    except KeyError as error:
        raise ValueError(f"unknown composite physical plan: {plan_id}") from error


def validate_plan(plan: CompositePlan) -> tuple[str, ...]:
    errors: list[str] = []
    if not plan.plan_id.strip():
        errors.append("plan id must be non-empty")
    if not plan.steps:
        errors.append("plan must contain at least one atomic step")
        return tuple(errors)

    ids = tuple(step.step_id for step in plan.steps)
    if len(set(ids)) != len(ids):
        errors.append("plan step ids must be unique")

    expected_prefix: list[str] = []
    for step in plan.steps:
        if not step.step_id.strip():
            errors.append("plan step id must be non-empty")
        if step.requires_accepted_steps != tuple(expected_prefix):
            errors.append(
                f"{step.step_id}: accepted-step dependency prefix differs"
            )
        expected_prefix.append(step.step_id)

        try:
            spec = atomic.atomic_operation_spec(step.operation_id)
        except ValueError:
            errors.append(f"{step.step_id}: unknown atomic operation {step.operation_id}")
        else:
            for detail in atomic.validate_atomic_spec(spec):
                errors.append(f"{step.step_id}: {detail}")

        if step.allow_satisfied_skip and not step.satisfied_predicate:
            errors.append(
                f"{step.step_id}: satisfied skip requires an explicit proof predicate"
            )
        if not step.allow_satisfied_skip and step.satisfied_predicate is not None:
            errors.append(
                f"{step.step_id}: satisfied predicate is forbidden when skip is disabled"
            )

    if plan.stop_terminals != STOP_TERMINALS:
        errors.append("plan stop terminals must remain REFUSED|UNKNOWN|QUARANTINED")
    return tuple(errors)


def classify_plan_progress(
    plan: CompositePlan,
    terminal_by_step: Mapping[str, str],
    *,
    satisfied_steps: frozenset[str] = frozenset(),
) -> PlanDecision:
    """Pure fail-closed composite orchestration decision.

    The function never invokes a physical operation. `satisfied_steps` may only
    represent a separately proven current desired-state predicate for steps that
    explicitly allow such a skip. Only ACCEPTED or an allowed proven-satisfied
    step advances the sequence. Any other terminal stops the plan.
    """

    errors = validate_plan(plan)
    if errors:
        raise PlanValidationError("; ".join(errors))

    known = {step.step_id for step in plan.steps}
    unknown_terminal_steps = sorted(set(terminal_by_step) - known)
    if unknown_terminal_steps:
        raise PlanValidationError(
            "unknown terminal plan steps: " + ", ".join(unknown_terminal_steps)
        )
    unknown_satisfied_steps = sorted(set(satisfied_steps) - known)
    if unknown_satisfied_steps:
        raise PlanValidationError(
            "unknown satisfied plan steps: " + ", ".join(unknown_satisfied_steps)
        )

    progressed: list[str] = []
    for index, step in enumerate(plan.steps):
        terminal = terminal_by_step.get(step.step_id)
        satisfied = step.step_id in satisfied_steps
        if terminal is not None and terminal not in TERMINAL_STATES:
            raise PlanValidationError(
                f"{step.step_id}: invalid terminal state {terminal}"
            )
        if terminal is not None and satisfied:
            raise PlanValidationError(
                f"{step.step_id}: cannot be both terminal and pre-satisfied"
            )

        if terminal == ACCEPTED:
            progressed.append(step.step_id)
            continue

        if satisfied:
            if not step.allow_satisfied_skip or not step.satisfied_predicate:
                raise PlanValidationError(
                    f"{step.step_id}: pre-satisfied skip is not authorized"
                )
            progressed.append(step.step_id)
            continue

        later_ids = {item.step_id for item in plan.steps[index + 1 :]}
        if later_ids & (set(terminal_by_step) | set(satisfied_steps)):
            raise PlanValidationError(
                f"{step.step_id}: later step evidence exists before required predecessor"
            )

        if terminal in plan.stop_terminals:
            return PlanDecision(
                action=PLAN_STOP,
                step_id=step.step_id,
                operation_id=step.operation_id,
                reason=f"terminal={terminal}",
            )
        if terminal is None:
            if step.requires_accepted_steps != tuple(progressed):
                raise PlanValidationError(
                    f"{step.step_id}: required accepted prefix not satisfied"
                )
            return PlanDecision(
                action=PLAN_RUN,
                step_id=step.step_id,
                operation_id=step.operation_id,
                reason="next_atomic_subtransaction",
            )
        raise PlanValidationError(
            f"{step.step_id}: unsupported progress classification"
        )

    return PlanDecision(
        action=PLAN_COMPLETE,
        step_id=None,
        operation_id=None,
        reason="all_atomic_subtransactions_accepted_or_proven_satisfied",
    )


PRIVATE_MUTATOR_INVENTORY = (
    PrivateMutatorInventoryEntry(
        workflow="android-signing-migration.yml",
        disposition="hard_blocked",
        hard_block_reason="migration gate explicitly hard-blocked on accepted private main",
    ),
    PrivateMutatorInventoryEntry(
        workflow="phone-clean-install.yml",
        disposition="composite",
        plan_id=CURRENT_SOURCE_CLEAN_INSTALL_PLAN.plan_id,
    ),
    PrivateMutatorInventoryEntry(
        workflow="phone-filesystem-certification.yml",
        disposition="composite",
        plan_id=FILESYSTEM_CERTIFICATION_PLAN.plan_id,
    ),
    PrivateMutatorInventoryEntry(
        workflow="phone-filesystem-quarantine-cleanup.yml",
        disposition="atomic",
        operation_id="android.filesystem-quarantine-cleanup-atomic.v1",
    ),
    PrivateMutatorInventoryEntry(
        workflow="phone-runtime-recovery.yml",
        disposition="hard_blocked",
        hard_block_reason="legacy existing-layout recovery is explicitly hard-blocked",
    ),
    PrivateMutatorInventoryEntry(
        workflow="phone-runtime-binary-repair.yml",
        disposition="composite",
        plan_id=RUNTIME_BINARY_REPAIR_PLAN.plan_id,
    ),
    PrivateMutatorInventoryEntry(
        workflow="runtime-reconstruction-execution.yml",
        disposition="composite",
        plan_id=RUNTIME_RECONSTRUCTION_PLAN.plan_id,
    ),
)


def validate_private_mutator_inventory() -> tuple[str, ...]:
    errors: list[str] = []
    workflows = tuple(item.workflow for item in PRIVATE_MUTATOR_INVENTORY)
    if len(workflows) != len(set(workflows)):
        errors.append("private mutator inventory contains duplicate workflows")

    allowed = {"atomic", "composite", "hard_blocked"}
    for item in PRIVATE_MUTATOR_INVENTORY:
        if item.disposition not in allowed:
            errors.append(f"{item.workflow}: invalid disposition")
            continue
        if item.disposition == "atomic":
            if item.operation_id is None or item.plan_id is not None:
                errors.append(f"{item.workflow}: atomic mapping is malformed")
            else:
                try:
                    spec = atomic.atomic_operation_spec(item.operation_id)
                except ValueError:
                    errors.append(f"{item.workflow}: unknown atomic operation")
                else:
                    for detail in atomic.validate_atomic_spec(spec):
                        errors.append(f"{item.workflow}: {detail}")
            if item.hard_block_reason is not None:
                errors.append(f"{item.workflow}: atomic mapping cannot be hard-blocked")
        elif item.disposition == "composite":
            if item.plan_id is None or item.operation_id is not None:
                errors.append(f"{item.workflow}: composite mapping is malformed")
            else:
                try:
                    plan = composite_plan(item.plan_id)
                except ValueError:
                    errors.append(f"{item.workflow}: unknown composite plan")
                else:
                    for detail in validate_plan(plan):
                        errors.append(f"{item.workflow}: {detail}")
            if item.hard_block_reason is not None:
                errors.append(f"{item.workflow}: composite mapping cannot be hard-blocked")
        else:
            if item.operation_id is not None or item.plan_id is not None:
                errors.append(f"{item.workflow}: hard-blocked path cannot map to execution")
            if not item.hard_block_reason:
                errors.append(f"{item.workflow}: hard-blocked path needs a reason")
    return tuple(errors)


def machine_readable_plan(plan: CompositePlan) -> dict[str, object]:
    """Return a bounded JSON-serializable plan description for hosted evidence."""

    errors = validate_plan(plan)
    if errors:
        raise PlanValidationError("; ".join(errors))
    return {
        "schema": "atomic-physical-mutation-plan.v1",
        "plan_id": plan.plan_id,
        "stop_terminals": sorted(plan.stop_terminals),
        "steps": [
            {
                "step_id": step.step_id,
                "operation_id": step.operation_id,
                "requires_accepted_steps": list(step.requires_accepted_steps),
                "allow_satisfied_skip": step.allow_satisfied_skip,
                "satisfied_predicate": step.satisfied_predicate,
                "affected_physical_domains": list(
                    atomic.atomic_operation_spec(
                        step.operation_id
                    ).contract.affected_physical_domains
                ),
                "fact_requirements": [
                    {
                        "subject": requirement.subject,
                        "predicate": requirement.predicate,
                        "freshness": requirement.freshness,
                        "required_dependency_kinds": list(
                            requirement.required_dependency_kinds
                        ),
                    }
                    for requirement in atomic.atomic_operation_spec(
                        step.operation_id
                    ).contract.fact_requirements
                ],
                "postcondition_step_id": atomic.atomic_operation_spec(
                    step.operation_id
                ).postcondition_step_id,
            }
            for step in plan.steps
        ],
    }
