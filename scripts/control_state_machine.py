from __future__ import annotations

from typing import Any, Iterable, Mapping, NamedTuple


CURRENT = "CURRENT"
STALE = "STALE"
CONTROL = "CONTROL"
DIAGNOSTIC = "DIAGNOSTIC"
AUDIT = "AUDIT"
UNKNOWN = object()

FACT_VALID = "VALID"
FACT_STALE = "STALE"
FACT_UNKNOWN = "UNKNOWN"
FACT_UNPERSISTED = "UNPERSISTED"
FACT_UNUSABLE = "UNUSABLE"
FACT_INVALID = "INVALID"

_DEPENDENCY_KINDS = frozenset(
    {
        "target",
        "observer",
        "domain",
        "boot",
        "session",
        "source",
        "artifact",
        "transaction",
    }
)


class Fact(NamedTuple):
    subject: str
    predicate: str
    value: Any
    lifecycle: str = CURRENT
    source_ref: str = ""
    authority: str = CONTROL


class FactDependency(NamedTuple):
    """One causal dependency that controls reuse of an observed physical fact."""

    scope: str
    identity: str


class ObservedFact(NamedTuple):
    """Durable physical observation before projection into the legacy reducer surface.

    ``source_ref`` is provenance only. A source change invalidates this fact only when
    ``source/...`` is explicitly present in ``dependencies``.
    """

    subject: str
    predicate: str
    value: Any
    target: str
    observation_ref: str
    source_ref: str
    dependencies: tuple[FactDependency, ...]
    authority: str = CONTROL
    persisted: bool = True


class FactValidity(NamedTuple):
    state: str
    reasons: tuple[str, ...] = ()


class FactConflict(RuntimeError):
    pass


def _dependency_map(fact: ObservedFact) -> tuple[dict[str, str], tuple[str, ...]]:
    dependencies: dict[str, str] = {}
    errors: list[str] = []

    for dependency in fact.dependencies:
        scope = dependency.scope.strip()
        identity = dependency.identity.strip()
        kind, separator, name = scope.partition("/")

        if not scope or not separator or not name or kind not in _DEPENDENCY_KINDS:
            errors.append(f"invalid_dependency_scope={dependency.scope}")
            continue
        if not identity:
            errors.append(f"missing_dependency_identity={scope}")
            continue
        if scope in dependencies:
            errors.append(f"duplicate_dependency_scope={scope}")
            continue
        dependencies[scope] = identity

    return dependencies, tuple(errors)


def classify_observed_fact(
    fact: ObservedFact,
    current_context: Mapping[str, str],
    *,
    required_scopes: Iterable[str] = (),
    required_authority: str = CONTROL,
) -> FactValidity:
    """Classify whether a durable physical fact is reusable in current context.

    Only dependencies declared by the fact participate. Extra current-context entries
    are intentionally ignored, so an unrelated Git/source change cannot stale a
    source-independent physical observation.
    """

    metadata_errors: list[str] = []
    if not fact.subject.strip():
        metadata_errors.append("missing_subject")
    if not fact.predicate.strip():
        metadata_errors.append("missing_predicate")
    if not fact.target.strip():
        metadata_errors.append("missing_target")
    if not fact.observation_ref.strip():
        metadata_errors.append("missing_observation_ref")
    if not fact.source_ref.strip():
        metadata_errors.append("missing_source_ref")

    dependencies, dependency_errors = _dependency_map(fact)
    metadata_errors.extend(dependency_errors)

    required = tuple(required_scopes)
    for scope in required:
        kind, separator, name = scope.partition("/")
        if not scope or not separator or not name or kind not in _DEPENDENCY_KINDS:
            metadata_errors.append(f"invalid_required_scope={scope}")
        elif scope not in dependencies:
            metadata_errors.append(f"missing_required_dependency={scope}")

    if metadata_errors:
        return FactValidity(FACT_INVALID, tuple(metadata_errors))

    if fact.authority != required_authority:
        return FactValidity(
            FACT_UNUSABLE,
            (f"authority={fact.authority};required={required_authority}",),
        )

    if not fact.persisted:
        return FactValidity(FACT_UNPERSISTED, ("evidence_persisted=false",))

    missing_context = [
        scope
        for scope in dependencies
        if not current_context.get(scope, "").strip()
    ]
    if missing_context:
        return FactValidity(
            FACT_UNKNOWN,
            tuple(f"missing_current_context={scope}" for scope in missing_context),
        )

    mismatches = [
        (scope, observed_identity, current_context[scope])
        for scope, observed_identity in dependencies.items()
        if current_context[scope] != observed_identity
    ]
    if mismatches:
        return FactValidity(
            FACT_STALE,
            tuple(
                f"dependency_changed={scope}:{observed}->{current}"
                for scope, observed, current in mismatches
            ),
        )

    return FactValidity(FACT_VALID)


def project_observed_fact(
    fact: ObservedFact,
    current_context: Mapping[str, str],
    *,
    required_scopes: Iterable[str] = (),
    required_authority: str = CONTROL,
) -> Fact | None:
    """Project an admitted observed fact into the existing CURRENT/STALE reducer API."""

    validity = classify_observed_fact(
        fact,
        current_context,
        required_scopes=required_scopes,
        required_authority=required_authority,
    )
    if validity.state == FACT_VALID:
        lifecycle = CURRENT
    elif validity.state == FACT_STALE:
        lifecycle = STALE
    else:
        return None

    return Fact(
        fact.subject,
        fact.predicate,
        fact.value,
        lifecycle=lifecycle,
        source_ref=fact.observation_ref,
        authority=fact.authority,
    )


def _facts_for(
    facts: Iterable[Fact],
    subject: str,
    predicate: str,
    lifecycle: str = CURRENT,
    authority: str = CONTROL,
) -> list[Fact]:
    return [
        fact
        for fact in facts
        if fact.subject == subject
        and fact.predicate == predicate
        and fact.lifecycle == lifecycle
        and fact.authority == authority
    ]


def _value(
    facts: Iterable[Fact],
    subject: str,
    predicate: str,
    *,
    lifecycle: str = CURRENT,
    authority: str = CONTROL,
) -> Any:
    matches = _facts_for(facts, subject, predicate, lifecycle, authority)
    if not matches:
        return UNKNOWN
    values = [fact.value for fact in matches]
    first = values[0]
    if any(value != first for value in values[1:]):
        raise FactConflict(
            f"conflicting {authority} {lifecycle} facts for {subject}.{predicate}"
        )
    return first


def _has_conflict(
    facts: Iterable[Fact],
    subject: str,
    predicates: set[str],
    *,
    authority: str,
) -> bool:
    for predicate in predicates:
        try:
            _value(facts, subject, predicate, authority=authority)
        except FactConflict:
            return True
    return False


def derive_job_state(facts: Iterable[Fact], *, authority: str = CONTROL) -> str:
    status = _value(facts, "run", "job_status", authority=authority)
    conclusion = _value(facts, "run", "job_conclusion", authority=authority)
    runner_assigned = _value(facts, "run", "runner_assigned", authority=authority)

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


def derive_runner_state(facts: Iterable[Fact], *, authority: str = CONTROL) -> str:
    predicates = {
        "runner_registered",
        "runner_labels_match",
        "runner_online",
        "runner_busy",
    }
    if _has_conflict(facts, "runner", predicates, authority=authority):
        return "RUNNER_CONFLICT"

    registered = _value(facts, "runner", "runner_registered", authority=authority)
    labels_match = _value(facts, "runner", "runner_labels_match", authority=authority)
    online = _value(facts, "runner", "runner_online", authority=authority)
    busy = _value(facts, "runner", "runner_busy", authority=authority)

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


def derive_transport_state(facts: Iterable[Fact], *, authority: str = CONTROL) -> str:
    predicates = {"transport_failed", "transport_tls_failure_recent", "transport_recent_success"}
    if _has_conflict(facts, "runner", predicates, authority=authority):
        return "TRANSPORT_UNKNOWN"

    failed = _value(facts, "runner", "transport_failed", authority=authority)
    tls_failure = _value(facts, "runner", "transport_tls_failure_recent", authority=authority)
    recent_success = _value(facts, "runner", "transport_recent_success", authority=authority)

    if failed is True:
        return "TRANSPORT_FAILED"
    if tls_failure is True:
        return "TRANSPORT_DEGRADED"
    if recent_success is True:
        return "TRANSPORT_RECENTLY_HEALTHY"
    return "TRANSPORT_UNKNOWN"


def derive_source_fetch_state(facts: Iterable[Fact], *, authority: str = CONTROL) -> str:
    result = _value(facts, "run", "source_fetch_result", authority=authority)
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


_PHONE_ACCESS_PREDICATES = (
    "adb_tool_available",
    "adb_inventory_valid",
    "adb_device_count",
    "registered_device_match",
    "registered_device_inventory_state",
    "adb_get_state",
    "adb_shell_probe",
)


def _phone_probe_values(
    facts: Iterable[Fact],
    lifecycle: str,
    *,
    authority: str,
) -> tuple[dict[str, Any], str] | None:
    selected: dict[str, Fact] = {}
    source_ref: str | None = None

    for predicate in _PHONE_ACCESS_PREDICATES:
        matches = _facts_for(facts, "phone", predicate, lifecycle, authority)
        if not matches:
            return None
        values = {fact.value for fact in matches}
        if len(values) != 1:
            if lifecycle == CURRENT:
                raise FactConflict(
                    f"conflicting {authority} current facts for phone.{predicate}"
                )
            return None
        refs = {fact.source_ref for fact in matches}
        if len(refs) != 1 or "" in refs:
            return None
        this_ref = next(iter(refs))
        if source_ref is None:
            source_ref = this_ref
        elif this_ref != source_ref:
            return None
        selected[predicate] = matches[0]

    assert source_ref is not None
    return ({predicate: fact.value for predicate, fact in selected.items()}, source_ref)


def _classify_phone_probe(values: dict[str, Any]) -> str:
    if values["adb_tool_available"] is not True:
        return "ADB_TOOL_UNAVAILABLE"
    if values["adb_inventory_valid"] is not True:
        return "ADB_INVENTORY_INVALID"

    count = values["adb_device_count"]
    if count == 0:
        return "ADB_ZERO_DEVICES"
    if count != 1:
        return "ADB_MULTIPLE_DEVICES"
    if values["registered_device_match"] is not True:
        return "ADB_WRONG_DEVICE"
    if values["registered_device_inventory_state"] != "device":
        return "ADB_REGISTERED_DEVICE_OFFLINE"
    if values["adb_get_state"] != "device":
        return "ADB_GET_STATE_FAILED"
    if values["adb_shell_probe"] is not True:
        return "ADB_SHELL_FAILED"
    return "PHONE_ACCESS_PROVEN"


def derive_phone_access_state(facts: Iterable[Fact], *, authority: str = CONTROL) -> str:
    try:
        current_probe = _phone_probe_values(facts, CURRENT, authority=authority)
    except FactConflict:
        return "PHONE_ACCESS_CONFLICT"

    if current_probe is not None:
        values, _ = current_probe
        return _classify_phone_probe(values)

    stale_probe = _phone_probe_values(facts, STALE, authority=authority)
    if stale_probe is not None:
        values, _ = stale_probe
        if _classify_phone_probe(values) == "PHONE_ACCESS_PROVEN":
            return "PHONE_ACCESS_STALE"

    current_phone_facts = [
        fact
        for fact in facts
        if fact.subject == "phone"
        and fact.lifecycle == CURRENT
        and fact.authority == authority
        and fact.predicate in _PHONE_ACCESS_PREDICATES
    ]
    refs = {fact.source_ref for fact in current_phone_facts}
    if not current_phone_facts or len(refs) != 1 or "" in refs:
        return "PHONE_ACCESS_UNOBSERVED"

    try:
        adb_tool = _value(facts, "phone", "adb_tool_available", authority=authority)
        if adb_tool is False:
            return "ADB_TOOL_UNAVAILABLE"
        if adb_tool is UNKNOWN:
            return "PHONE_ACCESS_UNOBSERVED"

        inventory_valid = _value(facts, "phone", "adb_inventory_valid", authority=authority)
        if inventory_valid is False:
            return "ADB_INVENTORY_INVALID"
        if inventory_valid is UNKNOWN:
            return "PHONE_ACCESS_UNOBSERVED"

        count = _value(facts, "phone", "adb_device_count", authority=authority)
        if count is UNKNOWN:
            return "PHONE_ACCESS_UNOBSERVED"
        if count == 0:
            return "ADB_ZERO_DEVICES"
        if count != 1:
            return "ADB_MULTIPLE_DEVICES"

        registered_match = _value(facts, "phone", "registered_device_match", authority=authority)
        if registered_match is False:
            return "ADB_WRONG_DEVICE"
        if registered_match is UNKNOWN:
            return "PHONE_ACCESS_UNOBSERVED"

        inventory_state = _value(
            facts, "phone", "registered_device_inventory_state", authority=authority
        )
        if inventory_state is UNKNOWN:
            return "PHONE_ACCESS_UNOBSERVED"
        if inventory_state != "device":
            return "ADB_REGISTERED_DEVICE_OFFLINE"

        get_state = _value(facts, "phone", "adb_get_state", authority=authority)
        if get_state is UNKNOWN:
            return "PHONE_ACCESS_UNOBSERVED"
        if get_state != "device":
            return "ADB_GET_STATE_FAILED"

        shell_probe = _value(facts, "phone", "adb_shell_probe", authority=authority)
        if shell_probe is UNKNOWN:
            return "PHONE_ACCESS_UNOBSERVED"
        if shell_probe is not True:
            return "ADB_SHELL_FAILED"
    except FactConflict:
        return "PHONE_ACCESS_CONFLICT"

    return "PHONE_ACCESS_PROVEN"


def derive_failure_stage(facts: Iterable[Fact], *, authority: str = CONTROL) -> str | None:
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
        if _value(facts, "run", predicate, authority=authority) is True:
            return stage
    return None


def derive_blocking_predicates(
    facts: Iterable[Fact], *, authority: str = CONTROL
) -> list[str]:
    facts = tuple(facts)

    failure_stage = derive_failure_stage(facts, authority=authority)
    if failure_stage == "SOURCE_FETCH":
        return ["source_fetch=SOURCE_FETCH_SUCCEEDED"]

    phone_access = derive_phone_access_state(facts, authority=authority)
    if phone_access != "PHONE_ACCESS_PROVEN":
        return [f"phone_access={phone_access}"]

    return []


def derive_snapshot(
    facts: Iterable[Fact], *, authority: str = CONTROL
) -> dict[str, Any]:
    facts = tuple(facts)
    mutation_performed = _value(
        facts, "run", "mutation_performed", authority=authority
    )
    if mutation_performed is UNKNOWN:
        mutation_performed = None

    return {
        "authority": authority,
        "command_job": derive_job_state(facts, authority=authority),
        "runner": derive_runner_state(facts, authority=authority),
        "transport": derive_transport_state(facts, authority=authority),
        "source_fetch": derive_source_fetch_state(facts, authority=authority),
        "phone_access": derive_phone_access_state(facts, authority=authority),
        "failure_stage": derive_failure_stage(facts, authority=authority),
        "blocking_predicates": derive_blocking_predicates(facts, authority=authority),
        "mutation_performed": mutation_performed,
    }
