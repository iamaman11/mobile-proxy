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
        if command != {
            "issue": 90,
            "syntax": "/accept-candidate <full_sha>",
            "authorized_actor": "repository_owner",
        }:
            errors.append("acceptance command authority differs from the contract")
        identity = acceptance.get("candidate_identity")
        if not isinstance(identity, dict) or identity.get("kind") != "full_git_sha" or identity.get("pattern") != "^[0-9a-f]{40}$":
            errors.append("acceptance candidate identity is not exact full-SHA only")
        separation = acceptance.get("authority_separation")
        if not isinstance(separation, dict) or any(
            separation.get(key) != value
            for key, value in {
                "final_production_authority": False,
                "production_environment": "forbidden",
                "final_release_tag": "forbidden",
                "production_environment_name": "production-vultr",
                "production_ref_type": "tag",
                "production_ref_pattern": "v*",
            }.items()
        ):
            errors.append("acceptance authority must remain distinct from final production authority")

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

        acceptance_env = github.get("acceptance_vultr_environment")
        if not isinstance(acceptance_env, dict):
            errors.append("acceptance-vultr credential boundary is missing")
        else:
            required = {
                "name": "acceptance-vultr",
                "authority": "pre_release_acceptance_credential_boundary_not_final_production_authority",
                "executor": "github-hosted",
                "final_production_authority": False,
            }
            for key, value in required.items():
                if acceptance_env.get(key) != value:
                    errors.append(f"acceptance-vultr {key!r} differs from protected value")
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
                    errors.append("read-only Vultr preflight capability must remain GET /v2/account only")
                lifecycle = capabilities.get("item_19_acceptance_lifecycle")
                if not isinstance(lifecycle, dict) or any(
                    lifecycle.get(key) != value
                    for key, value in {
                        "status": "implementation_active_live_invocation_forbidden_until_all_item_19_gates",
                        "scope": "acceptance_only",
                        "required_state": "durable_owner_controlled_acceptance_vm_lifecycle_state_outside_vcs",
                        "required_concurrency": "single_repository_wide_acceptance_lifecycle_writer_cancel_in_progress_false",
                        "production_scope": "forbidden",
                    }.items()
                ):
                    errors.append("item-19 acceptance lifecycle capability boundary is not fail-closed")
                elif lifecycle.get("required_exact_candidate_evidence") != [
                    "successful_quality_push_on_protected_main",
                    "fresh_immutable_acceptance_authority",
                    "fresh_vultr_readonly_preflight",
                    "physical_acceptance_window_ready",
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
            if phone.get("required_runner_labels") != ["self-hosted", "Linux", "X64", "android-production"]:
                errors.append("phone runner labels differ from protected contract")
            runner_forbidden = phone.get("runner_must_not_receive")
            required_runner_forbidden = {"VULTR_API_KEY", "VULTR_SSH_PRIVATE_KEY", "unrelated_github_pat"}
            if not isinstance(runner_forbidden, list) or not required_runner_forbidden.issubset(runner_forbidden):
                errors.append("private phone runner is not explicitly denied Vultr credentials")

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
            if "GitHub-hosted runner" not in str(execution.get("vultr_acceptance", "")) or "production-vultr" not in str(execution.get("vultr_acceptance", "")):
                errors.append("Vultr acceptance execution boundary is not GitHub-hosted and production-separated")
            if execution.get("phone") != "private-repository caller context with android-production self-hosted runner":
                errors.append("phone execution boundary differs from protected topology")
            if execution.get("cross_boundary_secret_rule") != "private phone runner never receives Vultr credentials and public Vultr jobs never receive raw phone identifiers or phone-control secrets":
                errors.append("cross-control-plane secret separation is not explicit")

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
            "github.event.issue.number == 90",
            "startsWith(github.event.comment.body, '/accept-candidate ')",
            "runs-on: ubuntu-latest",
            "software-release-candidate-",
            "vultr-acceptance-authority-",
        ):
            if required not in content:
                errors.append(f"acceptance authority workflow is missing {required!r}")
        for forbidden in ("environment: production-vultr", "VULTR_API_KEY", "VULTR_SSH_PRIVATE_KEY", "refs/tags/", "secrets."):
            if forbidden in content:
                errors.append(f"acceptance authority workflow contains forbidden production/provider token {forbidden!r}")

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
        if "environment: production-vultr" not in content or "refs/tags/" not in content:
            errors.append("production preflight must remain production-vultr/tag bound")

    return errors


def main() -> int:
    errors = check_repository(Path(__file__).resolve().parents[1])
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
