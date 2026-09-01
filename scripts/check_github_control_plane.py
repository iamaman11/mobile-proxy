#!/usr/bin/env python3
"""Keep the canonical GitHub/project control-plane boundary fail-closed."""

from __future__ import annotations

import json
from pathlib import Path


AUTHORITY_CONTRACT = Path("contracts/operations/project-authority-v1.json")
GITHUB_CONTRACT = Path("contracts/operations/github-control-plane-v1.json")
TOPOLOGY_CONTRACT = Path("contracts/operations/production-topology-v1.json")
ACCEPTANCE_CONTRACT = Path("contracts/operations/acceptance-authority-v1.json")
READONLY_WORKFLOW = Path(".github/workflows/vultr-readonly-preflight.yml")
ACCEPTANCE_WORKFLOW = Path(".github/workflows/acceptance-authority.yml")
PRODUCTION_PREFLIGHT = Path(".github/workflows/production-preflight.yml")
REQUIRED_DOCS = (
    Path("docs/GIT_DELIVERY.md"),
    Path("docs/operations/project-authority.md"),
    Path("docs/operations/github-bootstrap.md"),
    Path("docs/operations/secret-boundaries.md"),
    Path("docs/operations/phone-gitops-runtime.md"),
)


def _load(root: Path, path: Path, errors: list[str]) -> dict[str, object]:
    try:
        body = json.loads((root / path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"cannot load {path}: {error}")
        return {}
    if not isinstance(body, dict):
        errors.append(f"{path} root must be an object")
        return {}
    return body


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    authority = _load(root, AUTHORITY_CONTRACT, errors)
    github = _load(root, GITHUB_CONTRACT, errors)
    topology = _load(root, TOPOLOGY_CONTRACT, errors)
    acceptance = _load(root, ACCEPTANCE_CONTRACT, errors)

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
        if authority.get("conflict_policy") != "fail_closed_and_reconcile_in_canonical_repository_first":
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
                errors.append("execution satellite can become an independent project/provider source")
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
        if acceptance.get("command") != {
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
        if acceptance.get("execution") != {
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
        if acceptance.get("evidence") != {
            "format_version": 1,
            "artifact_name_template": "vultr-acceptance-authority-<candidate_sha>",
            "secret_derived_data": "forbidden",
            "retention_days": 90,
        }:
            errors.append("acceptance evidence contract is not bounded")

    if github:
        source = github.get("source_repository")
        if source != {
            "name": "iamaman11/mobile-proxy",
            "visibility": "public",
            "authority": "sole_project_source_of_truth",
            "self_hosted_runners": "forbidden",
        }:
            errors.append("public canonical source repository boundary is not exact")
        if github.get("project_authority_contract") != str(AUTHORITY_CONTRACT):
            errors.append("GitHub contract does not bind project authority")
        if github.get("acceptance_authority_contract") != str(ACCEPTANCE_CONTRACT):
            errors.append("GitHub contract does not bind acceptance authority")

        production = github.get("vultr_environment")
        if not isinstance(production, dict) or any(
            production.get(key) != value
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
            errors.append("production-vultr boundary is not protected tag-only")
        if not isinstance(production, dict) or production.get("required_secret_names") != [
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
            "candidate_evidence": "successful_quality_push_on_main_plus_matching_release_candidate_artifact",
            "executor": "github-hosted",
            "environment": "none_in_item_16",
            "final_production_authority": False,
            "vultr_secret_access": "forbidden_in_item_16",
            "vm_mutation": "forbidden_in_item_16",
        }:
            errors.append("GitHub acceptance authority differs from the protected contract")

        acceptance_env = github.get("acceptance_vultr_environment")
        if not isinstance(acceptance_env, dict):
            errors.append("acceptance-vultr credential boundary is missing")
        else:
            required = {
                "name": "acceptance-vultr",
                "authority": "pre_release_acceptance_credential_boundary_not_final_production_authority",
                "required_precondition": "verified_vultr_acceptance_authority_artifact_for_exact_candidate_sha",
                "executor": "github-hosted",
                "final_production_authority": False,
            }
            for key, value in required.items():
                if acceptance_env.get(key) != value:
                    errors.append(f"acceptance-vultr {key!r} differs from protected value")
            if acceptance_env.get("required_secret_names") != [
                "VULTR_API_KEY",
                "VULTR_SSH_PRIVATE_KEY",
            ]:
                errors.append("acceptance-vultr secret names differ from the contract")
            capabilities = acceptance_env.get("workflow_capabilities")
            if not isinstance(capabilities, dict):
                errors.append("acceptance-vultr must separate workflow capabilities")
            else:
                readonly = capabilities.get("readonly_preflight")
                if readonly != {
                    "workflow": ".github/workflows/vultr-readonly-preflight.yml",
                    "allowed_provider_api": ["GET /v2/account"],
                    "response_body_recording": "forbidden",
                    "vm_lifecycle": False,
                    "provider_mutation": False,
                }:
                    errors.append("read-only acceptance capability must remain GET /v2/account only")
                lifecycle = capabilities.get("item_19_acceptance_lifecycle")
                if not isinstance(lifecycle, dict) or any(
                    lifecycle.get(key) != value
                    for key, value in {
                        "status": "protected_live_invocation_requires_exact_item_19_provider_gates",
                        "scope": "acceptance_only",
                        "required_state": "durable_owner_controlled_acceptance_vm_lifecycle_state_outside_vcs",
                        "required_concurrency": "single_repository_wide_acceptance_lifecycle_writer_cancel_in_progress_false",
                        "provider_mutation": "bounded_item_19_only_after_exact_provider_gates",
                        "production_scope": "forbidden",
                    }.items()
                ):
                    errors.append("item-19 acceptance lifecycle capability boundary is not fail-closed")
                elif lifecycle.get("required_exact_candidate_evidence") != [
                    "successful_quality_push_on_protected_main",
                    "fresh_immutable_acceptance_authority",
                    "fresh_vultr_readonly_preflight",
                    "provider_proof_window_ready",
                ]:
                    errors.append("item-19 lifecycle exact-candidate gates differ from contract")

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
            errors.append("phone control repository must remain execution-only")
        else:
            if phone.get("preferred_logic_source") != "canonical_public_logic_pinned_to_immutable_sha_or_verified_release_artifact":
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
            if phone.get("required_runner_labels") != ["self-hosted", "Linux", "X64", "android-production"]:
                errors.append("phone runner labels differ from protected contract")
            runner_forbidden = phone.get("runner_must_not_receive")
            required_runner_forbidden = {"VULTR_API_KEY", "VULTR_SSH_PRIVATE_KEY", "unrelated_github_pat"}
            if not isinstance(runner_forbidden, list) or not required_runner_forbidden.issubset(runner_forbidden):
                errors.append("private phone runner is not explicitly denied Vultr credentials")

        runtime = github.get("runtime_verification")
        if runtime != {
            "vultr_secret_access": "passed_acceptance_vultr_read_only_preflight_on_exact_candidate",
            "android_runner_and_device": "passed_private_actions_read_only_preflight_on_registered_device; mutable_phone_operations_remain_blocked",
        }:
            errors.append("GitHub runtime-verification checkpoint differs from the contract")

        forbidden = github.get("forbidden")
        required_forbidden = {
            "acceptance_authority_using_production_vultr_environment",
            "acceptance_authority_using_final_release_tag",
            "acceptance_vultr_using_production_vultr_environment",
            "acceptance_vultr_lifecycle_without_exact_item_19_authority_preflight_and_readiness_gates",
            "acceptance_vultr_lifecycle_without_serialized_durable_state_transitions",
            "item_19_production_vultr_authority",
            "private_phone_runner_receiving_vultr_credentials",
        }
        if not isinstance(forbidden, list) or not required_forbidden.issubset(forbidden):
            errors.append("GitHub control-plane forbidden set does not protect item-19 boundaries")

    if topology:
        project = topology.get("project_authority")
        if project != {
            "canonical_repository": "iamaman11/mobile-proxy",
            "canonical_gitops_issue": 90,
            "satellite_conflict_policy": "fail_closed_and_reconcile_canonical_repository_first",
        }:
            errors.append("production topology does not bind canonical project authority")
        execution = topology.get("execution")
        if not isinstance(execution, dict):
            errors.append("production topology execution boundary is missing")
        else:
            vultr_acceptance = str(execution.get("vultr_acceptance", ""))
            if "GitHub-hosted runner" not in vultr_acceptance or "production-vultr" not in vultr_acceptance:
                errors.append("Vultr acceptance execution boundary is not GitHub-hosted and production-separated")
            if execution.get("vultr_production") != "GitHub-hosted runner in production-vultr from protected final v* release only":
                errors.append("Vultr production execution boundary differs from protected topology")
            if execution.get("phone") != "private-repository caller context with android-production self-hosted runner":
                errors.append("phone execution boundary differs from protected topology")
            if execution.get("phone_logic") != "canonical public logic pinned to the exact immutable accepted public SHA or verified canonical release artifact":
                errors.append("phone execution logic differs from protected topology")
            if execution.get("cross_boundary_secret_rule") != "private phone runner never receives Vultr credentials and public Vultr jobs never receive raw phone identifiers or phone-control secrets":
                errors.append("cross-control-plane secret separation is not explicit")
        migration = topology.get("migration_status")
        if not isinstance(migration, dict) or any(
            migration.get(key) != value
            for key, value in {
                "phone_execution_satellite": "read_only_preflight_workflow_enabled_and_private_runner_online",
                "phone_live_preflight": "passed_private_actions_read_only_preflight_on_registered_device",
                "acceptance_authority": "implemented_candidate_quality_evidence_gate",
                "vultr_readonly_preflight_workflow": "implemented_live_proof_passed_and_remains_read_only",
                "vultr_live_lifecycle": "historical_item_19_complete_provider_only_live_run_33342000338_exact_candidate_deployed_verified_deleted_and_durable_terminal_confirmed_not_active_item20_candidate_authority",
                "next_acceptance_lifecycle": "item_20_must_select_exact_current_protected_main_as_candidate_and_control_plane_then_open_fresh_jit_acceptance_session_with_distinct_item_20_ownership_intent_and_never_reuse_terminal_item_19_intent",
                "phone_mutation": "item_20_blocked_by_signing_continuity_gate_issue_115",
            }.items()
        ):
            errors.append("production topology GitOps checkpoint differs")

    for relative in REQUIRED_DOCS:
        if not (root / relative).is_file():
            errors.append(f"missing GitHub/project control-plane document: {relative}")

    workflow_root = root / ".github/workflows"
    for workflow in workflow_root.glob("*.yml"):
        content = workflow.read_text(encoding="utf-8").lower()
        for token in ("self-hosted", "adb", "gcloud", "with-production-secrets"):
            if token in content:
                errors.append(f"public workflow {workflow.relative_to(root)} contains forbidden {token!r}")

    acceptance_workflow = root / ACCEPTANCE_WORKFLOW
    if not acceptance_workflow.is_file():
        errors.append("immutable acceptance authority workflow is missing")
    else:
        content = acceptance_workflow.read_text(encoding="utf-8")
        for required in (
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
        ):
            if required not in content:
                errors.append("acceptance workflow does not enforce the exact hosted candidate gate")
                break
        for forbidden in (
            "environment: production-vultr",
            "VULTR_API_KEY",
            "VULTR_SSH_PRIVATE_KEY",
            "refs/tags/",
            "secrets.",
        ):
            if forbidden in content:
                errors.append("acceptance workflow attempts to use final production authority or secrets")
                break

    readonly_workflow = root / READONLY_WORKFLOW
    if not readonly_workflow.is_file():
        errors.append("Vultr read-only preflight workflow is missing")
    else:
        content = readonly_workflow.read_text(encoding="utf-8")
        if "environment: acceptance-vultr" not in content:
            errors.append("read-only preflight must use acceptance-vultr credential boundary")
        if "https://api.vultr.com/v2/account" not in content:
            errors.append("read-only preflight must call exactly the Vultr account endpoint")
        for forbidden in ("/v2/instances", "curl -X POST", "curl -X DELETE", "curl -X PATCH", "environment: production-vultr"):
            if forbidden in content:
                errors.append(f"read-only preflight contains forbidden lifecycle capability {forbidden!r}")

    production_preflight = root / PRODUCTION_PREFLIGHT
    if not production_preflight.is_file():
        errors.append("production preflight workflow is missing")
    else:
        content = production_preflight.read_text(encoding="utf-8")
        required_tag_gate = (
            "environment: production-vultr",
            '[[ "$GITHUB_REF_TYPE" == "tag" ]]',
            '[[ "$GITHUB_REF_NAME" == v* ]]',
            '[[ "$GITHUB_REF" == refs/tags/v* ]]',
            '[[ "$REF_PROTECTED" == "true" ]]',
        )
        if any(token not in content for token in required_tag_gate):
            errors.append("production preflight is no longer protected v*-tag only")

    return errors


def main() -> int:
    errors = check_repository(Path(__file__).resolve().parents[1])
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
