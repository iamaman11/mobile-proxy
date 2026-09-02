#!/usr/bin/env python3
"""Inventory Android production-runner capabilities without mutating the phone."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


SUPPORTED = "SUPPORTED"
UNSUPPORTED = "UNSUPPORTED"
UNKNOWN = "UNKNOWN"

_SCRIPT_DIR = Path(__file__).resolve().parent
_PREFLIGHT_PATH = _SCRIPT_DIR / "run_private_phone_preflight.py"
_SPEC = importlib.util.spec_from_file_location("run_private_phone_preflight", _PREFLIGHT_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("unable to load canonical phone preflight")
_PREFLIGHT = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_PREFLIGHT)


READ_ONLY_CAPABILITIES = (
    "adb_shell",
    "package_query",
    "root_shell",
    "managed_root_observe",
    "process_observe",
    "network_observe",
    "free_space_observe",
)

MUTATION_CAPABILITIES = (
    "adb_push_pull_roundtrip",
    "managed_root_write",
    "managed_atomic_replace",
    "package_install_uninstall",
    "runtime_start_stop",
)


class InventoryFailure(RuntimeError):
    pass


def _probe(serial: str, *shell_arguments: str, timeout: int = 10) -> str:
    try:
        result = subprocess.run(
            ["adb", "-s", serial, "shell", *shell_arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return UNKNOWN
    return SUPPORTED if result.returncode == 0 else UNSUPPORTED


def inventory(canonical_sha: str) -> dict[str, Any]:
    canonical_sha = _PREFLIGHT.require_canonical_sha(canonical_sha)
    expected_serial = _PREFLIGHT.require_expected_serial()
    _PREFLIGHT.require_tools()
    device = _PREFLIGHT.prove_registered_device(expected_serial)

    capabilities = {
        "adb_shell": SUPPORTED,
        "package_query": _probe(expected_serial, "pm", "path", "android"),
        "root_shell": _probe(expected_serial, "su", "0", "sh", "-c", "true"),
        "managed_root_observe": _probe(
            expected_serial,
            "su",
            "0",
            "sh",
            "-c",
            "root=/data/adb/mobile-proxy-node; [ ! -e \"$root\" ] || { [ -d \"$root\" ] && [ -r \"$root\" ] && [ -x \"$root\" ]; }",
        ),
        "process_observe": _probe(
            expected_serial,
            "su",
            "0",
            "sh",
            "-c",
            "[ -d /proc ] && [ -r /proc/1/status ]",
        ),
        "network_observe": _probe(
            expected_serial,
            "su",
            "0",
            "sh",
            "-c",
            "[ -r /proc/net/tcp ] && [ -r /proc/net/tcp6 ]",
        ),
        "free_space_observe": _probe(expected_serial, "df", "/data"),
    }
    for capability in MUTATION_CAPABILITIES:
        capabilities[capability] = UNKNOWN

    read_only_supported = all(
        capabilities[name] == SUPPORTED for name in READ_ONLY_CAPABILITIES
    )
    unresolved = sorted(
        name for name, state in capabilities.items() if state != SUPPORTED
    )

    return {
        "format_version": 1,
        "repository": "iamaman11/mobile-proxy",
        "canonical_sha": canonical_sha,
        "mode": "read_only_capability_inventory",
        "device": device,
        "capabilities": capabilities,
        "read_only_capabilities_proven": read_only_supported,
        "full_clean_install_capability_proven": not unresolved,
        "unresolved_capabilities": unresolved,
        "raw_device_identifier_recorded": False,
        "phone_mutation_performed": False,
        "inventory_complete": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = inventory(args.canonical_sha)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, _PREFLIGHT.PreflightFailure, InventoryFailure) as error:
        print(f"android capability inventory failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
