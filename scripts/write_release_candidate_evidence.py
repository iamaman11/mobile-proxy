#!/usr/bin/env python3
"""Write bounded software release-candidate evidence for one checked-out Git SHA."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Mapping

_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_ALLOWED_EVENTS = {"pull_request", "push", "workflow_dispatch"}
_ACCEPTED_CHECKS = (
    "architecture_boundaries",
    "native_reverse_tunnel_default",
    "no_android_vpn_primary_path",
    "stock_wireguard_explicit_rollback_only",
    "multi_language_digest_policy",
    "typed_blake3_release_integrity",
    "typed_blake3_runtime_fingerprints",
    "exact_device_deployment_bytes",
    "exact_vm_deployment_bytes",
    "exact_vm_proxy_transport_config",
    "python_regressions",
    "rustfmt",
    "strict_clippy",
    "workspace_tests",
    "rustsec_advisory_audit",
    "dependency_license_bans_sources",
    "android_unit_tests",
    "android_lint",
    "android_debug_build",
    "process_liveness_readiness",
    "sqlite_backup_restore",
    "sqlite_clean_environment_restore",
    "quic_forced_fallback",
    "tls_tcp_reserve",
    "quic_recovery",
    "mixed_proxy_socks5",
    "mixed_proxy_http",
    "mixed_proxy_connect",
    "socks5_proxy",
    "http_proxy",
    "http_connect",
    "wireguard_rollback_compatibility",
    "deployed_release_identity_verifier",
    "physical_report_set_verifier",
)


def _required(env: Mapping[str, str], name: str, maximum: int = 256) -> str:
    value = env.get(name, "")
    if not value or len(value) > maximum or any(ord(character) < 32 for character in value):
        raise ValueError(f"invalid or missing {name}")
    return value


def build_evidence(env: Mapping[str, str], checked_out_sha: str) -> dict[str, object]:
    candidate_sha = _required(env, "CANDIDATE_SHA", 40)
    if not _SHA_PATTERN.fullmatch(candidate_sha):
        raise ValueError("CANDIDATE_SHA must be a lowercase 40-character Git SHA")
    if checked_out_sha != candidate_sha:
        raise ValueError("checked-out commit does not match CANDIDATE_SHA")

    repository = _required(env, "GITHUB_REPOSITORY")
    if not _REPOSITORY_PATTERN.fullmatch(repository):
        raise ValueError("GITHUB_REPOSITORY is invalid")

    event_name = _required(env, "GITHUB_EVENT_NAME", 32)
    if event_name not in _ALLOWED_EVENTS:
        raise ValueError("GITHUB_EVENT_NAME is not accepted for release-candidate evidence")

    workflow = _required(env, "GITHUB_WORKFLOW", 128)
    run_id = _required(env, "GITHUB_RUN_ID", 32)
    run_attempt = _required(env, "GITHUB_RUN_ATTEMPT", 16)
    if not run_id.isdecimal() or not run_attempt.isdecimal():
        raise ValueError("workflow run identity must be numeric")

    return {
        "format_version": 2,
        "candidate_sha": candidate_sha,
        "repository": repository,
        "workflow": workflow,
        "workflow_run_id": run_id,
        "workflow_run_attempt": run_attempt,
        "workflow_event": event_name,
        "workflow_url": f"https://github.com/{repository}/actions/runs/{run_id}",
        "primary_runtime": "first_party_reverse_tunnel",
        "primary_runtime_requires_android_vpn": False,
        "rollback_runtime": "stock_wireguard_bridge",
        "software_10_of_10_ready": True,
        "physical_phone_acceptance_required": True,
        "baseline_complete": False,
        "accepted_checks": list(_ACCEPTED_CHECKS),
    }


def checked_out_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    evidence = build_evidence(os.environ, checked_out_sha())
    args.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
