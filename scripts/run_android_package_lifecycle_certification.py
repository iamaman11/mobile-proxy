#!/usr/bin/env python3
"""Certify install/uninstall/reinstall semantics for the exact signed Android candidate."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


_OPERATION_ID = "android.package-lifecycle-certification.v1"
_SCRIPT_DIR = Path(__file__).resolve().parent


def _load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPT_DIR / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load canonical module: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_CLEAN = _load_module("clean_install_android_production", "clean_install_android_production.py")
_CAPABILITIES = _load_module("run_android_capability_inventory", "run_android_capability_inventory.py")
_PACKAGE = "com.example.mobileproxy"


class PackageCertificationFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PackageCertificationFailure(message)


def _uninstall_and_verify_absent(serial: str) -> None:
    if not _CLEAN.package_present(serial):
        return
    result = _CLEAN.adb(serial, "uninstall", _PACKAGE, timeout=120)
    require("Success" in result.stdout, "Android package uninstall did not report success")
    require(not _CLEAN.package_present(serial), "Android package remained installed after uninstall")


def _install_candidate(serial: str, apk: Path) -> None:
    result = _CLEAN.adb(serial, "install", str(apk), timeout=180)
    require("Success" in result.stdout, "Android package install did not report success")
    require(_CLEAN.package_present(serial), "Android package is absent after install")


def _verify_candidate_installed(
    serial: str,
    *,
    expected_digest: str,
    digest_tool: Path,
    expected_version_name: str,
    expected_version_code: int,
) -> None:
    require(_CLEAN.package_present(serial), "exact Android candidate is not installed")
    installed_code, installed_name = _CLEAN.package_version(serial)
    require(
        (installed_code, installed_name) == (expected_version_code, expected_version_name),
        "installed Android package version differs from exact candidate",
    )
    _CLEAN.verify_installed_apk_digest(serial, expected_digest, digest_tool)


def _install_and_verify_candidate(
    serial: str,
    *,
    apk: Path,
    expected_digest: str,
    digest_tool: Path,
    expected_version_name: str,
    expected_version_code: int,
) -> None:
    _install_candidate(serial, apk)
    _verify_candidate_installed(
        serial,
        expected_digest=expected_digest,
        digest_tool=digest_tool,
        expected_version_name=expected_version_name,
        expected_version_code=expected_version_code,
    )


def _recover_to_candidate_or_absent(
    serial: str,
    *,
    apk: Path,
    expected_digest: str,
    digest_tool: Path,
    expected_version_name: str,
    expected_version_code: int,
) -> tuple[bool, str]:
    """Prefer a fully verified candidate; otherwise prove a clean absent package baseline."""

    try:
        _CLEAN.prove_registered_device(serial)
        if _CLEAN.package_present(serial):
            try:
                _verify_candidate_installed(
                    serial,
                    expected_digest=expected_digest,
                    digest_tool=digest_tool,
                    expected_version_name=expected_version_name,
                    expected_version_code=expected_version_code,
                )
                return True, "candidate_installed"
            except (_CLEAN.CleanInstallFailure, PackageCertificationFailure):
                _CLEAN.prove_registered_device(serial)
                _uninstall_and_verify_absent(serial)

        _CLEAN.prove_registered_device(serial)
        _install_and_verify_candidate(
            serial,
            apk=apk,
            expected_digest=expected_digest,
            digest_tool=digest_tool,
            expected_version_name=expected_version_name,
            expected_version_code=expected_version_code,
        )
        return True, "candidate_installed"
    except (_CLEAN.CleanInstallFailure, _CLEAN.PreflightFailure, PackageCertificationFailure):
        pass

    try:
        _CLEAN.prove_registered_device(serial)
        _uninstall_and_verify_absent(serial)
        require(not _CLEAN.package_present(serial), "recovery package absence is not proven")
        return True, "package_absent"
    except (_CLEAN.CleanInstallFailure, _CLEAN.PreflightFailure, PackageCertificationFailure):
        return False, "unproven"


def certify(
    *,
    canonical_sha: str,
    apk: Path,
    release_evidence: Path,
    digest_tool: Path,
    expected_version_name: str,
    expected_version_code: int,
) -> dict[str, Any]:
    canonical_sha = _CLEAN.require_canonical_sha(canonical_sha)
    serial = _CLEAN.require_expected_serial()

    mutation_started = False
    failure_stage = "precondition"
    old_package_observed = False
    expected_digest = ""

    try:
        evidence = _CLEAN.load_json(release_evidence)
        expected_digest = _CLEAN.verify_release_evidence(
            evidence,
            canonical_sha,
            apk,
            digest_tool,
            expected_version_name,
            expected_version_code,
        )

        _CLEAN.prove_registered_device(serial)
        inventory = _CAPABILITIES.inventory(canonical_sha)
        require(
            inventory.get("read_only_capabilities_proven") is True,
            "read-only capability prerequisite is not proven",
        )
        old_package_observed = _CLEAN.package_present(serial)

        failure_stage = "prepare_absent_baseline"
        _CLEAN.prove_registered_device(serial)
        mutation_started = True
        _uninstall_and_verify_absent(serial)
        require(not _CLEAN.package_present(serial), "initial package absence is not proven")

        failure_stage = "install_candidate_first"
        _CLEAN.prove_registered_device(serial)
        _install_and_verify_candidate(
            serial,
            apk=apk,
            expected_digest=expected_digest,
            digest_tool=digest_tool,
            expected_version_name=expected_version_name,
            expected_version_code=expected_version_code,
        )

        failure_stage = "uninstall_candidate"
        _CLEAN.prove_registered_device(serial)
        _uninstall_and_verify_absent(serial)
        require(not _CLEAN.package_present(serial), "candidate remained installed after lifecycle uninstall")

        failure_stage = "reinstall_candidate"
        _CLEAN.prove_registered_device(serial)
        _install_and_verify_candidate(
            serial,
            apk=apk,
            expected_digest=expected_digest,
            digest_tool=digest_tool,
            expected_version_name=expected_version_name,
            expected_version_code=expected_version_code,
        )

        return {
            "format_version": 1,
            "repository": "iamaman11/mobile-proxy",
            "canonical_sha": canonical_sha,
            "operation_id": _OPERATION_ID,
            "application_id": _PACKAGE,
            "expected_version_name": expected_version_name,
            "expected_version_code": expected_version_code,
            "state": "ACCEPTED",
            "failure_stage": None,
            "old_package_observed": old_package_observed,
            "initial_absence_verified": True,
            "first_install_verified": True,
            "candidate_uninstall_verified": True,
            "reinstall_verified": True,
            "package_install_uninstall_proven": True,
            "recovery_baseline": None,
            "raw_device_identifier_recorded": False,
            "runtime_lifecycle_mutation_performed": False,
            "phone_reboot_performed": False,
            "phone_mutation_performed": True,
            "accepted": True,
        }
    except (
        _CLEAN.CleanInstallFailure,
        _CLEAN.PreflightFailure,
        PackageCertificationFailure,
        OSError,
    ) as error:
        if mutation_started and expected_digest:
            recovered, baseline = _recover_to_candidate_or_absent(
                serial,
                apk=apk,
                expected_digest=expected_digest,
                digest_tool=digest_tool,
                expected_version_name=expected_version_name,
                expected_version_code=expected_version_code,
            )
            state = "RECOVERED" if recovered else "QUARANTINED"
        else:
            recovered = True
            baseline = "unchanged"
            state = "REFUSED"
        return {
            "format_version": 1,
            "repository": "iamaman11/mobile-proxy",
            "canonical_sha": canonical_sha,
            "operation_id": _OPERATION_ID,
            "application_id": _PACKAGE,
            "expected_version_name": expected_version_name,
            "expected_version_code": expected_version_code,
            "state": state,
            "failure_stage": failure_stage,
            "failure": str(error),
            "old_package_observed": old_package_observed,
            "package_install_uninstall_proven": False,
            "recovery_verified": recovered,
            "recovery_baseline": baseline,
            "raw_device_identifier_recorded": False,
            "runtime_lifecycle_mutation_performed": False,
            "phone_reboot_performed": False,
            "phone_mutation_performed": mutation_started,
            "accepted": False,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-sha", required=True)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--release-evidence", type=Path, required=True)
    parser.add_argument("--digest-tool", type=Path, required=True)
    parser.add_argument("--expected-version-name", required=True)
    parser.add_argument("--expected-version-code", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = certify(
            canonical_sha=args.canonical_sha,
            apk=args.apk,
            release_evidence=args.release_evidence,
            digest_tool=args.digest_tool,
            expected_version_name=args.expected_version_name,
            expected_version_code=args.expected_version_code,
        )
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Android package lifecycle certification failed before report: {error}", file=sys.stderr)
        return 2
    if not report.get("accepted"):
        print(
            f"Android package lifecycle certification not accepted: state={report.get('state')} stage={report.get('failure_stage')}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
