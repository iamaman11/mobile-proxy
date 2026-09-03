#!/usr/bin/env python3
"""Build one signed Android product Release artifact without target access."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

try:
    from scripts.verify_android_release_contract import verify_contract
    from scripts.verify_android_release_keystore import (
        decode_canonical_base64,
        require_private_text,
        verify_release_keystore,
    )
except ModuleNotFoundError:
    from verify_android_release_contract import verify_contract  # type: ignore[no-redef]
    from verify_android_release_keystore import (  # type: ignore[no-redef]
        decode_canonical_base64,
        require_private_text,
        verify_release_keystore,
    )

_SHA = re.compile(r"^[0-9a-f]{40}$")
_PACKAGE_PATTERN = re.compile(
    r"^package: name='([^']+)' versionCode='([0-9]+)' versionName='([^']+)'",
    re.MULTILINE,
)
_PACKAGE = "com.example.mobileproxy"


class ProductReleaseBuildFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProductReleaseBuildFailure(message)


def run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ProductReleaseBuildFailure("product Android Release build/verification subprocess failed") from exc


def android_tool(name: str) -> str:
    direct = shutil.which(name)
    if direct:
        return direct
    for raw in (os.environ.get("ANDROID_SDK_ROOT"), os.environ.get("ANDROID_HOME"), "/usr/local/lib/android/sdk"):
        if not raw:
            continue
        root = Path(raw) / "build-tools"
        if not root.is_dir():
            continue
        candidates = sorted(path for path in root.glob(f"*/{name}") if path.is_file())
        if candidates:
            return str(candidates[-1])
    raise ProductReleaseBuildFailure(f"required Android build tool is unavailable: {name}")


def prove_source(root: Path, source_sha: str) -> None:
    require(_SHA.fullmatch(source_sha) is not None, "product Release source SHA is invalid")
    require(run(["git", "rev-parse", "HEAD"], cwd=root, timeout=30).stdout.strip() == source_sha, "checked out product source SHA differs")
    require(not run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root, timeout=30).stdout.strip(), "product source has tracked modifications before Release build")


def build(root: Path, source_sha: str, output_dir: Path) -> dict[str, object]:
    root = root.resolve()
    output_dir = output_dir.resolve()
    prove_source(root, source_sha)
    contract = verify_contract(root)
    verify_release_keystore(source_sha)

    version = str(contract["version_name"])
    version_code = int(contract["version_code"])
    require(contract["application_id"] == _PACKAGE, "Android package identity differs")

    keystore_b64 = require_private_text("ANDROID_RELEASE_KEYSTORE_B64", maximum=4_000_000)
    store_password = require_private_text("ANDROID_RELEASE_KEYSTORE_PASSWORD", maximum=4096)
    alias = require_private_text("ANDROID_RELEASE_KEY_ALIAS", maximum=256)
    key_password = require_private_text("ANDROID_RELEASE_KEY_PASSWORD", maximum=4096)
    keystore_bytes = decode_canonical_base64(keystore_b64, "Android release keystore", maximum_bytes=3_000_000)

    gradle_root = root / "apps/android-app"
    built_apk = gradle_root / "app/build/outputs/apk/release/app-release.apk"
    apksigner = android_tool("apksigner")
    aapt = android_tool("aapt2")

    with tempfile.TemporaryDirectory(prefix="mobile-proxy-product-release-") as raw:
        keystore = Path(raw) / "release.keystore"
        keystore.write_bytes(keystore_bytes)
        os.chmod(keystore, 0o600)

        build_env = os.environ.copy()
        for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"):
            build_env.pop(name, None)
        build_env["ANDROID_RELEASE_KEYSTORE_PATH"] = str(keystore)
        build_env["ANDROID_RELEASE_KEYSTORE_PASSWORD"] = store_password
        build_env["ANDROID_RELEASE_KEY_ALIAS"] = alias
        build_env["ANDROID_RELEASE_KEY_PASSWORD"] = key_password

        run(["bash", "./gradlew", "--no-daemon", "clean", "testDebugUnitTest", "lintDebug", "assembleRelease"], cwd=gradle_root, env=build_env)
        require(built_apk.is_file() and built_apk.stat().st_size > 0, "signed Android Release APK was not produced")
        run([apksigner, "verify", "--verbose", str(built_apk)], timeout=120)
        badging = run([aapt, "dump", "badging", str(built_apk)], timeout=120).stdout
        match = _PACKAGE_PATTERN.search(badging)
        require(match is not None, "signed Android Release APK metadata is unreadable")
        package, actual_code, actual_name = match.group(1), int(match.group(2)), match.group(3)
        require(package == _PACKAGE, "signed Android Release package differs")
        require(actual_code == version_code, "signed Android Release versionCode differs")
        require(actual_name == version, "signed Android Release versionName differs")

        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / f"mobile-proxy-android-v{version}.apk"
        shutil.copyfile(built_apk, target)

    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    report = {
        "format_version": 2,
        "repository": "iamaman11/mobile-proxy",
        "source_sha": source_sha,
        "artifact_name": target.name,
        "sha256": digest,
        "kind": "android-apk",
        "package_name": _PACKAGE,
        "version_name": version,
        "version_code": version_code,
        "signature_verified": True,
        "target_access_performed": False,
        "target_mutation_performed": False,
        "accepted": True,
    }
    (output_dir / "android-release-build.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        build(args.repository_root, args.source_sha, args.output_dir)
    except Exception as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        print(f"product Android Release build failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
