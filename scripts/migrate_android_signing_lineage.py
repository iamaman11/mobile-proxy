#!/usr/bin/env python3
"""Perform the explicitly-authorized Android signing-lineage reset on one registered phone.

The migration is fail-closed and retains the currently-installed signed APK before
uninstall. If the new signed APK cannot be installed or made locally healthy, the
script attempts a destructive rollback to that exact retained old APK.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
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
_AUTHORIZATION = "DESTROY_OLD_SIGNING_LINEAGE_AND_APP_DATA"
_RUNTIME_ROOT = "/data/adb/mobile-proxy-node/current"
_SUPERVISOR = f"{_RUNTIME_ROOT}/bin/runtime-supervisor"
_EGRESS_SERVICE = "com.example.mobileproxy/.CellularEgressService"
_VERSION_CODE_PATTERN = re.compile(r"^\s*versionCode=([0-9]+)\b", re.MULTILINE)
_VERSION_NAME_PATTERN = re.compile(r"^\s*versionName=([^\s]+)\s*$", re.MULTILINE)
_CONTENT_DIGEST_PATTERN = re.compile(r"^b3:[0-9a-f]{64}$")
_ARTIFACT_DIGEST_DOMAIN = "mobile-proxy/android-apk/v1"


class MigrationFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise MigrationFailure(message)


def run_checked(
    command: Sequence[str],
    *,
    timeout: int = 120,
    text: bool = True,
) -> subprocess.CompletedProcess[Any]:
    try:
        return subprocess.run(
            list(command),
            check=True,
            capture_output=True,
            text=text,
            timeout=timeout,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise MigrationFailure("registered-phone migration command failed") from error


def adb(serial: str, *arguments: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return run_checked(["adb", "-s", serial, *arguments], timeout=timeout)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MigrationFailure("Android release evidence is unreadable") from error
    require(isinstance(value, dict), "Android release evidence must be an object")
    return value


def typed_artifact_digest(tool: Path, path: Path) -> str:
    require(tool.is_file() and os.access(tool, os.X_OK), "typed Android artifact digest helper is unavailable")
    result = run_checked([str(tool), str(path)], timeout=120).stdout.strip()
    require(_CONTENT_DIGEST_PATTERN.fullmatch(result) is not None, "typed Android artifact digest is invalid")
    return result


def parse_package_version(output: str) -> tuple[int, str]:
    codes = _VERSION_CODE_PATTERN.findall(output)
    names = _VERSION_NAME_PATTERN.findall(output)
    require(len(codes) == 1, "installed package versionCode is ambiguous")
    require(len(names) == 1, "installed package versionName is ambiguous")
    return int(codes[0]), names[0]


def package_version(serial: str) -> tuple[int, str]:
    result = adb(serial, "shell", "dumpsys", "package", _PACKAGE, timeout=60)
    require(
        f"Package [{_PACKAGE}]" in result.stdout or f"Package {{{_PACKAGE}" in result.stdout,
        "production package is not installed",
    )
    return parse_package_version(result.stdout)


def package_present(serial: str) -> bool:
    result = subprocess.run(
        ["adb", "-s", serial, "shell", "pm", "path", _PACKAGE],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode == 0 and any(
        line.startswith("package:/") for line in result.stdout.splitlines()
    )


def verify_release_evidence(
    evidence: dict[str, Any],
    canonical_sha: str,
    apk: Path,
    digest_tool: Path,
    expected_version_name: str,
    expected_version_code: int,
) -> str:
    require(evidence.get("format_version") == 1, "Android release evidence version is unsupported")
    require(
        evidence.get("repository") == "iamaman11/mobile-proxy",
        "Android release evidence repository differs",
    )
    require(evidence.get("canonical_sha") == canonical_sha, "Android release evidence SHA differs")
    require(evidence.get("android_baseline_ref") == "v0.1.3", "Android migration baseline differs")
    require(
        evidence.get("android_functional_source_preserved") is True,
        "Android functional-source preservation is unproven",
    )
    require(evidence.get("application_id") == _PACKAGE, "Android release package differs")
    require(
        evidence.get("version_name") == expected_version_name,
        "Android release versionName differs",
    )
    require(
        evidence.get("version_code") == expected_version_code,
        "Android release versionCode differs",
    )
    for field in (
        "release_contract_verified",
        "keystore_verified",
        "apk_signature_verified",
        "apk_signer_matches_private_key",
        "production_apk_signed",
        "accepted",
    ):
        require(evidence.get(field) is True, f"Android release evidence is missing {field}")
    require(
        evidence.get("phone_access_performed") is False,
        "Android release build evidence unexpectedly used the phone",
    )
    require(
        evidence.get("phone_mutation_performed") is False,
        "Android release build evidence unexpectedly mutated the phone",
    )
    require(
        evidence.get("artifact_digest_algorithm") == "blake3-256",
        "Android release artifact digest algorithm differs",
    )
    require(
        evidence.get("artifact_digest_domain") == _ARTIFACT_DIGEST_DOMAIN,
        "Android release artifact digest domain differs",
    )
    digest = evidence.get("artifact_digest")
    require(
        isinstance(digest, str) and _CONTENT_DIGEST_PATTERN.fullmatch(digest) is not None,
        "Android release artifact digest is invalid",
    )
    require(apk.is_file() and apk.stat().st_size > 0, "signed Android release APK is unavailable")
    require(
        typed_artifact_digest(digest_tool, apk) == digest,
        "signed Android release APK digest differs",
    )
    return digest


def capture_installed_apk(serial: str, output: Path, digest_tool: Path) -> str:
    pm = adb(serial, "shell", "pm", "path", _PACKAGE, timeout=30)
    remote = select_installed_apk_path(pm.stdout)
    output.parent.mkdir(parents=True, exist_ok=True)
    adb(serial, "pull", remote, str(output), timeout=120)
    require(
        output.is_file() and output.stat().st_size > 0,
        "installed rollback APK was not retained",
    )
    return typed_artifact_digest(digest_tool, output)


def exact_preflight(serial: str) -> None:
    prove_registered_device(serial)


def uninstall(serial: str) -> None:
    exact_preflight(serial)
    result = adb(serial, "uninstall", _PACKAGE, timeout=120)
    require("Success" in result.stdout, "Android package uninstall did not report success")
    require(not package_present(serial), "Android package remained installed after uninstall")


def install(serial: str, apk: Path) -> None:
    exact_preflight(serial)
    result = adb(serial, "install", str(apk), timeout=180)
    require("Success" in result.stdout, "Android package install did not report success")
    require(package_present(serial), "Android package is absent after install")


def _supervisor_restart_shell() -> str:
    return f'''set -eu
found=0
for proc in /proc/[0-9]*; do
  [ -r "$proc/cmdline" ] || continue
  cmd="$(tr '\\000' ' ' < "$proc/cmdline")"
  case "$cmd" in
    "{_SUPERVISOR} --runtime-root {_RUNTIME_ROOT} "*)
      pid="${{proc#/proc/}}"
      kill -TERM "$pid"
      found=1
      ;;
  esac
done
[ "$found" -eq 1 ]
'''


def restart_runtime_supervisor(serial: str) -> None:
    exact_preflight(serial)
    adb(
        serial,
        "shell",
        "su",
        "0",
        "sh",
        "-c",
        _supervisor_restart_shell(),
        timeout=60,
    )


def _root_test(serial: str, shell: str) -> bool:
    result = subprocess.run(
        ["adb", "-s", serial, "shell", "su", "0", "sh", "-c", shell],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=20,
    )
    return result.returncode == 0


def supervisor_running(serial: str) -> bool:
    shell = f'''for proc in /proc/[0-9]*; do
  [ -r "$proc/cmdline" ] || continue
  cmd="$(tr '\\000' ' ' < "$proc/cmdline")"
  case "$cmd" in
    "{_SUPERVISOR} --runtime-root {_RUNTIME_ROOT} "*) exit 0 ;;
  esac
done
exit 1
'''
    return _root_test(serial, shell)


def local_proxy_ports_ready(serial: str) -> bool:
    shell = '''BB=""
for candidate in /data/adb/magisk/busybox /debug_ramdisk/.magisk/busybox/busybox; do
  [ -x "$candidate" ] && BB="$candidate" && break
done
[ -n "$BB" ] || exit 1
"$BB" nc -z -w 2 127.0.0.1 18080 >/dev/null 2>&1
"$BB" nc -z -w 2 127.0.0.1 1080 >/dev/null 2>&1
'''
    return _root_test(serial, shell)


def egress_service_running(serial: str) -> bool:
    result = subprocess.run(
        ["adb", "-s", serial, "shell", "dumpsys", "activity", "services", _PACKAGE],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode == 0 and _EGRESS_SERVICE in result.stdout


def wait_for_local_health(serial: str, *, timeout_seconds: int = 60) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if (
            supervisor_running(serial)
            and egress_service_running(serial)
            and local_proxy_ports_ready(serial)
        ):
            return
        time.sleep(2)
    raise MigrationFailure("new Android signing generation did not become locally healthy")


def restore_old_generation(
    serial: str,
    old_apk: Path,
    old_code: int,
    old_name: str,
) -> bool:
    try:
        if package_present(serial):
            uninstall(serial)
        install(serial, old_apk)
        restored_code, restored_name = package_version(serial)
        require(
            (restored_code, restored_name) == (old_code, old_name),
            "rollback APK version differs from retained old package",
        )
        restart_runtime_supervisor(serial)
        wait_for_local_health(serial)
        return True
    except (MigrationFailure, PreflightFailure, OSError, subprocess.TimeoutExpired):
        return False


def migrate(args: argparse.Namespace) -> tuple[dict[str, Any], bool]:
    canonical_sha = require_canonical_sha(args.canonical_sha)
    require(
        args.authorization == _AUTHORIZATION,
        "explicit destructive migration authorization is absent",
    )
    serial = require_expected_serial()
    require(shutil.which("adb") is not None, "adb is unavailable")
    require(
        args.digest_tool.is_file() and os.access(args.digest_tool, os.X_OK),
        "typed Android artifact digest helper is unavailable",
    )

    new_digest = verify_release_evidence(
        load_json(args.release_evidence),
        canonical_sha,
        args.apk,
        args.digest_tool,
        args.expected_version_name,
        args.expected_version_code,
    )

    # Read-only identity gate before any mutation.
    exact_preflight(serial)
    old_code, old_name = package_version(serial)
    require(
        old_code == args.expected_old_version_code,
        "installed old Android versionCode differs from approved baseline",
    )
    require(
        old_name == args.expected_old_version_name,
        "installed old Android versionName differs from approved baseline",
    )
    old_digest = capture_installed_apk(serial, args.retained_old_apk, args.digest_tool)

    report: dict[str, Any] = {
        "format_version": 1,
        "repository": "iamaman11/mobile-proxy",
        "canonical_sha": canonical_sha,
        "package": _PACKAGE,
        "artifact_digest_algorithm": "blake3-256",
        "artifact_digest_domain": _ARTIFACT_DIGEST_DOMAIN,
        "old_version_name": old_name,
        "old_version_code": old_code,
        "old_apk_digest": old_digest,
        "new_version_name": args.expected_version_name,
        "new_version_code": args.expected_version_code,
        "new_apk_digest": new_digest,
        "destructive_authorization_verified": True,
        "registered_device_preflight_before_each_mutation": True,
        "old_signed_apk_retained_before_uninstall": True,
        "phone_identifier_recorded": False,
        "signer_fingerprint_recorded": False,
        "signing_material_recorded": False,
        "rollback_attempted": False,
        "rollback_succeeded": False,
        "accepted": False,
    }

    try:
        uninstall(serial)
        report["old_package_removed"] = True
        install(serial, args.apk)
        new_code, new_name = package_version(serial)
        require(
            new_code == args.expected_version_code,
            "installed new Android versionCode differs",
        )
        require(
            new_name == args.expected_version_name,
            "installed new Android versionName differs",
        )
        report["new_package_installed"] = True
        report["new_package_version_verified"] = True
        restart_runtime_supervisor(serial)
        report["runtime_supervisor_restarted"] = True
        wait_for_local_health(serial)
        report["runtime_supervisor_running"] = True
        report["cellular_egress_service_running"] = True
        report["local_app_egress_port_ready"] = True
        report["local_proxy_port_ready"] = True
        report["accepted"] = True
        return report, True
    except (MigrationFailure, PreflightFailure, OSError, subprocess.TimeoutExpired):
        report["rollback_attempted"] = True
        report["rollback_succeeded"] = restore_old_generation(
            serial,
            args.retained_old_apk,
            old_code,
            old_name,
        )
        return report, False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-sha", required=True)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--release-evidence", type=Path, required=True)
    parser.add_argument("--digest-tool", type=Path, required=True)
    parser.add_argument("--retained-old-apk", type=Path, required=True)
    parser.add_argument("--expected-old-version-name", required=True)
    parser.add_argument("--expected-old-version-code", type=int, required=True)
    parser.add_argument("--expected-version-name", required=True)
    parser.add_argument("--expected-version-code", type=int, required=True)
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report, accepted = migrate(args)
    except (MigrationFailure, PreflightFailure, OSError, subprocess.TimeoutExpired) as error:
        print(f"Android signing-lineage migration failed before mutation: {error}", file=sys.stderr)
        return 1
    try:
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as error:
        print(f"Android signing-lineage migration evidence write failed: {error}", file=sys.stderr)
        return 1
    if not accepted:
        print(
            "Android signing-lineage migration failed; bounded rollback was attempted",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
