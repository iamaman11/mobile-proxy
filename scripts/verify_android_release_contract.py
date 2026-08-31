#!/usr/bin/env python3
"""Verify canonical Android release identity and versioning without secrets."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

_EXPECTED_APPLICATION_ID = "com.example.mobileproxy"
_REQUIRED_SIGNING_ENV = (
    "ANDROID_RELEASE_KEYSTORE_PATH",
    "ANDROID_RELEASE_KEYSTORE_PASSWORD",
    "ANDROID_RELEASE_KEY_ALIAS",
    "ANDROID_RELEASE_KEY_PASSWORD",
)
_SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


class ContractFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractFailure(message)


def android_version_code(version: str) -> int:
    match = _SEMVER.fullmatch(version)
    require(match is not None, "workspace version must be stable X.Y.Z semver")
    major, minor, patch = (int(value) for value in match.groups())
    require(major <= 2_000, "Android major version is outside supported versionCode range")
    require(minor <= 999 and patch <= 999, "Android minor/patch version exceeds three digits")
    value = major * 1_000_000 + minor * 1_000 + patch
    require(1 <= value <= 2_100_000_000, "derived Android versionCode is invalid")
    return value


def _single(pattern: str, text: str, label: str) -> str:
    matches = re.findall(pattern, text, flags=re.MULTILINE)
    require(len(matches) == 1, f"expected exactly one {label}")
    return matches[0]


def verify_contract(root: Path, expected_version: str | None = None) -> dict[str, object]:
    cargo_path = root / "Cargo.toml"
    gradle_path = root / "apps/android-app/app/build.gradle.kts"
    try:
        cargo = tomllib.loads(cargo_path.read_text(encoding="utf-8"))
        gradle = gradle_path.read_text(encoding="utf-8")
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ContractFailure("release metadata is unreadable") from error

    version = cargo.get("workspace", {}).get("package", {}).get("version")
    require(isinstance(version, str), "workspace package version is missing")
    require(_SEMVER.fullmatch(version) is not None, "workspace version must be stable X.Y.Z semver")
    if expected_version is not None:
        require(version == expected_version, "workspace version differs from requested release")

    application_id = _single(r'^\s*applicationId\s*=\s*"([^"]+)"\s*$', gradle, "Android applicationId")
    version_name = _single(r'^\s*versionName\s*=\s*"([^"]+)"\s*$', gradle, "Android versionName")
    version_code = int(_single(r"^\s*versionCode\s*=\s*([0-9]+)\s*$", gradle, "Android versionCode"))

    require(application_id == _EXPECTED_APPLICATION_ID, "Android applicationId changed")
    require(version_name == version, "Android versionName differs from workspace version")
    require(version_code == android_version_code(version), "Android versionCode differs from canonical semver mapping")

    for name in _REQUIRED_SIGNING_ENV:
        require(gradle.count(f'providers.environmentVariable("{name}")') == 1, f"missing canonical signing input: {name}")
    require('create("productionRelease")' in gradle, "production release signing configuration is missing")
    require('signingConfig = signingConfigs.getByName("productionRelease")' in gradle, "release build is not bound to production signing configuration")

    return {
        "format_version": 1,
        "application_id": application_id,
        "version_name": version_name,
        "version_code": version_code,
        "workspace_version_match": True,
        "signing_contract_present": True,
        "secrets_recorded": False,
        "accepted": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--expected-version")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = verify_contract(args.root, args.expected_version)
        if args.output is not None:
            args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        else:
            print(json.dumps(report, sort_keys=True))
    except (ContractFailure, OSError, ValueError) as error:
        print(f"Android release contract verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
