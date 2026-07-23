#!/usr/bin/env python3
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "apps/operator-cli/src/provision.rs"
body = path.read_text(encoding="utf-8")
old = (
    "use crate::release_integrity::{\n"
    "    RELEASE_INTEGRITY_MANIFEST, verify_integrity_manifest, write_integrity_manifest,\n"
    "};\n"
)
new = (
    "use crate::release_integrity::{verify_integrity_manifest, write_integrity_manifest};\n"
)
if body.count(old) != 1:
    raise RuntimeError(f"expected one release integrity import, found {body.count(old)}")
path.write_text(body.replace(old, new, 1), encoding="utf-8")
