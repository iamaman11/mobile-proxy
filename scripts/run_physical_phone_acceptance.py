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
_TRANSPORT_BY_STAGE = {
    "online": "quic",
    "post-reboot": "quic",
    "fallback": "tls_tcp",
    "recovered": "quic",
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
    candidate_sha = evidence.get("candidate_sha")
    require(
        isinstance(candidate_sha, str) and _SHA_PATTERN.fullmatch(candidate_sha) is not None,
        "candidate evidence contains an invalid SHA",
    )
    require(evidence.get("software_complete") is True, "software evidence is not complete")
    require(
        evidence.get("physical_phone_acceptance_required") is True,
        "candidate evidence does not require the physical gate",
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


def curl_proxy(arguments: list[str]) -> None:
    command = [
        "curl",
        "--fail",
        "--silent",
        "--show-error",
        "--max-time",
        "20",
        *arguments,
    ]
    try:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError) as error:
        raise AcceptanceFailure("protected proxy surface failed") from error


def prove_proxy_surfaces(
    proxy_host: str,
    http_probe_url: str,
    https_probe_url: str,
) -> dict[str, bool]:
    curl_proxy(["--socks5-hostname", f"{proxy_host}:1080", http_probe_url])
    curl_proxy(["--socks5-hostname", f"{proxy_host}:1081", http_probe_url])
    curl_proxy(["--proxy", f"http://{proxy_host}:3128", http_probe_url])
    curl_proxy(["--proxy", f"http://{proxy_host}:3128", https_probe_url])
    return {
        "mixed_1080": True,
        "socks5_1081": True,
        "http_3128": True,
        "http_connect_3128": True,
    }


def run_stage(args: argparse.Namespace) -> dict[str, Any]:
    evidence = read_json(args.evidence)
    candidate_sha = verify_candidate(evidence)

    host_base = args.host_api_base.rstrip("/")
    control_base = args.control_plane_base.rstrip("/")
    host_token = os.environ.get(args.host_token_env, "")
    control_token = os.environ.get(args.control_token_env, "")
    require(host_token != "", f"{args.host_token_env} is required")
    require(control_token != "", f"{args.control_token_env} is required")

    host_live = request_json(f"{host_base}/livez")
    host_ready = request_json(f"{host_base}/readyz")
    control_ready = request_json(f"{control_base}/readyz")
    require(host_live.get("status") == "live", "host process is not live")
    require(host_ready.get("status") == "ready", "host process is not ready")
    require(control_ready.get("status") == "ready", "control plane is not ready")

    health = request_json(f"{host_base}/v1/health", host_token)
    status = request_json(f"{host_base}/v1/status", host_token)
    require(isinstance(health, dict), "host health response is invalid")
    require(isinstance(status, dict), "host status response is invalid")

    expected_transport = _TRANSPORT_BY_STAGE.get(args.stage)
    if expected_transport is not None:
        require(health.get("reverse_tunnel_connected") is True, "reverse tunnel is disconnected")
        require(
            health.get("reverse_tunnel_active_transport") == expected_transport,
            "reverse tunnel transport differs from the required stage",
        )
        require(health.get("reverse_tunnel_freshness") == "fresh", "reverse tunnel is stale")

    if args.stage == "wireguard":
        require(status.get("wireguard_enabled") is True, "WireGuard rollback is not enabled")

    devices = request_json(f"{control_base}/api/v1/devices", control_token)
    require(isinstance(devices, list) and devices, "restored device inventory is empty")
    if args.device_id:
        require(
            any(
                isinstance(device, dict) and device.get("node_id") == args.device_id
                for device in devices
            ),
            "expected device is absent from restored inventory",
        )

    proxies = prove_proxy_surfaces(
        args.proxy_host,
        args.http_probe_url,
        args.https_probe_url,
    )
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
        "reverse_tunnel": {
            "connected": health.get("reverse_tunnel_connected"),
            "active_transport": health.get("reverse_tunnel_active_transport"),
            "freshness": health.get("reverse_tunnel_freshness"),
        },
        "wireguard_enabled": status.get("wireguard_enabled") is True,
        "proxy_surfaces": proxies,
        "accepted": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stage",
        choices=["online", "post-reboot", "fallback", "recovered", "wireguard"],
        required=True,
    )
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--host-api-base", required=True)
    parser.add_argument("--control-plane-base", required=True)
    parser.add_argument("--proxy-host", required=True)
    parser.add_argument("--http-probe-url", required=True)
    parser.add_argument("--https-probe-url", required=True)
    parser.add_argument("--device-id")
    parser.add_argument("--host-token-env", default="HOST_ADMIN_TOKEN")
    parser.add_argument("--control-token-env", default="CONTROL_PLANE_ADMIN_TOKEN")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = run_stage(args)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except AcceptanceFailure as error:
        print(f"physical acceptance failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
