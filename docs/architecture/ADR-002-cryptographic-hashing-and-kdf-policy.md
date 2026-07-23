# ADR-002: Cryptographic hashing, password hashing and KDF policy

- **Status:** Accepted
- **Scope:** Entire `mobile-proxy` repository and every future bounded context
- **Decision owner:** Architecture
- **Applies to:** persisted identifiers, fingerprints, integrity checks, credentials, authentication, protocols, artifacts and release evidence

## Context

The project needs one explicit rule for cryptographic primitives. Choosing a hash independently in each crate creates incompatible persisted formats, accidental security misuse, difficult migrations and ambiguous incident response. BLAKE3 is an excellent Rust-native primitive for internal hashing, but it is not a universal replacement for standardized SHA-256, password hashing, signatures, MACs or encryption.

This ADR is normative. New code must follow it. An exception requires a separate ADR that identifies the external contract, threat model, migration and rollback plan.

## Decision summary

| Purpose | Required default | Notes |
| --- | --- | --- |
| Internal content/config/binary fingerprint | BLAKE3-256 | Full 32-byte output; serialized as `b3:<64 lowercase hex>` |
| Internal deterministic identity or deduplication digest | BLAKE3 `derive_key` mode | Mandatory versioned domain separation and length framing |
| Internal keyed integrity for high-entropy secrets/tokens | Keyed BLAKE3 | Only behind a security port; key ID and rotation metadata required |
| Password or human passphrase storage | Argon2id | Salted, memory-hard; never BLAKE3 or plain SHA-256 |
| Standard protocol KDF/MAC | Algorithm required by that protocol | For example HKDF or HMAC; do not substitute BLAKE3 silently |
| TLS certificate pinning and standardized certificate fingerprints | SHA-256 | Preserve published pin formats and ecosystem compatibility |
| OCI, SBOM, signature, package or third-party digest contract | Algorithm required by the format | Usually SHA-256 unless the standard explicitly supports another algorithm |
| FIPS-required deployment | Approved algorithm selected by the compliance profile | BLAKE3 is not assumed to be FIPS-approved |
| Digital signatures | A reviewed signature algorithm | BLAKE3 is not a signature scheme |
| Encryption | A reviewed AEAD construction | BLAKE3 is not encryption |
| Non-security corruption checksum | Explicit checksum type | CRC may be used only when clearly non-security-sensitive |

## 1. Internal default: BLAKE3

BLAKE3 is the default for new, internal, non-standardized digests because it has a maintained Rust implementation, streaming support, parallel/SIMD implementations, keyed hashing, key derivation and a 256-bit default output.

The default applies to:

- canonical configuration fingerprints;
- binary and deployment fingerprints owned by this project;
- descriptor fingerprints;
- deterministic record, conflict and deduplication identities;
- cache keys;
- immutable payload integrity digests;
- audit payload digests when no external algorithm is mandated.

The default does **not** authorize arbitrary direct calls to `blake3::hash`. Shared production code should use typed wrappers from `mobile-proxy-foundation` or a security adapter so formatting, domain separation and migrations remain consistent.

## 2. Canonical digest format

New internal digests use:

```text
b3:<64 lowercase hexadecimal characters>
```

The prefix is mandatory. Bare hex is forbidden for newly persisted or public fields because it loses the algorithm identity.

External SHA-256 values use their existing standard format. Where the project owns the field and no external format dictates otherwise, use:

```text
sha256:<64 lowercase hexadecimal characters>
```

A digest field must never rely on its Rust type name alone for persisted algorithm identification. Persist either an algorithm-prefixed string or a schema containing explicit `algorithm` and `value` fields.

The default output is the complete 256-bit digest. Truncation requires a documented collision analysis and must never be below 128 bits. Security tokens and fencing values should normally retain the full 256 bits.

## 3. Domain separation

Every deterministic internal digest must have a static, versioned context string:

```text
mobile-proxy.<bounded-context>.<purpose>.v<version>
```

Examples:

```text
mobile-proxy.lease.fencing-token.v1
mobile-proxy.proxy.descriptor.v1
mobile-proxy.runtime.config-fingerprint.v1
mobile-proxy.audit.entry-payload.v1
```

Rules:

1. Context strings are compile-time literals, never user-controlled input.
2. Changing canonical input semantics requires a new context version.
3. The same context must not be reused for unrelated values.
4. Security-key derivation contexts and public content-digest contexts must be distinct.

For BLAKE3 deterministic digests, use `Hasher::new_derive_key(context)` rather than prepending an informal text label to the payload.

## 4. Input framing and canonicalization

Hashing raw concatenation is forbidden. Each input part is framed as:

```text
u64 big-endian byte length || bytes
```

This prevents ambiguous sequences such as `("ab", "c")` and `("a", "bc")` from sharing the same input stream.

Structured data must be converted to a versioned canonical byte representation before hashing. Requirements include:

- deterministic field ordering;
- deterministic number and timestamp representation;
- explicit treatment of absent versus null fields;
- no map iteration order dependence;
- no platform path, locale or newline dependence;
- canonical encoding version included in the digest context or schema.

Pretty JSON, debug output and non-canonical serialization are not valid digest inputs.

## 5. Keyed hashing and API tokens

High-entropy bearer tokens, refresh tokens, one-time secrets and similar credentials must not be stored as plaintext when comparison can be performed using a verifier.

The internal default verifier is keyed BLAKE3 behind a security port. Requirements:

- the key is exactly 32 bytes of high-entropy secret material;
- raw key material is resolved through a credential/KMS adapter and never persisted with the digest;
- persisted records include a key identifier and verifier algorithm/version;
- comparison is constant-time;
- rotation supports dual verification during a bounded migration window;
- logs and errors never contain raw tokens or complete verifier values.

Use HMAC-SHA-256 instead when an external protocol, interoperability contract or FIPS profile requires it. Do not hash a low-entropy password with keyed BLAKE3 as a substitute for Argon2id.

## 6. Passwords and passphrases

Passwords and human-generated passphrases use Argon2id with a unique random salt and reviewed memory/time/parallelism parameters. Parameters are stored with the verifier and may be upgraded on successful authentication.

Forbidden password constructions include:

- BLAKE3(password);
- SHA-256(password);
- repeated fast hashes;
- unsalted hashes;
- encryption used as a password verifier.

## 7. KDF, MAC, signatures and encryption

BLAKE3 `derive_key` may derive subkeys only from high-entropy key material inside a project-owned protocol, using a versioned context and an architecture/security review.

When a protocol specifies HKDF, HMAC, TLS exporters or another KDF/MAC, use the specified algorithm exactly. Algorithm substitution breaks interoperability and can invalidate the protocol security proof.

BLAKE3 does not replace:

- Ed25519, ECDSA or other digital signatures;
- XChaCha20-Poly1305, ChaCha20-Poly1305 or AES-GCM encryption;
- certificate validation;
- password hashing;
- random-number generation.

## 8. SHA-256 compatibility boundary

SHA-256 remains required where it is part of an external or already published contract, including:

- TLS certificate/SPKI pinning and certificate fingerprints;
- OCI image and artifact digests;
- SBOM and provenance formats;
- package ecosystem checksums;
- signature formats;
- third-party APIs;
- FIPS-approved deployment profiles;
- previously persisted identifiers whose semantics cannot change silently.

Existing SHA-256 usages are not mass-rewritten. Each usage must be classified before migration as one of:

1. **External/standardized:** retain SHA-256.
2. **Persisted compatibility:** retain or migrate with dual-read/dual-write and versioned fields.
3. **Internal replaceable:** migrate to the typed BLAKE3 format in a dedicated production slice.
4. **Security misuse:** remediate immediately with the correct primitive.

## 9. Migration rules

Algorithm migration is a data-contract migration, not a refactor.

A migration must define:

- old and new algorithm identifiers;
- old and new canonical input bytes;
- read/write behavior during the transition;
- collision/conflict handling;
- replay and idempotency semantics;
- rollback behavior;
- retention and deletion of legacy digests;
- tests using persisted fixtures from the previous version.

Never recompute and overwrite an existing identifier in place if references, signatures, audit chains, cursors or idempotency claims depend on it.

## 10. Prohibited primitives and patterns

The following are forbidden for security-sensitive use:

- MD5;
- SHA-1;
- `DefaultHasher` or implementation-defined Rust hashes;
- CRC/adler checksums;
- unkeyed fast hashing of bearer tokens;
- fast hashing of passwords;
- bare unversioned hex digest strings;
- raw concatenation of fields;
- user-controlled domain-separation contexts;
- logging keys, tokens, passwords or full credential verifiers.

## 11. Rust implementation rules

1. `mobile-proxy-foundation::ContentDigest` is the default typed internal digest.
2. Foundation validates and formats values but does not generate keys, random IDs or read the clock.
3. Secret-bearing keyed operations belong behind security ports/adapters, not in domain crates.
4. Domain crates may depend on typed digest values but not on KMS, filesystem, networking or environment access.
5. Crates must not add a new cryptographic dependency without documenting its purpose and checking this ADR.
6. Digest comparisons involving secret verifiers must be constant-time.
7. Every persisted digest has an algorithm/version marker.

## 12. CI and review enforcement

The architecture validator enforces pure-crate dependencies and rejects random generation or clock access inside foundation/domain code. Follow-up CI slices must maintain an inventory of direct cryptographic dependencies and reject unapproved algorithms or bare digest formats.

Code review for any cryptographic change must answer:

- What is the threat model?
- Is the value secret, low-entropy, public or externally standardized?
- Is the digest persisted or externally visible?
- What is the domain-separation context and canonical encoding version?
- How are keys generated, stored, rotated and identified?
- How will old data be read and rolled back?

## Consequences

### Positive

- BLAKE3 becomes the clear high-performance Rust-native default for internal digests.
- SHA-256 compatibility remains deliberate rather than accidental.
- Password hashing, token verification, MAC, KDF, signature and encryption use cases cannot be conflated.
- Persisted values are self-describing and migration-safe.
- Future bounded contexts share one canonical implementation and review vocabulary.

### Trade-offs

- The repository temporarily contains both BLAKE3 and SHA-256.
- External/FIPS deployments may not use the internal default everywhere.
- Algorithm upgrades require explicit migrations instead of search-and-replace changes.

## 14. First-party persisted digest migration

All existing first-party internal persisted digest contracts are migration targets for BLAKE3-256. The earlier compatibility exception applies only while a concrete legacy reader or backfill is required; it is not permission to create new SHA-256 data.

The authoritative inventory and migration state is maintained in [Digest Inventory and Migration Matrix](digest-inventory-and-migration.md). New internal SHA-256 producers are rejected by the permanent architecture gate. External standardized boundaries, Cargo registry checksums, TLS pinning profiles and compliance-specific algorithms remain outside this internal migration.

Migration must recompute from canonical source bytes. `BLAKE3(SHA256(data))` is a digest of the legacy digest and is not equivalent to `BLAKE3(data)`.
