#!/usr/bin/env python3
"""Keep the public GitHub control-plane boundary fail-closed."""

from __future__ import annotations

import json
from pathlib import Path


GITHUB_CONTRACT = Path("contracts/operations/github-control-plane-v1.json")
TOPOLOGY_CONTRACT = Path("contracts/operations/production-topology-v1.json")
REQUIRED_DOCS = (
    Path("docs/GIT_DELIVERY.md"),
    Path("docs/operations/github-bootstrap.md"),
    Path("docs/operations/secret-boundaries.md"),
)


def _load(path: Path, errors: list[str]) -> dict[str, object]:
    if not path.is_file():
        errors.append(f"missing GitHub control-plane contract: {path}")
        return {}
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        errors.append(f"cannot parse GitHub control-plane contract {path}: {error}")
        return {}
    if not isinstance(body, dict):
        errors.append(f"GitHub control-plane contract must be an object: {path}")
        return {}
    return body


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    github = _load(root / GITHUB_CONTRACT, errors)
    topology = _load(root / TOPOLOGY_CONTRACT, errors)
    if github:
        source = github.get("source_repository")
        if not isinstance(source, dict) or source != {
            "name": "iamaman11/mobile-proxy",
            "visibility": "public",
            "self_hosted_runners": "forbidden",
        }:
            errors.append("public source repository boundary is not exact")
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
        if not isinstance(phone, dict) or phone.get("visibility") != "private":
            errors.append("phone control repository must remain private")
        elif phone.get("required_runner_labels") != [
            "self-hosted",
            "Linux",
            "X64",
            "android-production",
        ]:
            errors.append("phone runner labels differ from the contract")
    if topology:
        execution = topology.get("execution")
        if execution != {
            "vultr": "GitHub-hosted runner in production-vultr",
            "phone": "private-repository self-hosted runner with android-production label",
        }:
            errors.append("production topology execution split differs from the contract")

    for relative in REQUIRED_DOCS:
        if not (root / relative).is_file():
            errors.append(f"missing GitHub control-plane document: {relative}")

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
