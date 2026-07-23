#!/usr/bin/env python3
from pathlib import Path

path = Path(__file__).with_name("apply_blake3_internal_migration.py")
body = path.read_text(encoding="utf-8")

body = body.replace(
    "- [ADR-002: Cryptographic Hashing and KDF Policy](docs/architecture/ADR-002-cryptographic-hashing-and-kdf-policy.md)\\n",
    "- [ADR-002: Cryptographic Hashing, Password Hashing and KDF Policy](docs/architecture/ADR-002-cryptographic-hashing-and-kdf-policy.md)\\n",
)

old_block = '''replace_once(
    "docs/ULTIMATE_IMPLEMENTATION_PLAN.md",
    "Foundation primitives and cryptographic digest decisions are normative in [Foundation Primitives](architecture/foundation-primitives.md) and [ADR-002](architecture/ADR-002-cryptographic-hashing-and-kdf-policy.md).\\n",
    "Foundation primitives and cryptographic digest decisions are normative in [Foundation Primitives](architecture/foundation-primitives.md), [ADR-002](architecture/ADR-002-cryptographic-hashing-and-kdf-policy.md) and the [Digest Inventory and Migration Matrix](architecture/digest-inventory-and-migration.md).\\n",
)
'''
new_block = '''replace_once(
    "docs/ULTIMATE_IMPLEMENTATION_PLAN.md",
    "Cryptographic primitives are selected by purpose, not by crate preference. New internal content and deterministic digests use full BLAKE3-256 values with algorithm prefixes, versioned domain separation, canonical input bytes and length framing. SHA-256 remains for TLS certificate pinning, standardized artifact/signature formats, FIPS profiles and existing external or persisted compatibility contracts. Passwords use Argon2id; standard protocols retain their specified HMAC, HKDF, signature and AEAD algorithms. Algorithm migration is a versioned data-contract migration and never a blind search-and-replace. The normative rules are in [ADR-002](architecture/ADR-002-cryptographic-hashing-and-kdf-policy.md).\\n",
    "Cryptographic primitives are selected by purpose, not by crate preference. All first-party internal persisted digests migrate to full BLAKE3-256 values with algorithm prefixes, versioned domain separation, canonical input bytes and length framing; legacy internal SHA-256 is transitional only and must not be newly produced. SHA-256 remains for TLS certificate pinning, standardized artifact/signature formats, FIPS profiles and external compatibility contracts. Passwords use Argon2id; standard protocols retain their specified HMAC, HKDF, signature and AEAD algorithms. Algorithm migration is a versioned data-contract migration and never a blind search-and-replace. The normative rules are in [ADR-002](architecture/ADR-002-cryptographic-hashing-and-kdf-policy.md) and the [Digest Inventory and Migration Matrix](architecture/digest-inventory-and-migration.md).\\n",
)
'''
if old_block not in body:
    raise RuntimeError("expected Ultimate Plan replacement block was not found")
body = body.replace(old_block, new_block, 1)
path.write_text(body, encoding="utf-8")
