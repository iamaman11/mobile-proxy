# Foundation identifiers, request lineage and deadlines

## Status

Normative architecture detail for Phase 1. This document must be read together with:

- `ADR-001-bounded-contexts-and-clean-dependencies.md`;
- `ADR-002-cryptographic-hashing-and-kdf-policy.md`;
- `docs/ULTIMATE_IMPLEMENTATION_PLAN.md`.

## Decision

`crates/foundation` owns small, serializable and infrastructure-free primitives shared by application and transport boundaries:

- `RequestId` and `CorrelationId`;
- `CommandId`;
- bounded `ConsumerId`, `ApplicationId` and `ActorId`;
- bounded `IdempotencyKey`;
- absolute `Deadline` and bounded `DeadlineWindow`;
- `RequestContext`;
- BLAKE3-based `ContentDigest` and versioned `DigestDomain`.

The crate validates and formats values but never generates identity, resolves secrets or reads the clock. UUID generation, current time and secret resolution remain ingress/composition/security-adapter responsibilities.

## Compatibility

The newtypes preserve the existing JSON scalar shapes:

- UUID identifiers remain UUID strings;
- idempotency keys remain strings;
- command deadline windows remain JSON numbers.

Existing persisted command queues remain readable. This slice does not rename routes, response fields or public ports.

## Validation rules

### UUID identifiers

UUID-backed identifiers accept canonical UUID input and reject arbitrary strings. They do not expose implicit conversions between unrelated identifiers.

### Consumer, application and actor identifiers

These values:

- are 1–64 bytes;
- use only ASCII letters, digits, `.`, `_`, `-` and `:`;
- reject whitespace, control characters and raw credential material.

### Idempotency keys

Idempotency keys:

- are 1–128 bytes;
- contain only printable non-whitespace ASCII;
- are opaque and case-sensitive;
- are never logged unless explicitly redacted or represented by a safe digest;
- are scoped by consumer, application and operation once those application ports are introduced.

### Deadlines

`DeadlineWindow` is between 1 second and 24 hours. `Deadline` is an absolute Unix-seconds value. Foundation performs arithmetic and expiry comparison against an injected/current boundary value but never reads system time itself.

## HTTP request context

The control-plane accepts optional bounded headers:

```text
x-request-id
x-correlation-id
x-consumer-id
x-application-id
x-actor-id
x-deadline-unix-secs
```

Missing request identity is generated at the authenticated HTTP edge. A missing correlation ID inherits the request UUID. Successful authenticated responses return `x-request-id` and `x-correlation-id`.

Malformed identity, unsupported characters, expired deadlines and deadlines more than 24 hours in the future fail closed with bounded error codes. Raw invalid header values are never returned or logged.

Authentication remains the outer boundary: unauthenticated requests are rejected before parsing or reflecting request lineage.

## Command boundary

Command IDs, idempotency keys and deadline windows are typed across request models, queues, deduplication indexes, path extraction and persistence. Empty idempotency keys, keys over 128 bytes, zero deadlines and deadlines over 24 hours are rejected before command creation.

Typed wrappers serialize identically to the previous scalar values, preserving compatibility while preventing accidental cross-use inside Rust code.

## Digest boundary

Internal content digests use `ContentDigest` and `DigestDomain` under ADR-002:

- output format `b3:<64 lowercase hex>`;
- BLAKE3 derive-key domain separation;
- static versioned context strings;
- `u64` big-endian length framing for every input part;
- complete 256-bit output.

Foundation contains no keyed secret operations. Keyed verification and key rotation belong behind future security ports.

## Enforcement

The permanent architecture validator permits only `serde`, `uuid` and `blake3` in `crates/foundation`. It rejects networking, filesystem, process, environment and clock access, UUID/random generation, async runtimes, persistence frameworks and adapter-specific vocabulary.

## Next extraction

The next Phase 1 slice defines application ports for command issuance and acknowledgement, then moves orchestration and persistence decisions out of Axum handlers without changing the public API.
