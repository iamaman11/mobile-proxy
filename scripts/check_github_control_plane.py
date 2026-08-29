#!/usr/bin/env python3
"""Keep the canonical GitHub/project control-plane boundary fail-closed."""

from __future__ import annotations

import json
from pathlib import Path


AUTHORITY_CONTRACT = Path("contracts/operations/project-authority-v1.json")
GITHUB_CONTRACT = Path("contracts/operations/github-control-plane-v1.json")
TOPOLOGY_CONTRACT = Path("contracts/operations/production-topology-v1.json")
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
        if not isinstance(execution, dict) or any(
            execution.get(key) != value
            for key, value in {
                "vultr": "GitHub-hosted runner in production-vultr",
                "phone": (
                    "private-repository caller context with android-production self-hosted runner"
                ),
            }.items()
        ):
            errors.append("production topology execution split differs from the contract")

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
