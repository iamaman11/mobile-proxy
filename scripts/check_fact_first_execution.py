#!/usr/bin/env python3
"""Protect the unique physical-device control foundation invariants.

This is intentionally a small cross-document semantic guard. It does not test other
checks, does not validate test invocation, and does not encode a long Markdown
step-by-step roadmap. Behavioral State Machine semantics belong in direct reducer/
operation tests and real-phone acceptance.
"""

from __future__ import annotations

from pathlib import Path


IMPLEMENTATION = Path("IMPLEMENTATION_PLAN.md")
BASELINE = Path("docs/PRODUCTION_BASELINE_PLAN.md")
ARCHITECTURE = Path("docs/architecture/ARCHITECTURE_STANDARD.md")
OPERATION = Path("docs/operation-state-machine-v1.md")

REQUIRED: dict[Path, tuple[str, ...]] = {
    IMPLEMENTATION: (
        "The sole canonical roadmap for current development is:",
        "There is one sequential development direction",
        "blocking prerequisite for further application growth",
        "explicit ambiguous execution outcome",
        "re-observation",
        "protect boundaries, not the current instance",
        "do not add a checker only to verify another checker/test exists or ran",
    ),
    BASELINE: (
        "sole canonical implementation roadmap for current development",
        "Blocking foundation gate: reproducible physical-device control first",
        "one sequential development direction",
        "Operation execution result, independent postcondition verification and evidence persistence are separate dimensions.",
        "controller failure MUST NOT be collapsed into target-operation failure",
        "Do not verify verification.",
        "protect boundaries, not bootstrap state",
    ),
    ARCHITECTURE: (
        "one primary developer",
        "No code for code",
        "adding a checker whose only purpose is to confirm that another checker/test exists or ran",
        "Physical-device-control foundation",
        "Protect boundaries, not bootstrap state",
    ),
    OPERATION: (
        "operation_execution_result",
        "postcondition_verification_result",
        "evidence_persistence_result",
        "UNKNOWN_EXECUTION_OUTCOME",
        "non-idempotent mutation is never retried merely because the controller did not receive its result",
        "Protect boundaries, not bootstrap state",
        "Only then grow application behavior through this engine.",
    ),
}


def _read(root: Path, path: Path, errors: list[str]) -> str:
    try:
        return (root / path).read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"cannot read {path}: {error}")
        return ""


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    for path, tokens in REQUIRED.items():
        body = _read(root, path, errors)
        for token in tokens:
            if token not in body:
                errors.append(f"{path} is missing device-control foundation invariant {token!r}")
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = check_repository(root)
    if errors:
        print("device-control foundation consistency validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("device-control foundation consistency validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
