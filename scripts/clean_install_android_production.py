#!/usr/bin/env python3
"""Install the exact new production APK without preserving a legacy generation.

This primitive deliberately treats the currently installed application as disposable state.
It proves access to the registered production phone, verifies the source-built signed APK,
removes the package if present, installs the exact new APK, and verifies its identity/digest.
Runtime materialization and runtime-health acceptance remain separate orchestration steps.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

try:
    from scripts.run_private_phone_preflight import (
        PreflightFailure,
        prove_registered_device,
        require_canonical_sha,
        require_expected_serial,
    )
    from scripts.verify_android_installed_signer import select_installed_apk_path
except ModuleNotFoundError:
    from run_private_phone_preflight import (  # type: ignore[no-redef]
        PreflightFailure,
        prove_registered_device,
        require_canonical_sha,
        require_expected_serial,
    )
    from verify_android_installed_signer import select_installed_apk_path  # type: ignore[no-redef]

_PACKAGE = "com.example.mobileproxy"
_CONTENT_DIGEST_PATTERN = re.compile(r"^b3:[0-9a-f]{64}$")
_ARTIFACT_DIGEST_DOMAIN = "mobile-proxy/android-apk/v1"
_VERSION_CODE_PATTERN = re.compile(r"^\s*versionCode=([0-9]+)\b", re.MULTILINE)
_VERSION_NAME_PATTERN = re.compile(r"^\s*versionName=([^\s]+)\s*$", re.MULTILINE)


class CleanInstallFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CleanInstallFailure(message)


def run_checked(command: Sequence[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command),
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise CleanInstallFailure("registered-phone clean-install command failed") from error


def adb(serial: str, *arguments: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return run_checked(["adb", "-s", serial, *arguments], timeout=timeout)


def package_present(serial: str) -> bool:
    try:
        result = subprocess.run(
            ["adb", "-s", serial, "shell", "pm", "path", _PACKAGE],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and any(
        line.startswith("package:/") for line in result.stdout.splitlines()
    )


def package_version(serial: str) -> tuple[int, str]:
    result = adb(serial, "shell", "dumpsys", "package", _PACKAGE, timeout=60)
    codes = _VERSION_CODE_PATTERN.findall(result.stdout)
    names = _VERSION_NAME_PATTERN.findall(result.stdout)
    require(len(codes) == 1, "installed package versionCode is ambiguous")
    require(len(names) == 1, "installed package versionName is ambiguous")
    return int(codes[0]), names[0]


def typed_artifact_digest(tool: Path, path: Path) -> str:
    require(tool.is_file() and os.access(tool, os.X_OK), "typed Android artifact digest helper is unavailable")
    digest = run_checked([str(tool), str(path)], timeout=120).stdout.strip()
    require(_CONTENT_DIGEST_PATTERN.fullmatch(digest) is not None, "typed Android artifact digest is invalid")
    return digest


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CleanInstallFailure("Android release evidence is unreadable") from error
    require(isinstance(value, dict), "Android release evidence must be an object")
    return value


def verify_release_evidence(
    evidence: dict[str, Any],
    canonical_sha: str,
    apk: Path,
    digest_tool: Path,
    expected_version_name: str,
    expected_version_code: int,
) -> str:
    expected = {
        "format_version": 1,
        "repository": "iamaman11/mobile-proxy",
        "canonical_sha": canonical_sha,
        "application_id": _PACKAGE,
        "version_name": expected_version_name,
        "version_code": expected_version_code,
        "release_contract_verified": True,
        "keystore_verified": True,
        "apk_signature_verified": True,
        "apk_signer_matches_private_key": True,
        "production_apk_signed": True,
        "phone_access_performed": False,
        "phone_mutation_performed": False,
        "artifact_digest_algorithm": "blake3-256",
        "artifact_digest_domain": _ARTIFACT_DIGEST_DOMAIN,
        "accepted": True,
    }
    for key, value in expected.items():
        require(evidence.get(key) == value, f"Android release evidence mismatch: {key}")
    digest = evidence.get("artifact_digest")
    require(isinstance(digest, str) and _CONTENT_DIGEST_PATTERN.fullmatch(digest) is not None, "Android release artifact digest is invalid")
    require(apk.is_file() and apk.stat().st_size > 0, "signed Android release APK is unavailable")
    require(typed_artifact_digest(digest_tool, apk) == digest, "signed Android release APK digest differs")
    return digest


def verify_installed_apk_digest(serial: str, expected_digest: str, digest_tool: Path) -> None:
    pm = adb(serial, "shell", "pm", "path", _PACKAGE, timeout=30)
    remote = select_installed_apk_path(pm.stdout)
    with tempfile.TemporaryDirectory(prefix="mobile-proxy-clean-install-proof-") as raw:
        local = Path(raw) / "installed-base.apk"
        adb(serial, "pull", remote, str(local), timeout=120)
        require(local.is_file() and local.stat().st_size > 0, "installed APK proof is unavailable")
        observed = typed_artifact_digest(digest_tool, local)
    require(observed == expected_digest, "installed Android APK digest differs from exact signed candidate")


def clean_install(
    *,
    canonical_sha: str,
    apk: Path,
    release_evidence: Path,
    digest_tool: Path,
    expected_version_name: str,
    expected_version_code: int,
) -> dict[str, Any]:
    canonical_sha = require_canonical_sha(canonical_sha)
    serial = require_expected_serial()
    evidence = load_json(release_evidence)
    expected_digest = verify_release_evidence(
        evidence,
        canonical_sha,
        apk,
        digest_tool,
        expected_version_name,
        expected_version_code,
    )

    # PHONE_ACCESS is intentionally independent of package/runtime state.
    prove_registered_device(serial)
    old_package_present = package_present(serial)

    if old_package_present:
        # Re-prove the registered device immediately before the destructive boundary.
        prove_registered_device(serial)
        result = adb(serial, "uninstall", _PACKAGE, timeout=120)
        require("Success" in result.stdout, "Android package uninstall did not report success")
        require(not package_present(serial), "Android package remained installed after uninstall")

    # Re-prove again immediately before installing the new generation.
    prove_registered_device(serial)
    result = adb(serial, "install", str(apk), timeout=180)
    require("Success" in result.stdout, "Android package install did not report success")
    require(package_present(serial), "Android package is absent after install")

    installed_code, installed_name = package_version(serial)
    require(
        (installed_code, installed_name) == (expected_version_code, expected_version_name),
        "installed Android package version differs from exact candidate",
    )
    verify_installed_apk_digest(serial, expected_digest, digest_tool)

    return {
        "format_version": 1,
        "repository": "iamaman11/mobile-proxy",
        "canonical_sha": canonical_sha,
        "application_id": _PACKAGE,
        "expected_version_name": expected_version_name,
        "expected_version_code": expected_version_code,
        "phone_access": True,
        "old_package_required": False,
        "old_package_observed": old_package_present,
        "old_package_retained": False,
        "rollback_to_old_generation_available": False,
        "new_apk_installed": True,
        "new_apk_identity_verified": True,
        "new_apk_digest_verified": True,
        "raw_device_identifier_recorded": False,
        "phone_reboot_performed": False,
        "provider_access_performed": False,
        "accepted": True,
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
        report = clean_install(
            canonical_sha=args.canonical_sha,
            apk=args.apk,
            release_evidence=args.release_evidence,
            digest_tool=args.digest_tool,
            expected_version_name=args.expected_version_name,
            expected_version_code=args.expected_version_code,
        )
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (CleanInstallFailure, PreflightFailure, OSError) as error:
        print(f"clean Android install failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
