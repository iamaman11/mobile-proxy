#!/usr/bin/env python3
"""Probe Android filesystem tooling compatibility without mutating the phone."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SUPPORTED = "SUPPORTED"
UNSUPPORTED = "UNSUPPORTED"
UNKNOWN = "UNKNOWN"
_OPERATION_ID = "android.filesystem-tooling-compatibility.v1"

_SCRIPT_DIR = Path(__file__).resolve().parent
_PREFLIGHT_PATH = _SCRIPT_DIR / "run_private_phone_preflight.py"
_SPEC = importlib.util.spec_from_file_location("run_private_phone_preflight", _PREFLIGHT_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("unable to load canonical phone preflight")
_PREFLIGHT = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_PREFLIGHT)


_TOOL_PRESENCE = (
    "cp",
    "mv",
    "ln",
    "readlink",
    "rm",
    "mkdir",
    "test",
)

_COMPARATOR_PROBES = {
    "cmp_present": "command -v cmp >/dev/null 2>&1",
    "cmp_exact_invocation": "cmp -s -- /dev/null /dev/null >/dev/null 2>&1",
    "toybox_present": "command -v toybox >/dev/null 2>&1",
    "toybox_cmp_exact_invocation": "toybox cmp -s /dev/null /dev/null >/dev/null 2>&1",
    "busybox_present": "command -v busybox >/dev/null 2>&1",
    "busybox_cmp_exact_invocation": "busybox cmp -s /dev/null /dev/null >/dev/null 2>&1",
}


class ToolingDiagnosticFailure(RuntimeError):
    pass


def _probe(serial: str, command: str, *, root: bool, timeout: int = 10) -> str:
    prefix = ["adb", "-s", serial, "shell"]
    if root:
        prefix += ["su", "0", "sh", "-c", command]
    else:
        prefix += ["sh", "-c", command]
    try:
        result = subprocess.run(
            prefix,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return UNKNOWN
    return SUPPORTED if result.returncode == 0 else UNSUPPORTED


def _select_comparator(probes: dict[str, str]) -> tuple[str, str]:
    for selected, present_key, invocation_key in (
        ("cmp", "cmp_present", "cmp_exact_invocation"),
        ("toybox_cmp", "toybox_present", "toybox_cmp_exact_invocation"),
        ("busybox_cmp", "busybox_present", "busybox_cmp_exact_invocation"),
    ):
        presence = probes[present_key]
        if presence == UNKNOWN:
            return "UNKNOWN", UNKNOWN
        if presence == SUPPORTED:
            return selected, probes[invocation_key]
    return "NONE", UNSUPPORTED


def _scope_probe(serial: str, *, root: bool) -> dict[str, Any]:
    probes: dict[str, str] = {
        "shell_set_eu": _probe(serial, "set -eu; true", root=root),
    }
    for tool in _TOOL_PRESENCE:
        probes[f"{tool}_present"] = _probe(
            serial,
            f"command -v {tool} >/dev/null 2>&1",
            root=root,
        )
    for name, command in _COMPARATOR_PROBES.items():
        probes[name] = _probe(serial, command, root=root)

    selected, state = _select_comparator(probes)
    return {
        "probes": probes,
        "selected_comparator": selected,
        "canonical_comparator_path_state": state,
        "probe_complete": all(value != UNKNOWN for value in probes.values()),
    }


def diagnose(canonical_sha: str) -> dict[str, Any]:
    canonical_sha = _PREFLIGHT.require_canonical_sha(canonical_sha)
    serial = _PREFLIGHT.require_expected_serial()
    _PREFLIGHT.require_tools()
    device = _PREFLIGHT.prove_registered_device(serial)

    scratch = _scope_probe(serial, root=False)
    managed_root = _scope_probe(serial, root=True)
    diagnostic_complete = (
        scratch["probe_complete"] is True
        and managed_root["probe_complete"] is True
    )
    comparator_compatibility_proven = (
        diagnostic_complete
        and scratch["canonical_comparator_path_state"] == SUPPORTED
        and managed_root["canonical_comparator_path_state"] == SUPPORTED
    )

    return {
        "format_version": 1,
        "repository": "iamaman11/mobile-proxy",
        "canonical_sha": canonical_sha,
        "operation_id": _OPERATION_ID,
        "mode": "read_only_filesystem_tooling_compatibility",
        "device": device,
        "scratch_scope": scratch,
        "managed_root_scope": managed_root,
        "comparator_compatibility_proven": comparator_compatibility_proven,
        "diagnostic_complete": diagnostic_complete,
        "probe_contract": {
            "tool_presence_only_for_mutating_filesystem_tools": True,
            "comparator_invocation_targets": ["/dev/null", "/dev/null"],
            "persistent_test_files_created": False,
        },
        "raw_device_identifier_recorded": False,
        "raw_command_output_recorded": False,
        "phone_mutation_performed": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = diagnose(args.canonical_sha)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, _PREFLIGHT.PreflightFailure, ToolingDiagnosticFailure) as error:
        print(f"android filesystem tooling diagnostic failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
