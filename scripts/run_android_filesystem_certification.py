#!/usr/bin/env python3
"""Certify bounded Android filesystem mutation semantics on the registered phone."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Callable


SUPPORTED = "SUPPORTED"
UNSUPPORTED = "UNSUPPORTED"
UNKNOWN = "UNKNOWN"
_OPERATION_ID = "android.filesystem-certification.v1"
_TRANSACTION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_SCRATCH_BASE = PurePosixPath("/data/local/tmp/mobile-proxy-adapter-test")
_MANAGED_ROOT = PurePosixPath("/data/adb/mobile-proxy-node")
_MANAGED_BASE = _MANAGED_ROOT / ".adapter-test"

_SCRIPT_DIR = Path(__file__).resolve().parent
StepMarker = Callable[[str], None]


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
_TOOLING = _load_module(
    "run_android_filesystem_tooling_diagnostic",
    "run_android_filesystem_tooling_diagnostic.py",
)


class CertificationFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CertificationFailure(message)


def _mark(mark_step: StepMarker | None, substep: str) -> None:
    if mark_step is not None:
        mark_step(substep)


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


def _verify_remote_exact(
    serial: str,
    actual: str,
    expected: str,
    *,
    root: bool,
    comparator: str,
) -> None:
    try:
        command = _TOOLING.render_comparator_command(comparator, actual, expected)
    except _TOOLING.ToolingDiagnosticFailure as error:
        raise CertificationFailure(str(error)) from error
    shell(serial, f"set -eu; {command}", root=root)


def _pull_and_verify_exact(
    serial: str,
    remote_path: str,
    expected: bytes,
    local_root: Path,
    label: str,
) -> None:
    pulled = local_root / f"pulled-{label}.bin"
    adb(serial, "pull", remote_path, str(pulled))
    require(pulled.read_bytes() == expected, f"ADB pull exact-byte comparison differs: {label}")


def _verify_absent(serial: str, path: str, *, root: bool) -> None:
    shell(serial, f"test ! -e {_q(path)} && test ! -L {_q(path)}", root=root)


def _prepare_payloads(root: Path, canonical_sha: str, transaction_id: str) -> dict[str, Any]:
    original = (
        f"mobile-proxy-filesystem-certification\n{canonical_sha}\n{transaction_id}\noriginal\n"
    ).encode()
    replacement = (
        f"mobile-proxy-filesystem-certification\n{canonical_sha}\n{transaction_id}\nreplacement\n"
    ).encode()
    original_path = root / "original.bin"
    replacement_path = root / "replacement.bin"
    original_path.write_bytes(original)
    replacement_path.write_bytes(replacement)
    return {
        "original_path": original_path,
        "replacement_path": replacement_path,
        "original_bytes": original,
        "replacement_bytes": replacement,
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
    *,
    comparator: str,
    mark_step: StepMarker | None = None,
) -> None:
    scratch = paths["scratch"]
    _mark(mark_step, "scratch.mkdir")
    shell(serial, f"mkdir -p {_q(paths['scratch_base'])} && mkdir {_q(scratch)}")

    remote_original = f"{scratch}/original.bin"
    remote_replacement = f"{scratch}/replacement.bin"
    remote_active = f"{scratch}/active.bin"
    remote_next = f"{scratch}/active.next"
    remote_link = f"{scratch}/active.link"

    _mark(mark_step, "scratch.push_original")
    adb(serial, "push", str(payloads["original_path"]), remote_original)
    _mark(mark_step, "scratch.push_replacement")
    adb(serial, "push", str(payloads["replacement_path"]), remote_replacement)
    _mark(mark_step, "scratch.pull_original")
    _pull_and_verify_exact(
        serial,
        remote_original,
        payloads["original_bytes"],
        local_root,
        "original",
    )
    _mark(mark_step, "scratch.pull_replacement")
    _pull_and_verify_exact(
        serial,
        remote_replacement,
        payloads["replacement_bytes"],
        local_root,
        "replacement",
    )

    _mark(mark_step, "scratch.copy_original")
    shell(serial, f"cp {_q(remote_original)} {_q(remote_active)}")
    _mark(mark_step, "scratch.compare_original_remote")
    _verify_remote_exact(
        serial,
        remote_active,
        remote_original,
        root=False,
        comparator=comparator,
    )
    _mark(mark_step, "scratch.pull_active_original")
    _pull_and_verify_exact(
        serial,
        remote_active,
        payloads["original_bytes"],
        local_root,
        "active-original",
    )

    _mark(mark_step, "scratch.atomic_replace")
    shell(
        serial,
        f"cp {_q(remote_replacement)} {_q(remote_next)} && mv -f {_q(remote_next)} {_q(remote_active)}",
    )
    _mark(mark_step, "scratch.compare_replacement_remote")
    _verify_remote_exact(
        serial,
        remote_active,
        remote_replacement,
        root=False,
        comparator=comparator,
    )
    _mark(mark_step, "scratch.pull_active_replacement")
    _pull_and_verify_exact(
        serial,
        remote_active,
        payloads["replacement_bytes"],
        local_root,
        "active-replacement",
    )

    _mark(mark_step, "scratch.symlink_create")
    shell(serial, f"ln -s active.bin {_q(remote_link)}")
    _mark(mark_step, "scratch.symlink_read")
    link_target = shell(serial, f"readlink {_q(remote_link)}")
    _mark(mark_step, "scratch.symlink_target")
    require(link_target == "active.bin", "scratch symlink target differs")
    _mark(mark_step, "scratch.symlink_compare")
    _verify_remote_exact(
        serial,
        remote_link,
        remote_replacement,
        root=False,
        comparator=comparator,
    )

    _mark(mark_step, "scratch.remove_active")
    shell(serial, f"rm -f {_q(remote_link)} {_q(remote_active)}")
    _mark(mark_step, "scratch.verify_link_absent")
    _verify_absent(serial, remote_link, root=False)
    _mark(mark_step, "scratch.verify_active_absent")
    _verify_absent(serial, remote_active, root=False)


def run_managed_certification(
    serial: str,
    paths: dict[str, str],
    payloads: dict[str, Any],
    *,
    comparator: str,
    mark_step: StepMarker | None = None,
) -> None:
    scratch = paths["scratch"]
    managed = paths["managed"]
    remote_original = f"{scratch}/original.bin"
    remote_replacement = f"{scratch}/replacement.bin"
    managed_active = f"{managed}/active.bin"
    managed_next = f"{managed}/active.next"
    managed_link = f"{managed}/active.link"

    _mark(mark_step, "managed.mkdir")
    shell(
        serial,
        (
            f"mkdir -p {_q(paths['managed_base'])} && "
            f"chmod 700 {_q(paths['managed_base'])} && "
            f"mkdir {_q(managed)} && chmod 700 {_q(managed)}"
        ),
        root=True,
    )
    _mark(mark_step, "managed.copy_original")
    shell(
        serial,
        f"cp {_q(remote_original)} {_q(managed_active)} && chmod 600 {_q(managed_active)}",
        root=True,
    )
    _mark(mark_step, "managed.compare_original_remote")
    _verify_remote_exact(
        serial,
        managed_active,
        remote_original,
        root=True,
        comparator=comparator,
    )

    _mark(mark_step, "managed.atomic_replace")
    shell(
        serial,
        (
            f"cp {_q(remote_replacement)} {_q(managed_next)} && "
            f"chmod 600 {_q(managed_next)} && "
            f"mv -f {_q(managed_next)} {_q(managed_active)}"
        ),
        root=True,
    )
    _mark(mark_step, "managed.compare_replacement_remote")
    _verify_remote_exact(
        serial,
        managed_active,
        remote_replacement,
        root=True,
        comparator=comparator,
    )

    _mark(mark_step, "managed.symlink_create")
    shell(serial, f"ln -s active.bin {_q(managed_link)}", root=True)
    _mark(mark_step, "managed.symlink_read")
    link_target = shell(serial, f"readlink {_q(managed_link)}", root=True)
    _mark(mark_step, "managed.symlink_target")
    require(link_target == "active.bin", "managed symlink target differs")
    _mark(mark_step, "managed.symlink_compare")
    _verify_remote_exact(
        serial,
        managed_link,
        remote_replacement,
        root=True,
        comparator=comparator,
    )

    _mark(mark_step, "managed.remove_active")
    shell(serial, f"rm -f {_q(managed_link)} {_q(managed_active)}", root=True)
    _mark(mark_step, "managed.verify_link_absent")
    _verify_absent(serial, managed_link, root=True)
    _mark(mark_step, "managed.verify_active_absent")
    _verify_absent(serial, managed_active, root=True)


def cleanup_paths(
    serial: str,
    paths: dict[str, str],
    *,
    mark_step: StepMarker | None = None,
) -> bool:
    try:
        _mark(mark_step, "cleanup.managed_remove")
        shell(
            serial,
            f"rm -rf {_q(paths['managed'])}; rmdir {_q(paths['managed_base'])} 2>/dev/null || true",
            root=True,
        )
        _mark(mark_step, "cleanup.scratch_remove")
        shell(
            serial,
            f"rm -rf {_q(paths['scratch'])}; rmdir {_q(paths['scratch_base'])} 2>/dev/null || true",
        )
        _mark(mark_step, "cleanup.managed_verify_absent")
        _verify_absent(serial, paths["managed"], root=True)
        _mark(mark_step, "cleanup.scratch_verify_absent")
        _verify_absent(serial, paths["scratch"], root=False)
        return True
    except CertificationFailure:
        return False


def _comparator_report(
    scratch_selected: str,
    scratch_state: str,
    managed_selected: str,
    managed_state: str,
) -> dict[str, str]:
    return {
        "source": "android.filesystem-tooling-compatibility.v1",
        "scratch_selected_comparator": scratch_selected,
        "scratch_comparator_path_state": scratch_state,
        "managed_selected_comparator": managed_selected,
        "managed_comparator_path_state": managed_state,
    }


def certify(canonical_sha: str, transaction_id: str) -> dict[str, Any]:
    canonical_sha = _PREFLIGHT.require_canonical_sha(canonical_sha)
    transaction_id = require_transaction_id(transaction_id)
    paths = transaction_paths(transaction_id)
    serial = _PREFLIGHT.require_expected_serial()
    _PREFLIGHT.require_tools()

    capabilities: dict[str, str] = {}
    mutation_started = False
    cleanup_attempted = False
    cleanup_verified = False
    failure_stage: str | None = None
    failure_message: str | None = None
    current_substep: str | None = None
    current_cleanup_substep: str | None = None
    scratch_selected = "UNKNOWN"
    scratch_state = UNKNOWN
    managed_selected = "UNKNOWN"
    managed_state = UNKNOWN

    def mark_substep(substep: str) -> None:
        nonlocal current_substep
        current_substep = substep

    def mark_cleanup_substep(substep: str) -> None:
        nonlocal current_cleanup_substep
        current_cleanup_substep = substep

    try:
        failure_stage = "registered_device"
        _PREFLIGHT.prove_registered_device(serial)

        failure_stage = "capability_inventory"
        inventory = _CAPABILITIES.inventory(canonical_sha)
        capabilities = dict(inventory.get("capabilities", {}))
        require(
            inventory.get("read_only_capabilities_proven") is True,
            "read-only capability prerequisite is not proven",
        )

        failure_stage = "comparator_admission"
        scratch_tooling = _TOOLING.probe_scope(serial, root=False)
        managed_tooling = _TOOLING.probe_scope(serial, root=True)
        scratch_selected = str(scratch_tooling.get("selected_comparator", "UNKNOWN"))
        scratch_state = str(
            scratch_tooling.get("canonical_comparator_path_state", UNKNOWN)
        )
        managed_selected = str(managed_tooling.get("selected_comparator", "UNKNOWN"))
        managed_state = str(
            managed_tooling.get("canonical_comparator_path_state", UNKNOWN)
        )
        require(
            scratch_tooling.get("probe_complete") is True
            and scratch_state == SUPPORTED,
            f"scratch comparator compatibility is not proven: {scratch_state}",
        )
        require(
            managed_tooling.get("probe_complete") is True
            and managed_state == SUPPORTED,
            f"managed comparator compatibility is not proven: {managed_state}",
        )

        failure_stage = "prestate"
        verify_prestate(serial, paths)

        # Same-job boundary reproof: this is intentionally immediately before the
        # first write and is independent from the earlier access/capability probes.
        failure_stage = "mutation_boundary_reproof"
        _PREFLIGHT.prove_registered_device(serial)

        with tempfile.TemporaryDirectory(prefix="mobile-proxy-fs-cert-") as temp:
            local_root = Path(temp)
            payloads = _prepare_payloads(local_root, canonical_sha, transaction_id)

            failure_stage = "scratch_roundtrip"
            current_substep = "scratch.enter"
            mutation_started = True
            run_scratch_certification(
                serial,
                paths,
                payloads,
                local_root,
                comparator=scratch_selected,
                mark_step=mark_substep,
            )

            failure_stage = "managed_root_write"
            current_substep = "managed.enter"
            run_managed_certification(
                serial,
                paths,
                payloads,
                comparator=managed_selected,
                mark_step=mark_substep,
            )

            failure_stage = "cleanup_verify"
            current_substep = "cleanup.verify"
            current_cleanup_substep = "cleanup.enter"
            cleanup_attempted = True
            cleanup_verified = cleanup_paths(
                serial,
                paths,
                mark_step=mark_cleanup_substep,
            )
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
            "failure_substep": None,
            "comparison_contract": "exact-bytes",
            "comparator_contract": _comparator_report(
                scratch_selected,
                scratch_state,
                managed_selected,
                managed_state,
            ),
            "capabilities": capabilities,
            "filesystem_mutation_capabilities_proven": True,
            "cleanup_attempted": True,
            "cleanup_verified": True,
            "cleanup_failure_substep": None,
            "mutation_scope": {
                "scratch_base": str(_SCRATCH_BASE),
                "managed_base": str(_MANAGED_BASE),
                "transaction_scoped": True,
            },
            "raw_device_identifier_recorded": False,
            "phone_mutation_performed": True,
            "accepted": True,
        }
    except (
        _PREFLIGHT.PreflightFailure,
        _TOOLING.ToolingDiagnosticFailure,
        CertificationFailure,
    ) as error:
        failure_message = str(error)
        failure_substep = current_substep if mutation_started else None
        cleanup_failure_substep: str | None = None
        if mutation_started:
            cleanup_attempted = True
            current_cleanup_substep = "cleanup.enter"
            cleanup_verified = cleanup_paths(
                serial,
                paths,
                mark_step=mark_cleanup_substep,
            )
            if not cleanup_verified:
                cleanup_failure_substep = current_cleanup_substep
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
            "failure_substep": failure_substep,
            "failure": failure_message,
            "comparison_contract": "exact-bytes",
            "comparator_contract": _comparator_report(
                scratch_selected,
                scratch_state,
                managed_selected,
                managed_state,
            ),
            "capabilities": capabilities,
            "filesystem_mutation_capabilities_proven": False,
            "cleanup_attempted": cleanup_attempted,
            "cleanup_verified": cleanup_verified,
            "cleanup_failure_substep": cleanup_failure_substep,
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
            "android filesystem certification not accepted: "
            f"state={report.get('state')} "
            f"stage={report.get('failure_stage')} "
            f"substep={report.get('failure_substep')}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
