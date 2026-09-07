#!/usr/bin/env python3
"""Emit a bounded static repository map for humans, agents and CI.

Dynamic stage, release and production state intentionally do not live here.
Resolve them from the newest authoritative PRODUCT Issue #179 checkpoint and
its current subordinate Stage Issue.
"""

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
    source_version = workspace["package"]["version"]
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
        "format_version": 2,
        "project_authority": {
            "product_repository": "iamaman11/mobile-proxy",
            "deployment_controller_repository": "iamaman11/mobile-proxy-production",
            "stage_cursor": "iamaman11/mobile-proxy#179",
            "planning_backlog": "iamaman11/mobile-proxy#249",
            "product_release_command_surface": "iamaman11/mobile-proxy#90",
            "deployment_command_ingress": "iamaman11/mobile-proxy-production#1",
            "authority_rule": "one product, two authoritative planes; newest PRODUCT #179 checkpoint governs stage authority",
            "chat_history_authority": "none",
        },
        "git": {
            "branch": _git("branch", "--show-current") or "(detached)",
            "clean_tracked": not bool(
                _git("status", "--porcelain", "--untracked-files=no")
            ),
            "sha": _git("rev-parse", "HEAD"),
        },
        "current_execution": {
            "dynamic_stage_source": "newest authoritative checkpoint in iamaman11/mobile-proxy#179",
            "context_recovery_spine": [
                "AGENTS.md",
                "STAGE_WORKFLOW.md",
                "newest authoritative PRODUCT #179 checkpoint",
                "current subordinate Stage Issue",
            ],
            "stage_roadmap": "docs/PRODUCTION_STAGE_ROADMAP.md",
            "baseline_invariants": "docs/PRODUCTION_BASELINE_PLAN.md",
            "acceptance_catalog": "TEN_OUT_OF_TEN_VALIDATION_PLAN.md",
            "architecture_standard": "docs/architecture/ARCHITECTURE_STANDARD.md",
            "future_direction": "docs/FUTURE_PLATFORM_ARCHITECTURE_ROADMAP.md (non-active)",
            "dynamic_state_embedded_here": False,
        },
        "source_metadata": {
            "workspace_version": source_version,
            "expected_tag_from_source_version": f"v{source_version}",
            "warning": "source metadata is not the current immutable Product Release; resolve Release authority from GitHub Release evidence and #179",
        },
        "architecture": {
            "primary_runtime": "first_party_reverse_tunnel",
            "production_phone_owner": "first_party_reverse_tunnel",
            "default_tunnel_owner": "first_party_reverse_tunnel",
            "carrier_specific_egress_owner": "first_party_android_egress",
            "deployment_identity": "exact immutable Product Release + exact admitted Deployment Controller revision",
            "public_proxy_ports": {
                "1080": "mixed SOCKS5/HTTP compatibility",
                "1081": "SOCKS5",
                "3128": "HTTP including CONNECT",
            },
            "production_data_path": (
                "relay edge -> reverse-tunnel server -> phone-local proxy -> Android cellular egress"
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
            "release_tag_workflow": ".github/workflows/release-tag.yml",
            "deployment_controller_ingress": "iamaman11/mobile-proxy-production#1",
            "phone_mutation_owner": "Deployment Controller",
            "vm_provider_authority": "fail-closed until Stage 6 is explicitly opened by PRODUCT #179",
        },
        "authoritative_docs": [
            "AGENTS.md",
            "STAGE_WORKFLOW.md",
            "README.md",
            "QUICK_REFERENCE.md",
            "IMPLEMENTATION_PLAN.md",
            "docs/PRODUCTION_STAGE_ROADMAP.md",
            "docs/PRODUCTION_BASELINE_PLAN.md",
            "TEN_OUT_OF_TEN_VALIDATION_PLAN.md",
            "REPOSITORY_MAP.md",
            "RUNTIME_LAYOUT.md",
            "docs/architecture/ARCHITECTURE_STANDARD.md",
            "docs/architecture/invariant-enforcement.md",
            "docs/GIT_DELIVERY.md",
            "docs/operations/project-authority.md",
            "docs/operations/github-bootstrap.md",
            "docs/operations/secret-boundaries.md",
            "contracts/governance/invariant-enforcement.json",
            "contracts/governance/module-boundaries-v1.json",
            "contracts/governance/state-ownership-v1.json",
            "contracts/compatibility/proxy-surface-v1.json",
            "contracts/operations/project-authority-v2.json",
            "contracts/operations/github-control-plane-v2.json",
            "contracts/operations/production-topology-v2.json",
            "contracts/operations/product-release-authority-v2.json",
        ],
        "historical_not_execution_authority": [
            "A-H implementation sequences superseded by the seven-stage roadmap",
            "Item15-23 / Item19-20 execution plans",
            "v1 cross-repository authority/topology/control-plane contracts when they conflict with v2",
        ],
        "workflows": workflows,
    }


def to_markdown(context: dict[str, Any]) -> str:
    project = context["project_authority"]
    git = context["git"]
    current = context["current_execution"]
    source = context["source_metadata"]
    workspace = context["workspace"]
    quality = context["quality"]
    return "\n".join(
        [
            "## Repository context",
            "",
            f"- PRODUCT authority: {project['product_repository']}",
            f"- Deployment Controller authority: {project['deployment_controller_repository']}",
            f"- Dynamic stage cursor: {project['stage_cursor']}",
            f"- SHA: {git['sha']}",
            f"- Branch: {git['branch']}",
            f"- Tracked worktree clean: {str(git['clean_tracked']).lower()}",
            "- Context recovery: AGENTS.md -> STAGE_WORKFLOW.md -> newest #179 checkpoint -> current Stage Issue",
            f"- Static stage roadmap: {current['stage_roadmap']}",
            f"- Architecture standard: {current['architecture_standard']}",
            f"- Source workspace version: {source['workspace_version']} (not current Release authority)",
            f"- Workspace members: {workspace['member_count']}",
            f"- Required check: {quality['required_check']}",
            "- Current stage/release/production facts are intentionally not embedded here.",
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
