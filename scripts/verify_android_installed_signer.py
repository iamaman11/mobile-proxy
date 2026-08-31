#!/usr/bin/env python3
"""Fail-closed read-only verifier for the installed production Android signer.

This script is canonical public logic intended to run only from the private
`mobile-proxy-production` execution satellite on the registered phone runner.
It performs no phone mutation and never emits the raw device identifier,
certificate fingerprint, keystore bytes, passwords, or alias.

The verifier proves only one bounded fact: the certificate stored under the
recovered private keystore alias exactly matches the current signer reported by
`apksigner` for the APK installed as `com.example.mobileproxy`. It compares the
SHA-256 certificate fingerprints reported by Android's signing tools; it does not
introduce a first-party digest primitive or digest authority contract.

It does not generate a signing key, sign an APK, install/update/uninstall an APK,
restart the phone or service, mutate networking, or authorize Item 20 execution.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Sequence

from scripts.run_private_phone_preflight import (
    PreflightFailure,
    prove_registered_device,
    require_canonical_sha,
    require_expected_serial,
)

_PACKAGE_NAME = "com.example.mobileproxy"
_KEYSTORE_B64_ENV = "ANDROID_RELEASE_KEYSTORE_B64"
_KEYSTORE_PASSWORD_ENV = "ANDROID_RELEASE_KEYSTORE_PASSWORD"
_KEY_ALIAS_ENV = "ANDROID_RELEASE_KEY_ALIAS"
_REQUIRED_TOOLS = ("adb", "keytool", "apksigner")
_APKSIGNER_FINGERPRINT_PATTERN = re.compile(
    r"^Signer #\d+ certificate SHA-256 digest: ([0-9A-Fa-f]{64})$",
    re.MULTILINE,
)
_KEYTOOL_FINGERPRINT_PATTERN = re.compile(
    r"^\s*SHA256:\s*((?:[0-9A-Fa-f]{2}:){31}[0-9A-Fa-f]{2})\s*$",
    re.MULTILINE,
)


class SigningIdentityFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SigningIdentityFailure(message)


def require_tools() -> None:
    for tool in _REQUIRED_TOOLS:
        require(
            shutil.which(tool) is not None,
            f"required signing verifier tool is missing: {tool}",
        )


def require_private_text(name: str, *, maximum: int) -> str:
    value = os.environ.get(name, "")
    require(bool(value), f"required private signing input is unavailable: {name}")
    require(len(value) <= maximum, f"private signing input is invalid: {name}")
    require(
        not any(character in "\r\n\x00" for character in value),
        f"private signing input is invalid: {name}",
    )
    return value


def decode_canonical_base64(value: str, field: str, *, maximum_bytes: int) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise SigningIdentityFailure(f"{field} is not canonical base64") from error
    require(bool(decoded), f"{field} is empty")
    require(len(decoded) <= maximum_bytes, f"{field} is too large")
    require(
        base64.b64encode(decoded).decode("ascii") == value,
        f"{field} is not canonical padded base64",
    )
    return decoded


def run_checked(
    command: Sequence[str],
    *,
    timeout: int = 20,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command),
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise SigningIdentityFailure("read-only signing identity probe failed") from error


def select_installed_apk_path(pm_output: str) -> str:
    paths: list[str] = []
    for raw_line in pm_output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        require(line.startswith("package:"), "installed package path inventory is invalid")
        path = line.removeprefix("package:")
        require(path.startswith("/"), "installed package path inventory is invalid")
        require(
            not any(character.isspace() for character in path),
            "installed package path inventory is invalid",
        )
        paths.append(path)
    require(bool(paths), "installed production package is unavailable")
    base_paths = [path for path in paths if path.endswith("/base.apk")]
    if len(base_paths) == 1:
        return base_paths[0]
    require(len(paths) == 1, "installed package path inventory is ambiguous")
    return paths[0]


def parse_single_apksigner_fingerprint(output: str) -> str:
    matches = _APKSIGNER_FINGERPRINT_PATTERN.findall(output)
    require(
        len(matches) == 1,
        "installed APK signer inventory is not exactly one current signer",
    )
    return matches[0].lower()


def parse_single_keytool_fingerprint(output: str) -> str:
    matches = _KEYTOOL_FINGERPRINT_PATTERN.findall(output)
    require(
        len(matches) == 1,
        "recovered keystore certificate inventory is not exactly one signer",
    )
    return matches[0].replace(":", "").lower()


def read_keystore_fingerprint(
    keystore: Path,
    alias: str,
    store_password: str,
) -> str:
    command_env = os.environ.copy()
    command_env[_KEYSTORE_PASSWORD_ENV] = store_password
    result = run_checked(
        [
            "keytool",
            "-list",
            "-v",
            "-keystore",
            str(keystore),
            "-alias",
            alias,
            "-storepass:env",
            _KEYSTORE_PASSWORD_ENV,
        ],
        env=command_env,
    )
    return parse_single_keytool_fingerprint(result.stdout)


def verify_installed_signer(canonical_sha: str) -> dict[str, Any]:
    canonical_sha = require_canonical_sha(canonical_sha)
    require_tools()
    expected_serial = require_expected_serial()
    prove_registered_device(expected_serial)

    keystore_b64 = require_private_text(_KEYSTORE_B64_ENV, maximum=4_000_000)
    store_password = require_private_text(_KEYSTORE_PASSWORD_ENV, maximum=4096)
    alias = require_private_text(_KEY_ALIAS_ENV, maximum=256)
    require(
        not any(character.isspace() for character in alias),
        "private signing alias is invalid",
    )
    keystore_bytes = decode_canonical_base64(
        keystore_b64,
        "recovered Android release keystore",
        maximum_bytes=3_000_000,
    )

    with tempfile.TemporaryDirectory(
        prefix="mobile-proxy-signing-identity-"
    ) as temp_dir:
        root = Path(temp_dir)
        keystore = root / "release.keystore"
        installed_apk = root / "installed-base.apk"
        keystore.write_bytes(keystore_bytes)
        os.chmod(keystore, 0o600)

        pm_result = run_checked(
            ["adb", "-s", expected_serial, "shell", "pm", "path", _PACKAGE_NAME],
        )
        remote_apk = select_installed_apk_path(pm_result.stdout)
        run_checked(
            ["adb", "-s", expected_serial, "pull", remote_apk, str(installed_apk)],
            timeout=60,
        )
        require(
            installed_apk.is_file() and installed_apk.stat().st_size > 0,
            "installed APK copy is unavailable",
        )

        signer_result = run_checked(
            ["apksigner", "verify", "--print-certs", str(installed_apk)],
            timeout=60,
        )
        installed_fingerprint = parse_single_apksigner_fingerprint(signer_result.stdout)
        recovered_fingerprint = read_keystore_fingerprint(
            keystore,
            alias,
            store_password,
        )
        require(
            hmac.compare_digest(installed_fingerprint, recovered_fingerprint),
            "recovered signing identity does not match the installed production APK",
        )

    return {
        "format_version": 1,
        "repository": "iamaman11/mobile-proxy",
        "canonical_sha": canonical_sha,
        "package": _PACKAGE_NAME,
        "mode": "read_only_signing_identity_verification",
        "registered_device_match": True,
        "installed_apk_signer_verified": True,
        "recovered_keystore_signer_match": True,
        "raw_device_identifier_recorded": False,
        "signer_digest_recorded": False,
        "signing_material_recorded": False,
        "phone_mutation_performed": False,
        "signing_key_generated": False,
        "accepted": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = verify_installed_signer(args.canonical_sha)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, PreflightFailure, SigningIdentityFailure) as error:
        print(f"Android signing identity verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
