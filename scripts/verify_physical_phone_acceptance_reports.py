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
    "post-wireguard-recovered": "quic",
}
_REQUIRED_PROXY_SURFACES = {
    "mixed_1080_socks5",
    "mixed_1080_http",
    "mixed_1080_connect",
    "socks5_1081",
    "http_3128",
    "http_connect_3128",
}


def verify_deployment_report(
    report: dict[str, Any],
    candidate_sha: str,
    label: str,
    expected_owner: str,
) -> None:
    require(report.get("format_version") == 1, f"{label} deployment report version is unsupported")
    require(report.get("candidate_sha") == candidate_sha, f"{label} deployment report SHA differs")
    require(report.get("accepted") is True, f"{label} deployment report is not accepted")
    require(report.get("expected_tunnel_owner") == expected_owner, f"{label} deployment tunnel owner differs")
    require(report.get("device_release_metadata_match") is True, f"{label} device release metadata differs")
    require(report.get("device_deployment_match") is True, f"{label} device deployment differs")
    require(report.get("android_vpn_owner_match") is True, f"{label} Android VPN owner differs")
    require(report.get("vm_deployment_match") is True, f"{label} VM deployment differs")
    require(
        isinstance(report.get("device_release_entries"), int)
        and 0 < report["device_release_entries"] <= 128,
        f"{label} device deployment inventory is invalid",
    )
    require(
        isinstance(report.get("vm_release_entries"), int)
        and 0 < report["vm_release_entries"] <= 128,
        f"{label} VM deployment inventory is invalid",
    )


def verify_switch_report(report: dict[str, Any], mode: str, label: str) -> None:
    require(report.get("format_version") == 1, f"{label} switch report version is unsupported")
    require(report.get("mode") == mode, f"{label} switch report mode differs")
    require(report.get("accepted") is True, f"{label} switch report is not accepted")
    digest = report.get("config_sha256")
    require(
        isinstance(digest, str)
        and len(digest) == 64
        and all(character in "0123456789abcdef" for character in digest),
        f"{label} switch digest is invalid",
    )
    require(report.get("public_ports") == [1080, 1081, 3128], f"{label} switch ports differ")


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

    device_state = report.get("device_state")
    require(isinstance(device_state, dict), f"{stage} device state is invalid")
    for field in [
        "serving",
        "heartbeat_present",
        "cellular_route_ready",
        "proxy_bind_ready",
        "local_serving_ready",
    ]:
        require(device_state.get(field) is True, f"{stage} device state {field} is false")
    require(device_state.get("availability") == "available", f"{stage} device is unavailable")
    require(isinstance(device_state.get("node_id"), str), f"{stage} node_id is invalid")

    proxies = report.get("proxy_surfaces")
    require(isinstance(proxies, dict), f"{stage} proxy report is invalid")
    require(set(proxies) == _REQUIRED_PROXY_SURFACES, f"{stage} proxy report is incomplete")
    require(all(value is True for value in proxies.values()), f"{stage} proxy surface failed")

    reverse_tunnel = report.get("reverse_tunnel")
    require(isinstance(reverse_tunnel, dict), f"{stage} tunnel report is invalid")
    wireguard = report.get("wireguard")
    require(isinstance(wireguard, dict), f"{stage} WireGuard report is invalid")
    expected_transport = _EXPECTED_TRANSPORT.get(stage)
    if expected_transport is not None:
        require(report.get("tunnel_owner") == "first_party_reverse_tunnel", f"{stage} tunnel owner differs")
        require(reverse_tunnel.get("connected") is True, f"{stage} tunnel is disconnected")
        require(
            reverse_tunnel.get("active_transport") == expected_transport,
            f"{stage} tunnel transport differs",
        )
        require(reverse_tunnel.get("freshness") == "fresh", f"{stage} tunnel is stale")
        require(wireguard.get("enabled") is False, f"{stage} unexpectedly enables WireGuard")
        require(wireguard.get("tun0_present") is not True, f"{stage} leaves tun0 active")
    if stage == "wireguard":
        require(report.get("tunnel_owner") == "stock_wireguard_bridge", "WireGuard tunnel owner differs")
        require(wireguard.get("enabled") is True, "WireGuard rollback report is not enabled")
        require(wireguard.get("tun0_present") is True, "WireGuard tun0 is absent")
        require(wireguard.get("handshake_recent") is True, "WireGuard handshake is not recent")
        require(reverse_tunnel.get("connected") is not True, "reverse tunnel remained active during WireGuard report")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--primary-deployment", type=Path, required=True)
    parser.add_argument("--wireguard-deployment", type=Path, required=True)
    parser.add_argument("--final-deployment", type=Path, required=True)
    parser.add_argument("--primary-switch", type=Path, required=True)
    parser.add_argument("--wireguard-switch", type=Path, required=True)
    parser.add_argument("--reverse-switch", type=Path, required=True)
    parser.add_argument("--online", type=Path, required=True)
    parser.add_argument("--post-reboot", type=Path, required=True)
    parser.add_argument("--fallback", type=Path, required=True)
    parser.add_argument("--recovered", type=Path, required=True)
    parser.add_argument("--wireguard", type=Path, required=True)
    parser.add_argument("--post-wireguard-recovered", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        candidate_sha = verify_candidate(read_json(args.evidence))
        deployments = {
            "primary": (read_json(args.primary_deployment), "first_party_reverse_tunnel"),
            "wireguard": (read_json(args.wireguard_deployment), "stock_wireguard_bridge"),
            "final": (read_json(args.final_deployment), "first_party_reverse_tunnel"),
        }
        for label, (report, owner) in deployments.items():
            verify_deployment_report(report, candidate_sha, label, owner)
        verify_switch_report(read_json(args.primary_switch), "reverse-tunnel", "primary")
        verify_switch_report(read_json(args.wireguard_switch), "wireguard", "wireguard")
        verify_switch_report(read_json(args.reverse_switch), "reverse-tunnel", "final")
        reports = {
            "online": read_json(args.online),
            "post-reboot": read_json(args.post_reboot),
            "fallback": read_json(args.fallback),
            "recovered": read_json(args.recovered),
            "wireguard": read_json(args.wireguard),
            "post-wireguard-recovered": read_json(args.post_wireguard_recovered),
        }
        node_ids = set()
        for stage, report in reports.items():
            verify_stage_report(report, candidate_sha, stage)
            node_ids.add(report["device_state"]["node_id"])
        require(len(node_ids) == 1, "physical stage reports use different device IDs")
        summary = {
            "format_version": 1,
            "candidate_sha": candidate_sha,
            "device_id": node_ids.pop(),
            "deployment_integrity_accepted": True,
            "transport_switches_accepted": True,
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
