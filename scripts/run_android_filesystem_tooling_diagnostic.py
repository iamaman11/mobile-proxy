#!/usr/bin/env python3
"""Inspect Android filesystem-tool compatibility without mutating the phone."""

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

_SCRIPT_DIR = Path(__file__).resolve().parent
_PREFLIGHT_PATH = _SCRIPT_DIR / "run_private_phone_preflight.py"
_SPEC = importlib.util.spec_from_file_location("run_private_phone_preflight", _PREFLIGHT_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("unable to load canonical phone preflight")
_PREFLIGHT = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_PREFLIGHT)

_REQUIRED_SCRATCH_TOOLS = ("cp", "mv", "ln", "readlink", "mkdir", "rm")
_COMPARATOR_TOOLS = ("cmp", "toybox", "busybox")
_SCRATCH_PARENT = "/data/local/tmp"


class DiagnosticFailure(RuntimeError):
    pass


def _probe_shell(serial: str, command: str, *, timeout: int = 10) -> str:
    """Return only a bounded status; never expose command output."""
    try:
        result = subprocess.run(
            ["adb", "-s", serial, "shell", "sh", "-c", command],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return UNKNOWN
    return SUPPORTED if result.returncode == 0 else UNSUPPORTED


def _tool_presence(serial: str, tool: str) -> str:
    return _probe_shell(serial, f"command -v {tool} >/dev/null 2>&1")


def _available_probe(serial: str, presence: str, command: str) -> str:
    if presence == UNKNOWN:
        return UNKNOWN
    if presence == UNSUPPORTED:
        return UNSUPPORTED
    return _probe_shell(serial, command)


def _canonical_comparator(
    presence: dict[str, str], comparator_invocations: dict[str, str]
) -> tuple[str | None, str]:
    # Keep this ordering identical to run_android_filesystem_certification.py.
    if presence["cmp"] == SUPPORTED:
        return "cmp", comparator_invocations["cmp_with_double_dash"]
    if presence["cmp"] == UNKNOWN:
        return None, UNKNOWN
    if presence["toybox"] == SUPPORTED:
        return "toybox_cmp", comparator_invocations["toybox_cmp"]
    if presence["toybox"] == UNKNOWN:
        return None, UNKNOWN
    if presence["busybox"] == SUPPORTED:
        return "busybox_cmp", comparator_invocations["busybox_cmp"]
    if presence["busybox"] == UNKNOWN:
        return None, UNKNOWN
    return None, UNSUPPORTED


def diagnose(canonical_sha: str) -> dict[str, Any]:
    canonical_sha = _PREFLIGHT.require_canonical_sha(canonical_sha)
    serial = _PREFLIGHT.require_expected_serial()
    _PREFLIGHT.require_tools()
    device = _PREFLIGHT.prove_registered_device(serial)

    presence = {
        tool: _tool_presence(serial, tool)
        for tool in (*_COMPARATOR_TOOLS, *_REQUIRED_SCRATCH_TOOLS)
    }

    comparator_invocations = {
        "cmp_with_double_dash": _available_probe(
            serial,
            presence["cmp"],
            "cmp -s -- /dev/null /dev/null",
        ),
        "cmp_without_double_dash": _available_probe(
            serial,
            presence["cmp"],
            "cmp -s /dev/null /dev/null",
        ),
        "toybox_cmp": _available_probe(
            serial,
            presence["toybox"],
            "toybox cmp -s /dev/null /dev/null",
        ),
        "busybox_cmp": _available_probe(
            serial,
            presence["busybox"],
            "busybox cmp -s /dev/null /dev/null",
        ),
    }

    scratch_parent = {
        "directory": _probe_shell(serial, f"test -d {_SCRATCH_PARENT}"),
        "writable": _probe_shell(serial, f"test -w {_SCRATCH_PARENT}"),
        "executable": _probe_shell(serial, f"test -x {_SCRATCH_PARENT}"),
    }

    selected_comparator, selected_status = _canonical_comparator(
        presence, comparator_invocations
    )

    required_statuses = [
        *(presence[tool] for tool in _REQUIRED_SCRATCH_TOOLS),
        *scratch_parent.values(),
        selected_status,
    ]
    if any(status == UNKNOWN for status in required_statuses):
        classification = "UNOBSERVED"
        diagnostic_complete = False
    elif all(status == SUPPORTED for status in required_statuses):
        classification = "FILESYSTEM_TOOLING_COMPATIBLE"
        diagnostic_complete = True
    else:
        classification = "FILESYSTEM_TOOLING_INCOMPATIBLE"
        diagnostic_complete = True

    return {
        "format_version": 1,
        "repository": "iamaman11/mobile-proxy",
        "canonical_sha": canonical_sha,
        "mode": "read_only_filesystem_tooling_diagnostic",
        "classification": classification,
        "device": device,
        "tool_presence": presence,
        "comparator_invocations": comparator_invocations,
        "canonical_comparator": selected_comparator,
        "canonical_comparator_invocation_supported": selected_status,
        "scratch_parent": scratch_parent,
        "diagnostic_complete": diagnostic_complete,
        "raw_command_output_recorded": False,
        "raw_device_identifier_recorded": False,
        "phone_access_performed": True,
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
    except (OSError, DiagnosticFailure, _PREFLIGHT.PreflightFailure) as error:
        print(f"android filesystem tooling diagnostic failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
