#!/usr/bin/env python3
"""Prevent Production Baseline item-20 identity and gate drift."""

from __future__ import annotations

import json
from pathlib import Path


PLAN = Path("docs/PRODUCTION_BASELINE_PLAN.md")
PHYSICAL_RUNBOOK = Path("docs/physical-phone-acceptance-runbook.md")
PHONE_RUNTIME = Path("docs/operations/phone-gitops-runtime.md")
ITEM19_CLOSEOUT = Path("docs/operations/item19-provider-proof-closeout.md")
ITEM19_LIFECYCLE = Path("apps/operator-cli/src/bin/item19-acceptance-lifecycle.rs")
BINDING_STORE = Path("apps/operator-cli/src/github_vm_binding_store.rs")
ITEM20_IDENTITY = Path("apps/operator-cli/src/item20_acceptance.rs")
ITEM20_LIFECYCLE = Path("apps/operator-cli/src/item20_session_lifecycle.rs")
ITEM20_CONTRACT = Path("contracts/operations/item20-acceptance-v1.json")
ITEM20_ADMISSION = Path("scripts/verify_item20_admission.py")
ITEM20_CANDIDATE_EVIDENCE = Path("scripts/verify_item20_candidate_evidence.py")
LIB = Path("apps/operator-cli/src/lib.rs")


def _read(root: Path, path: Path, errors: list[str]) -> str:
    try:
        return (root / path).read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"cannot read {path}: {error}")
        return ""


def _load(root: Path, path: Path, errors: list[str]) -> dict[str, object]:
    try:
        value = json.loads((root / path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"cannot load {path}: {error}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path} root must be an object")
        return {}
    return value


def check_physical_runbook_text(physical: str) -> list[str]:
    errors: list[str] = []

    for required in (
        "Item 19 provider proof is COMPLETE",
        "protected typed Item 20 acceptance lifecycle",
        "distinct Item 20 ownership intent",
        "terminal Item 19 proof intent is never reused",
        "private Item 20 phone execution must not call Vultr APIs",
        "Fresh immutable `/accept-candidate <sha>` authority",
        "Fresh `/vultr-readonly-preflight <sha>` evidence",
    ):
        if required not in physical:
            errors.append(f"physical acceptance runbook is missing Item 20 boundary {required!r}")

    lowered = physical.lower()
    for forbidden in (
        "while item 19 and the mutable-phone gate remain incomplete",
        "github-hosted item-19 vultr acceptance lifecycle",
        "provider mutation is performed only through the item-19 typed vultr lifecycle",
        "while item 19 is active",
        "already verified item-19 acceptance target",
    ):
        if forbidden in lowered:
            errors.append(f"physical acceptance runbook contains stale Item 19 state {forbidden!r}")

    return errors


def check_item20_candidate_evidence_verifier_text(verifier: str) -> list[str]:
    errors: list[str] = []
    for required in (
        '_IMMUTABLE_CANDIDATE = "d151dbdd156279e32a5361d304c90f996bd2d565"',
        "def validate_sha(",
        "def verify_contract(",
        "def verify_control_plane(",
        "def verify_workflow_run(",
        "def verify_artifact_metadata(",
        "def verify_acceptance_evidence(",
        "def verify_preflight_evidence(",
        "def verify_fresh_order(",
        "def verify_candidate_chain(",
        '"item19_quality_run_id": 33341602485',
        '"candidate_quality_run_attempt": 1',
        '"candidate_control_plane_separation_required": True',
        '"candidate_control_plane_value_inequality_required": False',
        '"selection": "candidate_specific_artifact_then_exact_control_plane_run"',
        'expected_name_prefix="vultr-acceptance-authority"',
        'expected_name_prefix="vultr-readonly-preflight"',
        '"provider_mutation_authorized": False',
        '"phone_mutation_authorized": False',
        '"endpoint_handoff_authorized": False',
        '"live_execution_authorized": False',
        '"final_production_authority": False',
    ):
        if required not in verifier:
            errors.append(f"Item 20 pure candidate evidence verifier is missing {required!r}")

    for forbidden in (
        "candidate_sha == control_plane_sha",
        "identities to remain distinct",
        "VULTR_API_KEY",
        "VULTR_SSH_PRIVATE_KEY",
        "production-vultr",
        "subprocess.",
        "urllib.request",
        "requests.",
        "http.client",
        "socket.",
        "/v2/instances",
        "create_instance(",
        "delete_instance(",
        "adb ",
        "gh workflow run",
        "secrets.create_or_update",
        "secrets.set",
    ):
        if forbidden in verifier:
            errors.append(
                f"Item 20 pure candidate evidence verifier contains forbidden live/external-I/O or identity token {forbidden!r}"
            )

    return errors


def check_item20_contract(contract: dict[str, object]) -> list[str]:
    errors: list[str] = []
    expected = {
        "contract_version": 1,
        "status": "protected_non_live_admission_core",
        "canonical_repository": "iamaman11/mobile-proxy",
        "tracker_issue": 135,
        "completed_provider_proof_issue": 124,
        "phone_signing_gate_issue": 115,
    }
    for key, value in expected.items():
        if contract.get(key) != value:
            errors.append(f"Item 20 admission contract {key!r} differs from protected value")

    immutable = contract.get("immutable_candidate")
    if not isinstance(immutable, dict) or immutable.get("candidate_sha") != (
        "d151dbdd156279e32a5361d304c90f996bd2d565"
    ):
        errors.append("Item 20 admission contract candidate differs from Item 19 closeout")
    if not isinstance(immutable, dict) or immutable.get("item19_quality_run_id") != 33341602485:
        errors.append("Item 20 admission contract historical candidate Quality run differs")

    session = contract.get("session")
    if not isinstance(session, dict) or any(
        session.get(key) != value
        for key, value in {
            "identity_module": "apps/operator-cli/src/item20_acceptance.rs",
            "lifecycle_module": "apps/operator-cli/src/item20_session_lifecycle.rs",
            "ownership_intent_template": "item20:candidate:<candidate_sha>",
            "scope": "acceptance_only",
            "max_controlled_vms": 1,
            "terminal_item19_intent_reuse": "forbidden",
            "transport_endpoint": "derived_only_after_verified_target_resolution_never_authority",
        }.items()
    ):
        errors.append("Item 20 admission contract typed-session boundary differs")

    authorization = contract.get("authorization")
    if not isinstance(authorization, dict) or authorization != {
        "provider_mutation_authorized": False,
        "phone_mutation_authorized": False,
        "endpoint_handoff_authorized": False,
        "live_execution_authorized": False,
        "final_production_authority": False,
    }:
        errors.append("Item 20 admission contract must remain validation-only")

    handoff = contract.get("handoff")
    if not isinstance(handoff, dict) or handoff != {
        "status": "not_implemented",
        "public_provider_uuid_recording": "forbidden",
        "public_transport_endpoint_recording": "forbidden",
        "private_phone_runner_vultr_credentials": "forbidden",
    }:
        errors.append("Item 20 admission contract handoff boundary differs")

    admission = contract.get("admission")
    if not isinstance(admission, dict) or admission.get("fresh_candidate_evidence_required") is not True:
        errors.append("Item 20 admission contract must require fresh candidate evidence")
    if not isinstance(admission, dict) or admission.get("fresh_candidate_evidence_verifier") != (
        "scripts/verify_item20_candidate_evidence.py"
    ):
        errors.append("Item 20 admission contract does not consume the protected candidate verifier")
    required_states = admission.get("required_issue_states") if isinstance(admission, dict) else None
    if required_states != {
        "item19_tracker_124": "closed_completed",
        "item20_tracker_135": "open",
        "phone_signing_gate_115": "closed_completed_before_live_window",
    }:
        errors.append("Item 20 admission contract issue gates differ")

    future_live = contract.get("future_live_candidate_evidence")
    if not isinstance(future_live, dict) or future_live != {
        "acceptance_authority": "fresh_for_exact_candidate",
        "vultr_readonly_preflight": "fresh_for_exact_candidate",
        "same_candidate_required": True,
        "current_core_verification": "protected_pure_verifier_consumed_by_admission_core",
    }:
        errors.append("Item 20 fresh candidate authority requirements differ")

    future_verifier = contract.get("future_live_candidate_verifier")
    if not isinstance(future_verifier, dict) or future_verifier != {
        "candidate_control_plane_separation_required": True,
        "candidate_control_plane_value_inequality_required": False,
        "candidate_quality_run_attempt": 1,
        "grants_live_authority": False,
        "performs_external_io": False,
        "selection": "candidate_specific_artifact_then_exact_control_plane_run",
        "status": "protected_pure_verifier_consumed_by_admission_core",
        "verifier": "scripts/verify_item20_candidate_evidence.py",
        "workflow_wiring": "not_implemented",
    }:
        errors.append("Item 20 pure candidate evidence verifier contract differs")

    forbidden = contract.get("forbidden")
    if not isinstance(forbidden, list) or forbidden != [
        "provider_mutation_from_this_admission_core",
        "phone_mutation_from_this_admission_core",
        "public_endpoint_or_provider_uuid_evidence",
        "terminal_item19_intent_reuse",
        "live_window_without_fresh_exact_candidate_acceptance_authority",
        "live_window_without_fresh_exact_candidate_vultr_readonly_preflight",
        "production_vultr_authority",
        "final_release_tag_or_production_promotion",
        "gcp_or_manual_provider_control",
    ]:
        errors.append("Item 20 forbidden live-boundary set differs")

    return errors


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    plan = _read(root, PLAN, errors)
    physical = _read(root, PHYSICAL_RUNBOOK, errors)
    phone = _read(root, PHONE_RUNTIME, errors)
    closeout = _read(root, ITEM19_CLOSEOUT, errors)
    item19 = _read(root, ITEM19_LIFECYCLE, errors)
    binding_store = _read(root, BINDING_STORE, errors)
    item20 = _read(root, ITEM20_IDENTITY, errors)
    item20_lifecycle = _read(root, ITEM20_LIFECYCLE, errors)
    admission = _read(root, ITEM20_ADMISSION, errors)
    candidate_evidence = _read(root, ITEM20_CANDIDATE_EVIDENCE, errors)
    contract = _load(root, ITEM20_CONTRACT, errors)
    lib = _read(root, LIB, errors)

    for required in (
        "Item 20 is the first unfinished delivery item",
        "Item 20 remains blocked by the signing-continuity gate",
        "distinct ownership intent rather than reuse Item 19's terminal proof intent",
    ):
        if required not in plan:
            errors.append(f"canonical baseline plan is missing Item 20 boundary {required!r}")

    errors.extend(check_physical_runbook_text(physical))

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

    for required in (
        "pub trait Item20LifecycleStore",
        "pub trait Item20AcceptanceProvider",
        "pub fn open_item20_session",
        "pub fn verified_item20_target",
        "pub fn verified_item20_endpoint",
        "pub fn close_item20_session",
        "terminal Item 20 acceptance intent cannot be reused",
    ):
        if required not in item20_lifecycle:
            errors.append(f"typed Item 20 session lifecycle is missing {required!r}")

    for required in (
        "_IMMUTABLE_CANDIDATE",
        "from verify_item20_candidate_evidence import verify_candidate_chain",
        "def verify_contract",
        "def verify_control_plane",
        "def verify_issue_gates",
        "def verify_phone_preflight",
        "def _verify_fresh_result",
        "def verify_admission",
        "verify_candidate_chain(",
        '"fresh_acceptance_authority_verified": True',
        '"fresh_vultr_readonly_preflight_verified": True',
        '"provider_probe_read_only_verified": True',
        '"provider_mutation_authorized": False',
        '"phone_mutation_authorized": False',
        '"endpoint_handoff_authorized": False',
        '"live_execution_authorized": False',
    ):
        if required not in admission:
            errors.append(f"Item 20 non-live admission verifier is missing {required!r}")

    for forbidden in (
        "def verify_acceptance_evidence(",
        "def verify_preflight_evidence(",
        "def verify_artifact_metadata(",
        "VULTR_API_KEY",
        "VULTR_SSH_PRIVATE_KEY",
        "production-vultr",
        "subprocess.",
        "urllib.request",
        "requests.",
        "delete_instance(",
        "create_instance",
        "adb ",
    ):
        if forbidden in admission:
            errors.append(f"Item 20 admission verifier contains duplicated or forbidden live token {forbidden!r}")

    errors.extend(check_item20_candidate_evidence_verifier_text(candidate_evidence))

    if contract:
        errors.extend(check_item20_contract(contract))
        immutable = contract.get("immutable_candidate")
        candidate = immutable.get("candidate_sha") if isinstance(immutable, dict) else None
        if not isinstance(candidate, str) or candidate not in closeout:
            errors.append("Item 20 admission contract candidate is not anchored in Item 19 closeout")

    if "pub mod item20_acceptance;" not in lib:
        errors.append("operator-cli does not export the typed Item 20 acceptance identity")
    if "pub mod item20_session_lifecycle;" not in lib:
        errors.append("operator-cli does not export the typed Item 20 session lifecycle")

    return errors


def main() -> int:
    errors = check_repository(Path(__file__).resolve().parents[1])
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
