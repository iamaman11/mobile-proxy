#!/usr/bin/env python3
"""Build and verify the exact signed Android production APK from canonical Git."""

from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence

try:
    from scripts.run_private_phone_preflight import require_canonical_sha
    from scripts.verify_android_installed_signer import (
        parse_single_apksigner_fingerprint,
        read_keystore_fingerprint,
    )
    from scripts.verify_android_release_contract import verify_contract
    from scripts.verify_android_release_keystore import (
        decode_canonical_base64,
        require_private_text,
        verify_release_keystore,
    )
except ModuleNotFoundError:
    from run_private_phone_preflight import require_canonical_sha  # type: ignore[no-redef]
    from verify_android_installed_signer import (  # type: ignore[no-redef]
        parse_single_apksigner_fingerprint,
        read_keystore_fingerprint,
    )
    from verify_android_release_contract import verify_contract  # type: ignore[no-redef]
    from verify_android_release_keystore import (  # type: ignore[no-redef]
        decode_canonical_base64,
        require_private_text,
        verify_release_keystore,
    )

_PACKAGE = "com.example.mobileproxy"
_KEYSTORE_B64_ENV = "ANDROID_RELEASE_KEYSTORE_B64"
_KEYSTORE_PASSWORD_ENV = "ANDROID_RELEASE_KEYSTORE_PASSWORD"
_KEY_ALIAS_ENV = "ANDROID_RELEASE_KEY_ALIAS"
_KEY_PASSWORD_ENV = "ANDROID_RELEASE_KEY_PASSWORD"
_ALLOWED_MIGRATION_ANDROID_DIFF = {"apps/android-app/app/build.gradle.kts"}
_PACKAGE_PATTERN = re.compile(
    r"^package: name='([^']+)' versionCode='([0-9]+)' versionName='([^']+)'",
    re.MULTILINE,
)
_CONTENT_DIGEST_PATTERN = re.compile(r"^b3:[0-9a-f]{64}$")
_ARTIFACT_DIGEST_DOMAIN = "mobile-proxy/android-apk/v1"
_SAFE_APKSIGNER_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9._+() -]{1,80}$")
_SAFE_SIGNER_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9 #().,=:+-]{1,180}$")


class AndroidBuildFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AndroidBuildFailure(message)


def run_checked(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 1800,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command),
            cwd=cwd,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise AndroidBuildFailure("canonical Android release build or verification failed") from error


def resolve_android_build_tool(name: str) -> str:
    direct = shutil.which(name)
    if direct is not None:
        return direct
    roots = [
        os.environ.get("ANDROID_SDK_ROOT"),
        os.environ.get("ANDROID_HOME"),
        "/usr/local/lib/android/sdk",
        "/opt/android-sdk",
    ]
    candidates: list[Path] = []
    for raw in roots:
        if not raw:
            continue
        build_tools = Path(raw) / "build-tools"
        if not build_tools.is_dir():
            continue
        candidates.extend(path for path in build_tools.glob(f"*/{name}") if path.is_file())
    require(bool(candidates), f"required Android build tool is unavailable: {name}")
    return str(sorted(candidates, key=lambda path: path.parent.name)[-1])


def safe_apksigner_version(apksigner: str) -> str:
    try:
        result = subprocess.run(
            [apksigner, "version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return "unavailable"
    version = result.stdout.strip()
    if _SAFE_APKSIGNER_VERSION_PATTERN.fullmatch(version) is None:
        return "unavailable"
    return version


def safe_apksigner_signer_shapes(output: str) -> list[str]:
    shapes: list[str] = []
    marker = "certificate SHA-256 digest:"
    for raw_line in output.splitlines():
        if marker not in raw_line:
            continue
        label = raw_line.partition(marker)[0].strip()
        if _SAFE_SIGNER_LABEL_PATTERN.fullmatch(label) is None:
            shapes.append("<unavailable-label> certificate SHA-256 digest: <redacted>")
            continue
        shapes.append(f"{label} certificate SHA-256 digest: <redacted>")
    return shapes


def emit_safe_apksigner_diagnostic(apksigner: str, output: str) -> None:
    shapes = safe_apksigner_signer_shapes(output)
    print(f"apksigner safe version: {safe_apksigner_version(apksigner)}", file=sys.stderr)
    print(f"apksigner signer digest record count: {len(shapes)}", file=sys.stderr)
    for index, shape in enumerate(shapes, start=1):
        print(f"apksigner signer digest record {index}: {shape}", file=sys.stderr)


def prove_exact_source(root: Path, canonical_sha: str, android_baseline_ref: str | None) -> None:
    head = run_checked(["git", "rev-parse", "HEAD"], cwd=root, timeout=30).stdout.strip()
    require(head == canonical_sha, "checked out source SHA differs from canonical SHA")
    tracked = run_checked(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=root,
        timeout=30,
    ).stdout.strip()
    require(not tracked, "canonical source has tracked modifications before build")
    if android_baseline_ref is None:
        return
    changed = run_checked(
        ["git", "diff", "--name-only", f"{android_baseline_ref}..HEAD", "--", "apps/android-app"],
        cwd=root,
        timeout=30,
    ).stdout.splitlines()
    require(
        set(changed) == _ALLOWED_MIGRATION_ANDROID_DIFF,
        "Android functional source differs from the approved migration baseline",
    )


def parse_apk_identity(aapt_output: str) -> tuple[str, int, str]:
    match = _PACKAGE_PATTERN.search(aapt_output)
    require(match is not None, "signed APK package metadata is unreadable")
    return match.group(1), int(match.group(2)), match.group(3)


def typed_artifact_digest(root: Path, path: Path) -> str:
    result = run_checked(
        [
            "cargo",
            "run",
            "--quiet",
            "--locked",
            "--release",
            "-p",
            "operator-cli",
            "--bin",
            "android-artifact-digest",
            "--",
            str(path),
        ],
        cwd=root,
        timeout=600,
    ).stdout.strip()
    require(_CONTENT_DIGEST_PATTERN.fullmatch(result) is not None, "typed Android artifact digest is invalid")
    return result


def build_signed_release(
    root: Path,
    canonical_sha: str,
    output_dir: Path,
    android_baseline_ref: str | None,
) -> dict[str, object]:
    canonical_sha = require_canonical_sha(canonical_sha)
    root = root.resolve()
    output_dir = output_dir.resolve()
    contract = verify_contract(root)
    version = str(contract["version_name"])
    version_code = int(contract["version_code"])
    require(contract["application_id"] == _PACKAGE, "canonical Android package identity changed")
    prove_exact_source(root, canonical_sha, android_baseline_ref)
    verify_release_keystore(canonical_sha)

    keystore_b64 = require_private_text(_KEYSTORE_B64_ENV, maximum=4_000_000)
    store_password = require_private_text(_KEYSTORE_PASSWORD_ENV, maximum=4096)
    alias = require_private_text(_KEY_ALIAS_ENV, maximum=256)
    key_password = require_private_text(_KEY_PASSWORD_ENV, maximum=4096)
    keystore_bytes = decode_canonical_base64(
        keystore_b64,
        "Android release keystore",
        maximum_bytes=3_000_000,
    )

    apksigner = resolve_android_build_tool("apksigner")
    aapt = resolve_android_build_tool("aapt")
    gradle_root = root / "apps/android-app"
    built_apk = gradle_root / "app/build/outputs/apk/release/app-release.apk"

    with tempfile.TemporaryDirectory(prefix="mobile-proxy-android-release-") as raw:
        temp = Path(raw)
        keystore = temp / "release.keystore"
        keystore.write_bytes(keystore_bytes)
        os.chmod(keystore, 0o600)

        build_env = os.environ.copy()
        for name in (
            "http_proxy",
            "https_proxy",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "all_proxy",
            "NO_PROXY",
            "no_proxy",
        ):
            build_env.pop(name, None)
        build_env["ANDROID_RELEASE_KEYSTORE_PATH"] = str(keystore)
        build_env[_KEYSTORE_PASSWORD_ENV] = store_password
        build_env[_KEY_ALIAS_ENV] = alias
        build_env[_KEY_PASSWORD_ENV] = key_password

        run_checked(
            [
                "bash",
                "./gradlew",
                "--no-daemon",
                "clean",
                "testDebugUnitTest",
                "lintDebug",
                "assembleRelease",
            ],
            cwd=gradle_root,
            env=build_env,
        )
        require(
            built_apk.is_file() and built_apk.stat().st_size > 0,
            "signed release APK was not produced",
        )

        signer = run_checked(
            [apksigner, "verify", "--print-certs", str(built_apk)],
            timeout=120,
        )
        try:
            apk_fingerprint = parse_single_apksigner_fingerprint(signer.stdout)
        except Exception:
            emit_safe_apksigner_diagnostic(apksigner, signer.stdout)
            raise
        key_fingerprint = read_keystore_fingerprint(keystore, alias, store_password)
        require(
            hmac.compare_digest(apk_fingerprint, key_fingerprint),
            "signed APK signer differs from configured production key",
        )

        identity = run_checked([aapt, "dump", "badging", str(built_apk)], timeout=120)
        package, actual_code, actual_name = parse_apk_identity(identity.stdout)
        require(package == _PACKAGE, "signed APK applicationId differs from production package")
        require(actual_code == version_code, "signed APK versionCode differs from canonical metadata")
        require(actual_name == version, "signed APK versionName differs from canonical metadata")

        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / f"mobile-proxy-android-v{version}.apk"
        shutil.copyfile(built_apk, target)
        artifact_digest = typed_artifact_digest(root, target)

    report = {
        "format_version": 1,
        "repository": "iamaman11/mobile-proxy",
        "canonical_sha": canonical_sha,
        "android_baseline_ref": android_baseline_ref,
        "android_functional_source_preserved": android_baseline_ref is not None,
        "application_id": _PACKAGE,
        "version_name": version,
        "version_code": version_code,
        "artifact_name": target.name,
        "artifact_digest": artifact_digest,
        "artifact_digest_algorithm": "blake3-256",
        "artifact_digest_domain": _ARTIFACT_DIGEST_DOMAIN,
        "release_contract_verified": True,
        "keystore_verified": True,
        "apk_signature_verified": True,
        "apk_signer_matches_private_key": True,
        "production_apk_signed": True,
        "phone_access_performed": False,
        "phone_mutation_performed": False,
        "signing_material_recorded": False,
        "signer_fingerprint_recorded": False,
        "accepted": True,
    }
    (output_dir / "android-release-evidence.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--canonical-sha", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--android-baseline-ref")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        build_signed_release(
            args.repository_root,
            args.canonical_sha,
            args.output_dir,
            args.android_baseline_ref,
        )
    except Exception as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        print(f"signed Android release build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
