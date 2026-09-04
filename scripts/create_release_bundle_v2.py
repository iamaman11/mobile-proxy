#!/usr/bin/env python3
"""Create the canonical PRODUCT Release v2 manifest, provenance and typed digests.

This module is deliberately target-agnostic with respect to deployment. It consumes
already-built product artifacts and bounded Android signing evidence; it never talks
to a phone, provider, private deployment controller or GitHub deployment API.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Callable, Mapping

_TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_SHA = re.compile(r"[0-9a-f]{40}")
_TYPED_DIGEST = re.compile(r"b3:[0-9a-f]{64}")
_PACKAGE = "com.example.mobileproxy"
_DIGEST_DOMAIN = "mobile-proxy/product-release-asset/v2"


class ReleaseBundleError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseBundleError(message)


def _load_object(path: Path, label: str) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseBundleError(f"{label} is unavailable or invalid") from exc
    if not isinstance(value, Mapping):
        raise ReleaseBundleError(f"{label} must be a JSON object")
    return value


def typed_asset_digest(repository_root: Path, asset_name: str, path: Path) -> str:
    repository_root = repository_root.resolve()
    command = [
        "cargo",
        "run",
        "--quiet",
        "--locked",
        "--release",
        "-p",
        "operator-cli",
        "--bin",
        "product-release-asset-digest",
        "--",
        asset_name,
        str(path.resolve()),
    ]
    try:
        result = subprocess.run(
            command,
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ReleaseBundleError("typed Product Release asset digest failed") from exc
    digest = result.stdout.strip()
    require(_TYPED_DIGEST.fullmatch(digest) is not None, "typed Product Release asset digest is invalid")
    return digest


def _validated_android_evidence(
    evidence: Mapping[str, object], *, tag: str, source_sha: str, apk_name: str
) -> tuple[str, int]:
    version = tag.removeprefix("v")
    require(evidence.get("format_version") == 1, "Android release evidence version differs")
    require(evidence.get("repository") == "iamaman11/mobile-proxy", "Android evidence repository differs")
    require(evidence.get("canonical_sha") == source_sha, "Android evidence source SHA differs")
    require(evidence.get("artifact_name") == apk_name, "Android evidence artifact name differs")
    require(evidence.get("application_id") == _PACKAGE, "Android package identity differs")
    require(evidence.get("version_name") == version, "Android versionName differs from Release tag")
    code = evidence.get("version_code")
    require(isinstance(code, int) and not isinstance(code, bool) and code > 0, "Android versionCode is invalid")
    for field in (
        "release_contract_verified",
        "keystore_verified",
        "apk_signature_verified",
        "apk_signer_matches_private_key",
        "production_apk_signed",
        "accepted",
    ):
        require(evidence.get(field) is True, f"Android signing evidence is not accepted: {field}")
    for field in (
        "phone_access_performed",
        "phone_mutation_performed",
        "signing_material_recorded",
        "signer_fingerprint_recorded",
    ):
        require(evidence.get(field) is False, f"Android signing evidence violates bounded PRODUCT build rule: {field}")
    return version, code


def create_bundle(
    *,
    repository_root: Path,
    release_dir: Path,
    tag: str,
    source_sha: str,
    android_evidence_path: Path,
    builder: str,
    workflow_ref: str,
    github_native_attestation: bool,
    digest_file: Callable[[Path, str, Path], str] = typed_asset_digest,
) -> tuple[dict[str, object], dict[str, object], dict[str, str]]:
    require(_TAG.fullmatch(tag) is not None, "Release tag is invalid")
    require(_SHA.fullmatch(source_sha) is not None, "Release source SHA is invalid")
    require(bool(builder) and "\n" not in builder and "\r" not in builder, "Release builder identity is invalid")
    require(bool(workflow_ref) and "\n" not in workflow_ref and "\r" not in workflow_ref, "Release workflow ref is invalid")

    repository_root = repository_root.resolve()
    release_dir = release_dir.resolve()
    linux_name = f"mobile-proxy-linux-x86_64-{tag}.tar.gz"
    apk_name = f"mobile-proxy-android-{tag}.apk"
    linux = release_dir / linux_name
    apk = release_dir / apk_name
    require(linux.is_file() and linux.stat().st_size > 0, "Linux Release artifact is missing")
    require(apk.is_file() and apk.stat().st_size > 0, "Android Release artifact is missing")

    evidence = _load_object(android_evidence_path, "Android release evidence")
    version, version_code = _validated_android_evidence(
        evidence, tag=tag, source_sha=source_sha, apk_name=apk_name
    )
    artifact_digests = {
        linux_name: digest_file(repository_root, linux_name, linux),
        apk_name: digest_file(repository_root, apk_name, apk),
    }
    for name, digest in artifact_digests.items():
        require(_TYPED_DIGEST.fullmatch(digest) is not None, f"typed digest is invalid: {name}")

    artifacts: list[dict[str, object]] = [
        {
            "content_digest": artifact_digests[linux_name],
            "content_digest_algorithm": "blake3-256",
            "content_digest_domain": _DIGEST_DOMAIN,
            "kind": "linux-x86_64-tar",
            "name": linux_name,
        },
        {
            "content_digest": artifact_digests[apk_name],
            "content_digest_algorithm": "blake3-256",
            "content_digest_domain": _DIGEST_DOMAIN,
            "kind": "android-apk",
            "name": apk_name,
            "package_name": _PACKAGE,
            "version_code": version_code,
            "version_name": version,
        },
    ]
    manifest: dict[str, object] = {
        "artifacts": artifacts,
        "format_version": 2,
        "git_sha": source_sha,
        "release_tag": tag,
    }
    provenance: dict[str, object] = {
        "artifacts": [
            {
                "content_digest": artifact_digests[linux_name],
                "content_digest_algorithm": "blake3-256",
                "content_digest_domain": _DIGEST_DOMAIN,
                "name": linux_name,
            },
            {
                "content_digest": artifact_digests[apk_name],
                "content_digest_algorithm": "blake3-256",
                "content_digest_domain": _DIGEST_DOMAIN,
                "name": apk_name,
            },
        ],
        "builder": builder,
        "format_version": 2,
        "git_sha": source_sha,
        "github_native_attestation": bool(github_native_attestation),
        "release_tag": tag,
        "workflow_ref": workflow_ref,
    }

    manifest_path = release_dir / "release-manifest.json"
    provenance_path = release_dir / "provenance.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    contract_digests = {
        "release-manifest.json": digest_file(repository_root, "release-manifest.json", manifest_path),
        "provenance.json": digest_file(repository_root, "provenance.json", provenance_path),
    }
    digests = {**artifact_digests, **contract_digests}
    for name, digest in digests.items():
        require(_TYPED_DIGEST.fullmatch(digest) is not None, f"typed digest is invalid: {name}")

    digest_set = {
        "algorithm": "blake3-256",
        "assets": [
            {"digest": digest, "name": name}
            for name, digest in sorted(digests.items())
        ],
        "digest_domain": _DIGEST_DOMAIN,
        "format_version": 1,
    }
    (release_dir / "artifact-digests.json").write_text(
        json.dumps(digest_set, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest, provenance, digests


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--android-evidence", type=Path, required=True)
    parser.add_argument("--builder", required=True)
    parser.add_argument("--workflow-ref", required=True)
    parser.add_argument("--github-native-attestation", choices=("true", "false"), required=True)
    args = parser.parse_args()
    try:
        create_bundle(
            repository_root=args.repository_root,
            release_dir=args.release_dir,
            tag=args.tag,
            source_sha=args.source_sha,
            android_evidence_path=args.android_evidence,
            builder=args.builder,
            workflow_ref=args.workflow_ref,
            github_native_attestation=args.github_native_attestation == "true",
        )
    except (OSError, ReleaseBundleError) as exc:
        print(f"Release v2 bundle refused: {exc}", file=__import__("sys").stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
