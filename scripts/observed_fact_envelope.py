from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping


_SCRIPT_DIR = Path(__file__).resolve().parent
_SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")


def _load_control_module():
    path = _SCRIPT_DIR / "control_state_machine.py"
    spec = importlib.util.spec_from_file_location("observed_fact_envelope_control", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load canonical control state machine")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_CONTROL = _load_control_module()


class ObservedFactEnvelopeError(ValueError):
    pass


def require_bounded_ref(value: str, *, label: str) -> str:
    if not isinstance(value, str) or _SAFE_REF.fullmatch(value) is None:
        raise ObservedFactEnvelopeError(f"{label} is not a bounded reference")
    return value


def bounded_identity(namespace: str, raw_value: str) -> str:
    """Return a non-raw stable dependency identity with domain separation."""

    if not namespace or not isinstance(raw_value, str) or not raw_value:
        raise ObservedFactEnvelopeError("bounded identity input is empty")
    digest = hashlib.sha256(
        b"mobile-proxy-observed-fact-v1\0"
        + namespace.encode("utf-8")
        + b"\0"
        + raw_value.encode("utf-8")
    ).hexdigest()
    return f"sha256:{digest}"


def make_envelope(
    *,
    subject: str,
    predicate: str,
    value: Any,
    target: str,
    observation_ref: str,
    source_ref: str,
    dependencies: Iterable[tuple[str, str]],
    authority: str = "CONTROL",
    persisted: bool = False,
) -> dict[str, Any]:
    dependency_values = [
        {"scope": scope, "identity": identity}
        for scope, identity in dependencies
    ]
    payload = {
        "schema_version": 1,
        "subject": subject,
        "predicate": predicate,
        "value": value,
        "target": target,
        "observation_ref": require_bounded_ref(observation_ref, label="observation_ref"),
        "source_ref": require_bounded_ref(source_ref, label="source_ref"),
        "dependencies": dependency_values,
        "authority": authority,
        "persisted": bool(persisted),
    }
    # Reuse the canonical classifier as the semantic validator. A producer report is
    # intentionally unpersisted; otherwise a self-authored report could authorize its
    # own reuse before durable orchestration evidence exists.
    fact = to_observed_fact(payload)
    dependency_context = {item.scope: item.identity for item in fact.dependencies}
    validity = _CONTROL.classify_observed_fact(fact, dependency_context)
    if persisted and validity.state != _CONTROL.FACT_VALID:
        raise ObservedFactEnvelopeError(
            "persisted observed fact is not semantically valid: " + ",".join(validity.reasons)
        )
    if not persisted and validity.state != _CONTROL.FACT_UNPERSISTED:
        raise ObservedFactEnvelopeError(
            "unpersisted observed fact envelope is malformed: " + ",".join(validity.reasons)
        )
    return payload


def to_observed_fact(payload: Mapping[str, Any]):
    if payload.get("schema_version") != 1:
        raise ObservedFactEnvelopeError("unsupported observed fact envelope version")
    dependencies = payload.get("dependencies")
    if not isinstance(dependencies, list):
        raise ObservedFactEnvelopeError("dependencies must be an array")
    try:
        parsed_dependencies = tuple(
            _CONTROL.FactDependency(str(item["scope"]), str(item["identity"]))
            for item in dependencies
        )
        return _CONTROL.ObservedFact(
            subject=str(payload["subject"]),
            predicate=str(payload["predicate"]),
            value=payload.get("value"),
            target=str(payload["target"]),
            observation_ref=str(payload["observation_ref"]),
            source_ref=str(payload["source_ref"]),
            dependencies=parsed_dependencies,
            authority=str(payload.get("authority", "CONTROL")),
            persisted=bool(payload.get("persisted", False)),
        )
    except (KeyError, TypeError) as error:
        raise ObservedFactEnvelopeError("observed fact envelope is incomplete") from error


def mark_persisted(payload: Mapping[str, Any], *, observation_ref: str) -> dict[str, Any]:
    """Return a durable copy after orchestration has independently persisted evidence."""

    copied = dict(payload)
    copied["observation_ref"] = require_bounded_ref(observation_ref, label="observation_ref")
    copied["persisted"] = True
    fact = to_observed_fact(copied)
    context = {item.scope: item.identity for item in fact.dependencies}
    validity = _CONTROL.classify_observed_fact(fact, context)
    if validity.state != _CONTROL.FACT_VALID:
        raise ObservedFactEnvelopeError(
            "persisted observed fact is not reusable: " + ",".join(validity.reasons)
        )
    return copied
