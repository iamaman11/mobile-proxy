#!/usr/bin/env python3
"""Create a byte-reproducible gzip-compressed GNU tar release archive."""

from __future__ import annotations

import argparse
import gzip
import os
import stat
import tarfile
from pathlib import Path


def _normalized_mode(path: Path) -> int:
    if path.is_symlink():
        return 0o777
    if path.is_dir():
        return 0o755
    return 0o755 if path.stat().st_mode & stat.S_IXUSR else 0o644


def create_archive(root: Path, output: Path, source_date_epoch: int) -> None:
    root = root.resolve(strict=True)
    output = output.resolve()
    if not root.is_dir():
        raise ValueError("release root must be a directory")
    if source_date_epoch < 0:
        raise ValueError("source date epoch must be non-negative")
    if output == root or root in output.parents:
        raise ValueError("archive output must be outside the release root")
    if not root.name or root.name in {".", ".."}:
        raise ValueError("release root name is invalid")

    paths = [root, *sorted(root.rglob("*"), key=lambda path: path.as_posix())]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(
                fileobj=compressed,
                mode="w",
                format=tarfile.GNU_FORMAT,
            ) as archive:
                for path in paths:
                    if not (
                        path.is_symlink() or path.is_file() or path.is_dir()
                    ):
                        raise ValueError(f"unsupported archive entry: {path}")
                    relative = path.relative_to(root.parent).as_posix()
                    info = archive.gettarinfo(str(path), arcname=relative)
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mtime = source_date_epoch
                    info.mode = _normalized_mode(path)
                    if path.is_file() and not path.is_symlink():
                        with path.open("rb") as body:
                            archive.addfile(info, body)
                    else:
                        archive.addfile(info)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-date-epoch", type=int, required=True)
    args = parser.parse_args()
    create_archive(args.root, args.output, args.source_date_epoch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
