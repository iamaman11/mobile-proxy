#!/usr/bin/env python3
"""Keep protected Item 20 non-live orchestration wired into canonical control-plane contracts."""

from __future__ import annotations

import json
from pathlib import Path


ITEM20_CONTRACT = Path("contracts/operations/item20-acceptance-v1.json")
ITEM20_HANDOFF_CONTRACT = Path("contracts/operations/item20-private-handoff-v1.json")
GITHUB_CONTRACT = Path("contracts/operations/github-control-plane-v1.json")
TOPOLOGY_CONTRACT = Path("contracts/operations/production-topology-v1.json")
ITEM20_WORKFLOW = Path(".github/workflows/item20-session-orchestration.yml")

EXPECTED_SURFACE = {
    "contract": "contracts/operations/item20-acceptance-v1.json",
    "status": "protected_validation_and_candidate_build_only",
    "workflow": ".github/workflows/item20-session-orchestration.yml",
    "executor": "github-hosted",
    "environment": "none",
    "provider_credentials": "forbidden",
    "provider_mutation": False,
    "phone_execution": False,
    "endpoint_handoff": "not_implemented",
    "live_execution": False,
    "final_production_authority": False,
}

EXPECTED_TOPOLOGY_EXECUTION = (
    "GitHub-hosted exact-current protected-main validation plus exact immutable candidate build only; "
    "no acceptance-vultr environment, provider credentials, provider mutation, phone execution or endpoint handoff"
)
EXPECTED_MIGRATION = (
    "protected_non_live_validation_and_exact_candidate_build_only_no_provider_or_phone_authority"
)
EXPECTED_NEXT_LIFECYCLE = (
    "item_20_must_open_fresh_jit_acceptance_session_with_distinct_item_20_ownership_intent_"
    "and_never_reuse_terminal_item_19_intent"
)
EXPECTED_HANDOFF_IMPLEMENTATION = {
    "public_handoff_enabled": False,
    "private_phone_workflow_enabled": False,
    "private_secret_write_enabled": False,
    "workflow_dispatch_enabled": False,
    "live_execution_authorized": False,
}
EXPECTED_HANDOFF_PRECONDITIONS = {
    "phone_signing_gate": "closed_completed",
    "candidate_sha": "d151dbdd156279e32a5361d304c90f996bd2d565",
    "exact_control_plane_protected_quality": True,
    "fresh_acceptance_authority": True,
    "fresh_vultr_readonly_preflight": True,
    "verified_item20_target_before_endpoint": True,
    "same_window_private_phone_preflight": True,
}
EXPECTED_HANDOFF_IDENTITY = {
    "candidate_sha": "exact_immutable_item19_proven_candidate",
    "control_plane_sha": "exact_current_protected_main",
    "session_nonce": "fresh_opaque_random_at_least_128_bits",
    "transport_endpoint": "derived_only_after_exact_verified_target_resolution_never_authority",
}
EXPECTED_HANDOFF_TRANSPORT = {
    "mechanism": "application_level_sealed_envelope_in_private_workflow_dispatch",
    "public_dispatch_credential_secret_name": "ITEM20_PHONE_HANDOFF_TOKEN",
    "public_dispatch_credential_scope": "private_repository_only",
    "required_private_repository_permissions": ["Actions: write"],
    "private_dispatch_inputs": [
        "candidate_sha",
        "control_plane_sha",
        "session_nonce",
        "sealed_session_envelope",
    ],
    "plaintext_endpoint_in_dispatch_inputs": False,
    "sealed_ciphertext_in_dispatch_inputs": True,
    "public_persistence": "forbidden",
    "encryption": "libsodium_crypto_box_seal_to_dedicated_private_execution_recipient_key",
    "recipient_public_key": "future_protected_canonical_public_value_not_secret",
    "recipient_private_key_secret_name": "ITEM20_HANDOFF_PRIVATE_KEY_B64",
    "recipient_private_key_location": "private_repository_actions_secret_only",
    "public_job_private_secret_write": "forbidden",
    "dispatch_run_correlation": "fresh_session_nonce_without_plaintext_endpoint_or_provider_identity",
}
EXPECTED_HANDOFF_ENVELOPE = {
    "format_version": 1,
    "plaintext_fields_before_sealing": [
        "candidate_sha",
        "control_plane_sha",
        "session_nonce",
        "transport_endpoint",
    ],
    "provider_uuid": "forbidden",
    "provider_credentials": "forbidden",
    "phone_credentials": "forbidden",
}
EXPECTED_HANDOFF_CRASH_RECOVERY = {
    "serialized_public_lifecycle": True,
    "serialized_private_session": True,
    "stale_envelope_must_fail_tuple_match": True,
    "ciphertext_single_use_by_session_nonce": True,
    "private_decryption_key_not_mutated_by_public_job": True,
    "provider_cleanup_runs_even_if_dispatch_or_private_execution_fails": True,
    "acceptance_success_requires_terminal_private_result": True,
    "acceptance_success_requires_provider_terminal_cleanup": True,
}
EXPECTED_HANDOFF_EVIDENCE = {
    "public_endpoint_recording": False,
    "public_provider_uuid_recording": False,
    "public_secret_or_token_recording": False,
    "private_plaintext_endpoint_evidence_recording": False,
    "public_dispatch_payload_may_record": ["candidate_sha", "control_plane_sha"],
    "private_dispatch_may_retain_only_sealed_ciphertext": True,
    "public_terminal_evidence_may_record": [
        "private_workflow_run_id",
        "private_workflow_conclusion",
        "provider_terminal_cleanup_confirmed",
    ],
}
EXPECTED_HANDOFF_FORBIDDEN = [
    "endpoint_in_public_issue",
    "endpoint_in_public_artifact",
    "endpoint_in_public_output",
    "endpoint_in_public_summary",
    "endpoint_in_public_log",
    "plaintext_endpoint_in_workflow_dispatch_input",
    "provider_uuid_in_handoff_envelope_or_dispatch",
    "vultr_credentials_on_private_phone_runner",
    "handoff_token_on_private_phone_runner",
    "private_handoff_decryption_key_on_public_runner",
    "public_handoff_job_with_private_repository_secrets_write",
    "handoff_while_issue_115_open",
    "handoff_without_fresh_exact_candidate_acceptance_authority",
    "handoff_without_fresh_exact_candidate_vultr_readonly_preflight",
    "handoff_before_exact_verified_item20_target",
    "live_execution_from_this_design_contract",
    "plaintext_public_handoff_envelope",
    "gcp_or_manual_provider_fallback",
]


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


def _check_handoff_contract(handoff: dict[str, object]) -> list[str]:
    errors: list[str] = []
    expected_top = {
        "contract_version": 1,
        "status": "protected_design_only_not_enabled",
        "canonical_repository": "iamaman11/mobile-proxy",
        "private_execution_repository": "iamaman11/mobile-proxy-production",
        "tracker_issue": 135,
        "phone_signing_gate_issue": 115,
    }
    for key, value in expected_top.items():
        if handoff.get(key) != value:
            errors.append(f"Item 20 handoff contract {key!r} differs from protected design")

    expected_sections = {
        "implementation": EXPECTED_HANDOFF_IMPLEMENTATION,
        "future_live_preconditions": EXPECTED_HANDOFF_PRECONDITIONS,
        "identity": EXPECTED_HANDOFF_IDENTITY,
        "transport": EXPECTED_HANDOFF_TRANSPORT,
        "envelope": EXPECTED_HANDOFF_ENVELOPE,
        "crash_recovery": EXPECTED_HANDOFF_CRASH_RECOVERY,
        "evidence": EXPECTED_HANDOFF_EVIDENCE,
        "forbidden": EXPECTED_HANDOFF_FORBIDDEN,
    }
    for key, value in expected_sections.items():
        if handoff.get(key) != value:
            errors.append(f"Item 20 handoff contract section {key!r} differs from protected design")
    return errors


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    item20 = _load(root, ITEM20_CONTRACT, errors)
    handoff = _load(root, ITEM20_HANDOFF_CONTRACT, errors)
    github = _load(root, GITHUB_CONTRACT, errors)
    topology = _load(root, TOPOLOGY_CONTRACT, errors)

    if github.get("item20_acceptance_contract") != str(ITEM20_CONTRACT):
        errors.append("GitHub control plane does not bind the protected Item 20 contract")
    if github.get("item20_private_handoff_contract") != str(ITEM20_HANDOFF_CONTRACT):
        errors.append("GitHub control plane does not bind the protected Item 20 private handoff design")
    if github.get("item20_non_live_orchestration") != EXPECTED_SURFACE:
        errors.append("GitHub Item 20 non-live orchestration wiring differs from protected value")

    orchestration = item20.get("orchestration")
    if not isinstance(orchestration, dict):
        errors.append("Item 20 contract orchestration block is missing")
    else:
        expected_contract_fields = {
            "status": EXPECTED_SURFACE["status"],
            "workflow": EXPECTED_SURFACE["workflow"],
            "executor": EXPECTED_SURFACE["executor"],
            "provider_environment": "none",
            "provider_credentials": "forbidden",
            "provider_mutation": False,
            "phone_execution": False,
            "endpoint_handoff": "not_implemented",
        }
        for key, value in expected_contract_fields.items():
            if orchestration.get(key) != value:
                errors.append(f"Item 20 contract orchestration field {key!r} differs")

    authorization = item20.get("authorization")
    if not isinstance(authorization, dict) or authorization != {
        "endpoint_handoff_authorized": False,
        "final_production_authority": False,
        "live_execution_authorized": False,
        "phone_mutation_authorized": False,
        "provider_mutation_authorized": False,
    }:
        errors.append("Item 20 protected contract must remain non-live and non-mutating")

    current_handoff = item20.get("handoff")
    if not isinstance(current_handoff, dict) or current_handoff.get("status") != "not_implemented":
        errors.append("Item 20 active acceptance contract must keep endpoint handoff unimplemented")

    if handoff:
        errors.extend(_check_handoff_contract(handoff))

    execution = topology.get("execution")
    if not isinstance(execution, dict) or execution.get("item20_non_live") != EXPECTED_TOPOLOGY_EXECUTION:
        errors.append("production topology does not expose the protected Item 20 non-live boundary")

    migration = topology.get("migration_status")
    if not isinstance(migration, dict):
        errors.append("production topology migration status is missing")
    else:
        if migration.get("item_20_non_live_orchestration") != EXPECTED_MIGRATION:
            errors.append("production topology Item 20 non-live checkpoint differs")
        if migration.get("next_acceptance_lifecycle") != EXPECTED_NEXT_LIFECYCLE:
            errors.append("production topology Item 20 live-session gate differs")
        if migration.get("phone_mutation") != "item_20_blocked_by_signing_continuity_gate_issue_115":
            errors.append("production topology no longer preserves the #115 phone-mutation gate")

    workflow_path = root / ITEM20_WORKFLOW
    if not workflow_path.is_file():
        errors.append("protected Item 20 non-live orchestration workflow is missing")
    else:
        workflow = workflow_path.read_text(encoding="utf-8")
        for required in (
            "runs-on: ubuntu-latest",
            "Verify build-only Item 20 orchestration boundary",
            "Build exact immutable candidate server artifact",
            "Provider mutation authorized: false",
            "Phone mutation authorized: false",
            "Endpoint handoff authorized: false",
            "Live execution authorized: false",
        ):
            if required not in workflow:
                errors.append(f"Item 20 non-live workflow is missing boundary token {required!r}")

        lowered = workflow.lower()
        for forbidden in (
            "environment: acceptance-vultr",
            "environment: production-vultr",
            "vultr_api_key",
            "vultr_ssh_private_key",
            "item20_phone_handoff_token",
            "item20_handoff_private_key_b64",
            "sealed_session_envelope",
            "self-hosted",
            "adb ",
            "/v2/instances",
            "curl -x post",
            "curl -x delete",
            "curl -x patch",
        ):
            if forbidden in lowered:
                errors.append(f"Item 20 non-live workflow contains forbidden live token {forbidden!r}")

    return errors


def main() -> int:
    errors = check_repository(Path(__file__).resolve().parents[1])
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
