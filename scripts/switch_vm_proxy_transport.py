#!/usr/bin/env python3
"""Atomically switch VM public proxy ports and verify exact configuration bytes."""

from __future__ import annotations

import argparse
import base64
import json
import shlex
import subprocess
import sys
from pathlib import Path


class SwitchFailure(RuntimeError):
    pass


_CONFIG_VERSION = 1
_CONFIGS = {
    "reverse-tunnel": """server { listen 0.0.0.0:1080; proxy_pass 127.0.0.1:14080; }
server { listen 0.0.0.0:1081; proxy_pass 127.0.0.1:14081; }
server { listen 0.0.0.0:3128; proxy_pass 127.0.0.1:14128; }
""",
    "wireguard": """server { listen 0.0.0.0:1080; proxy_pass 127.0.0.1:11080; }
server { listen 0.0.0.0:1081; proxy_pass 127.0.0.1:11081; }
server { listen 0.0.0.0:3128; proxy_pass 127.0.0.1:13128; }
""",
    "server-termination": """server { listen 0.0.0.0:1080; proxy_pass 127.0.0.1:12080; }
server { listen 0.0.0.0:1081; proxy_pass 127.0.0.1:12081; }
server { listen 0.0.0.0:3128; proxy_pass 127.0.0.1:12128; }
""",
}
_REMOTE_CONFIG = "/etc/nginx/stream-available/mobile-public-proxy.conf"
_SUCCESS_MARKER = "exact-config-match"


def remote_command(mode: str) -> str:
    encoded = base64.b64encode(_CONFIGS[mode].encode()).decode()
    if mode == "wireguard":
        required_services = "wg-quick@wg0.service mobile-public-proxy.service"
    elif mode == "server-termination":
        required_services = "mobile-public-proxy.service mobile-reverse-tunnel-server.service"
    else:
        required_services = "mobile-reverse-tunnel-server.service"
    temporary = f"{_REMOTE_CONFIG}.candidate.$$"
    expected = f"{_REMOTE_CONFIG}.expected.$$"
    backup = f"{_REMOTE_CONFIG}.backup.$$"
    return f"""set -eu
CONFIG={shlex.quote(_REMOTE_CONFIG)}
TEMP={shlex.quote(temporary)}
EXPECTED={shlex.quote(expected)}
BACKUP={shlex.quote(backup)}
COMMITTED=0
cleanup() {{
  if [ "$COMMITTED" -ne 1 ] && [ -f "$BACKUP" ]; then
    sudo cp "$BACKUP" "$CONFIG"
    if sudo nginx -t; then
      sudo systemctl reload nginx || true
    fi
  fi
  sudo rm -f "$TEMP" "$EXPECTED" "$BACKUP"
}}
trap cleanup EXIT
sudo cp "$CONFIG" "$BACKUP"
printf %s {shlex.quote(encoded)} | base64 -d | sudo tee "$TEMP" >/dev/null
sudo cp "$TEMP" "$EXPECTED"
sudo chmod 0644 "$TEMP" "$EXPECTED"
sudo mv "$TEMP" "$CONFIG"
sudo nginx -t
sudo systemctl reload nginx
sudo systemctl is-active {required_services}
sudo ss -lnt | grep -E ':(1080|1081|3128) '
sudo cmp -s -- "$CONFIG" "$EXPECTED"
printf '{_SUCCESS_MARKER}\\n'
COMMITTED=1
"""


def exact_match_returned(output: str) -> bool:
    return any(line.strip() == _SUCCESS_MARKER for line in output.splitlines())


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
    if not exact_match_returned(completed.stdout):
        raise SwitchFailure("VM public proxy transport config was not verified byte-for-byte")
    return {
        "format_version": 1,
        "mode": args.mode,
        "config_contract": "mobile-public-proxy/v1",
        "config_version": _CONFIG_VERSION,
        "exact_config_match": True,
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
