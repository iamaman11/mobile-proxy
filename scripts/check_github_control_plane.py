#!/usr/bin/env python3
"""Keep the PRODUCT/deployment-controller GitHub authority boundary fail-closed."""

from __future__ import annotations

import json
from pathlib import Path

PROJECT = Path("contracts/operations/project-authority-v2.json")
GITHUB = Path("contracts/operations/github-control-plane-v2.json")
TOPOLOGY = Path("contracts/operations/production-topology-v2.json")
RELEASE = Path("contracts/operations/product-release-authority-v2.json")
RELEASE_WORKFLOW = Path(".github/workflows/release.yml")
TAG_WORKFLOW = Path(".github/workflows/release-tag.yml")
RELEASE_DOC = Path("docs/operations/final-release-authority-order.md")


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


def _read(root: Path, path: Path, errors: list[str]) -> str:
    try:
        return (root / path).read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"cannot read {path}: {error}")
        return ""


def _require_tokens(body: str, path: Path, tokens: tuple[str, ...], errors: list[str]) -> None:
    for token in tokens:
        if token not in body:
            errors.append(f"{path} is missing protected authority token {token!r}")


def _forbid_tokens(body: str, path: Path, tokens: tuple[str, ...], errors: list[str]) -> None:
    for token in tokens:
        if token in body:
            errors.append(f"{path} contains wrong-owner authority token {token!r}")


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    project = _load(root, PROJECT, errors)
    github = _load(root, GITHUB, errors)
    topology = _load(root, TOPOLOGY, errors)
    release = _load(root, RELEASE, errors)
    release_workflow = _read(root, RELEASE_WORKFLOW, errors)
    tag_workflow = _read(root, TAG_WORKFLOW, errors)
    release_doc = _read(root, RELEASE_DOC, errors)

    if project.get("contract_version") != 2 or project.get("status") != "protected":
        errors.append("project authority v2 identity differs")
    public = project.get("public_product_authority")
    if not isinstance(public, dict) or public.get("repository") != "iamaman11/mobile-proxy" or public.get("visibility") != "public":
        errors.append("public PRODUCT authority is not exact")
    else:
        expected = {
            "application_and_runtime_source",
            "shared_domain_and_product_architecture",
            "public_quality",
            "product_build",
            "product_signing_verification",
            "annotated_product_tags",
            "immutable_product_releases",
            "product_release_contracts_and_provenance",
        }
        if not isinstance(public.get("responsibilities"), list) or set(public["responsibilities"]) != expected:
            errors.append("public PRODUCT responsibility set differs")
        forbidden = set(public.get("forbidden", [])) if isinstance(public.get("forbidden"), list) else set()
        if not {
            "phone_or_vm_target_mutation",
            "runtime_deployment_transaction_ledger",
            "deployment_exactly_once_dispatch_authority",
        }.issubset(forbidden):
            errors.append("public PRODUCT plane is not denied target/runtime execution authority")

    private = project.get("private_deployment_authority")
    if not isinstance(private, dict) or any(
        private.get(key) != value
        for key, value in {
            "repository": "iamaman11/mobile-proxy-production",
            "visibility": "private",
            "control_issue": 1,
            "authority": "deployment_controller",
        }.items()
    ):
        errors.append("private Deployment Controller authority is not exact")
    else:
        responsibilities = set(private.get("responsibilities", [])) if isinstance(private.get("responsibilities"), list) else set()
        if not {
            "deployment_state_machine_and_transaction_kernel",
            "target_admission_and_serialization",
            "target_observation_and_adapters",
            "durable_mutation_intent",
            "exactly_once_destructive_dispatch",
            "postcondition_verification",
            "recovery_and_quarantine",
            "durable_canonical_runtime_execution_evidence",
        }.issubset(responsibilities):
            errors.append("private Deployment Controller is missing runtime authority responsibilities")
        forbidden = set(private.get("forbidden", [])) if isinstance(private.get("forbidden"), list) else set()
        if not {
            "application_source_copy",
            "independent_product_build",
            "independent_product_signing_policy",
            "independent_product_release_creation",
            "independent_product_tag_authority",
        }.issubset(forbidden):
            errors.append("private Deployment Controller can drift into PRODUCT ownership")

    runtime_identity = project.get("runtime_identity")
    if runtime_identity != {
        "product_release": "exact_immutable_public_product_release_v2",
        "controller_revision": "exact_private_controller_git_revision",
        "identity": "product_release_plus_controller_revision",
        "public_main_sha_as_runtime_cursor": "forbidden",
        "public_issue_179_as_runtime_cursor": "forbidden",
    }:
        errors.append("runtime identity is not Product Release plus controller revision")
    evidence = project.get("evidence_authority")
    if not isinstance(evidence, dict) or evidence.get("runtime_execution_truth") != "private_deployment_controller_durable_ledger" or evidence.get("public_github_deployment") != "bounded_status_and_history_projection_only":
        errors.append("canonical runtime evidence/public projection boundary differs")

    if topology.get("contract_version") != 2 or topology.get("status") != "protected":
        errors.append("production topology v2 identity differs")
    if topology.get("authority_contract") != str(PROJECT) or topology.get("product_release_contract") != str(RELEASE):
        errors.append("production topology does not bind authority/release v2 contracts")
    planes = topology.get("planes")
    controller = planes.get("deployment_controller") if isinstance(planes, dict) else None
    if not isinstance(controller, dict) or controller.get("repository") != "iamaman11/mobile-proxy-production" or controller.get("authority") != "deployment_controller" or controller.get("command") != "/deploy <target> <vX.Y.Z>":
        errors.append("production topology Deployment Controller plane differs")
    execution = topology.get("execution_rules")
    if execution != {
        "mutation_intent_before_destructive_dispatch": True,
        "blind_retry_after_dispatch_boundary": False,
        "independent_postcondition_observation": True,
        "unknown_continuation": "read_only_recovery_only",
        "recovered_retroactively_equals_original_success": False,
        "duplicate_semantic_request_second_mutation": "forbidden",
        "recovery_mode_reconciled_after_target_lock": True,
    }:
        errors.append("production topology transaction/recovery rules differ")
    release_link = topology.get("release_link")
    if not isinstance(release_link, dict) or release_link.get("product_release_must_exist_before_deployment_admission") is not True or release_link.get("physical_acceptance_before_product_release") is not False:
        errors.append("production topology no longer requires Product Release before deployment")

    if github.get("contract_version") != 2 or github.get("status") != "protected":
        errors.append("GitHub control plane v2 identity differs")
    if github.get("project_authority_contract") != str(PROJECT) or github.get("production_topology_contract") != str(TOPOLOGY) or github.get("product_release_contract") != str(RELEASE):
        errors.append("GitHub control plane does not bind current v2 authority contracts")
    product_repository = github.get("public_product_repository")
    if not isinstance(product_repository, dict) or product_repository.get("name") != "iamaman11/mobile-proxy" or product_repository.get("self_hosted_runners") != "forbidden":
        errors.append("public PRODUCT repository boundary differs")
    environment = github.get("product_release_environment")
    expected_secrets = [
        "PRODUCT_RELEASE_SETTINGS_TOKEN",
        "ANDROID_RELEASE_KEYSTORE_B64",
        "ANDROID_RELEASE_KEYSTORE_PASSWORD",
        "ANDROID_RELEASE_KEY_ALIAS",
        "ANDROID_RELEASE_KEY_PASSWORD",
    ]
    if not isinstance(environment, dict) or environment.get("name") != "product-release" or environment.get("executor") != "github-hosted" or environment.get("required_secret_names") != expected_secrets or environment.get("phone_or_target_access") != "forbidden" or environment.get("provider_mutation") != "forbidden":
        errors.append("public product-release environment boundary differs")
    private_control = github.get("private_deployment_controller")
    if not isinstance(private_control, dict) or any(
        private_control.get(key) != value
        for key, value in {
            "name": "iamaman11/mobile-proxy-production",
            "visibility": "private",
            "authority": "deployment_controller",
            "control_issue": 1,
            "command": "/deploy <target> <vX.Y.Z>",
            "product_source_copy": "forbidden",
            "product_build_or_signing": "forbidden",
            "canonical_runtime_evidence": True,
            "bounded_public_deployment_projection": True,
        }.items()
    ):
        errors.append("private deployment controller GitHub boundary differs")

    if release.get("contract_version") != 2 or release.get("status") != "protected":
        errors.append("Product Release v2 authority contract identity differs")

    _require_tokens(
        tag_workflow,
        TAG_WORKFLOW,
        (
            "github.event.issue.number == 90",
            "exact protected main has no eligible successful Quality push",
            "git tag -a",
            "Phone access performed: false",
            "Deployment performed: false",
        ),
        errors,
    )
    _forbid_tokens(
        tag_workflow,
        TAG_WORKFLOW,
        ("ITEM20_ISSUE", "PHONE_SIGNING_ISSUE", "final_accepted_candidate_sha"),
        errors,
    )
    _require_tokens(
        release_workflow,
        RELEASE_WORKFLOW,
        (
            "environment: product-release",
            "PRODUCT_RELEASE_SETTINGS_TOKEN",
            "scripts/build_signed_android_release.py",
            "scripts/create_release_bundle_v2.py",
            "artifact-digests.json",
            "--draft",
            "cmp -s --",
            "gh release verify",
            "Phone access performed: false",
            "Deployment performed: false",
        ),
        errors,
    )
    _forbid_tokens(
        release_workflow,
        RELEASE_WORKFLOW,
        ("adb ", "phone-production", "/deploy ", "mobile-proxy-production", "vultr"),
        errors,
    )
    _require_tokens(
        release_doc,
        RELEASE_DOC,
        (
            "A Product Release is an **input to deployment**, not an output of prior physical phone acceptance.",
            "private Deployment Controller",
            "product_release + exact controller_revision",
            "artifact-digests.json",
            "exact bytes",
            "bounded status/history projection",
        ),
        errors,
    )
    return errors
