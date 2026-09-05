#!/usr/bin/env python3
"""Pure/off-phone Android Product Release signing helpers."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
from typing import Sequence

_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_APKSIGNER_NUMBERED_FINGERPRINT_PATTERN = re.compile(
    r"^Signer #\d+ certificate SHA-256 digest: ([0-9A-Fa-f]{64})$",
    re.MULTILINE,
)
_APKSIGNER_V31_RANGE_FINGERPRINT_PATTERN = re.compile(
    r"^Signer \(minSdkVersion=\d+(?: \(dev release=true\))?, maxSdkVersion=\d+\) "
    r"certificate SHA-256 digest: ([0-9A-Fa-f]{64})$",
    re.MULTILINE,
)
_APKSIGNER_VERSIONED_FINGERPRINT_PATTERN = re.compile(
    r"^V(?:1|2|3\.0|3\.1|3\.2) Signer"
    r"(?: #\d+)?"
    r"(?: \(minSdkVersion=\d+(?: \(dev release=true\))?, maxSdkVersion=\d+\))?"
    r": certificate SHA-256 digest: ([0-9A-Fa-f]{64})$",
    re.MULTILINE,
)
_KEYTOOL_FINGERPRINT_PATTERN = re.compile(
    r"^\s*SHA256:\s*((?:[0-9A-Fa-f]{2}:){31}[0-9A-Fa-f]{2})\s*$",
    re.MULTILINE,
)
_KEYSTORE_PASSWORD_ENV = "ANDROID_RELEASE_KEYSTORE_PASSWORD"


class AndroidReleaseSigningFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AndroidReleaseSigningFailure(message)


def require_canonical_sha(value: str) -> str:
    if _SHA_PATTERN.fullmatch(value) is None:
        raise ValueError("canonical SHA is invalid")
    return value


def parse_single_apksigner_fingerprint(output: str) -> str:
    numbered_matches = _APKSIGNER_NUMBERED_FINGERPRINT_PATTERN.findall(output)
    range_matches = _APKSIGNER_V31_RANGE_FINGERPRINT_PATTERN.findall(output)
    versioned_matches = _APKSIGNER_VERSIONED_FINGERPRINT_PATTERN.findall(output)
    signer_digest_lines = [
        line
        for line in output.splitlines()
        if (line.startswith("Signer ") or re.match(r"^V[0-9]", line) is not None)
        and "certificate SHA-256 digest:" in line
    ]
    require(
        len(signer_digest_lines)
        == len(numbered_matches) + len(range_matches) + len(versioned_matches),
        "APK signer inventory contains an unrecognized certificate digest record",
    )
    format_count = sum(
        bool(matches)
        for matches in (numbered_matches, range_matches, versioned_matches)
    )
    require(
        format_count == 1,
        "APK signer inventory format is unavailable or ambiguous",
    )

    if numbered_matches:
        require(
            len(numbered_matches) == 1,
            "APK signer inventory is not exactly one current signer",
        )
        return numbered_matches[0].lower()

    active_matches = range_matches if range_matches else versioned_matches
    unique_fingerprints = {fingerprint.lower() for fingerprint in active_matches}
    require(
        len(unique_fingerprints) == 1,
        "APK signer records do not resolve to exactly one signing identity",
    )
    return next(iter(unique_fingerprints))


def parse_single_keytool_fingerprint(output: str) -> str:
    matches = _KEYTOOL_FINGERPRINT_PATTERN.findall(output)
    require(
        len(matches) == 1,
        "release keystore certificate inventory is not exactly one signer",
    )
    return matches[0].replace(":", "").lower()


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
        raise AndroidReleaseSigningFailure(
            "offline Android signing identity verification failed"
        ) from error


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
