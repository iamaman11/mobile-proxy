#!/usr/bin/env python3
"""Fail closed when Android migration and final release authority ordering drift."""

from __future__ import annotations

import json
from pathlib import Path

CONTRACT = Path("contracts/operations/final-release-authority-v1.json")
WORKFLOW = Path(".github/workflows/release-tag.yml")
ORDER_DOC = Path("docs/operations/final-release-authority-order.md")
BASELINE_PLAN = Path("docs/PRODUCTION_BASELINE_PLAN.md")
PHONE_DOC = Path("docs/operations/phone-gitops-runtime.md")

EXPECTED_COMMAND = {
    "issue": 90,
    "syntax": "/release-tag vMAJOR.MINOR.PATCH <full_sha>",
    "authorized_actor": "repository_owner",
}
EXPECTED_PRECONDITIONS = {
    "item20_tracker_issue": 135,
    "item20_required_state": "closed",
    "item20_required_state_reason": "completed",
    "phone_signing_gate_issue": 115,
    "phone_signing_required_state": "closed",
    "phone_signing_required_state_reason": "completed",
    "item20_release_sha_marker": "final_release_control_plane_sha",
    "target_sha": "exact_full_40_char_sha_matching_item20_release_sha_marker",
    "target_main_quality": "completed_successful_push_on_main",
    "target_must_be_ancestor_of_current_main": True,
    "canonical_release_contract_verified": True,
}
EXPECTED_ORDERING = {
    "android_signing_generation_migration": "pre_item20_exact_sha_signed_candidate_without_final_v_tag_or_release",
    "item20_physical_acceptance": "must_complete_before_final_v_tag",
    "final_v_tag": "item21_only_after_item20_closed_completed",
    "release_publication": "only_after_exact_tag_quality_success",
    "production_promotion": "only_after_final_release",
}
EXPECTED_TAG = {
    "kind": "annotated",
    "pattern": r"^v[0-9]+\.[0-9]+\.[0-9]+$",
    "deletion_forbidden": True,
    "non_fast_forward_forbidden": True,
}
EXPECTED_FORBIDDEN = [
    "release_tag_command_from_issue_162",
    "final_v_tag_while_item20_open",
    "final_v_tag_without_item20_exact_release_sha_marker",
    "final_v_tag_while_phone_signing_gate_open",
    "android_signing_generation_migration_requiring_final_v_tag",
    "android_signing_generation_migration_creating_final_release_authority",
    "production_promotion_before_final_release",
]


def _read(root: Path, path: Path, errors: list[str]) -> str:
    try:
        return (root / path).read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"cannot read {path}: {error}")
        return ""


def _load_contract(root: Path, errors: list[str]) -> dict[str, object]:
    body = _read(root, CONTRACT, errors)
    if not body:
        return {}
    try:
        value = json.loads(body)
    except json.JSONDecodeError as error:
        errors.append(f"cannot parse {CONTRACT}: {error}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{CONTRACT} root must be an object")
        return {}
    return value


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    contract = _load_contract(root, errors)
    workflow = _read(root, WORKFLOW, errors)
    order_doc = _read(root, ORDER_DOC, errors)
    baseline = _read(root, BASELINE_PLAN, errors)
    phone_doc = _read(root, PHONE_DOC, errors)

    expected_top = {
        "contract_version": 1,
        "status": "protected",
        "canonical_repository": "iamaman11/mobile-proxy",
        "workflow": str(WORKFLOW),
    }
    for key, value in expected_top.items():
        if contract.get(key) != value:
            errors.append(f"final release authority contract {key!r} differs from protected value")
    if contract.get("command") != EXPECTED_COMMAND:
        errors.append("final release command authority must remain on canonical tracker #90")
    if contract.get("preconditions") != EXPECTED_PRECONDITIONS:
        errors.append("final release preconditions differ from protected Item 20 ordering")
    if contract.get("ordering") != EXPECTED_ORDERING:
        errors.append("final release ordering differs from protected Item 20 -> Item 21 sequence")
    if contract.get("tag") != EXPECTED_TAG:
        errors.append("final release tag contract must remain exact annotated semantic version")
    if contract.get("forbidden") != EXPECTED_FORBIDDEN:
        errors.append("final release forbidden ordering set differs")

    required_workflow_tokens = (
        "github.event.issue.number == 90",
        "ITEM20_ISSUE: 135",
        "PHONE_SIGNING_ISSUE: 115",
        'item20.get("state") != "closed"',
        'item20.get("state_reason") != "completed"',
        'signing.get("state") != "closed"',
        'signing.get("state_reason") != "completed"',
        "final_release_control_plane_sha",
        "target SHA does not match Item 20 final release marker",
        "target SHA has no exact successful main Quality run",
        "git merge-base --is-ancestor",
        "scripts/verify_android_release_contract.py",
        "git tag -a",
        "git cat-file -t",
    )
    for token in required_workflow_tokens:
        if token not in workflow:
            errors.append(f"release-tag workflow is missing protected ordering token {token!r}")
    for forbidden in (
        "github.event.issue.number == 162",
        "CANONICAL_TAG: v0.1.4",
    ):
        if forbidden in workflow:
            errors.append(f"release-tag workflow contains forbidden pre-Item20 authority token {forbidden!r}")

    required_order_doc_tokens = (
        "Version metadata is not release authority.",
        "A final `v*` tag is therefore an **output** of successful Item 20, never an input to #162.",
        "final_release_control_plane_sha",
        "#162 does **not** authorize:",
    )
    for token in required_order_doc_tokens:
        if token not in order_doc:
            errors.append(f"final release order document is missing normative token {token!r}")

    baseline_required = (
        "Only after successful physical acceptance, create the final immutable release evidence and protected annotated `vMAJOR.MINOR.PATCH` tag",
        "20. immutable-SHA physical acceptance on the real phone",
        "21. final immutable release evidence, protected annotated release tag and artifacts",
    )
    for token in baseline_required:
        if token not in baseline:
            errors.append(f"production baseline release ordering drifted: missing {token!r}")

    phone_required = (
        "Final release authority ordering",
        "No final `v0.1.4` tag or GitHub Release is an input to the signing-generation migration.",
        "exact canonical SHA plus retained signed-candidate evidence",
    )
    for token in phone_required:
        if token not in phone_doc:
            errors.append(f"phone GitOps document is not synchronized with release ordering: missing {token!r}")

    return errors


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    failures = check_repository(args.repo_root.resolve())
    if failures:
        print("final release authority ordering validation failed:")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)
    print("final release authority ordering validation passed")
