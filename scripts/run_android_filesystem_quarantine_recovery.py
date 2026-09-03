#!/usr/bin/env python3
"""Observe and recover exact filesystem-certification quarantine transactions."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


ABSENT = "ABSENT"
DIRECTORY = "DIRECTORY"
SYMLINK = "SYMLINK"
OTHER = "OTHER"
UNKNOWN = "UNKNOWN"
SUPPORTED = "SUPPORTED"
UNSUPPORTED = "UNSUPPORTED"

_OBSERVE_OPERATION_ID = "android.filesystem-quarantine-observation.v1"
_CLEANUP_OPERATION_ID = "android.filesystem-quarantine-cleanup.v1"
_QUARANTINE_OBSERVER = "android.filesystem-quarantine-observer.v2"
_TARGET = "android-production"

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
_CERT = _load_module(
    "run_android_filesystem_certification",
    "run_android_filesystem_certification.py",
)


class QuarantineRecoveryFailure(RuntimeError):
    pass


def _require_transaction_ids(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        try:
            transaction_id = _CERT.require_transaction_id(value)
            _CERT.transaction_paths(transaction_id)
        except _CERT.CertificationFailure as error:
            raise QuarantineRecoveryFailure(str(error)) from error
        if transaction_id in seen:
            raise QuarantineRecoveryFailure("duplicate transaction ID")
        seen.add(transaction_id)
        result.append(transaction_id)
    if not result:
        raise QuarantineRecoveryFailure("at least one transaction ID is required")
    return tuple(result)


def _transaction_set_identity(transaction_ids: Iterable[str]) -> str:
    encoded = "\n".join(sorted(transaction_ids)).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def build_quarantine_fact_envelopes(
    canonical_sha: str,
    transaction_ids: Iterable[str],
    report: dict[str, Any],
    *,
    target_binding_id: str,
    filesystem_generation: str,
    observation_ref: str,
) -> list[dict[str, Any]]:
    """Build reusable filesystem facts from one complete bounded observation.

    The exact transaction set is represented by an opaque digest dependency so a
    fact for one quarantine set cannot accidentally satisfy a different set. The
    producer does not claim persistence; the outer durable CONTROL adapter owns
    that transition.
    """

    canonical_sha = _PREFLIGHT.require_canonical_sha(canonical_sha)
    transaction_ids = _require_transaction_ids(transaction_ids)
    target_binding_id = _PREFLIGHT.require_opaque_identity(
        target_binding_id, "target binding identity"
    )
    filesystem_generation = _PREFLIGHT.require_opaque_identity(
        filesystem_generation, "filesystem generation"
    )
    observation_ref = _PREFLIGHT.require_opaque_identity(
        observation_ref, "observation reference"
    )

    if not report.get("observation_complete"):
        return []

    transactions = report.get("transactions")
    if not isinstance(transactions, list):
        raise QuarantineRecoveryFailure("observation transactions are invalid")
    observed_ids = tuple(
        str(item.get("transaction_id", ""))
        for item in transactions
        if isinstance(item, dict)
    )
    if tuple(transaction_ids) != observed_ids:
        raise QuarantineRecoveryFailure("observation transaction set differs")

    all_absent = all(
        item["scratch"]["node_state"] == ABSENT
        and item["managed_root"]["node_state"] == ABSENT
        for item in transactions
    )
    dependencies = [
        {"scope": f"target/{_TARGET}", "identity": target_binding_id},
        {"scope": "observer/filesystem-quarantine", "identity": _QUARANTINE_OBSERVER},
        {"scope": "domain/filesystem", "identity": filesystem_generation},
        {
            "scope": "transaction/quarantine-set",
            "identity": _transaction_set_identity(transaction_ids),
        },
    ]

    common = {
        "target": _TARGET,
        "observation_ref": observation_ref,
        "source_ref": canonical_sha,
        "dependencies": dependencies,
        "authority": "CONTROL",
        "persisted": False,
    }
    return [
        {
            "subject": "filesystem-quarantine",
            "predicate": "transactions_absent",
            "value": all_absent,
            **common,
        },
        {
            "subject": "filesystem-quarantine",
            "predicate": "cleanup_admissible",
            "value": report.get("cleanup_admissible") is True,
            **common,
        },
    ]


def _remote_status(
    serial: str,
    command: str,
    *,
    root: bool,
    timeout: int = 15,
) -> int | None:
    prefix = ["adb", "-s", serial, "shell"]
    if root:
        prefix += ["su", "0", "sh", "-c", command]
    else:
        prefix += ["sh", "-c", command]
    try:
        result = subprocess.run(
            prefix,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.returncode


def _node_state(serial: str, path: str, *, root: bool) -> str:
    quoted = _CERT._q(path)
    status = _remote_status(
        serial,
        (
            f"p={quoted}; "
            'if [ -L "$p" ]; then exit 12; '
            'elif [ -d "$p" ]; then exit 11; '
            'elif [ -e "$p" ]; then exit 13; '
            "else exit 10; fi"
        ),
        root=root,
    )
    return {10: ABSENT, 11: DIRECTORY, 12: SYMLINK, 13: OTHER}.get(status, UNKNOWN)


def _access_state(serial: str, path: str, expression: str, *, root: bool) -> str:
    quoted = _CERT._q(path)
    status = _remote_status(
        serial,
        f'p={quoted}; if test {expression} "$p"; then exit 20; else exit 21; fi',
        root=root,
    )
    if status == 20:
        return SUPPORTED
    if status == 21:
        return UNSUPPORTED
    return UNKNOWN


def _scope_observation(serial: str, base: str, *, root: bool) -> dict[str, str]:
    node = _node_state(serial, base, root=root)
    if node == DIRECTORY:
        writable = _access_state(serial, base, "-w", root=root)
        executable = _access_state(serial, base, "-x", root=root)
    elif node == ABSENT:
        writable = UNSUPPORTED
        executable = UNSUPPORTED
    else:
        writable = UNKNOWN
        executable = UNKNOWN
    return {"node_state": node, "writable": writable, "executable": executable}


def _transaction_observation(serial: str, transaction_id: str) -> dict[str, Any]:
    paths = _CERT.transaction_paths(transaction_id)
    return {
        "transaction_id": transaction_id,
        "scratch": {"node_state": _node_state(serial, paths["scratch"], root=False)},
        "managed_root": {"node_state": _node_state(serial, paths["managed"], root=True)},
    }


def _observation_complete(report: dict[str, Any]) -> bool:
    base_states = (
        report["scratch_base"]["node_state"],
        report["scratch_base"]["writable"],
        report["scratch_base"]["executable"],
        report["managed_base"]["node_state"],
        report["managed_base"]["writable"],
        report["managed_base"]["executable"],
    )
    if UNKNOWN in base_states:
        return False
    for transaction in report["transactions"]:
        if transaction["scratch"]["node_state"] == UNKNOWN:
            return False
        if transaction["managed_root"]["node_state"] == UNKNOWN:
            return False
    return True


def _scope_cleanup_admissible(
    base: dict[str, str], transaction_states: Iterable[str]
) -> bool:
    states = tuple(transaction_states)
    if any(state not in {ABSENT, DIRECTORY} for state in states):
        return False
    if base["node_state"] == ABSENT:
        return all(state == ABSENT for state in states)
    if base["node_state"] != DIRECTORY:
        return False
    if any(state == DIRECTORY for state in states):
        return base["writable"] == SUPPORTED and base["executable"] == SUPPORTED
    return True


def _cleanup_admissible(report: dict[str, Any]) -> bool:
    if not _observation_complete(report):
        return False
    return _scope_cleanup_admissible(
        report["scratch_base"],
        (transaction["scratch"]["node_state"] for transaction in report["transactions"]),
    ) and _scope_cleanup_admissible(
        report["managed_base"],
        (
            transaction["managed_root"]["node_state"]
            for transaction in report["transactions"]
        ),
    )


def observe(
    canonical_sha: str,
    transaction_ids: Iterable[str],
    *,
    target_binding_id: str | None = None,
    filesystem_generation: str | None = None,
    observation_ref: str | None = None,
) -> dict[str, Any]:
    canonical_sha = _PREFLIGHT.require_canonical_sha(canonical_sha)
    transaction_ids = _require_transaction_ids(transaction_ids)
    serial = _PREFLIGHT.require_expected_serial()
    _PREFLIGHT.require_tools()
    _PREFLIGHT.prove_registered_device(serial)

    context = (target_binding_id, filesystem_generation, observation_ref)
    if any(value is not None for value in context) and not all(
        value is not None for value in context
    ):
        raise QuarantineRecoveryFailure(
            "causal fact context must provide target binding, filesystem generation and observation reference together"
        )

    first_paths = _CERT.transaction_paths(transaction_ids[0])
    report: dict[str, Any] = {
        "format_version": 1,
        "repository": "iamaman11/mobile-proxy",
        "canonical_sha": canonical_sha,
        "operation_id": _OBSERVE_OPERATION_ID,
        "mode": "read_only_quarantine_observation",
        "scratch_base": _scope_observation(serial, first_paths["scratch_base"], root=False),
        "managed_base": _scope_observation(serial, first_paths["managed_base"], root=True),
        "transactions": [
            _transaction_observation(serial, transaction_id)
            for transaction_id in transaction_ids
        ],
        "observed_facts": [],
        "causal_fact_envelope_emitted": False,
        "raw_directory_contents_recorded": False,
        "raw_command_output_recorded": False,
        "raw_device_identifier_recorded": False,
        "phone_mutation_performed": False,
    }
    report["observation_complete"] = _observation_complete(report)
    report["cleanup_admissible"] = _cleanup_admissible(report)

    if all(value is not None for value in context):
        assert target_binding_id is not None
        assert filesystem_generation is not None
        assert observation_ref is not None
        report["observed_facts"] = build_quarantine_fact_envelopes(
            canonical_sha,
            transaction_ids,
            report,
            target_binding_id=target_binding_id,
            filesystem_generation=filesystem_generation,
            observation_ref=observation_ref,
        )
        report["causal_fact_envelope_emitted"] = bool(report["observed_facts"])

    return report


def _remove_exact(serial: str, path: str, *, root: bool) -> None:
    _CERT.shell(serial, f"rm -rf -- {_CERT._q(path)}", root=root)


def _cleanup_needed(report: dict[str, Any]) -> bool:
    return any(
        transaction[scope]["node_state"] == DIRECTORY
        for transaction in report["transactions"]
        for scope in ("scratch", "managed_root")
    )


def cleanup(canonical_sha: str, transaction_ids: Iterable[str]) -> dict[str, Any]:
    canonical_sha = _PREFLIGHT.require_canonical_sha(canonical_sha)
    transaction_ids = _require_transaction_ids(transaction_ids)
    serial = _PREFLIGHT.require_expected_serial()
    _PREFLIGHT.require_tools()
    _PREFLIGHT.prove_registered_device(serial)

    pre = observe(canonical_sha, transaction_ids)
    base_report = {
        "format_version": 1,
        "repository": "iamaman11/mobile-proxy",
        "canonical_sha": canonical_sha,
        "operation_id": _CLEANUP_OPERATION_ID,
        "mode": "bounded_quarantine_cleanup",
        "transaction_ids": list(transaction_ids),
        "pre_cleanup_observation": pre,
        "cleanup_attempted": False,
        "cleanup_verified": False,
        "phone_mutation_performed": False,
        "package_mutation_performed": False,
        "runtime_lifecycle_mutation_performed": False,
        "provider_access_performed": False,
        "phone_reboot_performed": False,
        "raw_directory_contents_recorded": False,
        "raw_command_output_recorded": False,
        "raw_device_identifier_recorded": False,
    }
    if not pre["cleanup_admissible"]:
        return {
            **base_report,
            "state": "REFUSED",
            "accepted": False,
            "failure_stage": "cleanup_admission",
            "failure_substep": None,
            "post_cleanup_observation": None,
        }

    if not _cleanup_needed(pre):
        return {
            **base_report,
            "state": "ALREADY_CLEAN",
            "accepted": True,
            "cleanup_attempted": False,
            "cleanup_verified": True,
            "phone_mutation_performed": False,
            "failure_stage": None,
            "failure_substep": None,
            "failure": None,
            "post_cleanup_observation": pre,
        }

    _PREFLIGHT.prove_registered_device(serial)

    cleanup_attempted = False
    mutation_performed = False
    failure_substep: str | None = None
    failure_message: str | None = None
    try:
        for transaction in pre["transactions"]:
            transaction_id = transaction["transaction_id"]
            paths = _CERT.transaction_paths(transaction_id)
            if transaction["scratch"]["node_state"] == DIRECTORY:
                failure_substep = f"{transaction_id}.scratch.remove"
                cleanup_attempted = True
                mutation_performed = True
                _remove_exact(serial, paths["scratch"], root=False)
            if transaction["managed_root"]["node_state"] == DIRECTORY:
                failure_substep = f"{transaction_id}.managed.remove"
                cleanup_attempted = True
                mutation_performed = True
                _remove_exact(serial, paths["managed"], root=True)
    except (_CERT.CertificationFailure, _PREFLIGHT.PreflightFailure) as error:
        failure_message = str(error)

    post: dict[str, Any] | None = None
    try:
        post = observe(canonical_sha, transaction_ids)
    except (
        QuarantineRecoveryFailure,
        _CERT.CertificationFailure,
        _PREFLIGHT.PreflightFailure,
    ) as error:
        failure_substep = "post_cleanup_observation"
        failure_message = str(error)

    cleanup_verified = post is not None and all(
        transaction["scratch"]["node_state"] == ABSENT
        and transaction["managed_root"]["node_state"] == ABSENT
        for transaction in post["transactions"]
    )

    if cleanup_verified:
        return {
            **base_report,
            "state": "CLEANED",
            "accepted": True,
            "cleanup_attempted": cleanup_attempted,
            "cleanup_verified": True,
            "phone_mutation_performed": mutation_performed,
            "failure_stage": None,
            "failure_substep": None,
            "failure": None,
            "post_cleanup_observation": post,
        }

    return {
        **base_report,
        "state": "QUARANTINED",
        "accepted": False,
        "cleanup_attempted": cleanup_attempted,
        "cleanup_verified": False,
        "phone_mutation_performed": mutation_performed,
        "failure_stage": "cleanup_execution",
        "failure_substep": failure_substep,
        "failure": failure_message or "post-cleanup absence is not proven",
        "post_cleanup_observation": post,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("observe", "cleanup"), required=True)
    parser.add_argument("--canonical-sha", required=True)
    parser.add_argument("--transaction-id", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-binding-id")
    parser.add_argument("--filesystem-generation")
    parser.add_argument("--observation-ref")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.mode == "observe":
            report = observe(
                args.canonical_sha,
                args.transaction_id,
                target_binding_id=args.target_binding_id,
                filesystem_generation=args.filesystem_generation,
                observation_ref=args.observation_ref,
            )
        else:
            report = cleanup(args.canonical_sha, args.transaction_id)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (
        OSError,
        ValueError,
        QuarantineRecoveryFailure,
        _CERT.CertificationFailure,
        _PREFLIGHT.PreflightFailure,
    ) as error:
        print(f"filesystem quarantine recovery failed before report: {error}", file=sys.stderr)
        return 2
    if args.mode == "cleanup" and not report.get("accepted"):
        print(
            "filesystem quarantine cleanup not accepted: "
            f"state={report.get('state')} stage={report.get('failure_stage')}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
