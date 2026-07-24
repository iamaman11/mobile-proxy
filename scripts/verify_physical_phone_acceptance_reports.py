#!/usr/bin/env python3
"""Verify the complete immutable-SHA physical-phone acceptance report set."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from run_physical_phone_acceptance import (
    AcceptanceFailure,
    read_json,
    require,
    verify_candidate,
)

_EXPECTED_TRANSPORT = {
    "online": "quic",
    "post-reboot": "quic",
    "fallback": "tls_tcp",
    "recovered": "quic",
}
_REQUIRED_PROXY_SURFACES = {
    "mixed_1080_socks5",
    "mixed_1080_http",
    "mixed_1080_connect",
    "socks5_1081",
    "http_3128",
    "http_connect_3128",
}


def verify_deployment_report(report: dict[str, Any], candidate_sha: str) -> None:
    require(report.get("format_version") == 1, "deployment report version is unsupported")
    require(report.get("candidate_sha") == candidate_sha, "deployment report SHA differs")
    require(report.get("accepted") is True, "deployment report is not accepted")
    require(report.get("device_release_metadata_match") is True, "device release metadata differs")
    require(report.get("device_deployment_match") is True, "device deployment differs")
    require(report.get("vm_deployment_match") is True, "VM deployment differs")
    require(
        isinstance(report.get("device_release_entries"), int)
        and 0 < report["device_release_entries"] <= 128,
        "device deployment inventory is invalid",
    )
    require(
        isinstance(report.get("vm_release_entries"), int)
        and 0 < report["vm_release_entries"] <= 128,
        "VM deployment inventory is invalid",
    )


def verify_stage_report(report: dict[str, Any], candidate_sha: str, stage: str) -> None:
    require(report.get("format_version") == 1, f"{stage} report version is unsupported")
    require(report.get("candidate_sha") == candidate_sha, f"{stage} report SHA differs")
    require(report.get("stage") == stage, f"{stage} report stage differs")
    require(report.get("accepted") is True, f"{stage} report is not accepted")
    require(report.get("device_inventory_present") is True, f"{stage} device inventory is missing")
    require(report.get("expected_device_present") is True, f"{stage} expected device is missing")

    process_health = report.get("process_health")
    require(isinstance(process_health, dict), f"{stage} process health is invalid")
    require(
        process_health == {
            "host_live": True,
            "host_ready": True,
            "control_plane_ready": True,
        },
        f"{stage} process health is incomplete",
    )

    proxies = report.get("proxy_surfaces")
    require(isinstance(proxies, dict), f"{stage} proxy report is invalid")
    require(set(proxies) == _REQUIRED_PROXY_SURFACES, f"{stage} proxy report is incomplete")
    require(all(value is True for value in proxies.values()), f"{stage} proxy surface failed")

    reverse_tunnel = report.get("reverse_tunnel")
    require(isinstance(reverse_tunnel, dict), f"{stage} tunnel report is invalid")
    expected_transport = _EXPECTED_TRANSPORT.get(stage)
    if expected_transport is not None:
        require(reverse_tunnel.get("connected") is True, f"{stage} tunnel is disconnected")
        require(
            reverse_tunnel.get("active_transport") == expected_transport,
            f"{stage} tunnel transport differs",
        )
        require(reverse_tunnel.get("freshness") == "fresh", f"{stage} tunnel is stale")
    if stage == "wireguard":
        require(report.get("wireguard_enabled") is True, "WireGuard rollback report is not enabled")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--deployment", type=Path, required=True)
    parser.add_argument("--online", type=Path, required=True)
    parser.add_argument("--post-reboot", type=Path, required=True)
    parser.add_argument("--fallback", type=Path, required=True)
    parser.add_argument("--recovered", type=Path, required=True)
    parser.add_argument("--wireguard", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        candidate_sha = verify_candidate(read_json(args.evidence))
        deployment = read_json(args.deployment)
        verify_deployment_report(deployment, candidate_sha)
        reports = {
            "online": read_json(args.online),
            "post-reboot": read_json(args.post_reboot),
            "fallback": read_json(args.fallback),
            "recovered": read_json(args.recovered),
            "wireguard": read_json(args.wireguard),
        }
        for stage, report in reports.items():
            verify_stage_report(report, candidate_sha, stage)
        summary = {
            "format_version": 1,
            "candidate_sha": candidate_sha,
            "deployment_integrity_accepted": True,
            "accepted_stages": list(reports),
            "physical_phone_acceptance_complete": True,
            "accepted": True,
        }
        args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except AcceptanceFailure as error:
        print(f"physical report verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
