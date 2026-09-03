#!/usr/bin/env python3
"""Verify one exact GitHub PRODUCT Release against the local Release v2 bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Mapping, Sequence

_TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_SHA256 = re.compile(r"sha256:([0-9a-f]{64})")
_REQUIRED_CONTRACTS = ("release-manifest.json", "provenance.json", "SHA256SUMS")


class PublishedReleaseError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PublishedReleaseError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_release(
    release: Mapping[str, object], *, tag: str, release_dir: Path, allow_draft: bool = False
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

    expected_names = {
        f"mobile-proxy-linux-x86_64-{tag}.tar.gz",
        f"mobile-proxy-android-{tag}.apk",
        *_REQUIRED_CONTRACTS,
    }
    require(set(assets) == expected_names, "GitHub Release asset set differs from exact v2 bundle")
    release_dir = release_dir.resolve()
    for name in sorted(expected_names):
        local = release_dir / name
        require(local.is_file() and local.stat().st_size > 0, f"local Release asset is missing: {name}")
        asset = assets[name]
        require(asset.get("state") == "uploaded", f"GitHub Release asset is not uploaded: {name}")
        match = _SHA256.fullmatch(str(asset.get("digest", "")))
        require(match is not None, f"GitHub Release asset lacks SHA-256 digest: {name}")
        require(match.group(1) == sha256(local), f"GitHub Release asset digest differs: {name}")
    return ident


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-json", type=Path, required=True)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--allow-draft", action="store_true")
    args = parser.parse_args()
    try:
        value = json.loads(args.release_json.read_text(encoding="utf-8"))
        if not isinstance(value, Mapping):
            raise PublishedReleaseError("GitHub Release response is not an object")
        ident = validate_release(value, tag=args.tag, release_dir=args.release_dir, allow_draft=args.allow_draft)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, PublishedReleaseError) as exc:
        print(f"Release v2 verification refused: {exc}", file=__import__("sys").stderr)
        return 1
    print(f"PRODUCT_RELEASE_V2_VERIFIED release_id={ident}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
