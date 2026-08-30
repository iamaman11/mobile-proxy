#!/usr/bin/env python3
"""Keep the canonical GitHub/project control-plane boundary fail-closed."""

from __future__ import annotations

import json
from pathlib import Path


AUTHORITY_CONTRACT = Path("contracts/operations/project-authority-v1.json")
GITHUB_CONTRACT = Path("contracts/operations/github-control-plane-v1.json")
TOPOLOGY_CONTRACT = Path("contracts/operations/production-topology-v1.json")
ACCEPTANCE_CONTRACT = Path("contracts/operations/acceptance-authority-v1.json")
REQUIRED_DOCS = (
    Path("docs/GIT_DELIVERY.md"),
    Path("docs/operations/project-authority.md"),
    Path("docs/operations/github-bootstrap.md"),
    Path("docs/operations/secret-boundaries.md"),
)


def _load(path: Path, errors: list[str]) -> dict[str, object]:
    if not path.is_file():
        errors.append(f"missing GitHub/project control-plane contract: {path}")
        return {}
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        errors.append(f"cannot parse GitHub/project control-plane contract {path}: {error}")
        return {}
    if not isinstance(body, dict):
        errors.append(f"GitHub/project control-plane contract must be an object: {path}")
        return {}
    return body


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    authority = _load(root / AUTHORITY_CONTRACT, errors)
    github = _load(root / GITHUB_CONTRACT, errors)
    topology = _load(root / TOPOLOGY_CONTRACT, errors)
    acceptance = _load(root / ACCEPTANCE_CONTRACT, errors)

    if authority:
        canonical = authority.get("canonical_repository")
        if not isinstance(canonical, dict) or any(
            canonical.get(key) != value
            for key, value in {
                "name": "iamaman11/mobile-proxy",
                "url": "https://github.com/iamaman11/mobile-proxy",
                "authority": "sole_project_source_of_truth",
                "canonical_gitops_issue": 90,
            }.items()
        ):
            errors.append("canonical project authority is not exact")
        if authority.get("conflict_policy") != (
            "fail_closed_and_reconcile_in_canonical_repository_first"
        ):
            errors.append("canonical conflict policy is not fail-closed")
        satellites = authority.get("execution_satellites")
        if not isinstance(satellites, list) or len(satellites) != 1:
            errors.append("project authority must define exactly one execution satellite")
        else:
            satellite = satellites[0]
            if not isinstance(satellite, dict) or any(
                satellite.get(key) != value
                for key, value in {
                    "repository": "iamaman11/mobile-proxy-production",
                    "visibility": "private",
                    "authority": "execution_only",
                    "control_issue": 1,
                }.items()
            ):
                errors.append("phone execution satellite authority is not exact")
            forbidden = satellite.get("forbidden") if isinstance(satellite, dict) else None
            required_forbidden = {
                "independent_project_roadmap",
                "independent_architecture_decision",
                "independent_release_policy",
                "independent_provider_desired_state",
                "independent_acceptance_policy",
                "application_source_copy",
                "canonical_manifest_copy",
                "vultr_credentials_or_lifecycle",
            }
            if not isinstance(forbidden, list) or not required_forbidden.issubset(forbidden):
                errors.append("execution satellite can become an independent project source")
        release_identity = authority.get("release_identity")
        if not isinstance(release_identity, dict) or any(
            release_identity.get(key) != value
            for key, value in {
                "repository": "iamaman11/mobile-proxy",
                "tag": "vMAJOR.MINOR.PATCH",
                "tag_kind": "annotated",
                "deployment_id_rule": "mobile-proxy-<tag>-<first12sha>",
                "mutable_branch_authority": "forbidden",
            }.items()
        ):
            errors.append("cross-repository release identity is not immutable")

    if acceptance:
        if any(
            acceptance.get(key) != value
            for key, value in {
                "contract_version": 1,
                "status": "protected",
                "authority": "pre_release_acceptance",
                "canonical_repository": "iamaman11/mobile-proxy",
            }.items()
        ):
            errors.append("acceptance authority identity is not canonical and pre-release only")
        command = acceptance.get("command")
        if not isinstance(command, dict) or command != {
            "issue": 90,
            "syntax": "/accept-candidate <full_sha>",
            "authorized_actor": "repository_owner",
        }:
            errors.append("acceptance command authority differs from the contract")
        identity = acceptance.get("candidate_identity")
        if not isinstance(identity, dict) or any(
            identity.get(key) != value
            for key, value in {
                "kind": "full_git_sha",
                "pattern": "^[0-9a-f]{40}$",
            }.items()
        ):
            errors.append("acceptance candidate identity is not exact full-SHA only")
        elif identity.get("mutable_or_approximate_refs_forbidden") != [
            "main",
            "latest",
            "branch_name",
            "short_sha",
        ]:
            errors.append("acceptance candidate mutable-ref rejection differs from the contract")
        candidate_evidence = acceptance.get("candidate_evidence")
        if not isinstance(candidate_evidence, dict) or any(
            candidate_evidence.get(key) != value
            for key, value in {
                "quality_workflow": "Quality",
                "quality_workflow_path": ".github/workflows/quality.yml",
                "required_event": "push",
                "required_branch": "main",
                "required_status": "completed",
                "required_conclusion": "success",
                "artifact_name_template": "software-release-candidate-<candidate_sha>",
                "artifact_file": "release-candidate-evidence.json",
                "required_format_version": 2,
                "required_repository": "iamaman11/mobile-proxy",
            }.items()
        ):
            errors.append("acceptance candidate evidence source is not exact")
        elif candidate_evidence.get("required_flags") != {
            "software_10_of_10_ready": True,
            "physical_phone_acceptance_required": True,
            "baseline_complete": False,
        }:
            errors.append("acceptance candidate evidence flags differ from the contract")
        execution = acceptance.get("execution")
        if not isinstance(execution, dict) or execution != {
            "workflow": ".github/workflows/acceptance-authority.yml",
            "executor": "github-hosted",
            "environment": "none_in_item_16",
            "vultr_api_access": "forbidden_in_item_16",
            "vultr_secret_access": "forbidden_in_item_16",
            "vm_mutation": "forbidden_in_item_16",
            "phone_mutation": "forbidden_in_item_16",
        }:
            errors.append("acceptance execution boundary is not item-16 authority-only")
        separation = acceptance.get("authority_separation")
        if not isinstance(separation, dict) or separation != {
            "final_production_authority": False,
            "production_environment": "forbidden",
            "final_release_tag": "forbidden",
            "production_workflow": ".github/workflows/production-preflight.yml",
            "production_environment_name": "production-vultr",
            "production_ref_type": "tag",
            "production_ref_pattern": "v*",
        }:
            errors.append("acceptance authority must remain distinct from final production authority")
        bounded = acceptance.get("evidence")
        if not isinstance(bounded, dict) or bounded != {
            "format_version": 1,
            "artifact_name_template": "vultr-acceptance-authority-<candidate_sha>",
            "secret_derived_data": "forbidden",
            "retention_days": 90,
        }:
            errors.append("acceptance evidence contract is not bounded")

    if github:
        source = github.get("source_repository")
        if not isinstance(source, dict) or source != {
            "name": "iamaman11/mobile-proxy",
            "visibility": "public",
            "authority": "sole_project_source_of_truth",
            "self_hosted_runners": "forbidden",
        }:
            errors.append("public canonical source repository boundary is not exact")
        if github.get("project_authority_contract") != str(AUTHORITY_CONTRACT):
            errors.append("GitHub contract does not bind the project-authority contract")
        if github.get("acceptance_authority_contract") != str(ACCEPTANCE_CONTRACT):
            errors.append("GitHub contract does not bind the acceptance-authority contract")
        environment = github.get("vultr_environment")
        if not isinstance(environment, dict) or any(
            environment.get(key) != value
            for key, value in {
                "name": "production-vultr",
                "allowed_ref_type": "tag",
                "allowed_ref_pattern": "v*",
                "required_reviewers": "forbidden",
                "wait_timer": "forbidden",
                "admin_bypass": "forbidden",
                "executor": "github-hosted",
            }.items()
        ):
            errors.append("production-vultr boundary is not fail-closed")
        if not isinstance(environment, dict) or environment.get("required_secret_names") != [
            "VULTR_API_KEY",
            "VULTR_SSH_PRIVATE_KEY",
        ]:
            errors.append("production-vultr secret names differ from the contract")
        acceptance_authority = github.get("acceptance_authority")
        if not isinstance(acceptance_authority, dict) or acceptance_authority != {
            "name": "vultr-pre-release-acceptance",
            "workflow": ".github/workflows/acceptance-authority.yml",
            "command_issue": 90,
            "command": "/accept-candidate <full_sha>",
            "allowed_identity": "full_40_char_git_sha",
            "candidate_evidence": (
                "successful_quality_push_on_main_plus_matching_release_candidate_artifact"
            ),
            "executor": "github-hosted",
            "environment": "none_in_item_16",
            "final_production_authority": False,
            "vultr_secret_access": "forbidden_in_item_16",
            "vm_mutation": "forbidden_in_item_16",
        }:
            errors.append("GitHub acceptance authority differs from the protected contract")
        phone = github.get("phone_control_repository")
        if not isinstance(phone, dict) or any(
            phone.get(key) != value
            for key, value in {
                "name": "iamaman11/mobile-proxy-production",
                "visibility": "private",
                "authority": "execution_only",
                "canonical_source": "iamaman11/mobile-proxy",
                "control_issue": 1,
            }.items()
        ):
            errors.append("phone control repository must remain an execution-only satellite")
        elif phone.get("required_runner_labels") != [
            "self-hosted",
            "Linux",
            "X64",
            "android-production",
        ]:
            errors.append("phone runner labels differ from the contract")
        if isinstance(phone, dict):
            if phone.get("preferred_logic_source") != (
                "canonical_public_logic_pinned_to_immutable_sha_or_verified_release_artifact"
            ):
                errors.append("phone execution logic source is not immutable and canonical")
            if phone.get("required_device_binding_secret") != "ANDROID_PRODUCTION_SERIAL":
                errors.append("phone registered-device binding differs from the contract")
            if phone.get("reserved_android_signing_secret_names") != [
                "ANDROID_RELEASE_KEYSTORE_B64",
                "ANDROID_RELEASE_KEYSTORE_PASSWORD",
                "ANDROID_RELEASE_KEY_ALIAS",
                "ANDROID_RELEASE_KEY_PASSWORD",
            ]:
                errors.append("phone Android signing-secret contract differs")

        runtime = github.get("runtime_verification")
        if runtime != {
            "vultr_secret_access": "pending_actions_preflight",
            "android_runner_and_device": (
                "passed_private_actions_read_only_preflight_on_registered_device; "
                "mutable_phone_operations_remain_blocked"
            ),
        }:
            errors.append("GitHub runtime-verification checkpoint differs from the contract")
        forbidden = github.get("forbidden")
        required_acceptance_forbidden = {
            "acceptance_authority_using_production_vultr_environment",
            "acceptance_authority_using_final_release_tag",
        }
        if not isinstance(forbidden, list) or not required_acceptance_forbidden.issubset(forbidden):
            errors.append("GitHub contract does not forbid acceptance/production authority collapse")

    if topology:
        project_authority = topology.get("project_authority")
        if not isinstance(project_authority, dict) or project_authority != {
            "canonical_repository": "iamaman11/mobile-proxy",
            "canonical_gitops_issue": 90,
            "satellite_conflict_policy": (
                "fail_closed_and_reconcile_canonical_repository_first"
            ),
        }:
            errors.append("production topology does not bind canonical project authority")
        execution = topology.get("execution")
        if not isinstance(execution, dict) or execution != {
            "vultr_acceptance": (
                "GitHub-hosted runner under immutable pre-release acceptance authority; "
                "production-vultr forbidden before final release"
            ),
            "vultr_production": (
                "GitHub-hosted runner in production-vultr from protected final v* release only"
            ),
            "phone": (
                "private-repository caller context with android-production self-hosted runner"
            ),
            "phone_logic": (
                "canonical public logic pinned to immutable SHA or verified canonical release artifact"
            ),
        }:
            errors.append("production topology acceptance/production execution split differs")
        migration = topology.get("migration_status")
        if not isinstance(migration, dict) or any(
            migration.get(key) != value
            for key, value in {
                "phone_execution_satellite": (
                    "read_only_preflight_workflow_enabled_and_private_runner_online"
                ),
                "phone_live_preflight": (
                    "passed_private_actions_read_only_preflight_on_registered_device"
                ),
                "acceptance_authority": "implemented_candidate_quality_evidence_gate",
            }.items()
        ):
            errors.append("production topology GitOps checkpoint differs")

    for relative in REQUIRED_DOCS:
        if not (root / relative).is_file():
            errors.append(f"missing GitHub/project control-plane document: {relative}")

    workflow_root = root / ".github/workflows"
    forbidden_workflow_tokens = ("self-hosted", "adb", "gcloud", "with-production-secrets")
    for workflow in workflow_root.glob("*.yml"):
        content = workflow.read_text(encoding="utf-8").lower()
        for token in forbidden_workflow_tokens:
            if token in content:
                errors.append(f"public workflow {workflow.relative_to(root)} contains forbidden {token!r}")

    acceptance_workflow = workflow_root / "acceptance-authority.yml"
    if not acceptance_workflow.is_file():
        errors.append("immutable acceptance authority workflow is missing")
    else:
        content = acceptance_workflow.read_text(encoding="utf-8")
        required_tokens = (
            "issue_comment:",
            "github.event.issue.number == 90",
            "github.event.comment.user.login == github.repository_owner",
            "startsWith(github.event.comment.body, '/accept-candidate ')",
            "runs-on: ubuntu-latest",
            "actions: read",
            "contents: read",
            "verify_acceptance_candidate.py",
            "software-release-candidate-",
            "vultr-acceptance-authority-",
        )
        if any(token not in content for token in required_tokens):
            errors.append("acceptance workflow does not enforce the exact hosted candidate gate")
        forbidden_tokens = (
            "environment: production-vultr",
            "VULTR_API_KEY",
            "VULTR_SSH_PRIVATE_KEY",
            "refs/tags/",
            "secrets.",
        )
        if any(token in content for token in forbidden_tokens):
            errors.append("acceptance workflow attempts to use final production authority or secrets")

    production_preflight = workflow_root / "production-preflight.yml"
    if not production_preflight.is_file():
        errors.append("tag-only production preflight workflow is missing")
    else:
        content = production_preflight.read_text(encoding="utf-8")
        required_tokens = (
            '[[ "$GITHUB_REF_TYPE" == "tag" ]]',
            '[[ "$GITHUB_REF_NAME" == v* ]]',
            '[[ "$REF_PROTECTED" == "true" ]]',
            "environment: production-vultr",
        )
        if any(token not in content for token in required_tokens):
            errors.append("production-vultr workflow is no longer protected v*-tag only")

    deployment = workflow_root / "deploy-production.yml"
    if not deployment.is_file() or "Production deployment is blocked" not in deployment.read_text(
        encoding="utf-8"
    ):
        errors.append("legacy public deployment workflow must remain blocked during migration")

    for retired in (
        Path("scripts/register-production-runner"),
        Path("scripts/run-production-runner"),
        Path("scripts/install-production-runner-task.ps1"),
    ):
        if (root / retired).exists():
            errors.append(f"public repository retains retired runner bootstrap: {retired}")
    return errors
