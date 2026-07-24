#!/usr/bin/env python3
"""Activate an already installed immutable phone release with a full runtime restart."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

from run_physical_phone_acceptance import (
    AcceptanceFailure,
    read_json,
    require,
    verify_candidate,
)

_RELEASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _adb_prefix(serial: str | None) -> list[str]:
    command = ["adb"]
    if serial:
        command += ["-s", serial]
    return command


def activation_script(device_root: str, release_id: str) -> str:
    require(_RELEASE_ID.fullmatch(release_id) is not None, "release ID is invalid")
    root = shlex.quote(device_root.rstrip("/"))
    release = shlex.quote(release_id)
    return f"""set -eu
ROOT={root}
REL={release}
TARGET="$ROOT/releases/$REL"
test -d "$TARGET"
test -x "$TARGET/service.sh"
if command -v pkill >/dev/null 2>&1; then
  pkill -f mobile-proxy-runtime-watchdog || true
  pkill -f /data/local/tmp/mobile-proxy-logs/runtime-watchdog.sh || true
  pkill -f "$ROOT/.*/bin/runtime-supervisor" || true
  pkill -f "$ROOT/.*/bin/host-daemon" || true
  pkill -f "$ROOT/.*/bin/sing-box" || true
fi
for pid in $(pidof runtime-supervisor host-daemon sing-box 2>/dev/null || true); do
  kill "$pid" || true
done
rm -f /data/local/tmp/mobile-proxy-logs/runtime-watchdog.pid
sleep 1
ln -sfn "$TARGET" "$ROOT/current"
sh "$ROOT/current/service.sh"
readlink "$ROOT/current"
"""


def activate(args: argparse.Namespace) -> dict[str, object]:
    candidate_sha = verify_candidate(read_json(args.evidence))
    script = activation_script(args.device_root, args.release_id)
    command = [
        *_adb_prefix(args.device_serial),
        "shell",
        "su",
        "0",
        "sh",
        "-c",
        script,
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise AcceptanceFailure("device release activation failed") from error
    active = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
    expected = f"{args.device_root.rstrip('/')}/releases/{args.release_id}"
    require(active == expected, "active device release differs after restart")
    return {
        "format_version": 1,
        "candidate_sha": candidate_sha,
        "release_id": args.release_id,
        "active_release": expected,
        "full_runtime_restart": True,
        "accepted": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--device-serial")
    parser.add_argument("--device-root", default="/data/adb/mobile-proxy-node")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = activate(args)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except AcceptanceFailure as error:
        print(f"device release activation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
