#!/usr/bin/env python3
"""Certify bounded Android filesystem mutation semantics on the registered phone."""

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
from pathlib import Path, PurePosixPath
from typing import Any


SUPPORTED = "SUPPORTED"
UNKNOWN = "UNKNOWN"
_OPERATION_ID = "android.filesystem-certification.v1"
_TRANSACTION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_SCRATCH_BASE = PurePosixPath("/data/local/tmp/mobile-proxy-adapter-test")
_MANAGED_ROOT = PurePosixPath("/data/adb/mobile-proxy-node")
_MANAGED_BASE = _MANAGED_ROOT / ".adapter-test"

_SCRIPT_DIR = Path(__file__).resolve().parent


def _load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPT_DIR / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load canonical module: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_PREFLIGHT = _load_module("run_private_phone_preflight", "run_private_phone_preflight.py")
_CAPABILITIES = _load_module("run_android_capability_inventory", "run_android_capability_inventory.py")


class CertificationFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CertificationFailure(message)


def require_transaction_id(value: str) -> str:
    require(_TRANSACTION_ID.fullmatch(value) is not None, "transaction ID is invalid")
    return value


def transaction_paths(transaction_id: str) -> dict[str, str]:
    transaction_id = require_transaction_id(transaction_id)
    scratch = _SCRATCH_BASE / transaction_id
    managed = _MANAGED_BASE / transaction_id
    for base, target in ((_SCRATCH_BASE, scratch), (_MANAGED_BASE, managed)):
        require(target.parent == base, "transaction path escaped certification base")
        require(".." not in target.parts, "transaction path contains traversal")
        require(target != base, "transaction path must not equal certification base")
    return {
        "scratch_base": str(_SCRATCH_BASE),
        "scratch": str(scratch),
        "managed_root": str(_MANAGED_ROOT),
        "managed_base": str(_MANAGED_BASE),
        "managed": str(managed),
    }


def _run(command: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CertificationFailure("device command transport failed") from error
    if result.returncode != 0:
        raise CertificationFailure("device command returned nonzero status")
    return result


def adb(serial: str, *arguments: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return _run(["adb", "-s", serial, *arguments], timeout=timeout)


def shell(serial: str, command: str, *, root: bool = False, timeout: int = 30) -> str:
    prefix = ["shell"]
    if root:
        prefix += ["su", "0", "sh", "-c", command]
    else:
        prefix += ["sh", "-c", command]
    return adb(serial, *prefix, timeout=timeout).stdout.strip()


def _q(path: str) -> str:
    return shlex.quote(path)


def _remote_digest(serial: str, path: str, *, root: bool) -> str:
    quoted = _q(path)
    command = f"""set -eu
p={quoted}
if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$p" | awk '{{print $1}}'
elif command -v toybox >/dev/null 2>&1; then
  toybox sha256sum "$p" | awk '{{print $1}}'
elif command -v busybox >/dev/null 2>&1; then
  busybox sha256sum "$p" | awk '{{print $1}}'
else
  exit 73
fi
"""
    digest = shell(serial, command, root=root).splitlines()
    require(len(digest) == 1, "remote digest output is ambiguous")
    value = digest[0].strip().lower()
    require(re.fullmatch(r"[0-9a-f]{64}", value) is not None, "remote digest is invalid")
    return value


def _verify_remote_digest(serial: str, path: str, expected: str, *, root: bool) -> None:
    require(_remote_digest(serial, path, root=root) == expected, "remote digest differs")


def _verify_absent(serial: str, path: str, *, root: bool) -> None:
    shell(serial, f"test ! -e {_q(path)} && test ! -L {_q(path)}", root=root)


def _prepare_payloads(root: Path, canonical_sha: str, transaction_id: str) -> dict[str, Any]:
    original = (f"mobile-proxy-filesystem-certification\n{canonical_sha}\n{transaction_id}\noriginal\n").encode()
    replacement = (f"mobile-proxy-filesystem-certification\n{canonical_sha}\n{transaction_id}\nreplacement\n").encode()
    original_path = root / "original.bin"
    replacement_path = root / "replacement.bin"
    original_path.write_bytes(original)
    replacement_path.write_bytes(replacement)
    return {
        "original_path": original_path,
        "replacement_path": replacement_path,
        "original_sha256": hashlib.sha256(original).hexdigest(),
        "replacement_sha256": hashlib.sha256(replacement).hexdigest(),
    }


def verify_prestate(serial: str, paths: dict[str, str]) -> None:
    shell(
        serial,
        (
            f"test -d {_q(paths['managed_root'])} && "
            f"test ! -L {_q(paths['managed_root'])} && "
            f"{{ test ! -e {_q(paths['managed_base'])} || "
            f"{{ test -d {_q(paths['managed_base'])} && test ! -L {_q(paths['managed_base'])}; }}; }} && "
            f"test ! -e {_q(paths['managed'])} && test ! -L {_q(paths['managed'])} && "
            f"test ! -e {_q(paths['scratch'])} && test ! -L {_q(paths['scratch'])}"
        ),
        root=True,
    )


def run_scratch_certification(
    serial: str,
    paths: dict[str, str],
    payloads: dict[str, Any],
    local_root: Path,
) -> None:
    scratch = paths["scratch"]
    shell(serial, f"mkdir -p {_q(paths['scratch_base'])} && mkdir {_q(scratch)}")

    remote_original = f"{scratch}/original.bin"
    remote_replacement = f"{scratch}/replacement.bin"
    remote_active = f"{scratch}/active.bin"
    remote_next = f"{scratch}/active.next"
    remote_link = f"{scratch}/active.link"

    adb(serial, "push", str(payloads["original_path"]), remote_original)
    adb(serial, "push", str(payloads["replacement_path"]), remote_replacement)
    _verify_remote_digest(serial, remote_original, payloads["original_sha256"], root=False)
    _verify_remote_digest(serial, remote_replacement, payloads["replacement_sha256"], root=False)

    pulled = local_root / "pulled-original.bin"
    adb(serial, "pull", remote_original, str(pulled))
    require(
        hashlib.sha256(pulled.read_bytes()).hexdigest() == payloads["original_sha256"],
        "ADB pull roundtrip digest differs",
    )

    shell(serial, f"cp {_q(remote_original)} {_q(remote_active)}")
    _verify_remote_digest(serial, remote_active, payloads["original_sha256"], root=False)
    shell(serial, f"cp {_q(remote_replacement)} {_q(remote_next)} && mv -f {_q(remote_next)} {_q(remote_active)}")
    _verify_remote_digest(serial, remote_active, payloads["replacement_sha256"], root=False)

    shell(serial, f"ln -s active.bin {_q(remote_link)}")
    link_target = shell(serial, f"readlink {_q(remote_link)}")
    require(link_target == "active.bin", "scratch symlink target differs")
    _verify_remote_digest(serial, remote_link, payloads["replacement_sha256"], root=False)

    shell(serial, f"rm -f {_q(remote_link)} {_q(remote_active)}")
    _verify_absent(serial, remote_link, root=False)
    _verify_absent(serial, remote_active, root=False)


def run_managed_certification(
    serial: str,
    paths: dict[str, str],
    payloads: dict[str, Any],
) -> None:
    scratch = paths["scratch"]
    managed = paths["managed"]
    remote_original = f"{scratch}/original.bin"
    remote_replacement = f"{scratch}/replacement.bin"
    managed_active = f"{managed}/active.bin"
    managed_next = f"{managed}/active.next"
    managed_link = f"{managed}/active.link"

    shell(
        serial,
        f"mkdir -p {_q(paths['managed_base'])} && chmod 700 {_q(paths['managed_base'])} && mkdir {_q(managed)} && chmod 700 {_q(managed)}",
        root=True,
    )
    shell(serial, f"cp {_q(remote_original)} {_q(managed_active)} && chmod 600 {_q(managed_active)}", root=True)
    _verify_remote_digest(serial, managed_active, payloads["original_sha256"], root=True)

    shell(serial, f"cp {_q(remote_replacement)} {_q(managed_next)} && chmod 600 {_q(managed_next)} && mv -f {_q(managed_next)} {_q(managed_active)}", root=True)
    _verify_remote_digest(serial, managed_active, payloads["replacement_sha256"], root=True)

    shell(serial, f"ln -s active.bin {_q(managed_link)}", root=True)
    link_target = shell(serial, f"readlink {_q(managed_link)}", root=True)
    require(link_target == "active.bin", "managed symlink target differs")
    _verify_remote_digest(serial, managed_link, payloads["replacement_sha256"], root=True)

    shell(serial, f"rm -f {_q(managed_link)} {_q(managed_active)}", root=True)
    _verify_absent(serial, managed_link, root=True)
    _verify_absent(serial, managed_active, root=True)


def cleanup_paths(serial: str, paths: dict[str, str]) -> bool:
    try:
        shell(
            serial,
            f"rm -rf {_q(paths['managed'])}; rmdir {_q(paths['managed_base'])} 2>/dev/null || true",
            root=True,
        )
        shell(
            serial,
            f"rm -rf {_q(paths['scratch'])}; rmdir {_q(paths['scratch_base'])} 2>/dev/null || true",
        )
        _verify_absent(serial, paths["managed"], root=True)
        _verify_absent(serial, paths["scratch"], root=False)
        return True
    except CertificationFailure:
        return False


def certify(canonical_sha: str, transaction_id: str) -> dict[str, Any]:
    canonical_sha = _PREFLIGHT.require_canonical_sha(canonical_sha)
    transaction_id = require_transaction_id(transaction_id)
    paths = transaction_paths(transaction_id)
    serial = _PREFLIGHT.require_expected_serial()
    _PREFLIGHT.require_tools()

    capabilities: dict[str, str] = {}
    mutation_started = False
    cleanup_verified = False
    failure_stage: str | None = None
    failure_message: str | None = None

    try:
        _PREFLIGHT.prove_registered_device(serial)
        inventory = _CAPABILITIES.inventory(canonical_sha)
        capabilities = dict(inventory.get("capabilities", {}))
        require(
            inventory.get("read_only_capabilities_proven") is True,
            "read-only capability prerequisite is not proven",
        )
        verify_prestate(serial, paths)

        # Same-job boundary reproof: this is intentionally immediately before the
        # first write and is independent from the earlier access/capability probes.
        _PREFLIGHT.prove_registered_device(serial)

        with tempfile.TemporaryDirectory(prefix="mobile-proxy-fs-cert-") as temp:
            local_root = Path(temp)
            payloads = _prepare_payloads(local_root, canonical_sha, transaction_id)

            failure_stage = "scratch_roundtrip"
            mutation_started = True
            run_scratch_certification(serial, paths, payloads, local_root)

            failure_stage = "managed_root_write"
            run_managed_certification(serial, paths, payloads)

            failure_stage = "cleanup_verify"
            cleanup_verified = cleanup_paths(serial, paths)
            require(cleanup_verified, "certification namespace cleanup could not be proven")

        for name in (
            "adb_push_pull_roundtrip",
            "managed_root_write",
            "managed_atomic_replace",
        ):
            capabilities[name] = SUPPORTED

        return {
            "format_version": 1,
            "repository": "iamaman11/mobile-proxy",
            "canonical_sha": canonical_sha,
            "operation_id": _OPERATION_ID,
            "transaction_id": transaction_id,
            "state": "ACCEPTED",
            "failure_stage": None,
            "capabilities": capabilities,
            "filesystem_mutation_capabilities_proven": True,
            "cleanup_verified": True,
            "mutation_scope": {
                "scratch_base": str(_SCRATCH_BASE),
                "managed_base": str(_MANAGED_BASE),
                "transaction_scoped": True,
            },
            "raw_device_identifier_recorded": False,
            "phone_mutation_performed": True,
            "accepted": True,
        }
    except (_PREFLIGHT.PreflightFailure, CertificationFailure) as error:
        failure_message = str(error)
        if mutation_started:
            cleanup_verified = cleanup_paths(serial, paths)
            state = "RECOVERED" if cleanup_verified else "QUARANTINED"
        else:
            state = "REFUSED"
            cleanup_verified = True
        for name in (
            "adb_push_pull_roundtrip",
            "managed_root_write",
            "managed_atomic_replace",
        ):
            capabilities.setdefault(name, UNKNOWN)
        return {
            "format_version": 1,
            "repository": "iamaman11/mobile-proxy",
            "canonical_sha": canonical_sha,
            "operation_id": _OPERATION_ID,
            "transaction_id": transaction_id,
            "state": state,
            "failure_stage": failure_stage or "precondition",
            "failure": failure_message,
            "capabilities": capabilities,
            "filesystem_mutation_capabilities_proven": False,
            "cleanup_verified": cleanup_verified,
            "mutation_scope": {
                "scratch_base": str(_SCRATCH_BASE),
                "managed_base": str(_MANAGED_BASE),
                "transaction_scoped": True,
            },
            "raw_device_identifier_recorded": False,
            "phone_mutation_performed": mutation_started,
            "accepted": False,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-sha", required=True)
    parser.add_argument("--transaction-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = certify(args.canonical_sha, args.transaction_id)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, CertificationFailure, _PREFLIGHT.PreflightFailure) as error:
        print(f"android filesystem certification failed before report: {error}", file=sys.stderr)
        return 2
    if not report.get("accepted"):
        print(
            f"android filesystem certification not accepted: state={report.get('state')} stage={report.get('failure_stage')}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
