from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, NamedTuple


CONTROL = "CONTROL"
CURRENT = "CURRENT"

RESOLVED = "RESOLVED"
UNKNOWN_EXECUTION_OUTCOME = "UNKNOWN_EXECUTION_OUTCOME"
INVALID_EVIDENCE = "INVALID_EVIDENCE"

BOOTSTRAP = "BOOTSTRAP"
MUTATION_INTENT = "MUTATION_INTENT"

FILESYSTEM_DOMAIN_SCOPE = "domain/filesystem"
FILESYSTEM_BOOTSTRAP_GENERATION = "filesystem-bootstrap-v1"

_TERMINAL_RESULT_STATES = frozenset(
    {
        "ACCEPTED",
        "RECOVERED",
        "REFUSED",
        "QUARANTINED",
        "CLEANED",
        "ALREADY_CLEAN",
    }
)


class MutationIntentEvidence(NamedTuple):
    operation_transaction_id: str
    workflow_run_id: int
    workflow_run_attempt: int
    affected_domain_generations: Mapping[str, str]
    result_persisted: bool
    result_state: str = ""
    authority: str = CONTROL
    lifecycle: str = CURRENT
    persisted: bool = True


class DomainGenerationResolution(NamedTuple):
    state: str
    domain_scope: str
    generation: str
    source: str
    latest_transaction_id: str | None
    unresolved_transaction_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()


class GenerationEvidenceError(RuntimeError):
    pass


def _require_identity(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise GenerationEvidenceError(f"{label} is required")
    if len(value) > 160:
        raise GenerationEvidenceError(f"{label} is too long")
    if any(character.isspace() for character in value):
        raise GenerationEvidenceError(f"{label} contains whitespace")
    return value


def _validate_intent(intent: MutationIntentEvidence) -> tuple[int, int, str]:
    transaction_id = _require_identity(
        intent.operation_transaction_id,
        "operation transaction identity",
    )
    if intent.workflow_run_id <= 0:
        raise GenerationEvidenceError("workflow run ID must be positive")
    if intent.workflow_run_attempt <= 0:
        raise GenerationEvidenceError("workflow run attempt must be positive")
    if intent.authority != CONTROL:
        raise GenerationEvidenceError(
            f"intent authority is not CONTROL: {transaction_id}"
        )
    if intent.lifecycle != CURRENT:
        raise GenerationEvidenceError(
            f"intent lifecycle is not CURRENT: {transaction_id}"
        )
    if not intent.persisted:
        raise GenerationEvidenceError(
            f"mutation intent is not durably persisted: {transaction_id}"
        )

    generations = dict(intent.affected_domain_generations)
    if generations.get(FILESYSTEM_DOMAIN_SCOPE) != transaction_id:
        raise GenerationEvidenceError(
            "filesystem generation must equal exact operation transaction identity: "
            + transaction_id
        )

    if intent.result_persisted:
        if intent.result_state not in _TERMINAL_RESULT_STATES:
            raise GenerationEvidenceError(
                f"persisted result state is not terminal: {transaction_id}"
            )
    elif intent.result_state:
        raise GenerationEvidenceError(
            f"unpersisted result must not claim terminal state: {transaction_id}"
        )

    return intent.workflow_run_id, intent.workflow_run_attempt, transaction_id


def resolve_filesystem_generation(
    intents: Iterable[MutationIntentEvidence],
    *,
    bootstrap_generation: str = FILESYSTEM_BOOTSTRAP_GENERATION,
) -> DomainGenerationResolution:
    """Resolve the causal generation for ``domain/filesystem``.

    Only durable CURRENT CONTROL mutation-intent evidence is admissible.
    No Git/source identity participates in this resolution.

    If no persisted mutation intent exists, one explicit stable bootstrap
    generation is returned. Once any mutation intent exists, the latest exact
    operation transaction owns ``domain/filesystem``. Any unresolved persisted
    intent keeps the resolver fail-closed with ``UNKNOWN_EXECUTION_OUTCOME``.
    """

    try:
        bootstrap_generation = _require_identity(
            bootstrap_generation,
            "bootstrap filesystem generation",
        )
        normalized: list[tuple[tuple[int, int, str], MutationIntentEvidence]] = []
        seen_sequence: dict[tuple[int, int], str] = {}
        seen_transactions: set[str] = set()

        for intent in intents:
            run_id, run_attempt, transaction_id = _validate_intent(intent)
            sequence = (run_id, run_attempt)
            previous = seen_sequence.get(sequence)
            if previous is not None and previous != transaction_id:
                raise GenerationEvidenceError(
                    "multiple mutation transactions share one workflow run attempt: "
                    f"{previous},{transaction_id}"
                )
            if transaction_id in seen_transactions:
                raise GenerationEvidenceError(
                    f"duplicate mutation transaction evidence: {transaction_id}"
                )
            seen_sequence[sequence] = transaction_id
            seen_transactions.add(transaction_id)
            normalized.append(((run_id, run_attempt, transaction_id), intent))
    except GenerationEvidenceError as error:
        return DomainGenerationResolution(
            INVALID_EVIDENCE,
            FILESYSTEM_DOMAIN_SCOPE,
            "",
            MUTATION_INTENT,
            None,
            (),
            (str(error),),
        )

    if not normalized:
        return DomainGenerationResolution(
            RESOLVED,
            FILESYSTEM_DOMAIN_SCOPE,
            bootstrap_generation,
            BOOTSTRAP,
            None,
        )

    normalized.sort(key=lambda item: item[0])
    latest = normalized[-1][1]
    latest_transaction_id = latest.operation_transaction_id.strip()
    unresolved = tuple(
        intent.operation_transaction_id.strip()
        for _, intent in normalized
        if not intent.result_persisted
    )
    if unresolved:
        return DomainGenerationResolution(
            UNKNOWN_EXECUTION_OUTCOME,
            FILESYSTEM_DOMAIN_SCOPE,
            latest_transaction_id,
            MUTATION_INTENT,
            latest_transaction_id,
            unresolved,
            tuple(f"unresolved_mutation_intent={value}" for value in unresolved),
        )

    return DomainGenerationResolution(
        RESOLVED,
        FILESYSTEM_DOMAIN_SCOPE,
        latest_transaction_id,
        MUTATION_INTENT,
        latest_transaction_id,
    )


def intent_from_mapping(payload: Mapping[str, Any]) -> MutationIntentEvidence:
    generations = payload.get("affected_domain_generations")
    if not isinstance(generations, Mapping):
        generations = {}

    return MutationIntentEvidence(
        operation_transaction_id=str(payload.get("operation_transaction_id", "")),
        workflow_run_id=int(payload.get("workflow_run_id", 0)),
        workflow_run_attempt=int(payload.get("workflow_run_attempt", 0)),
        affected_domain_generations={
            str(key): str(value) for key, value in generations.items()
        },
        result_persisted=payload.get("result_persisted") is True,
        result_state=str(payload.get("result_state", "")),
        authority=str(payload.get("authority", CONTROL)),
        lifecycle=str(payload.get("lifecycle", CURRENT)),
        persisted=payload.get("persisted") is True,
    )


def resolve_inventory(payload: Mapping[str, Any]) -> DomainGenerationResolution:
    if payload.get("format_version") != 1:
        return DomainGenerationResolution(
            INVALID_EVIDENCE,
            FILESYSTEM_DOMAIN_SCOPE,
            "",
            MUTATION_INTENT,
            None,
            (),
            ("unsupported_inventory_format",),
        )
    if payload.get("domain_scope") != FILESYSTEM_DOMAIN_SCOPE:
        return DomainGenerationResolution(
            INVALID_EVIDENCE,
            FILESYSTEM_DOMAIN_SCOPE,
            "",
            MUTATION_INTENT,
            None,
            (),
            ("filesystem_domain_scope_required",),
        )

    raw_intents = payload.get("intents")
    if not isinstance(raw_intents, list):
        return DomainGenerationResolution(
            INVALID_EVIDENCE,
            FILESYSTEM_DOMAIN_SCOPE,
            "",
            MUTATION_INTENT,
            None,
            (),
            ("intent_inventory_must_be_list",),
        )

    try:
        intents = tuple(
            intent_from_mapping(item)
            for item in raw_intents
            if isinstance(item, Mapping)
        )
    except (TypeError, ValueError) as error:
        return DomainGenerationResolution(
            INVALID_EVIDENCE,
            FILESYSTEM_DOMAIN_SCOPE,
            "",
            MUTATION_INTENT,
            None,
            (),
            (f"invalid_intent_inventory={error}",),
        )
    if len(intents) != len(raw_intents):
        return DomainGenerationResolution(
            INVALID_EVIDENCE,
            FILESYSTEM_DOMAIN_SCOPE,
            "",
            MUTATION_INTENT,
            None,
            (),
            ("intent_inventory_contains_non_object",),
        )

    return resolve_filesystem_generation(
        intents,
        bootstrap_generation=str(
            payload.get("bootstrap_generation", FILESYSTEM_BOOTSTRAP_GENERATION)
        ),
    )


def resolution_payload(resolution: DomainGenerationResolution) -> dict[str, Any]:
    return {
        "format_version": 1,
        "state": resolution.state,
        "domain_scope": resolution.domain_scope,
        "generation": resolution.generation,
        "source": resolution.source,
        "latest_transaction_id": resolution.latest_transaction_id,
        "unresolved_transaction_ids": list(resolution.unresolved_transaction_ids),
        "reasons": list(resolution.reasons),
        "git_source_dependency": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = json.loads(args.inventory.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("inventory root must be an object")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"filesystem generation inventory invalid: {error}", file=sys.stderr)
        return 2

    resolution = resolve_inventory(payload)
    args.output.write_text(
        json.dumps(resolution_payload(resolution), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0 if resolution.state == RESOLVED else 1


if __name__ == "__main__":
    raise SystemExit(main())
