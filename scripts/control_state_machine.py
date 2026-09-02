from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


CURRENT = "CURRENT"
UNKNOWN = object()


@dataclass(frozen=True)
class Fact:
    subject: str
    predicate: str
    value: Any
    lifecycle: str = CURRENT
    source_ref: str = ""


class FactConflict(RuntimeError):
    pass


def _current_value(facts: Iterable[Fact], predicate: str) -> Any:
    values = [fact.value for fact in facts if fact.predicate == predicate and fact.lifecycle == CURRENT]
    if not values:
        return UNKNOWN
    first = values[0]
    if any(value != first for value in values[1:]):
        raise FactConflict(f"conflicting current facts for {predicate}")
    return first


def _has_conflict(facts: Iterable[Fact], predicates: set[str]) -> bool:
    for predicate in predicates:
        try:
            _current_value(facts, predicate)
        except FactConflict:
            return True
    return False


def derive_job_state(facts: Iterable[Fact]) -> str:
    status = _current_value(facts, "job_status")
    conclusion = _current_value(facts, "job_conclusion")
    runner_assigned = _current_value(facts, "runner_assigned")

    if status is UNKNOWN:
        return "COMMAND_UNOBSERVED"
    if status == "queued":
        if runner_assigned is True:
            return "JOB_ASSIGNED"
        if runner_assigned is False or runner_assigned is UNKNOWN:
            return "JOB_QUEUED_UNASSIGNED"
    if status == "in_progress":
        return "JOB_RUNNING"
    if status == "completed":
        if conclusion == "success":
            return "JOB_SUCCEEDED"
        if conclusion == "failure":
            return "JOB_FAILED"
        if conclusion == "cancelled":
            return "JOB_CANCELLED"
        if conclusion == "skipped":
            return "JOB_SKIPPED"
        if conclusion == "timed_out":
            return "JOB_TIMED_OUT"
    return "COMMAND_UNOBSERVED"


def derive_runner_state(facts: Iterable[Fact]) -> str:
    predicates = {
        "runner_registered",
        "runner_labels_match",
        "runner_online",
        "runner_busy",
    }
    if _has_conflict(facts, predicates):
        return "RUNNER_CONFLICT"

    registered = _current_value(facts, "runner_registered")
    labels_match = _current_value(facts, "runner_labels_match")
    online = _current_value(facts, "runner_online")
    busy = _current_value(facts, "runner_busy")

    if registered is False:
        return "RUNNER_UNREGISTERED"
    if registered is UNKNOWN:
        return "RUNNER_UNKNOWN"
    if labels_match is False:
        return "RUNNER_LABEL_MISMATCH"
    if labels_match is UNKNOWN:
        return "RUNNER_UNKNOWN"
    if online is False:
        return "RUNNER_OFFLINE"
    if online is UNKNOWN or busy is UNKNOWN:
        return "RUNNER_UNKNOWN"
    return "RUNNER_ONLINE_BUSY" if busy else "RUNNER_ONLINE_IDLE"


def derive_transport_state(facts: Iterable[Fact]) -> str:
    if _has_conflict(facts, {"transport_failed", "transport_tls_failure_recent", "transport_recent_success"}):
        return "TRANSPORT_UNKNOWN"

    failed = _current_value(facts, "transport_failed")
    tls_failure = _current_value(facts, "transport_tls_failure_recent")
    recent_success = _current_value(facts, "transport_recent_success")

    if failed is True:
        return "TRANSPORT_FAILED"
    if tls_failure is True:
        return "TRANSPORT_DEGRADED"
    if recent_success is True:
        return "TRANSPORT_RECENTLY_HEALTHY"
    return "TRANSPORT_UNKNOWN"


def derive_source_fetch_state(facts: Iterable[Fact]) -> str:
    result = _current_value(facts, "source_fetch_result")
    mapping = {
        "success": "SOURCE_FETCH_SUCCEEDED",
        "transport_failure": "SOURCE_FETCH_FAILED_TRANSPORT",
        "transient_failure": "SOURCE_FETCH_FAILED_TRANSIENT",
        "permanent_failure": "SOURCE_FETCH_FAILED_PERMANENT",
        "digest_mismatch": "SOURCE_FETCH_DIGEST_MISMATCH",
    }
    if result is UNKNOWN:
        return "SOURCE_FETCH_UNOBSERVED"
    return mapping.get(result, "SOURCE_FETCH_UNOBSERVED")


def derive_phone_access_state(facts: Iterable[Fact]) -> str:
    predicates = {
        "adb_tool_available",
        "adb_inventory_valid",
        "adb_device_count",
        "registered_device_match",
        "registered_device_inventory_state",
        "adb_get_state",
        "adb_shell_probe",
    }
    if _has_conflict(facts, predicates):
        return "PHONE_ACCESS_CONFLICT"

    adb_tool = _current_value(facts, "adb_tool_available")
    if adb_tool is UNKNOWN:
        return "PHONE_ACCESS_UNOBSERVED"
    if adb_tool is False:
        return "ADB_TOOL_UNAVAILABLE"

    inventory_valid = _current_value(facts, "adb_inventory_valid")
    if inventory_valid is UNKNOWN:
        return "PHONE_ACCESS_UNOBSERVED"
    if inventory_valid is False:
        return "ADB_INVENTORY_INVALID"

    count = _current_value(facts, "adb_device_count")
    if count is UNKNOWN:
        return "PHONE_ACCESS_UNOBSERVED"
    if count == 0:
        return "ADB_ZERO_DEVICES"
    if count != 1:
        return "ADB_MULTIPLE_DEVICES"

    registered_match = _current_value(facts, "registered_device_match")
    if registered_match is UNKNOWN:
        return "PHONE_ACCESS_UNOBSERVED"
    if registered_match is False:
        return "ADB_WRONG_DEVICE"

    inventory_state = _current_value(facts, "registered_device_inventory_state")
    if inventory_state is UNKNOWN:
        return "PHONE_ACCESS_UNOBSERVED"
    if inventory_state != "device":
        return "ADB_REGISTERED_DEVICE_OFFLINE"

    get_state = _current_value(facts, "adb_get_state")
    if get_state is UNKNOWN:
        return "PHONE_ACCESS_UNOBSERVED"
    if get_state != "device":
        return "ADB_GET_STATE_FAILED"

    shell_probe = _current_value(facts, "adb_shell_probe")
    if shell_probe is UNKNOWN:
        return "PHONE_ACCESS_UNOBSERVED"
    if shell_probe is not True:
        return "ADB_SHELL_FAILED"

    return "PHONE_ACCESS_PROVEN"


def derive_failure_stage(facts: Iterable[Fact]) -> str | None:
    ordered = (
        ("command_gate_failed", "COMMAND_GATE"),
        ("source_authority_failed", "SOURCE_AUTHORITY"),
        ("runner_assignment_failed", "RUNNER_ASSIGNMENT"),
        ("runner_transport_failed", "RUNNER_TRANSPORT"),
        ("source_fetch_failed", "SOURCE_FETCH"),
        ("adb_tool_failed", "ADB_TOOL"),
        ("adb_inventory_failed", "ADB_INVENTORY"),
        ("device_identity_failed", "DEVICE_IDENTITY"),
        ("adb_state_failed", "ADB_STATE"),
        ("adb_shell_failed", "ADB_SHELL"),
        ("capability_failed", "CAPABILITY"),
        ("artifact_failed", "ARTIFACT"),
        ("mutation_authority_failed", "MUTATION_AUTHORITY"),
        ("mutation_lock_failed", "MUTATION_LOCK"),
        ("mutation_boundary_failed", "MUTATION_BOUNDARY"),
        ("mutation_execution_failed", "MUTATION_EXECUTION"),
        ("postcondition_failed", "POSTCONDITION"),
        ("structural_acceptance_failed", "STRUCTURAL_ACCEPTANCE"),
        ("functional_acceptance_failed", "FUNCTIONAL_ACCEPTANCE"),
        ("recovery_failed", "RECOVERY"),
    )
    for predicate, stage in ordered:
        if _current_value(facts, predicate) is True:
            return stage
    return None


def derive_snapshot(facts: Iterable[Fact]) -> dict[str, Any]:
    facts = tuple(facts)
    mutation_performed = _current_value(facts, "mutation_performed")
    if mutation_performed is UNKNOWN:
        mutation_performed = False

    return {
        "command_job": derive_job_state(facts),
        "runner": derive_runner_state(facts),
        "transport": derive_transport_state(facts),
        "source_fetch": derive_source_fetch_state(facts),
        "phone_access": derive_phone_access_state(facts),
        "failure_stage": derive_failure_stage(facts),
        "mutation_performed": mutation_performed,
    }
