#!/usr/bin/env python3
"""Fail closed when the active roadmap drifts away from fact-first production execution."""

from __future__ import annotations

from pathlib import Path


IMPLEMENTATION = Path("IMPLEMENTATION_PLAN.md")
BASELINE = Path("docs/PRODUCTION_BASELINE_PLAN.md")
CONTROL = Path("docs/control-state-machine-v1.md")
OPERATION = Path("docs/operation-state-machine-v1.md")

REQUIRED: dict[Path, tuple[str, ...]] = {
    IMPLEMENTATION: (
        "### Fact-first execution spine",
        "Development MUST advance from the current `CONTROL` projection and exact blocking predicates",
        "Operation execution result",
        "independent postcondition verification",
        "evidence persistence",
        "No phone, runtime, VM or provider is globally `READY`",
        "Android is the first adapter to be proven end to end",
        "VM/provider generalization comes only after the phone baseline",
        "### Android physical-reality authority",
        "The real registered production phone is the authoritative observation oracle for Android device reality.",
        "If an Android predicate or postcondition can be verified on the real production phone",
        "Infrastructure or control-plane hardening may run ahead of the phone only to remove a demonstrated blocker",
        "Return immediately to the real phone",
    ),
    BASELINE: (
        "Production execution is **fact-first**",
        "Current production state is derived only from current scoped `CONTROL` evidence",
        "Operation execution result, independent postcondition verification and evidence persistence are separate dimensions.",
        "No phone, runtime, VM or provider has a stored global `READY` truth.",
        "OBSERVE -> VERIFY -> MUTATE -> INDEPENDENTLY VERIFY -> ACCEPT",
        "required-but-unpersisted evidence fail closed",
        "For Android physical state, the real registered production phone is the authoritative observation oracle.",
        "Unit/integration/hosted-Actions evidence alone cannot complete that Android state.",
        "Infrastructure/control-plane hardening may precede a device operation only to remove a demonstrated blocker",
        "### 6.1 Current fact-first execution sub-sequence",
        "**Current-SHA phone admission**",
        "**Quarantine reconciliation**",
        "VM/provider generalization",
    ),
    CONTROL: (
        "The control state machine MUST be a deterministic projection of bounded evidence.",
        "No evidence -> `UNKNOWN`",
        "Mutation permission always consumes the `CONTROL` projection.",
        "### Android device-reality authority",
        "The real registered production phone is the authoritative observation oracle for Android device reality.",
        "Hosted/offline evidence MUST NOT replace device-backed evidence",
        "Permission is a predicate, never a stored global READY flag",
        "A successful command is an operation result, not proof of its postcondition.",
    ),
    OPERATION: (
        "operation_execution_result",
        "postcondition_verification_result",
        "evidence_persistence_result",
        "Missing durability must not be reconstructed later from narrative, logs or remembered operator state.",
        "### Android physical-reality rule",
        "The real registered production phone is the authoritative observation oracle for Android device reality.",
        "the phase may be completed only from bounded device-backed `CONTROL` evidence",
        "Infrastructure/control-plane work may interrupt the device sequence only to remove a demonstrated blocker",
        "workflow success never substitutes for reducer acceptance",
        "only then generalize the proven operation primitives to a VM/provider adapter",
    ),
}

IMPLEMENTATION_ORDER = (
    "Close the demonstrated evidence-persistence blocker",
    "Return immediately to the real phone",
    "Let durable device facts decide the next transition",
    "Repeat bounded Android filesystem certification",
    "Move APK/signing work through the same transaction model",
    "Move native runtime deployment through the same model",
    "Exercise the complete product data path",
    "Execute the required failure/restart/recovery matrix",
    "Only after the functional phone baseline is accepted, generalize the proven operation primitives to VM/provider adapters",
)

BASELINE_ORDER = (
    "**Evidence reliability**",
    "**Current-SHA phone admission**",
    "**Quarantine reconciliation**",
    "**Android filesystem certification**",
    "**APK/signing lifecycle**",
    "**Native runtime lifecycle**",
    "**Real data path**",
    "**Restart/recovery/failure matrix**",
    "**Soak and release acceptance**",
    "**VM/provider generalization**",
)


def _read(root: Path, path: Path, errors: list[str]) -> str:
    try:
        return (root / path).read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"cannot read {path}: {error}")
        return ""


def _require_tokens(path: Path, body: str, tokens: tuple[str, ...], errors: list[str]) -> None:
    for token in tokens:
        if token not in body:
            errors.append(f"{path} is missing fact-first invariant {token!r}")


def _require_order(path: Path, body: str, markers: tuple[str, ...], errors: list[str]) -> None:
    positions: list[int] = []
    for marker in markers:
        position = body.find(marker)
        if position < 0:
            errors.append(f"{path} is missing ordered fact-first marker {marker!r}")
            return
        positions.append(position)
    if positions != sorted(positions):
        errors.append(f"{path} fact-first delivery sequence is out of order")


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    bodies = {path: _read(root, path, errors) for path in REQUIRED}

    for path, tokens in REQUIRED.items():
        _require_tokens(path, bodies[path], tokens, errors)

    _require_order(IMPLEMENTATION, bodies[IMPLEMENTATION], IMPLEMENTATION_ORDER, errors)
    _require_order(BASELINE, bodies[BASELINE], BASELINE_ORDER, errors)

    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = check_repository(root)
    if errors:
        print("fact-first execution validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("fact-first execution validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
