#!/usr/bin/env python3
"""Emit a bounded, current repository map for humans, agents and CI."""

from __future__ import annotations

import argparse
import json
import subprocess
import tomllib
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def build_context() -> dict[str, Any]:
    cargo = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8"))
    workspace = cargo["workspace"]
    version = workspace["package"]["version"]
    members = sorted(workspace["members"])
    workflows = sorted(path.name for path in (ROOT / ".github/workflows").glob("*.yml"))
    source_files = sum(
        1
        for group in ("apps", "crates", "services", "scripts")
        for path in (ROOT / group).rglob("*")
        if path.is_file()
        and not any(
            part in {"target", "build", "__pycache__", ".gradle"}
            for part in path.parts
        )
    )
    return {
        "format_version": 1,
        "project_authority": {
            "canonical_repository": "iamaman11/mobile-proxy",
            "canonical_url": "https://github.com/iamaman11/mobile-proxy",
            "canonical_gitops_issue": 90,
            "execution_satellite": "iamaman11/mobile-proxy-production",
            "execution_satellite_control_issue": 1,
            "authority_rule": (
                "canonical repository wins; conflicts fail closed and are reconciled here first"
            ),
            "chat_history_authority": "none",
        },
        "git": {
            "branch": _git("branch", "--show-current") or "(detached)",
            "clean_tracked": not bool(
                _git("status", "--porcelain", "--untracked-files=no")
            ),
            "sha": _git("rev-parse", "HEAD"),
        },
        "release": {
            "version": version,
            "expected_tag": f"v{version}",
            "release_id_rule": "git-<first 12 characters of tag commit SHA>",
            "cross_repository_deployment_id_rule": "mobile-proxy-<tag>-<first12sha>",
            "identity_fields": [
                "annotated release tag",
                "full Git SHA",
                "artifact name",
                "artifact digest",
                "provenance identity",
            ],
        },
        "architecture": {
            "primary_runtime": "first_party_reverse_tunnel",
            "production_phone_owner": "first_party_android_egress",
            "public_proxy_ports": {
                "1080": "mixed SOCKS5/HTTP compatibility",
                "1081": "SOCKS5",
                "3128": "HTTP including CONNECT",
            },
            "production_data_path": (
                "nginx -> Rust reverse-tunnel server -> Android cellular egress"
            ),
            "rollback_only": [
                "sing-box VM termination",
                "stock WireGuard bridge",
            ],
        },
        "workspace": {
            "members": members,
            "member_count": len(members),
            "bounded_source_file_count": source_files,
        },
        "quality": {
            "required_check": "Quality Gate",
            "workflow": ".github/workflows/quality.yml",
            "local_fast_gate": "scripts/quality-gate.sh fast",
            "local_full_gate": "scripts/quality-gate.sh",
            "summary_artifact": "quality-summary-<git-sha>",
        },
        "delivery": {
            "release_workflow": ".github/workflows/release.yml",
            "deployment_workflow": ".github/workflows/deploy-production.yml",
            "vultr_environment": "production-vultr (tag-only; GitHub-hosted)",
            "phone_control_repository": (
                "iamaman11/mobile-proxy-production (private execution satellite only)"
            ),
            "phone_control_issue": "iamaman11/mobile-proxy-production#1",
            "deployment_status": "blocked until split GitOps workflows are implemented",
            "release_immutability": "not enabled until publish ordering is corrected",
        },
        "authoritative_docs": [
            "README.md",
            "AGENTS.md",
            "IMPLEMENTATION_PLAN.md",
            "docs/PRODUCTION_BASELINE_PLAN.md",
            "docs/GIT_DELIVERY.md",
            "docs/operations/project-authority.md",
            "docs/operations/github-bootstrap.md",
            "docs/operations/secret-boundaries.md",
            "RUNTIME_LAYOUT.md",
            "contracts/governance/invariant-enforcement.json",
            "contracts/operations/project-authority-v1.json",
            "contracts/operations/github-control-plane-v1.json",
            "contracts/operations/production-topology-v1.json",
        ],
        "workflows": workflows,
    }


def to_markdown(context: dict[str, Any]) -> str:
    project = context["project_authority"]
    git = context["git"]
    release = context["release"]
    workspace = context["workspace"]
    quality = context["quality"]
    return "\n".join(
        [
            "## Repository context",
            "",
            f"- Canonical repository: {project['canonical_repository']}",
            f"- Canonical GitOps issue: #{project['canonical_gitops_issue']}",
            f"- Execution satellite: {project['execution_satellite']}",
            f"- SHA: {git['sha']}",
            f"- Branch: {git['branch']}",
            f"- Tracked worktree clean: {str(git['clean_tracked']).lower()}",
            f"- Version/tag: {release['version']} / {release['expected_tag']}",
            f"- Workspace members: {workspace['member_count']}",
            f"- Required check: {quality['required_check']}",
            "- Production path: nginx -> Rust reverse tunnel -> Android cellular egress",
            "- Deployable unit: published annotated tag resolved to one immutable SHA",
            "- Satellite authority: execution-only; canonical repository wins on conflict",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", default="-")
    args = parser.parse_args()
    context = build_context()
    body = (
        json.dumps(context, indent=2, sort_keys=True) + "\n"
        if args.format == "json"
        else to_markdown(context)
    )
    if args.output == "-":
        print(body, end="")
    else:
        Path(args.output).write_text(body, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
