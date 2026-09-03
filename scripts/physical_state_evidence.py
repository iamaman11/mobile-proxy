from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, NamedTuple


CONTROL = "CONTROL"
TARGET = "android-production"
OBSERVED_FACT = "OBSERVED_FACT"
MUTATION_DISPATCH_INTENT = "MUTATION_DISPATCH_INTENT"
DISPATCHED = "DISPATCHED"

GENERATION_BOOTSTRAP = "BOOTSTRAP"
GENERATION_OBSERVED = "OBSERVED"
GENERATION_UNKNOWN_EXECUTION_OUTCOME = "UNKNOWN_EXECUTION_OUTCOME"
GENERATION_CONFLICT = "CONFLICT"
GENERATION_INVALID = "INVALID"

_ALLOWED_DEPENDENCY_KINDS = frozenset(
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


class PhysicalEvidenceFailure(ValueError):
    pass


class OrderedPhysicalEvidence(NamedTuple):
    """One durable CONTROL record plus its transport-provided monotonic order.

    ``sequence`` is external transport metadata (for example a private CONTROL issue
    comment id). It is intentionally not part of physical truth and therefore does
    not become a causal dependency of observed facts.
    """

    sequence: int
    evidence: Mapping[str, Any]


@dataclass(frozen=True)
class DomainGenerationResolution:
    scope: str
    identity: str
    state: str
    source_sequence: int | None
    transaction_id: str | None
    blocking_predicates: tuple[str, ...] = ()


def _require_text(value: Any, label: str, *, max_length: int = 160) -> str:
    if not isinstance(value, str):
        raise PhysicalEvidenceFailure(f"{label} must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > max_length:
        raise PhysicalEvidenceFailure(f"{label} is invalid")
    if any(character.isspace() for character in normalized):
        raise PhysicalEvidenceFailure(f"{label} must not contain whitespace")
    return normalized


def canonical_domain_scope(domain: str) -> str:
    normalized = _require_text(domain, "physical domain", max_length=64)
    if "/" in normalized:
        raise PhysicalEvidenceFailure("physical domain must not contain slash")
    if not normalized[0].isalpha() or not all(
        character.islower() or character.isdigit() or character in "_-"
        for character in normalized
    ):
        raise PhysicalEvidenceFailure("physical domain is invalid")
    return f"domain/{normalized}"


def bootstrap_generation_identity(domain: str) -> str:
    scope = canonical_domain_scope(domain)
    return f"bootstrap:{scope.split('/', 1)[1]}:v1"


def _validate_dependency(dependency: Mapping[str, Any]) -> dict[str, str]:
    if set(dependency) != {"scope", "identity"}:
        raise PhysicalEvidenceFailure("observed fact dependency shape differs")
    scope = _require_text(dependency.get("scope"), "dependency scope")
    kind, separator, name = scope.partition("/")
    if not separator or not name or kind not in _ALLOWED_DEPENDENCY_KINDS:
        raise PhysicalEvidenceFailure(f"dependency scope is invalid: {scope}")
    identity = _require_text(dependency.get("identity"), f"dependency identity {scope}")
    return {"scope": scope, "identity": identity}


def promote_observed_fact(raw_fact: Mapping[str, Any]) -> dict[str, Any]:
    """Wrap one producer fact as canonical durable physical evidence.

    Producers must emit ``persisted=false`` because they cannot prove outer CONTROL
    persistence. This function flips that flag only in the payload that the outer
    adapter is about to persist. If persistence fails, no durable fact exists and the
    payload must not be admitted by any consumer.
    """

    required = {
        "subject",
        "predicate",
        "value",
        "target",
        "observation_ref",
        "source_ref",
        "dependencies",
        "authority",
        "persisted",
    }
    if set(raw_fact) != required:
        raise PhysicalEvidenceFailure("producer observed fact shape differs")
    if raw_fact.get("target") != TARGET:
        raise PhysicalEvidenceFailure("observed fact target differs")
    if raw_fact.get("authority") != CONTROL:
        raise PhysicalEvidenceFailure("observed fact authority differs")
    if raw_fact.get("persisted") is not False:
        raise PhysicalEvidenceFailure("producer must not claim outer persistence")

    subject = _require_text(raw_fact.get("subject"), "observed fact subject")
    predicate = _require_text(raw_fact.get("predicate"), "observed fact predicate")
    observation_ref = _require_text(
        raw_fact.get("observation_ref"), "observation reference"
    )
    source_ref = _require_text(raw_fact.get("source_ref"), "source reference")
    dependencies_value = raw_fact.get("dependencies")
    if not isinstance(dependencies_value, list) or not dependencies_value:
        raise PhysicalEvidenceFailure("observed fact dependencies are invalid")

    dependencies: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in dependencies_value:
        if not isinstance(item, Mapping):
            raise PhysicalEvidenceFailure("observed fact dependency is invalid")
        dependency = _validate_dependency(item)
        if dependency["scope"] in seen:
            raise PhysicalEvidenceFailure(
                f"duplicate observed fact dependency: {dependency['scope']}"
            )
        seen.add(dependency["scope"])
        dependencies.append(dependency)

    fact = {
        "subject": subject,
        "predicate": predicate,
        "value": raw_fact.get("value"),
        "target": TARGET,
        "observation_ref": observation_ref,
        "source_ref": source_ref,
        "dependencies": dependencies,
        "authority": CONTROL,
        "persisted": True,
    }
    return {
        "schema_version": 1,
        "evidence_type": OBSERVED_FACT,
        "target": TARGET,
        "source_ref": source_ref,
        "authority": CONTROL,
        "observed_fact": fact,
    }


def build_dispatch_intent_evidence(
    *,
    source_ref: str,
    operation_id: str,
    transaction_id: str,
    step_id: str,
    affected_domain_generations: Mapping[str, str],
) -> dict[str, Any]:
    """Build canonical evidence that mutation may be dispatched after persistence."""

    source_ref = _require_text(source_ref, "source reference")
    operation_id = _require_text(operation_id, "operation id")
    transaction_id = _require_text(transaction_id, "transaction id")
    step_id = _require_text(step_id, "step id")
    if not affected_domain_generations:
        raise PhysicalEvidenceFailure("dispatch intent needs affected domains")

    generations: dict[str, str] = {}
    for raw_scope, raw_identity in affected_domain_generations.items():
        scope = _require_text(raw_scope, "affected domain scope")
        if not scope.startswith("domain/") or scope.count("/") != 1:
            raise PhysicalEvidenceFailure(f"affected domain scope is invalid: {scope}")
        canonical_domain_scope(scope.split("/", 1)[1])
        identity = _require_text(raw_identity, f"generation identity {scope}")
        if identity != transaction_id:
            raise PhysicalEvidenceFailure(
                f"affected domain generation must equal transaction identity: {scope}"
            )
        if scope in generations:
            raise PhysicalEvidenceFailure(f"duplicate affected domain scope: {scope}")
        generations[scope] = identity

    return {
        "schema_version": 1,
        "evidence_type": MUTATION_DISPATCH_INTENT,
        "target": TARGET,
        "source_ref": source_ref,
        "authority": CONTROL,
        "dispatch_intent": {
            "operation_id": operation_id,
            "transaction_id": transaction_id,
            "step_id": step_id,
            "status": DISPATCHED,
            "affected_domain_generations": generations,
            "persistence_precedes_dispatch": True,
            "blind_retry_allowed": False,
            "phone_command_result": "UNKNOWN_AT_MARKER_TIME",
            "raw_device_identifier_recorded": False,
        },
    }


def _domain_identity_from_observed_fact(
    evidence: Mapping[str, Any], scope: str
) -> str | None:
    if evidence.get("evidence_type") != OBSERVED_FACT:
        return None
    if evidence.get("target") != TARGET or evidence.get("authority") != CONTROL:
        return None
    fact = evidence.get("observed_fact")
    if not isinstance(fact, Mapping):
        return None
    if fact.get("target") != TARGET or fact.get("authority") != CONTROL:
        return None
    if fact.get("persisted") is not True:
        return None
    dependencies = fact.get("dependencies")
    if not isinstance(dependencies, list):
        return None
    identities = [
        item.get("identity")
        for item in dependencies
        if isinstance(item, Mapping) and item.get("scope") == scope
    ]
    if len(identities) != 1:
        return None
    identity = identities[0]
    if not isinstance(identity, str) or not identity.strip():
        return None
    return identity


def _dispatch_generation(
    evidence: Mapping[str, Any], scope: str
) -> tuple[str, str] | None:
    if evidence.get("evidence_type") != MUTATION_DISPATCH_INTENT:
        return None
    if evidence.get("target") != TARGET or evidence.get("authority") != CONTROL:
        raise PhysicalEvidenceFailure("dispatch intent CONTROL metadata differs")
    intent = evidence.get("dispatch_intent")
    if not isinstance(intent, Mapping):
        raise PhysicalEvidenceFailure("dispatch intent payload is missing")
    if intent.get("status") != DISPATCHED:
        raise PhysicalEvidenceFailure("dispatch intent status differs")
    if intent.get("persistence_precedes_dispatch") is not True:
        raise PhysicalEvidenceFailure("dispatch intent persistence ordering differs")
    if intent.get("blind_retry_allowed") is not False:
        raise PhysicalEvidenceFailure("dispatch intent permits blind retry")
    if intent.get("phone_command_result") != "UNKNOWN_AT_MARKER_TIME":
        raise PhysicalEvidenceFailure("dispatch intent command-result marker differs")
    if intent.get("raw_device_identifier_recorded") is not False:
        raise PhysicalEvidenceFailure("dispatch intent records raw device identity")
    transaction_id = _require_text(intent.get("transaction_id"), "dispatch transaction id")
    generations = intent.get("affected_domain_generations")
    if not isinstance(generations, Mapping):
        raise PhysicalEvidenceFailure("dispatch intent affected generations differ")
    if scope not in generations:
        return None
    identity = _require_text(generations.get(scope), f"dispatch generation {scope}")
    if identity != transaction_id:
        raise PhysicalEvidenceFailure(
            f"dispatch generation must equal transaction identity: {scope}"
        )
    return transaction_id, identity


def resolve_domain_generation(
    domain: str,
    records: Iterable[OrderedPhysicalEvidence],
) -> DomainGenerationResolution:
    """Resolve one physical-domain generation from durable CONTROL evidence only.

    No intent means the explicit versioned bootstrap generation. Once any persisted
    dispatch intent exists, the latest intent owns the generation. That generation
    remains ``UNKNOWN_EXECUTION_OUTCOME`` until a later durable observed fact carries
    the exact same domain dependency. The resolver never uses Git/source SHA as
    physical freshness and never authorizes an operation; operation admission remains
    the responsibility of the existing control/operation reducers.
    """

    scope = canonical_domain_scope(domain)
    ordered = tuple(records)
    sequence_values: set[int] = set()
    for record in ordered:
        if not isinstance(record.sequence, int) or record.sequence <= 0:
            return DomainGenerationResolution(
                scope,
                bootstrap_generation_identity(domain),
                GENERATION_INVALID,
                None,
                None,
                ("invalid_control_sequence",),
            )
        if record.sequence in sequence_values:
            return DomainGenerationResolution(
                scope,
                bootstrap_generation_identity(domain),
                GENERATION_CONFLICT,
                record.sequence,
                None,
                (f"duplicate_control_sequence={record.sequence}",),
            )
        sequence_values.add(record.sequence)

    intents: list[tuple[int, str, str]] = []
    try:
        for record in ordered:
            dispatch = _dispatch_generation(record.evidence, scope)
            if dispatch is not None:
                transaction_id, identity = dispatch
                intents.append((record.sequence, transaction_id, identity))
    except PhysicalEvidenceFailure as error:
        return DomainGenerationResolution(
            scope,
            bootstrap_generation_identity(domain),
            GENERATION_INVALID,
            None,
            None,
            (str(error),),
        )

    if not intents:
        return DomainGenerationResolution(
            scope,
            bootstrap_generation_identity(domain),
            GENERATION_BOOTSTRAP,
            None,
            None,
            (),
        )

    latest_sequence, transaction_id, identity = max(intents, key=lambda item: item[0])
    observed_after = False
    for record in ordered:
        if record.sequence <= latest_sequence:
            continue
        observed_identity = _domain_identity_from_observed_fact(record.evidence, scope)
        if observed_identity == identity:
            observed_after = True
            break

    if observed_after:
        return DomainGenerationResolution(
            scope,
            identity,
            GENERATION_OBSERVED,
            latest_sequence,
            transaction_id,
            (),
        )

    return DomainGenerationResolution(
        scope,
        identity,
        GENERATION_UNKNOWN_EXECUTION_OUTCOME,
        latest_sequence,
        transaction_id,
        (
            f"fresh_domain_observation_required={scope}:{identity}",
            "blind_retry=FORBIDDEN",
        ),
    )
