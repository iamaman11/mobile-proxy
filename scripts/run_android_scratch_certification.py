#!/usr/bin/env python3
"""Certify bounded Android scratch mutation with explicit recovery."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PREFLIGHT_PATH = SCRIPT_DIR / "run_private_phone_preflight.py"
SPEC = importlib.util.spec_from_file_location("run_private_phone_preflight", PREFLIGHT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("unable to load canonical phone preflight")
PREFLIGHT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREFLIGHT)

SCRATCH_ROOT = "/data/local/tmp/mobile-proxy-adapter-test"
TX_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


class CertificationFailure(RuntimeError):
    pass


def _run(argv: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CertificationFailure(f"transport failure: {argv[0]}") from error


def _shell(serial: str, command: str, *, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return _run(["adb", "-s", serial, "shell", "sh", "-c", command], timeout=timeout)


def _require_success(result: subprocess.CompletedProcess[str], stage: str) -> None:
    if result.returncode != 0:
        raise CertificationFailure(f"{stage} failed")


def _require_absent(serial: str, path: str, stage: str) -> None:
    result = _shell(serial, f"test ! -e {shlex.quote(path)}")
    _require_success(result, stage)


def _push(serial: str, local: Path, remote: str) -> None:
    _require_success(
        _run(["adb", "-s", serial, "push", str(local), remote], timeout=60),
        "adb_push",
    )


def _pull(serial: str, remote: str, local: Path) -> None:
    _require_success(
        _run(["adb", "-s", serial, "pull", remote, str(local)], timeout=60),
        "adb_pull",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _phase(evidence: list[dict[str, str]], step_id: str, status: str) -> None:
    evidence.append({"step_id": step_id, "status": status})


def certify(canonical_sha: str, transaction_id: str) -> tuple[dict[str, Any], bool]:
    canonical_sha = PREFLIGHT.require_canonical_sha(canonical_sha)
    if TX_RE.fullmatch(transaction_id) is None:
        raise CertificationFailure("invalid transaction id")

    serial = PREFLIGHT.require_expected_serial()
    PREFLIGHT.require_tools()
    device_initial = PREFLIGHT.prove_registered_device(serial)

    tx_root = f"{SCRATCH_ROOT}/{transaction_id}"
    payload_remote = f"{tx_root}/payload.bin"
    replacement_remote = f"{tx_root}/payload.next"
    evidence: list[dict[str, str]] = []
    mutation_started = False
    recovery_attempted = False
    recovery_succeeded = False
    failure_stage: str | None = None

    report: dict[str, Any] = {
        "format_version": 1,
        "repository": "iamaman11/mobile-proxy",
        "canonical_sha": canonical_sha,
        "transaction_id": transaction_id,
        "mode": "scratch_mutation_certification",
        "scratch_root": SCRATCH_ROOT,
        "device": device_initial,
        "phase_evidence": evidence,
        "phone_mutation_performed": False,
        "raw_device_identifier_recorded": False,
        "accepted": False,
        "state": "PREPARING",
        "failure_stage": None,
        "recovery_attempted": False,
        "recovery_succeeded": False,
    }

    try:
        _require_absent(serial, tx_root, "initial_scratch_absence")
        _phase(evidence, "scratch_absent_initial", "PASSED")

        boundary = PREFLIGHT.prove_registered_device(serial)
        if boundary != device_initial:
            raise CertificationFailure("registered device boundary proof changed")
        _phase(evidence, "phone_access_boundary", "PASSED")

        with tempfile.TemporaryDirectory(prefix="mobile-proxy-scratch-cert-") as temp_dir:
            temp = Path(temp_dir)
            first = temp / "payload.bin"
            second = temp / "payload.next"
            pulled_first = temp / "pulled-first.bin"
            pulled_second = temp / "pulled-second.bin"
            first.write_bytes(
                b"mobile-proxy-scratch-v1:first\n"
                + canonical_sha.encode("ascii")
                + b"\n"
                + transaction_id.encode("ascii")
                + b"\n"
            )
            second.write_bytes(
                b"mobile-proxy-scratch-v1:replacement\n"
                + canonical_sha.encode("ascii")
                + b"\n"
                + transaction_id.encode("ascii")
                + b"\n"
            )
            first_digest = _sha256(first)
            second_digest = _sha256(second)

            mutation_started = True
            report["phone_mutation_performed"] = True
            _require_success(
                _shell(serial, f"mkdir {shlex.quote(tx_root)}"),
                "scratch_create",
            )
            _phase(evidence, "scratch_create", "PASSED")

            _push(serial, first, payload_remote)
            _phase(evidence, "scratch_push", "PASSED")

            _pull(serial, payload_remote, pulled_first)
            if _sha256(pulled_first) != first_digest:
                raise CertificationFailure("scratch_roundtrip_digest mismatch")
            _phase(evidence, "scratch_roundtrip_verify", "PASSED")

            _push(serial, second, replacement_remote)
            _phase(evidence, "scratch_stage_replacement", "PASSED")

            _require_success(
                _shell(
                    serial,
                    f"mv {shlex.quote(replacement_remote)} {shlex.quote(payload_remote)}",
                ),
                "scratch_atomic_replace",
            )
            _phase(evidence, "scratch_atomic_replace", "PASSED")

            _pull(serial, payload_remote, pulled_second)
            if _sha256(pulled_second) != second_digest:
                raise CertificationFailure("scratch_replacement_digest mismatch")
            _phase(evidence, "scratch_replacement_verify", "PASSED")

            _require_success(
                _shell(serial, f"rm -rf {shlex.quote(tx_root)}"),
                "scratch_cleanup",
            )
            _phase(evidence, "scratch_cleanup", "PASSED")
            _require_absent(serial, tx_root, "scratch_cleanup_verify")
            _phase(evidence, "scratch_absent_final", "PASSED")

        report.update(
            {
                "accepted": True,
                "state": "ACCEPTED",
                "failure_stage": None,
                "recovery_attempted": False,
                "recovery_succeeded": False,
            }
        )
        return report, True
    except (CertificationFailure, PREFLIGHT.PreflightFailure) as error:
        failure_stage = str(error)
        report["failure_stage"] = failure_stage
        if not mutation_started:
            report["state"] = "REFUSED"
            return report, False

        recovery_attempted = True
        report["recovery_attempted"] = True
        try:
            cleanup = _shell(serial, f"rm -rf {shlex.quote(tx_root)}")
            _require_success(cleanup, "recovery_cleanup")
            _phase(evidence, "recovery_cleanup", "PASSED")
            _require_absent(serial, tx_root, "recovery_absence_verify")
            _phase(evidence, "recovery_absence_verify", "PASSED")
            recovery_succeeded = True
            report["recovery_succeeded"] = True
            report["state"] = "RECOVERED"
        except CertificationFailure:
            _phase(evidence, "recovery_cleanup", "FAILED")
            report["state"] = "QUARANTINED"
            report["recovery_succeeded"] = False
        return report, False
    finally:
        report["failure_stage"] = failure_stage
        report["recovery_attempted"] = recovery_attempted
        report["recovery_succeeded"] = recovery_succeeded


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-sha", required=True)
    parser.add_argument("--transaction-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report, accepted = certify(args.canonical_sha, args.transaction_id)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0 if accepted else 1
    except (OSError, CertificationFailure, PREFLIGHT.PreflightFailure) as error:
        print(f"android scratch certification failed before evidence: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
