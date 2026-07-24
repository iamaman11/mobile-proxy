#!/usr/bin/env python3
"""Atomically switch VM public proxy ports between reverse tunnel and WireGuard."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path


class SwitchFailure(RuntimeError):
    pass


_CONFIGS = {
    "reverse-tunnel": """server { listen 0.0.0.0:1080; proxy_pass 127.0.0.1:14080; }
server { listen 0.0.0.0:1081; proxy_pass 127.0.0.1:14081; }
server { listen 0.0.0.0:3128; proxy_pass 127.0.0.1:14128; }
""",
    "wireguard": """server { listen 0.0.0.0:1080; proxy_pass 127.0.0.1:11080; }
server { listen 0.0.0.0:1081; proxy_pass 127.0.0.1:11081; }
server { listen 0.0.0.0:3128; proxy_pass 127.0.0.1:13128; }
""",
}
_REMOTE_CONFIG = "/etc/nginx/stream-available/mobile-public-proxy.conf"


def config_digest(mode: str) -> str:
    return hashlib.sha256(_CONFIGS[mode].encode()).hexdigest()


def remote_command(mode: str) -> str:
    encoded = base64.b64encode(_CONFIGS[mode].encode()).decode()
    required_services = (
        "wg-quick@wg0.service mobile-public-proxy.service"
        if mode == "wireguard"
        else "mobile-reverse-tunnel-server.service"
    )
    temporary = f"{_REMOTE_CONFIG}.candidate"
    return " && ".join(
        [
            f"printf %s {shlex.quote(encoded)} | base64 -d | sudo tee {shlex.quote(temporary)} >/dev/null",
            f"sudo chmod 0644 {shlex.quote(temporary)}",
            f"sudo mv {shlex.quote(temporary)} {shlex.quote(_REMOTE_CONFIG)}",
            "sudo nginx -t",
            "sudo systemctl reload nginx",
            f"sudo systemctl is-active {required_services}",
            "sudo ss -lnt | grep -E ':(1080|1081|3128) '",
            f"sudo sha256sum -- {shlex.quote(_REMOTE_CONFIG)}",
        ]
    )


def parse_remote_digest(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        raise SwitchFailure("VM transport switch did not return a config digest")
    parts = lines[-1].split(maxsplit=1)
    if len(parts) != 2 or len(parts[0]) != 64:
        raise SwitchFailure("VM transport switch returned an invalid config digest")
    digest = parts[0]
    if any(character not in "0123456789abcdef" for character in digest):
        raise SwitchFailure("VM transport switch returned an invalid config digest")
    return digest


def switch(args: argparse.Namespace) -> dict[str, object]:
    command = [
        "gcloud",
        "compute",
        "ssh",
        f"{args.ssh_user}@{args.instance}",
        "--project",
        args.project,
        "--zone",
        args.zone,
        "--ssh-key-file",
        args.ssh_key,
        "--tunnel-through-iap",
        "--command",
        remote_command(args.mode),
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise SwitchFailure("VM public proxy transport switch failed") from error
    actual = parse_remote_digest(completed.stdout)
    expected = config_digest(args.mode)
    if actual != expected:
        raise SwitchFailure("VM public proxy transport config differs after reload")
    return {
        "format_version": 1,
        "mode": args.mode,
        "config_sha256": expected,
        "public_ports": [1080, 1081, 3128],
        "accepted": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=sorted(_CONFIGS), required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--zone", required=True)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--ssh-user", required=True)
    parser.add_argument("--ssh-key", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = switch(args)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except SwitchFailure as error:
        print(f"VM proxy transport switch failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
