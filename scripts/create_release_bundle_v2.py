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
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping, Sequence

try:
    from scripts.create_release_archive import create_archive
except ModuleNotFoundError:
    from create_release_archive import create_archive  # type: ignore[no-redef]

_TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_SHA = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_TYPED_DIGEST = re.compile(r"b3:[0-9a-f]{64}")
_PACKAGE = "com.example.mobileproxy"
_DIGEST_DOMAIN = "mobile-proxy/product-release-asset/v2"
_PHONE_TARGET = "phone-production"
_PHONE_ARCHIVE_ROOT = "phone-production-runtime"
_PHONE_ABI = {
    "os": "android",
    "arch": "arm",
    "rust_target": "armv7-linux-androideabi",
    "elf_machine": 40,
}
_PHONE_COMPONENT_INVENTORY = "components.json"
_PHONE_COMPONENT_DIGEST_PREFIX = "phone-production-runtime/"
_SING_BOX_ARCHIVE_DOMAIN = "mobile-proxy/upstream-sing-box-archive/v1"


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


def _sequence(value: object, label: str) -> Sequence[object]:
    require(
        isinstance(value, Sequence) and not isinstance(value, (str, bytes)),
        f"{label} must be an array",
    )
    return value


def _safe_relative_path(value: object, label: str) -> PurePosixPath:
    require(isinstance(value, str) and bool(value), f"{label} is invalid")
    path = PurePosixPath(value)
    require(not path.is_absolute(), f"{label} must be relative")
    require(".." not in path.parts and "." not in path.parts, f"{label} escapes its root")
    return path


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


def _phone_runtime_contract(path: Path) -> Mapping[str, object]:
    contract = _load_object(path, "phone-production runtime component contract")
    require(contract.get("contract_version") == 1, "phone-production runtime contract version differs")
    require(contract.get("status") == "protected", "phone-production runtime contract is not protected")
    require(contract.get("target") == _PHONE_TARGET, "phone-production runtime target differs")
    require(
        contract.get("archive_name_pattern")
        == "mobile-proxy-phone-production-runtime-vMAJOR.MINOR.PATCH.tar.gz",
        "phone-production runtime archive pattern differs",
    )
    require(contract.get("archive_root") == _PHONE_ARCHIVE_ROOT, "phone-production runtime archive root differs")
    require(contract.get("runtime_abi") == _PHONE_ABI, "phone-production runtime ABI differs")
    return contract


def _sing_box_identity(repository_root: Path, contract: Mapping[str, object]) -> dict[str, object]:
    raw = contract.get("third_party_runtime")
    require(isinstance(raw, Mapping), "phone-production third-party runtime contract is invalid")
    spec = raw.get("sing-box")
    require(isinstance(spec, Mapping), "phone-production sing-box identity contract is missing")
    lock_file = _safe_relative_path(spec.get("lock_file"), "sing-box lock file")
    lock_target = spec.get("lock_target")
    require(lock_target == "android-arm", "phone-production sing-box lock target differs")
    lock = _load_object(repository_root / Path(*lock_file.parts), "sing-box artifact lock")
    require(lock.get("schema_version") == 1, "sing-box artifact lock schema differs")
    version = lock.get("version")
    require(isinstance(version, str) and bool(version), "sing-box pinned version is invalid")
    artifacts = lock.get("artifacts")
    require(isinstance(artifacts, Mapping), "sing-box artifact lock targets are invalid")
    pin = artifacts.get(lock_target)
    require(isinstance(pin, Mapping), "sing-box Android ARM pin is missing")
    size = pin.get("size")
    upstream_sha256 = pin.get("upstream_sha256")
    archive_digest = pin.get("content_digest")
    require(isinstance(size, int) and not isinstance(size, bool) and size > 0, "sing-box Android ARM size is invalid")
    require(isinstance(upstream_sha256, str) and _SHA256.fullmatch(upstream_sha256) is not None, "sing-box Android ARM upstream SHA-256 is invalid")
    require(isinstance(archive_digest, str) and _TYPED_DIGEST.fullmatch(archive_digest) is not None, "sing-box Android ARM typed archive digest is invalid")
    return {
        "name": "sing-box",
        "version": version,
        "lock_target": lock_target,
        "archive_size": size,
        "archive_upstream_sha256": upstream_sha256,
        "archive_content_digest": archive_digest,
        "archive_content_digest_algorithm": "blake3-256",
        "archive_content_digest_domain": _SING_BOX_ARCHIVE_DOMAIN,
    }


def _create_phone_runtime_asset(
    *,
    repository_root: Path,
    release_dir: Path,
    tag: str,
    contract_path: Path,
    source_date_epoch: int,
    digest_file: Callable[[Path, str, Path], str],
) -> tuple[str, Path, dict[str, object], str]:
    require(source_date_epoch >= 0, "source date epoch must be non-negative")
    contract = _phone_runtime_contract(contract_path)
    components_raw = _sequence(contract.get("components"), "phone-production runtime components")
    forbidden_raw = _sequence(
        contract.get("forbidden_source_prefixes"),
        "phone-production forbidden source prefixes",
    )
    forbidden_prefixes: list[str] = []
    for raw in forbidden_raw:
        require(isinstance(raw, str) and bool(raw), "phone-production forbidden source prefix is invalid")
        forbidden_prefixes.append(raw)

    components: list[dict[str, object]] = []
    seen_names: set[str] = set()
    seen_archive_paths: set[str] = set()
    with tempfile.TemporaryDirectory(prefix="product-release-phone-runtime-", dir=release_dir) as raw_stage:
        stage = Path(raw_stage) / _PHONE_ARCHIVE_ROOT
        stage.mkdir()
        for raw in components_raw:
            require(isinstance(raw, Mapping), "phone-production runtime component entry is invalid")
            name = raw.get("name")
            kind = raw.get("kind")
            executable = raw.get("executable")
            require(isinstance(name, str) and bool(name), "phone-production runtime component name is invalid")
            require(name not in seen_names, f"phone-production runtime component name is duplicate: {name}")
            require(isinstance(kind, str) and bool(kind), f"phone-production runtime component kind is invalid: {name}")
            require(isinstance(executable, bool), f"phone-production runtime executable flag is invalid: {name}")
            source_rel = _safe_relative_path(raw.get("source"), f"phone-production runtime source: {name}")
            archive_rel = _safe_relative_path(raw.get("archive_path"), f"phone-production runtime archive path: {name}")
            source_text = source_rel.as_posix()
            archive_text = archive_rel.as_posix()
            require(
                not any(source_text.startswith(prefix) for prefix in forbidden_prefixes),
                f"phone-production runtime component uses forbidden source: {source_text}",
            )
            require(
                archive_text not in seen_archive_paths,
                f"phone-production runtime archive path is duplicate: {archive_text}",
            )
            source = repository_root / Path(*source_rel.parts)
            require(source.is_file() and source.stat().st_size > 0, f"phone-production runtime component is missing: {source_text}")
            destination = stage / Path(*archive_rel.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            destination.chmod(0o755 if executable else 0o644)
            digest_name = _PHONE_COMPONENT_DIGEST_PREFIX + archive_text
            digest = digest_file(repository_root, digest_name, source)
            require(_TYPED_DIGEST.fullmatch(digest) is not None, f"phone-production runtime component digest is invalid: {name}")
            components.append(
                {
                    "archive_path": archive_text,
                    "content_digest": digest,
                    "content_digest_algorithm": "blake3-256",
                    "content_digest_domain": _DIGEST_DOMAIN,
                    "executable": executable,
                    "kind": kind,
                    "name": name,
                }
            )
            seen_names.add(name)
            seen_archive_paths.add(archive_text)

        require(bool(components), "phone-production runtime component set is empty")
        components.sort(key=lambda item: str(item["archive_path"]))
        third_party = [_sing_box_identity(repository_root, contract)]
        inventory: dict[str, object] = {
            "components": components,
            "format_version": 1,
            "runtime_abi": dict(_PHONE_ABI),
            "target": _PHONE_TARGET,
            "third_party_runtime": third_party,
        }
        inventory_path = stage / _PHONE_COMPONENT_INVENTORY
        inventory_path.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        inventory_digest_name = _PHONE_COMPONENT_DIGEST_PREFIX + _PHONE_COMPONENT_INVENTORY
        inventory_digest = digest_file(repository_root, inventory_digest_name, inventory_path)
        require(_TYPED_DIGEST.fullmatch(inventory_digest) is not None, "phone-production runtime inventory digest is invalid")

        phone_name = f"mobile-proxy-phone-production-runtime-{tag}.tar.gz"
        phone_path = release_dir / phone_name
        create_archive(stage, phone_path, source_date_epoch)
    require(phone_path.is_file() and phone_path.stat().st_size > 0, "phone-production runtime Release artifact is missing")
    return phone_name, phone_path, inventory, inventory_digest


def create_bundle(
    *,
    repository_root: Path,
    release_dir: Path,
    tag: str,
    source_sha: str,
    android_evidence_path: Path,
    phone_runtime_contract_path: Path,
    source_date_epoch: int,
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
    require(release_dir.is_dir(), "Release directory is missing")
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
    phone_name, phone, phone_inventory, phone_inventory_digest = _create_phone_runtime_asset(
        repository_root=repository_root,
        release_dir=release_dir,
        tag=tag,
        contract_path=phone_runtime_contract_path.resolve(),
        source_date_epoch=source_date_epoch,
        digest_file=digest_file,
    )
    artifact_digests = {
        linux_name: digest_file(repository_root, linux_name, linux),
        apk_name: digest_file(repository_root, apk_name, apk),
        phone_name: digest_file(repository_root, phone_name, phone),
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
        {
            "component_inventory": {
                "content_digest": phone_inventory_digest,
                "content_digest_algorithm": "blake3-256",
                "content_digest_domain": _DIGEST_DOMAIN,
                "path": f"{_PHONE_ARCHIVE_ROOT}/{_PHONE_COMPONENT_INVENTORY}",
            },
            "components": phone_inventory["components"],
            "content_digest": artifact_digests[phone_name],
            "content_digest_algorithm": "blake3-256",
            "content_digest_domain": _DIGEST_DOMAIN,
            "kind": "phone-production-runtime-tar",
            "name": phone_name,
            "runtime_abi": phone_inventory["runtime_abi"],
            "target": _PHONE_TARGET,
            "third_party_runtime": phone_inventory["third_party_runtime"],
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
                "content_digest": artifact_digests[name],
                "content_digest_algorithm": "blake3-256",
                "content_digest_domain": _DIGEST_DOMAIN,
                "name": name,
            }
            for name in (linux_name, apk_name, phone_name)
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
    parser.add_argument("--phone-runtime-contract", type=Path, required=True)
    parser.add_argument("--source-date-epoch", type=int, required=True)
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
            phone_runtime_contract_path=args.phone_runtime_contract,
            source_date_epoch=args.source_date_epoch,
            builder=args.builder,
            workflow_ref=args.workflow_ref,
            github_native_attestation=args.github_native_attestation == "true",
        )
    except (OSError, ReleaseBundleError, ValueError) as exc:
        print(f"Release v2 bundle refused: {exc}", file=__import__("sys").stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
