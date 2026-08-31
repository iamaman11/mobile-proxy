#!/usr/bin/env python3
"""Prevent Production Baseline item-20 identity and gate drift."""

from __future__ import annotations

from pathlib import Path


PLAN = Path("docs/PRODUCTION_BASELINE_PLAN.md")
PHYSICAL_RUNBOOK = Path("docs/physical-phone-acceptance-runbook.md")
PHONE_RUNTIME = Path("docs/operations/phone-gitops-runtime.md")
ITEM19_CLOSEOUT = Path("docs/operations/item19-provider-proof-closeout.md")
ITEM19_LIFECYCLE = Path("apps/operator-cli/src/bin/item19-acceptance-lifecycle.rs")
BINDING_STORE = Path("apps/operator-cli/src/github_vm_binding_store.rs")
ITEM20_IDENTITY = Path("apps/operator-cli/src/item20_acceptance.rs")
LIB = Path("apps/operator-cli/src/lib.rs")


def _read(root: Path, path: Path, errors: list[str]) -> str:
    try:
        return (root / path).read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"cannot read {path}: {error}")
        return ""


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    plan = _read(root, PLAN, errors)
    physical = _read(root, PHYSICAL_RUNBOOK, errors)
    phone = _read(root, PHONE_RUNTIME, errors)
    closeout = _read(root, ITEM19_CLOSEOUT, errors)
    item19 = _read(root, ITEM19_LIFECYCLE, errors)
    binding_store = _read(root, BINDING_STORE, errors)
    item20 = _read(root, ITEM20_IDENTITY, errors)
    lib = _read(root, LIB, errors)

    for required in (
        "Item 20 is the first unfinished delivery item",
        "Item 20 remains blocked by the signing-continuity gate",
        "distinct ownership intent rather than reuse Item 19's terminal proof intent",
    ):
        if required not in plan:
            errors.append(f"canonical baseline plan is missing Item 20 boundary {required!r}")

    for required in (
        "distinct Item 20 ownership intent",
        "terminal Item 19 proof intent is never reused",
    ):
        if required not in physical:
            errors.append(f"physical acceptance runbook is missing Item 20 identity boundary {required!r}")

    for required in (
        "The physical item-20 window opens only after the Item 19 provider proof is complete",
        "mutable-phone gate is satisfied",
        "distinct Item 20 ownership intent",
    ):
        if required not in phone:
            errors.append(f"phone runtime is missing Item 20 gate token {required!r}")

    for required in (
        "Candidate SHA:",
        "d151dbdd156279e32a5361d304c90f996bd2d565",
        "terminal; that intent is not reusable by Item 20",
    ):
        if required not in closeout:
            errors.append(f"Item 19 closeout is missing immutable handoff token {required!r}")

    legacy_item19_intent = 'format!("candidate:{candidate_sha}")'
    if legacy_item19_intent not in item19:
        errors.append("Item 19 historical ownership intent semantics changed")

    for required in (
        "pub enum AcceptanceVmIntentNamespace",
        "Item19,",
        "Item20,",
        'Self::Item19 => format!("candidate:{candidate_sha}"),',
        'Self::Item20 => format!("item20:candidate:{candidate_sha}"),',
        "pub fn new_item20",
        "BindingStoreError::TerminalIntentReuse",
        "item19_and_item20_intents_are_distinct_and_exact",
        "independent_ledgers_can_share_one_immutable_candidate",
        "unknown_namespace_record_poisoning_fails_closed",
    ):
        if required not in binding_store:
            errors.append(f"durable acceptance store is missing Item 20 namespace guard {required!r}")

    for required in (
        'const ITEM20_INTENT_PREFIX: &str = "item20:candidate:";',
        "pub struct Item20SessionIdentity",
        "candidate_sha: String",
        "control_plane_sha: String",
        "LifecycleScope::Acceptance",
        "pub fn ownership_intent",
        "pub fn desired_vm",
    ):
        if required not in item20:
            errors.append(f"typed Item 20 identity is missing {required!r}")

    for forbidden in (
        legacy_item19_intent,
        "item20-physical:candidate:",
        "LifecycleScope::Production",
        "production-vultr",
        "VULTR_API_KEY",
        "VULTR_SSH_PRIVATE_KEY",
        "adb ",
    ):
        if forbidden in item20:
            errors.append(f"typed Item 20 identity contains forbidden boundary token {forbidden!r}")

    if "pub mod item20_acceptance;" not in lib:
        errors.append("operator-cli does not export the typed Item 20 acceptance identity")

    return errors


def main() -> int:
    errors = check_repository(Path(__file__).resolve().parents[1])
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
