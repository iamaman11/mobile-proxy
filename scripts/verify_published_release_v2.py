#!/usr/bin/env python3
"""Verify one exact GitHub PRODUCT Release against the local Release v2 bundle.

GitHub's immutable-release digest is an external integrity postcondition. First-party
content identity remains the typed Product Release BLAKE3 contract. Exact remote
asset bytes are compared separately by the workflow before a draft is published,
and GitHub-native release verification is required after publication.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Callable, Mapping, Sequence

try:
    from scripts.create_release_bundle_v2 import typed_asset_digest
except ModuleNotFoundError:
    from create_release_bundle_v2 import typed_asset_digest  # type: ignore[no-redef]

_TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_GITHUB_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_TYPED_DIGEST = re.compile(r"b3:[0-9a-f]{64}")
_DIGEST_DOMAIN = "mobile-proxy/product-release-asset/v2"
_REQUIRED_CONTRACTS = ("release-manifest.json", "provenance.json", "artifact-digests.json")


class PublishedReleaseError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PublishedReleaseError(message)


def _expected_names(tag: str) -> set[str]:
    return {
        f"mobile-proxy-linux-x86_64-{tag}.tar.gz",
        f"mobile-proxy-android-{tag}.apk",
        *_REQUIRED_CONTRACTS,
    }


def _validate_local_typed_digests(
    *,
    repository_root: Path,
    release_dir: Path,
    tag: str,
    digest_file: Callable[[Path, str, Path], str],
) -> None:
    digest_path = release_dir / "artifact-digests.json"
    try:
        value = json.loads(digest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublishedReleaseError("local typed digest set is unavailable or invalid") from exc
    require(isinstance(value, Mapping), "local typed digest set must be an object")
    require(value.get("format_version") == 1, "local typed digest set version differs")
    require(value.get("algorithm") == "blake3-256", "local typed digest algorithm differs")
    require(value.get("digest_domain") == _DIGEST_DOMAIN, "local typed digest domain differs")
    entries_raw = value.get("assets")
    require(
        isinstance(entries_raw, Sequence) and not isinstance(entries_raw, (str, bytes)),
        "local typed digest entries are invalid",
    )
    entries: dict[str, str] = {}
    for raw in entries_raw:
        require(isinstance(raw, Mapping), "local typed digest entry is invalid")
        name = str(raw.get("name", ""))
        digest = str(raw.get("digest", ""))
        require(bool(name) and name not in entries, "local typed digest names are empty or duplicate")
        require(_TYPED_DIGEST.fullmatch(digest) is not None, f"local typed digest is invalid: {name}")
        entries[name] = digest

    covered = _expected_names(tag) - {"artifact-digests.json"}
    require(set(entries) == covered, "local typed digest set coverage differs")
    for name in sorted(covered):
        local = release_dir / name
        require(local.is_file() and local.stat().st_size > 0, f"local Release asset is missing: {name}")
        actual = digest_file(repository_root, name, local)
        require(actual == entries[name], f"local typed digest differs: {name}")


def validate_release(
    release: Mapping[str, object],
    *,
    repository_root: Path,
    tag: str,
    release_dir: Path,
    allow_draft: bool = False,
    digest_file: Callable[[Path, str, Path], str] = typed_asset_digest,
) -> int:
    require(_TAG.fullmatch(tag) is not None, "Release tag is invalid")
    require(release.get("tag_name") == tag, "GitHub Release tag differs")
    require(release.get("prerelease") is False, "GitHub Release is prerelease")
    if allow_draft:
        require(release.get("draft") is True, "recoverable Release must still be draft")
    else:
        require(release.get("draft") is False, "GitHub Release is not published")
        require(release.get("immutable") is True, "published GitHub Release is not immutable")

    ident = release.get("id")
    require(isinstance(ident, int) and not isinstance(ident, bool) and ident > 0, "Release id is invalid")
    assets_raw = release.get("assets")
    require(isinstance(assets_raw, Sequence) and not isinstance(assets_raw, (str, bytes)), "Release assets are invalid")
    assets: dict[str, Mapping[str, object]] = {}
    for raw in assets_raw:
        require(isinstance(raw, Mapping), "Release asset entry is invalid")
        name = str(raw.get("name", ""))
        require(bool(name) and name not in assets, "Release asset names are empty or duplicate")
        assets[name] = raw

    expected_names = _expected_names(tag)
    require(set(assets) == expected_names, "GitHub Release asset set differs from exact v2 bundle")
    release_dir = release_dir.resolve()
    _validate_local_typed_digests(
        repository_root=repository_root.resolve(),
        release_dir=release_dir,
        tag=tag,
        digest_file=digest_file,
    )
    for name in sorted(expected_names):
        local = release_dir / name
        require(local.is_file() and local.stat().st_size > 0, f"local Release asset is missing: {name}")
        asset = assets[name]
        require(asset.get("state") == "uploaded", f"GitHub Release asset is not uploaded: {name}")
        require(
            _GITHUB_DIGEST.fullmatch(str(asset.get("digest", ""))) is not None,
            f"GitHub Release asset lacks platform digest: {name}",
        )
        asset_id = asset.get("id")
        require(
            isinstance(asset_id, int) and not isinstance(asset_id, bool) and asset_id > 0,
            f"GitHub Release asset id is invalid: {name}",
        )
    return ident


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--release-json", type=Path, required=True)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--allow-draft", action="store_true")
    args = parser.parse_args()
    try:
        value = json.loads(args.release_json.read_text(encoding="utf-8"))
        if not isinstance(value, Mapping):
            raise PublishedReleaseError("GitHub Release response is not an object")
        ident = validate_release(
            value,
            repository_root=args.repository_root,
            tag=args.tag,
            release_dir=args.release_dir,
            allow_draft=args.allow_draft,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, PublishedReleaseError) as exc:
        print(f"Release v2 verification refused: {exc}", file=__import__("sys").stderr)
        return 1
    print(f"PRODUCT_RELEASE_V2_VERIFIED release_id={ident}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
