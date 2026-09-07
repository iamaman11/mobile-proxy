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
        and not any(part in {"target", "build", "__pycache__", ".gradle"} for part in path.parts)
    )

    return {
        "format_version": 3,
        "project_authority": {
            "product_repository": "iamaman11/mobile-proxy",
            "deployment_controller_repository": "iamaman11/mobile-proxy-production",
            "stage_cursor": "iamaman11/mobile-proxy#179",
            "planning_backlog": "iamaman11/mobile-proxy#249",
            "product_release_command_surface": "iamaman11/mobile-proxy#90",
            "deployment_command_ingress": "iamaman11/mobile-proxy-production#1",
            "chat_history_authority": "none",
        },
        "source_of_truth_by_concern": {
            "dynamic_stage_operations_authority": "iamaman11/mobile-proxy#179 newest owner checkpoint",
            "cross_project_working_method": "STAGE_WORKFLOW.md",
            "cross_plane_ownership": "docs/operations/project-authority.md + v2 authority/topology/Product Release contracts",
            "static_stage_sequence_scope": "docs/PRODUCTION_STAGE_ROADMAP.md",
            "architecture_complexity_standard": "docs/architecture/ARCHITECTURE_STANDARD.md",
            "stage_acceptance_catalog": "TEN_OUT_OF_TEN_VALIDATION_PLAN.md",
            "current_stage_evidence": "one subordinate Stage Issue named by the current #179 checkpoint",
            "controller_runtime_transaction_truth": "iamaman11/mobile-proxy-production#1 exact causal ledger records",
            "reusable_phone_diagnostic_mechanics": "iamaman11/mobile-proxy-production#97 on demand only",
        },
        "context_recovery": {
            "spine": [
                "AGENTS.md",
                "STAGE_WORKFLOW.md",
                "newest authoritative PRODUCT #179 checkpoint",
                "current subordinate Stage Issue",
            ],
            "issue_179_access": "metadata/body + last owner-authored checkpoint comment only; walk backward minimally if needed",
            "stage_issue_access": "body + newest stage-relevant comments only",
            "controller_issue_1_access": "exact causal command/ACK/intent/terminal/recovery comment IDs only",
            "controller_issue_97_access": "optional reusable diagnostic reference on demand only",
            "optional_human_navigation": ["QUICK_REFERENCE.md", "IMPLEMENTATION_PLAN.md"],
            "dynamic_state_embedded_here": False,
        },
        "git": {
            "branch": _git("branch", "--show-current") or "(detached)",
            "clean_tracked": not bool(_git("status", "--porcelain", "--untracked-files=no")),
            "sha": _git("rev-parse", "HEAD"),
        },
        "source_metadata": {
            "workspace_version": source_version,
            "expected_tag_from_source_version": f"v{source_version}",
            "warning": "source metadata is not current immutable Product Release authority",
        },
        "architecture": {
            "primary_runtime": "first_party_reverse_tunnel",
            "carrier_specific_egress_owner": "first_party_android_egress",
            "deployment_identity": "exact immutable Product Release + exact admitted Deployment Controller revision",
            "production_data_path": "relay edge -> reverse-tunnel server -> phone-local proxy -> Android cellular egress",
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
        },
        "delivery": {
            "release_workflow": ".github/workflows/release.yml",
            "release_tag_workflow": ".github/workflows/release-tag.yml",
            "phone_mutation_owner": "Deployment Controller",
            "vm_provider_authority": "fail-closed until Stage 6 is explicitly opened by PRODUCT #179",
        },
        "reference_docs_on_demand": [
            "README.md",
            "QUICK_REFERENCE.md",
            "IMPLEMENTATION_PLAN.md",
            "docs/PRODUCTION_BASELINE_PLAN.md",
            "RUNTIME_LAYOUT.md",
            "REPOSITORY_MAP.md",
            "docs/GIT_DELIVERY.md",
            "docs/operations/github-bootstrap.md",
            "docs/operations/secret-boundaries.md",
            "docs/architecture/invariant-enforcement.md",
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
    source = context["source_metadata"]
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
            "- Context recovery: AGENTS.md -> STAGE_WORKFLOW.md -> last #179 checkpoint -> current Stage Issue",
            "- #179 access: last owner-authored checkpoint comment only for normal recovery",
            "- Controller #1: exact causal ledger comment IDs only",
            "- Controller #97: optional reusable diagnostic reference only",
            f"- Source workspace version: {source['workspace_version']} (not current Release authority)",
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
    body = json.dumps(context, indent=2, sort_keys=True) + "\n" if args.format == "json" else to_markdown(context)
    if args.output == "-":
        print(body, end="")
    else:
        Path(args.output).write_text(body, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
