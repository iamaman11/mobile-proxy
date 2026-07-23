#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
from io import BytesIO
from pathlib import Path, PurePosixPath
import tarfile

ARCHIVE_SHA256 = "62b54f210a45cbd26739b57d81e68571ec4e51dc0006b101f7a4898ca14fbfd2"
ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    chunks = sorted((ROOT / ".agent" / "runtime-fingerprint-payload").glob("chunk-*"))
    if len(chunks) != 8:
        raise SystemExit(f"expected 8 payload chunks, found {len(chunks)}")
    encoded = "".join(path.read_text(encoding="ascii").strip() for path in chunks)
    data = base64.b64decode(encoded, validate=True)
    actual = hashlib.sha256(data).hexdigest()
    if actual != ARCHIVE_SHA256:
        raise SystemExit(f"archive digest mismatch: {actual}")
    with tarfile.open(fileobj=BytesIO(data), mode="r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not member.isfile():
                raise SystemExit(f"unsafe archive member: {member.name}")
        archive.extractall(ROOT, members=members, filter="data")
    print(f"applied {len(members)} runtime fingerprint slice files")


if __name__ == "__main__":
    main()
