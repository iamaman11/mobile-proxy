#!/usr/bin/env python3
"""Fail-closed offline verifier for Android product release signing identity.

This product-release logic validates the four Android signing inputs without contacting
or mutating any production target. It decodes the keystore into an ephemeral directory,
proves the configured alias is readable with `keytool`, signs a throwaway JAR with
`jarsigner`, verifies the signature, and removes all temporary material.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Sequence
import zipfile

_KEYSTORE_B64_ENV = "ANDROID_RELEASE_KEYSTORE_B64"
_KEYSTORE_PASSWORD_ENV = "ANDROID_RELEASE_KEYSTORE_PASSWORD"
_KEY_ALIAS_ENV = "ANDROID_RELEASE_KEY_ALIAS"
_KEY_PASSWORD_ENV = "ANDROID_RELEASE_KEY_PASSWORD"
_REQUIRED_TOOLS = ("keytool", "jarsigner")
_SHA = re.compile(r"^[0-9a-f]{40}$")


class ReleaseKeystoreFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseKeystoreFailure(message)


def require_source_sha(value: str) -> str:
    require(_SHA.fullmatch(value) is not None, "product release source SHA is invalid")
    return value


def require_tools() -> None:
    for tool in _REQUIRED_TOOLS:
        require(shutil.which(tool) is not None, f"required offline signing verifier tool is missing: {tool}")


def require_private_text(name: str, *, maximum: int) -> str:
    value = os.environ.get(name, "")
    require(bool(value), f"required private signing input is unavailable: {name}")
    require(len(value) <= maximum, f"private signing input is invalid: {name}")
    require(not any(character in "\r\n\x00" for character in value), f"private signing input is invalid: {name}")
    return value


def decode_canonical_base64(value: str, field: str, *, maximum_bytes: int) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ReleaseKeystoreFailure(f"{field} is not canonical base64") from error
    require(bool(decoded), f"{field} is empty")
    require(len(decoded) <= maximum_bytes, f"{field} is too large")
    require(base64.b64encode(decoded).decode("ascii") == value, f"{field} is not canonical padded base64")
    return decoded


def run_checked(
    command: Sequence[str],
    *,
    timeout: int = 30,
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
        raise ReleaseKeystoreFailure("offline signing identity proof failed") from error


def create_probe_jar(path: Path) -> None:
    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("mobile-proxy-signing-proof.txt", "offline signing proof\n")


def verify_release_keystore(source_sha: str) -> dict[str, Any]:
    source_sha = require_source_sha(source_sha)
    require_tools()

    keystore_b64 = require_private_text(_KEYSTORE_B64_ENV, maximum=4_000_000)
    store_password = require_private_text(_KEYSTORE_PASSWORD_ENV, maximum=4096)
    alias = require_private_text(_KEY_ALIAS_ENV, maximum=256)
    key_password = require_private_text(_KEY_PASSWORD_ENV, maximum=4096)
    require(not any(character.isspace() for character in alias), "private signing alias is invalid")
    keystore_bytes = decode_canonical_base64(
        keystore_b64,
        "Android release keystore",
        maximum_bytes=3_000_000,
    )

    with tempfile.TemporaryDirectory(prefix="mobile-proxy-offline-signing-proof-") as temp_dir:
        root = Path(temp_dir)
        keystore = root / "release.keystore"
        probe_jar = root / "signing-proof.jar"
        keystore.write_bytes(keystore_bytes)
        os.chmod(keystore, 0o600)
        create_probe_jar(probe_jar)

        command_env = os.environ.copy()
        command_env[_KEYSTORE_PASSWORD_ENV] = store_password
        command_env[_KEY_PASSWORD_ENV] = key_password

        run_checked(
            [
                "keytool",
                "-list",
                "-keystore",
                str(keystore),
                "-alias",
                alias,
                "-storepass:env",
                _KEYSTORE_PASSWORD_ENV,
            ],
            env=command_env,
        )
        run_checked(
            [
                "jarsigner",
                "-keystore",
                str(keystore),
                "-storepass:env",
                _KEYSTORE_PASSWORD_ENV,
                "-keypass:env",
                _KEY_PASSWORD_ENV,
                str(probe_jar),
                alias,
            ],
            timeout=60,
            env=command_env,
        )
        run_checked(["jarsigner", "-verify", str(probe_jar)], timeout=60)

    return {
        "format_version": 2,
        "repository": "iamaman11/mobile-proxy",
        "source_sha": source_sha,
        "mode": "offline_product_release_keystore_verification",
        "keystore_decoded": True,
        "keystore_password_verified": True,
        "key_alias_verified": True,
        "private_key_password_verified": True,
        "ephemeral_signature_verified": True,
        "target_access_performed": False,
        "target_mutation_performed": False,
        "production_apk_signed": False,
        "signing_key_generated": False,
        "signing_material_recorded": False,
        "secret_derived_value_recorded": False,
        "accepted": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha", "--canonical-sha", dest="source_sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = verify_release_keystore(args.source_sha)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ReleaseKeystoreFailure, ValueError) as error:
        print(f"Android release keystore verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
