#!/usr/bin/env python3
"""Run one stage of physical-phone acceptance against an immutable candidate."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_EXPECTED_REPOSITORY = "iamaman11/mobile-proxy"
_EXPECTED_WORKFLOW = "Quality"
_REQUIRED_SOFTWARE_CHECKS = {
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
}
_TRANSPORT_BY_STAGE = {
    "online": "quic",
    "post-reboot": "quic",
    "fallback": "tls_tcp",
    "recovered": "quic",
    "post-wireguard-recovered": "quic",
}


class AcceptanceFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceFailure(message)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AcceptanceFailure("candidate evidence is unreadable") from error
    require(isinstance(value, dict), "candidate evidence must be a JSON object")
    return value


def git_output(*arguments: str) -> str:
    try:
        return subprocess.run(
            ["git", *arguments],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as error:
        raise AcceptanceFailure("Git checkout verification failed") from error


def verify_candidate(evidence: dict[str, Any]) -> str:
    require(evidence.get("format_version") == 2, "candidate evidence version is unsupported")
    require(evidence.get("repository") == _EXPECTED_REPOSITORY, "candidate evidence repository differs")
    require(evidence.get("workflow") == _EXPECTED_WORKFLOW, "candidate evidence workflow differs")
    candidate_sha = evidence.get("candidate_sha")
    require(
        isinstance(candidate_sha, str) and _SHA_PATTERN.fullmatch(candidate_sha) is not None,
        "candidate evidence contains an invalid SHA",
    )
    require(
        evidence.get("primary_runtime") == "first_party_reverse_tunnel",
        "candidate primary runtime differs",
    )
    require(
        evidence.get("primary_runtime_requires_android_vpn") is False,
        "candidate incorrectly requires Android VPN for the primary runtime",
    )
    require(
        evidence.get("rollback_runtime") == "stock_wireguard_bridge",
        "candidate rollback runtime differs",
    )
    require(evidence.get("software_10_of_10_ready") is True, "software evidence is not 10/10-ready")
    require(
        evidence.get("physical_phone_acceptance_required") is True,
        "candidate evidence does not require the physical gate",
    )
    require(evidence.get("baseline_complete") is False, "software evidence falsely declares baseline complete")
    accepted_checks = evidence.get("accepted_checks")
    require(isinstance(accepted_checks, list), "candidate evidence checks are invalid")
    require(
        all(isinstance(check, str) and len(check) <= 64 for check in accepted_checks),
        "candidate evidence checks are invalid",
    )
    require(
        len(accepted_checks) == len(set(accepted_checks)),
        "candidate evidence contains duplicate checks",
    )
    require(
        _REQUIRED_SOFTWARE_CHECKS.issubset(set(accepted_checks)),
        "candidate evidence is missing required software checks",
    )
    require(git_output("rev-parse", "HEAD") == candidate_sha, "checkout SHA differs from candidate")
    require(not git_output("status", "--porcelain"), "candidate checkout is not clean")
    return candidate_sha


def request_json(url: str, token: str | None = None) -> dict[str, Any] | list[Any]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            require(200 <= response.status < 300, "health API returned a non-success status")
            value = json.loads(response.read())
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        raise AcceptanceFailure("health API request failed") from error
    require(isinstance(value, (dict, list)), "health API returned an invalid JSON value")
    return value


def require_object(value: dict[str, Any] | list[Any], name: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{name} response is invalid")
    return value


def _curl_config_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def curl_proxy(arguments: list[str], proxy_credentials: str) -> None:
    command = [
        "curl",
        "--fail",
        "--silent",
        "--show-error",
        "--max-time",
        "20",
        "--noproxy",
        "",
        "--config",
        "-",
        *arguments,
    ]
    environment = os.environ.copy()
    environment["NO_PROXY"] = ""
    environment["no_proxy"] = ""
    curl_config = f'proxy-user = "{_curl_config_value(proxy_credentials)}"\n'
    try:
        subprocess.run(
            command,
            check=True,
            input=curl_config,
            text=True,
            stdout=subprocess.DEVNULL,
            env=environment,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise AcceptanceFailure("protected proxy surface failed") from error


def prove_proxy_surfaces(
    proxy_host: str,
    http_probe_url: str,
    https_probe_url: str,
    proxy_credentials: str,
) -> dict[str, bool]:
    curl_proxy(["--socks5-hostname", f"{proxy_host}:1080", http_probe_url], proxy_credentials)
    curl_proxy(["--proxy", f"http://{proxy_host}:1080", http_probe_url], proxy_credentials)
    curl_proxy(["--proxy", f"http://{proxy_host}:1080", https_probe_url], proxy_credentials)
    curl_proxy(["--socks5-hostname", f"{proxy_host}:1081", http_probe_url], proxy_credentials)
    curl_proxy(["--proxy", f"http://{proxy_host}:3128", http_probe_url], proxy_credentials)
    curl_proxy(["--proxy", f"http://{proxy_host}:3128", https_probe_url], proxy_credentials)
    return {
        "mixed_1080_socks5": True,
        "mixed_1080_http": True,
        "mixed_1080_connect": True,
        "socks5_1081": True,
        "http_3128": True,
        "http_connect_3128": True,
    }


def _required_environment(name: str, maximum: int = 4096) -> str:
    value = os.environ.get(name, "")
    require(bool(value), f"required environment variable {name} is missing")
    require(len(value) <= maximum, f"required environment variable {name} is too long")
    require(not any(character.isspace() and character not in " " for character in value), f"required environment variable {name} is invalid")
    return value


def find_device(inventory: dict[str, Any] | list[Any], expected_device_id: str) -> tuple[bool, dict[str, Any] | None]:
    if isinstance(inventory, dict):
        devices = inventory.get("devices")
    else:
        devices = inventory
    require(isinstance(devices, list), "device inventory response is invalid")
    require(len(devices) <= 10_000, "device inventory response is unbounded")
    matches = [device for device in devices if isinstance(device, dict) and device.get("node_id") == expected_device_id]
    require(len(matches) <= 1, "device inventory contains duplicate expected devices")
    return bool(matches), matches[0] if matches else None


def build_stage_report(args: argparse.Namespace, candidate_sha: str) -> dict[str, Any]:
    host_token = _required_environment("HOST_ADMIN_TOKEN")
    control_token = _required_environment("CONTROL_PLANE_ADMIN_TOKEN")
    proxy_username = _required_environment("PROXY_USERNAME", 256)
    proxy_password = _required_environment("PROXY_PASSWORD")
    proxy_credentials = f"{proxy_username}:{proxy_password}"

    host_live = request_json(f"{args.host_api_base.rstrip('/')}/livez")
    host_ready = request_json(f"{args.host_api_base.rstrip('/')}/readyz")
    control_ready = request_json(f"{args.control_plane_base.rstrip('/')}/readyz")
    require_object(host_live, "host liveness")
    require_object(host_ready, "host readiness")
    require_object(control_ready, "control-plane readiness")

    health = require_object(
        request_json(f"{args.host_api_base.rstrip('/')}/v1/health", host_token),
        "host health",
    )
    inventory = request_json(
        f"{args.control_plane_base.rstrip('/')}/api/v1/devices",
        control_token,
    )
    present, device = find_device(inventory, args.expected_device_id)
    require(present and device is not None, "expected device is absent from control-plane inventory")

    required_true = {
        "serving": health.get("serving"),
        "cellular_route_ready": health.get("cellular_route_ready"),
        "proxy_bind_ready": health.get("proxy_bind_ready"),
        "local_serving_ready": health.get("local_serving_ready"),
    }
    for name, value in required_true.items():
        require(value is True, f"device health {name} is not true")
    require(health.get("node_id") == args.expected_device_id, "host health device ID differs")
    require(device.get("node_id") == args.expected_device_id, "control-plane device ID differs")
    require(device.get("serving") is True, "control-plane device is not serving")
    require(device.get("availability") == "available", "control-plane device is unavailable")
    require(device.get("last_heartbeat_at") is not None, "control-plane heartbeat is missing")

    owner = health.get("tunnel_owner")
    reverse = {
        "connected": health.get("reverse_tunnel_connected"),
        "active_transport": health.get("reverse_tunnel_active_transport"),
        "freshness": health.get("reverse_tunnel_freshness"),
    }
    wireguard = {
        "enabled": health.get("wireguard_enabled"),
        "tun0_present": health.get("tun0_present"),
        "handshake_recent": health.get("wg_handshake_recent"),
    }
    expected_transport = _TRANSPORT_BY_STAGE.get(args.stage)
    if expected_transport is not None:
        require(owner == "first_party_reverse_tunnel", "reverse stage tunnel owner differs")
        require(reverse["connected"] is True, "reverse tunnel is disconnected")
        require(reverse["active_transport"] == expected_transport, "reverse tunnel transport differs")
        require(reverse["freshness"] == "fresh", "reverse tunnel is not fresh")
        require(wireguard["enabled"] is False, "reverse stage unexpectedly enables WireGuard")
        require(wireguard["tun0_present"] is not True, "reverse stage leaves Android VPN active")
    elif args.stage == "wireguard":
        require(owner == "stock_wireguard_bridge", "WireGuard stage owner differs")
        require(wireguard["enabled"] is True, "WireGuard stage is not enabled")
        require(wireguard["tun0_present"] is True, "WireGuard stage tun0 is absent")
        require(wireguard["handshake_recent"] is True, "WireGuard stage handshake is not recent")
        require(reverse["connected"] is not True, "reverse tunnel remained active during WireGuard stage")

    return {
        "format_version": 1,
        "candidate_sha": candidate_sha,
        "stage": args.stage,
        "process_health": {
            "host_live": True,
            "host_ready": True,
            "control_plane_ready": True,
        },
        "device_inventory_present": True,
        "expected_device_present": True,
        "device_state": {
            "node_id": args.expected_device_id,
            "serving": True,
            "availability": "available",
            "heartbeat_present": True,
            "cellular_route_ready": True,
            "proxy_bind_ready": True,
            "local_serving_ready": True,
        },
        "tunnel_owner": owner,
        "reverse_tunnel": reverse,
        "wireguard": wireguard,
        "proxy_surfaces": prove_proxy_surfaces(
            args.proxy_host,
            args.http_probe_url,
            args.https_probe_url,
            proxy_credentials,
        ),
        "accepted": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stage",
        choices=["online", "post-reboot", "fallback", "recovered", "wireguard", "post-wireguard-recovered"],
        required=True,
    )
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--host-api-base", required=True)
    parser.add_argument("--control-plane-base", required=True)
    parser.add_argument("--proxy-host", required=True)
    parser.add_argument("--expected-device-id", required=True)
    parser.add_argument("--http-probe-url", default="http://example.com/")
    parser.add_argument("--https-probe-url", default="https://example.com/")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        candidate_sha = verify_candidate(read_json(args.evidence))
        report = build_stage_report(args, candidate_sha)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except AcceptanceFailure as error:
        print(f"physical acceptance failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
