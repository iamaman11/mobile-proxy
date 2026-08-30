#!/usr/bin/env python3
"""Run the canonical read-only preflight for the private production phone runner."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_REQUIRED_TOOLS = ("adb", "python", "git", "curl")
_REQUIRED_RUNNER_LABELS = ("self-hosted", "Windows", "X64", "android-production")
_SERIAL_ENV = "ANDROID_PRODUCTION_SERIAL"


class PreflightFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PreflightFailure(message)


def require_canonical_sha(value: str) -> str:
    require(_SHA_PATTERN.fullmatch(value) is not None, "canonical SHA is invalid")
    return value


def require_expected_serial() -> str:
    value = os.environ.get(_SERIAL_ENV, "")
    require(bool(value), "registered production device binding is unavailable")
    require(len(value) <= 128, "registered production device binding is invalid")
    require(
        not any(character.isspace() for character in value),
        "registered production device binding is invalid",
    )
    require(
        all(32 < ord(character) < 127 for character in value),
        "registered production device binding is invalid",
    )
    return value


def require_tools() -> dict[str, bool]:
    result: dict[str, bool] = {}
    for tool in _REQUIRED_TOOLS:
        available = shutil.which(tool) is not None
        require(available, f"required runner tool is missing: {tool}")
        result[tool] = True
    return result


def run_adb(*arguments: str) -> str:
    try:
        return subprocess.run(
            ["adb", *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise PreflightFailure("read-only ADB probe failed") from error


def parse_device_rows(output: str) -> list[tuple[str, str]]:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    require(
        bool(lines) and lines[0] == "List of devices attached",
        "ADB device inventory is invalid",
    )
    rows: list[tuple[str, str]] = []
    for line in lines[1:]:
        parts = line.split()
        require(len(parts) == 2, "ADB device inventory is invalid")
        rows.append((parts[0], parts[1]))
    return rows


def prove_registered_device(expected_serial: str) -> dict[str, Any]:
    rows = parse_device_rows(run_adb("devices"))
    require(len(rows) == 1, "production runner must expose exactly one ADB device")
    serial, state = rows[0]
    require(
        serial == expected_serial,
        "connected device does not match registered production device",
    )
    require(state == "device", "registered production device is not online")
    require(
        run_adb("-s", expected_serial, "get-state") == "device",
        "registered production device state differs",
    )
    run_adb("-s", expected_serial, "shell", "true")
    return {
        "device_count": 1,
        "registered_device_match": True,
        "adb_state": "device",
        "shell_probe": True,
    }


def build_report(canonical_sha: str) -> dict[str, Any]:
    tools = require_tools()
    expected_serial = require_expected_serial()
    device = prove_registered_device(expected_serial)
    return {
        "format_version": 1,
        "repository": "iamaman11/mobile-proxy",
        "canonical_sha": require_canonical_sha(canonical_sha),
        "mode": "read_only",
        "required_runner_labels": list(_REQUIRED_RUNNER_LABELS),
        "required_tools": tools,
        "device": device,
        "raw_device_identifier_recorded": False,
        "mutation_performed": False,
        "accepted": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = build_report(args.canonical_sha)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, PreflightFailure) as error:
        print(f"phone preflight failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
