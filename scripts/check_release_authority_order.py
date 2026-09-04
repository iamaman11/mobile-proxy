#!/usr/bin/env python3
"""Fail closed when Product Release v2 readiness, ownership or ordering drift."""

from __future__ import annotations

import json
from pathlib import Path

CONTRACT = Path("contracts/operations/product-release-authority-v2.json")
READINESS_WORKFLOW = Path(".github/workflows/product-release-readiness.yml")
TAG_WORKFLOW = Path(".github/workflows/release-tag.yml")
RELEASE_WORKFLOW = Path(".github/workflows/release.yml")
ORDER_DOC = Path("docs/operations/final-release-authority-order.md")

EXPECTED_COMMAND = {
    "issue": 90,
    "syntax": "/release-tag vMAJOR.MINOR.PATCH <full_sha>",
    "authorized_actor": "repository_owner",
}
EXPECTED_READINESS_COMMAND = {
    "issue": 90,
    "syntax": "/release-readiness",
    "authorized_actor": "repository_owner",
    "mutation_authority": False,
}
EXPECTED_PRECONDITIONS = {
    "target_sha": "exact_full_40_char_sha",
    "protected_main_sha": "must_equal_exact_target_sha",
    "target_main_quality": "at_least_one_completed_successful_push_on_main_for_exact_target_sha",
    "target_product_release_readiness": "at_least_one_completed_successful_issue_comment_run_for_exact_target_sha",
    "canonical_release_contract_verified": True,
    "tag_kind": "annotated",
    "publication_source_sha": "must_equal_exact_tag_target_sha",
    "immutable_releases_enabled_before_tag_creation": True,
    "immutable_releases_enabled_before_release_creation": True,
    "product_release_environment": "product-release",
    "settings_token_permissions": [
        "repository_administration_read",
        "repository_environments_read",
    ],
    "exact_environment_secret_name_contract_required": True,
    "protected_environment_required": True,
    "signed_android_release_required": True,
}
EXPECTED_ORDERING = {
    "product_source_acceptance": "exact_protected_main_sha_plus_exact_successful_main_quality",
    "release_configuration_readiness": "exact_same_main_sha_read_only_readiness_before_product_tag",
    "final_v_tag": "after_product_source_and_release_configuration_acceptance_and_before_any_release_deployment",
    "release_build": "public_product_repository_builds_linux_and_exact_signed_android_from_final_tag_target",
    "release_publication": "draft_first_attach_exact_v2_bundle_then_publish_immutable",
    "deployment_admission": "private_controller_only_after_exact_immutable_product_release_v2_exists",
    "physical_acceptance": "private_controller_observes_executes_recovers_and_classifies_target_after_product_release_exists",
    "public_deployment_projection": "bounded_status_history_only_not_execution_authority",
}
EXPECTED_ASSETS = [
    "mobile-proxy-linux-x86_64-vMAJOR.MINOR.PATCH.tar.gz",
    "mobile-proxy-android-vMAJOR.MINOR.PATCH.apk",
    "release-manifest.json",
    "provenance.json",
    "artifact-digests.json",
]
EXPECTED_MANIFEST = {
    "format_version": 2,
    "android_package": "com.example.mobileproxy",
    "source_sha": "exact_final_tag_target_sha",
    "content_digest_algorithm": "blake3-256",
    "content_digest_domain": "mobile-proxy/product-release-asset/v2",
}
EXPECTED_DIGEST_SET = {
    "format_version": 1,
    "algorithm": "blake3-256",
    "domain": "mobile-proxy/product-release-asset/v2",
    "covers": [
        "mobile-proxy-linux-x86_64-vMAJOR.MINOR.PATCH.tar.gz",
        "mobile-proxy-android-vMAJOR.MINOR.PATCH.apk",
        "release-manifest.json",
        "provenance.json",
    ],
    "self_digest_forbidden": True,
}
EXPECTED_TAG = {
    "kind": "annotated",
    "pattern": r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$",
    "deletion_forbidden_after_immutable_publication": True,
    "non_fast_forward_forbidden_after_immutable_publication": True,
}
EXPECTED_FORBIDDEN = [
    "physical_acceptance_required_before_product_tag",
    "phone_signing_gate_required_before_product_tag",
    "item20_final_accepted_candidate_required_before_product_tag",
    "product_tag_without_exact_same_sha_release_readiness",
    "release_readiness_reading_signing_secret_values",
    "release_readiness_mutating_product_or_target",
    "public_release_workflow_accessing_phone",
    "public_release_workflow_mutating_provider",
    "public_release_workflow_executing_private_deployment_controller",
    "release_publication_without_exact_signed_android_apk",
    "release_publication_without_immutable_releases_enabled",
    "direct_published_release_creation_before_assets_are_verified",
    "overwrite_or_replace_existing_release_assets",
    "accept_mutable_published_release_as_deployable",
    "deployment_from_latest_or_moving_release_alias",
    "deployment_before_exact_immutable_product_release_v2",
    "first_party_direct_cryptographic_digest_primitive",
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


def _require_tokens(body: str, tokens: tuple[str, ...], label: str, errors: list[str]) -> None:
    for token in tokens:
        if token not in body:
            errors.append(f"{label} is missing protected Product Release v2 token {token!r}")


def _forbid_tokens(body: str, tokens: tuple[str, ...], label: str, errors: list[str]) -> None:
    for token in tokens:
        if token in body:
            errors.append(f"{label} contains retired/wrong-owner token {token!r}")


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    contract = _load_contract(root, errors)
    readiness_workflow = _read(root, READINESS_WORKFLOW, errors)
    tag_workflow = _read(root, TAG_WORKFLOW, errors)
    release_workflow = _read(root, RELEASE_WORKFLOW, errors)
    order_doc = _read(root, ORDER_DOC, errors)

    for key, value in {
        "contract_version": 2,
        "status": "protected",
        "canonical_repository": "iamaman11/mobile-proxy",
        "deployment_controller_repository": "iamaman11/mobile-proxy-production",
        "readiness_workflow": str(READINESS_WORKFLOW),
        "tag_workflow": str(TAG_WORKFLOW),
        "publication_workflow": str(RELEASE_WORKFLOW),
    }.items():
        if contract.get(key) != value:
            errors.append(f"Product Release authority contract {key!r} differs from protected value")
    if contract.get("command") != EXPECTED_COMMAND:
        errors.append("Product Release tag command authority must remain on canonical public tracker #90")
    if contract.get("readiness_command") != EXPECTED_READINESS_COMMAND:
        errors.append("Product Release readiness command authority differs")
    if contract.get("preconditions") != EXPECTED_PRECONDITIONS:
        errors.append("Product Release v2 preconditions differ from protected exact-source/readiness contract")
    if contract.get("ordering") != EXPECTED_ORDERING:
        errors.append("Product Release v2 ordering no longer requires same-SHA readiness before tag/deployment")
    if contract.get("required_release_assets") != EXPECTED_ASSETS:
        errors.append("Product Release v2 exact asset set differs")
    if contract.get("manifest") != EXPECTED_MANIFEST:
        errors.append("Product Release v2 manifest contract differs")
    if contract.get("digest_set") != EXPECTED_DIGEST_SET:
        errors.append("Product Release v2 typed digest-set contract differs")
    if contract.get("tag") != EXPECTED_TAG:
        errors.append("Product Release v2 annotated-tag contract differs")
    if contract.get("forbidden") != EXPECTED_FORBIDDEN:
        errors.append("Product Release v2 forbidden ownership/order set differs")

    _require_tokens(
        readiness_workflow,
        (
            "name: Product Release Readiness",
            "github.event.issue.number == 90",
            "github.event.comment.user.login == github.repository_owner",
            "github.event.comment.body == '/release-readiness'",
            "permissions:",
            "actions: read",
            "contents: read",
            "issues: read",
            "environment: product-release",
            "PRODUCT_RELEASE_SETTINGS_TOKEN",
            "repos/$GITHUB_REPOSITORY/environments/product-release",
            "repos/$GITHUB_REPOSITORY/environments/product-release/secrets?per_page=100",
            "repos/$GITHUB_REPOSITORY/immutable-releases",
            "product-release environment has no protection rules",
            "product-release secret-name contract differs",
            "repository immutable Releases are not enabled",
            "Exact protected main SHA:",
            "Phone access performed: false",
            "Deployment performed: false",
            "Product tag created: false",
            "Product Release published: false",
        ),
        "Product Release readiness workflow",
        errors,
    )
    _forbid_tokens(
        readiness_workflow,
        (
            "contents: write",
            "actions: write",
            "ANDROID_RELEASE_KEYSTORE_B64: ${{ secrets.",
            "ANDROID_RELEASE_KEYSTORE_PASSWORD: ${{ secrets.",
            "ANDROID_RELEASE_KEY_ALIAS: ${{ secrets.",
            "ANDROID_RELEASE_KEY_PASSWORD: ${{ secrets.",
            "adb ",
            "phone-production",
            "/deploy ",
            "mobile-proxy-production",
            "vultr",
            "gh release create",
            "git tag -a",
        ),
        "Product Release readiness workflow",
        errors,
    )

    _require_tokens(
        tag_workflow,
        (
            "github.event.issue.number == 90",
            "github.event.comment.user.login == github.repository_owner",
            r"/release-tag (v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)) ([0-9a-f]{40})",
            "target SHA does not equal exact protected main",
            "exact protected main has no eligible successful Quality push",
            "Require exact successful Product Release Readiness",
            "event=issue_comment",
            'run.get("name") == "Product Release Readiness"',
            'run.get("path") == ".github/workflows/product-release-readiness.yml"',
            "exact protected main has no eligible successful Product Release Readiness proof",
            'test "$(git rev-parse origin/main)" = "$TARGET_SHA"',
            "scripts/verify_android_release_contract.py",
            "git tag -a",
            "git cat-file -t",
            "Exact same-SHA Product Release Readiness required: true",
            "Phone access performed: false",
            "Deployment performed: false",
        ),
        "release-tag workflow",
        errors,
    )
    _forbid_tokens(
        tag_workflow,
        (
            "ITEM20_ISSUE",
            "PHONE_SIGNING_ISSUE",
            "final_accepted_candidate_sha",
            "Item 20 tracker",
            "Phone signing gate closed completed",
            "github.event.issue.number == 162",
        ),
        "release-tag workflow",
        errors,
    )

    _require_tokens(
        release_workflow,
        (
            "environment: product-release",
            "PRODUCT_RELEASE_SETTINGS_TOKEN",
            "repos/$GITHUB_REPOSITORY/immutable-releases",
            "X-GitHub-Api-Version: 2026-03-10",
            'value.get("enabled") is not True',
            "scripts/build_signed_android_release.py",
            "ANDROID_RELEASE_KEYSTORE_B64",
            "ANDROID_RELEASE_KEYSTORE_PASSWORD",
            "ANDROID_RELEASE_KEY_ALIAS",
            "ANDROID_RELEASE_KEY_PASSWORD",
            "scripts/create_release_bundle_v2.py",
            "--repository-root .",
            '--builder "github-actions:iamaman11/mobile-proxy/.github/workflows/release.yml"',
            '--workflow-ref "iamaman11/mobile-proxy/.github/workflows/release.yml@refs/tags/$RELEASE_TAG"',
            "mobile-proxy-linux-x86_64-${{ steps.tag.outputs.name }}.tar.gz",
            "mobile-proxy-android-${{ steps.tag.outputs.name }}.apk",
            "release/release-manifest.json",
            "release/provenance.json",
            "release/artifact-digests.json",
            "gh release create",
            "--draft",
            "scripts/verify_published_release_v2.py",
            "--allow-draft",
            "Accept: application/octet-stream",
            "cmp -s --",
            "-F draft=false",
            "releases/tags/$RELEASE_TAG",
            "gh release verify \"$RELEASE_TAG\"",
            "gh release verify-asset",
            "Provenance identity retry-stable: true",
            "GitHub Release immutable: true",
            "Phone access performed: false",
            "Deployment performed: false",
        ),
        "release publication workflow",
        errors,
    )
    _forbid_tokens(
        release_workflow,
        (
            "softprops/action-gh-release",
            "GITHUB_RUN_ID",
            "GITHUB_WORKFLOW_REF",
            "adb ",
            "adb\n",
            "phone-production",
            "mobile-proxy-production",
            "/deploy ",
            "vultr",
        ),
        "release publication workflow",
        errors,
    )

    _require_tokens(
        order_doc,
        (
            "A Product Release is an **input to deployment**, not an output of prior physical phone acceptance.",
            "Machine contract: `contracts/operations/product-release-authority-v2.json`",
            "Runtime deployment command surface: private Issue #1",
            "/release-readiness",
            "same exact protected main SHA",
            "Administration: read",
            "Environments: read",
            "secret names without reading signing secret values",
            "public PRODUCT workflow builds Linux + exact signed Android APK from tag target SHA",
            "create GitHub Release as draft",
            "verify GitHub Release immutable == true",
            "only now may private /deploy <target> <tag> consume that Product Release",
            "Physical acceptance belongs to deployment/runtime control after the immutable Product Release exists.",
            "PRODUCT_RELEASE_SETTINGS_TOKEN",
            "artifact-digests.json",
            "mobile-proxy/product-release-asset/v2",
            "exact bytes",
            "The private Deployment Controller revision is deliberately **not** part of Product Release identity.",
            "public GitHub Deployment receives bounded status/history projection only",
        ),
        "Product Release authority document",
        errors,
    )
    _forbid_tokens(
        order_doc,
        (
            "A final `v*` tag is therefore an **output** of successful Item 20",
            "#135 must be closed",
            "#115 closed `completed`",
            "private `mobile-proxy-production` repository remains execution-only",
        ),
        "Product Release authority document",
        errors,
    )
    return errors


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    failures = check_repository(args.repo_root.resolve())
    if failures:
        print("Product Release v2 readiness/authority validation failed:")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)
    print("Product Release v2 readiness/authority validation passed")
