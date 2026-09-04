#!/usr/bin/env python3
"""Protect retained Item20 pure invariants while legacy execution authority stays historical."""

from __future__ import annotations

import json
from pathlib import Path


HISTORICAL_ITEM19_SHA = "d151dbdd156279e32a5361d304c90f996bd2d565"
RETIREMENT = Path("contracts/operations/historical-public-acceptance-retirement-v1.json")
FINAL_RELEASE_V1 = Path("contracts/operations/final-release-authority-v1.json")
PHYSICAL_RUNBOOK = Path("docs/physical-phone-acceptance-runbook.md")
ITEM19_STATE_DOC = Path("docs/architecture/acceptance-vm-binding-store.md")
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


def check_retirement_contract(retirement: dict[str, object]) -> list[str]:
    errors: list[str] = []
    if retirement.get("status") != "protected_historical_non_executable":
        errors.append("legacy public authority retirement status differs")

    snapshots = retirement.get("historical_contract_snapshots")
    required_snapshots = {
        "contracts/operations/github-control-plane-v1.json",
        "contracts/operations/vultr-readonly-preflight-v1.json",
        "contracts/operations/item20-admission-readiness-v1.json",
        "contracts/operations/item20-acceptance-v1.json",
        "contracts/operations/production-topology-v1.json",
        "contracts/operations/final-release-authority-v1.json",
    }
    if not isinstance(snapshots, list) or not required_snapshots.issubset(set(snapshots)):
        errors.append("legacy authority retirement registry lost required historical contract snapshots")

    historical_docs = retirement.get("historical_execution_docs")
    required_docs = {str(PHYSICAL_RUNBOOK), str(ITEM19_STATE_DOC)}
    if not isinstance(historical_docs, list) or not required_docs.issubset(set(historical_docs)):
        errors.append("legacy Item19/Item20 execution documents are not classified historical-only")

    execution = retirement.get("execution")
    if not isinstance(execution, dict):
        errors.append("legacy authority retirement execution block is missing")
    else:
        for key in (
            "issue_comment_execution",
            "workflow_dispatch_execution",
            "provider_api_execution",
            "provider_mutation",
            "phone_execution",
            "private_controller_mutation",
            "legacy_public_item20_execution_authority",
            "legacy_final_release_v1_authority",
        ):
            if execution.get(key) is not False:
                errors.append(f"legacy retirement unexpectedly enables {key}")

    superseded = retirement.get("superseded_by")
    if not isinstance(superseded, dict) or superseded.get("product_release") != (
        "contracts/operations/product-release-authority-v2.json"
    ) or superseded.get("runtime_deployment_authority") != "iamaman11/mobile-proxy-production":
        errors.append("legacy authority retirement no longer binds Product Release v2 and private deployment authority")
    return errors


def check_final_release_v1(contract: dict[str, object]) -> list[str]:
    errors: list[str] = []
    if contract.get("contract_version") != 1:
        errors.append("historical final-release contract version differs")
    if contract.get("status") != "protected_historical_non_executable":
        errors.append("final-release v1 must remain explicitly historical and non-executable")
    if contract.get("historical_snapshot") is not True:
        errors.append("final-release v1 lost historical snapshot classification")
    if contract.get("superseded_by") != "contracts/operations/product-release-authority-v2.json":
        errors.append("final-release v1 no longer points to Product Release v2")
    if contract.get("execution_authority") is not False:
        errors.append("final-release v1 cannot regain execution authority")
    return errors


def check_item20_candidate_evidence_verifier_text(verifier: str) -> list[str]:
    errors: list[str] = []
    for required in (
        "Pure verifier for fresh single-SHA Item 20 candidate evidence",
        "def validate_sha(",
        "def verify_contract(",
        "def verify_control_plane(",
        "def verify_workflow_run(",
        "def verify_artifact_metadata(",
        "def verify_candidate_chain(",
        "candidate_sha != control_plane_sha",
        "candidate/control-plane SHA mismatch violates 10/10 single-SHA acceptance",
    ):
        if required not in verifier:
            errors.append(f"retained Item20 pure verifier is missing {required!r}")

    for forbidden in (
        f'_IMMUTABLE_CANDIDATE = "{HISTORICAL_ITEM19_SHA}"',
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
            errors.append(f"retained Item20 pure verifier contains forbidden live token {forbidden!r}")
    return errors


def check_item20_contract(contract: dict[str, object]) -> list[str]:
    errors: list[str] = []
    if contract.get("contract_version") != 1:
        errors.append("retained Item20 historical contract version differs")

    historical = contract.get("historical_item19_proof")
    if not isinstance(historical, dict) or historical.get("candidate_sha") != HISTORICAL_ITEM19_SHA:
        errors.append("Item20 contract lost the immutable historical Item19 proof SHA")
    if not isinstance(historical, dict) or historical.get("item19_quality_run_id") != 33341602485:
        errors.append("Item20 contract historical Item19 Quality run differs")
    if not isinstance(historical, dict) or historical.get("role") != (
        "historical_provider_lifecycle_proof_only_not_item20_final_candidate"
    ):
        errors.append("Item20 contract does not label Item19 evidence as historical-only")

    identity = contract.get("identity")
    if not isinstance(identity, dict) or identity.get("exact_equality_required") is not True:
        errors.append("retained Item20 identity lost exact candidate/control-plane equality")

    authorization = contract.get("authorization")
    if authorization != {
        "endpoint_handoff_authorized": False,
        "final_production_authority": False,
        "live_execution_authorized": False,
        "phone_mutation_authorized": False,
        "provider_mutation_authorized": False,
    }:
        errors.append("retained Item20 contract grants live, mutation or production authority")

    serialized = json.dumps(contract, sort_keys=True)
    for forbidden in (
        "candidate_must_match_item19_closeout",
        "exact_immutable_item19_proven_sha",
        "immutable_item19_proven",
        "candidate_control_plane_separation_required",
        "candidate_control_plane_value_inequality_required",
        "control_plane_may_advance_without_redefining_candidate",
    ):
        if forbidden in serialized:
            errors.append(f"Item20 contract contains retired two-SHA semantic {forbidden!r}")
    return errors


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    retirement = _load(root, RETIREMENT, errors)
    final_release_v1 = _load(root, FINAL_RELEASE_V1, errors)
    closeout = _read(root, ITEM19_CLOSEOUT, errors)
    item19 = _read(root, ITEM19_LIFECYCLE, errors)
    binding_store = _read(root, BINDING_STORE, errors)
    item20 = _read(root, ITEM20_IDENTITY, errors)
    item20_lifecycle = _read(root, ITEM20_LIFECYCLE, errors)
    admission = _read(root, ITEM20_ADMISSION, errors)
    candidate_evidence = _read(root, ITEM20_CANDIDATE_EVIDENCE, errors)
    contract = _load(root, ITEM20_CONTRACT, errors)
    lib = _read(root, LIB, errors)

    if retirement:
        errors.extend(check_retirement_contract(retirement))
    if final_release_v1:
        errors.extend(check_final_release_v1(final_release_v1))

    for historical_path in (PHYSICAL_RUNBOOK, ITEM19_STATE_DOC):
        if not (root / historical_path).is_file():
            errors.append(f"historical execution record is missing: {historical_path}")

    for required in (
        "Candidate SHA:",
        HISTORICAL_ITEM19_SHA,
        "terminal; that intent is not reusable by Item 20",
    ):
        if required not in closeout:
            errors.append(f"Item19 closeout is missing immutable historical token {required!r}")

    legacy_item19_intent = 'format!("candidate:{candidate_sha}")'
    if legacy_item19_intent not in item19:
        errors.append("Item19 historical ownership intent semantics changed")

    for required in (
        "pub enum AcceptanceVmIntentNamespace",
        "Item19,",
        "Item20,",
        'Self::Item19 => format!("candidate:{candidate_sha}"),',
        'Self::Item20 => format!("item20:candidate:{candidate_sha}"),',
        "pub fn new_item20",
        "BindingStoreError::TerminalIntentReuse",
        "item19_and_item20_intents_are_distinct_and_exact",
        "unknown_namespace_record_poisoning_fails_closed",
    ):
        if required not in binding_store:
            errors.append(f"retained durable acceptance store is missing pure namespace guard {required!r}")

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
            errors.append(f"retained typed Item20 identity is missing {required!r}")

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
            errors.append(f"retained typed Item20 identity contains forbidden authority token {forbidden!r}")

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
            errors.append(f"retained typed Item20 session lifecycle is missing {required!r}")

    for required in (
        "from verify_item20_candidate_evidence import verify_candidate_chain",
        "def verify_contract",
        "def verify_control_plane",
        "def verify_admission",
        "candidate_sha != control_plane_sha",
        '"provider_mutation_authorized": False',
        '"phone_mutation_authorized": False',
        '"endpoint_handoff_authorized": False',
        '"live_execution_authorized": False',
    ):
        if required not in admission:
            errors.append(f"retained Item20 admission verifier is missing pure/non-live token {required!r}")

    for forbidden in (
        f'_IMMUTABLE_CANDIDATE = "{HISTORICAL_ITEM19_SHA}"',
        "VULTR_API_KEY",
        "VULTR_SSH_PRIVATE_KEY",
        "production-vultr",
        "subprocess.",
        "urllib.request",
        "requests.",
        "delete_instance(",
        "create_instance(",
        "adb ",
    ):
        if forbidden in admission:
            errors.append(f"retained Item20 admission verifier contains forbidden live token {forbidden!r}")

    errors.extend(check_item20_candidate_evidence_verifier_text(candidate_evidence))
    if contract:
        errors.extend(check_item20_contract(contract))

    if "pub mod item20_acceptance;" not in lib:
        errors.append("operator-cli does not export the retained typed Item20 acceptance identity")
    if "pub mod item20_session_lifecycle;" not in lib:
        errors.append("operator-cli does not export the retained typed Item20 session lifecycle")
    return errors


def main() -> int:
    errors = check_repository(Path(__file__).resolve().parents[1])
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
