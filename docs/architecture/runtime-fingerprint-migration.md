# Runtime config and binary fingerprint migration

Status: production migration contract  
Owner: runtime and security  
Target fields: `config_fingerprint`, `binary_fingerprint`

## Inventory before migration

### Producers

- `config_fingerprint` had no production producer. Host-daemon heartbeats always sent `null`.
- `binary_fingerprint` was supplied through `HOST_DAEMON_BINARY_FINGERPRINT`; when absent the host daemon produced the opaque literal `reconstructed`.

### Readers and API surfaces

- host-daemon authenticated `GET /v1/health` returned `binary_fingerprint` as a JSON string;
- the host-daemon control-plane heartbeat sent both fields as optional JSON strings;
- control-plane device list/read responses returned both fields as optional JSON strings;
- operator CLI status and relay device probing deserialize those control-plane/host records.

### Persistence and comparisons

The control plane persists both fields inside `DeviceRecord` in its existing JSON state file. There are no database columns, indexes, equality gates, deduplication keys, identifiers, signatures, audit-chain links or cursor contracts derived from either fingerprint. No deployment script reads either value. The only deployment input was the removed binary-fingerprint environment variable.

This absence of identity/index dependencies permits value backfill without rewriting references. It does not permit silently changing the JSON representation.

## Target contracts

Both fields retain their existing JSON scalar shape:

```json
{
  "config_fingerprint": "b3:<64 lowercase hex>",
  "binary_fingerprint": "b3:<64 lowercase hex>"
}
```

The field type fixes the domain and version. A `b3:` value in `config_fingerprint` is interpreted only as `mobile-proxy/host-daemon-nonsecret-config/v1`; a `b3:` value in `binary_fingerprint` is interpreted only as `mobile-proxy/host-daemon-binary/v1`. The wire value does not carry a user-selectable context.

### Config fingerprint v1

Domain:

```text
mobile-proxy/host-daemon-nonsecret-config/v1
```

Canonical source bytes are produced from the exact host-daemon JSON configuration source after:

1. rejecting invalid JSON, trailing values and duplicate object keys;
2. recursively sorting object keys;
3. retaining array order, scalar types and deterministic JSON number encoding;
4. replacing credential-bearing fields with the fixed literal `<redacted>` before hashing;
5. serializing compact canonical JSON;
6. applying typed `ContentDigest` BLAKE3 derive-key mode and unsigned 64-bit big-endian length framing.

The non-secret domain name is intentional. Admin, device, tunnel, proxy and private-key material is not placed into an unkeyed public digest. Changes to non-secret effective configuration change the fingerprint; secret rotation does not.

When host-daemon starts without a configuration file, `config_fingerprint` remains `null`. CLI/environment overrides are not included in v1; changing that semantic requires a new domain version.

### Binary fingerprint v1

Domain:

```text
mobile-proxy/host-daemon-binary/v1
```

The input is the exact running host-daemon executable bytes. Linux and Android read `/proc/self/exe`, binding the value to the executing inode rather than a potentially replaced path. Other supported targets use the resolved current executable path. The bytes are passed directly to typed `ContentDigest`; no legacy digest is re-hashed.

## Typed boundaries

`ConfigFingerprint` and `BinaryFingerprint` are separate typed wrappers around `ContentDigest`. Canonical persisted `DeviceRecord` fields use those types. Heartbeat and health transport boundaries use isolated migration-input wrappers so a rolling deployment can temporarily read bounded legacy opaque strings.

The legacy adapter accepts only non-empty, printable, unprefixed values up to 256 bytes. It rejects:

- malformed `b3:` values;
- uppercase or truncated BLAKE3 text;
- any other algorithm/domain/version prefix;
- whitespace, controls and oversized values.

Legacy values are never converted into BLAKE3 and are never persisted by new code. Canonical device readers drop accepted legacy values to `null`, allowing a new operator or relay to read an old control-plane response without treating the old value as trustworthy.

## Backfill and observability

At control-plane startup, the isolated migration adapter scans only the two fields in persisted device records:

- valid typed values are preserved byte-for-byte;
- bounded unprefixed legacy values are replaced with `null`;
- non-string or unknown-prefixed values fail startup closed;
- removal counts are logged as fixed field-specific counters without logging raw values;
- the normalized state is written through a synchronized temporary file and atomic rename;
- a restart sees no remaining legacy values, making the migration idempotent.

The next typed host heartbeat backfills both current values. Legacy heartbeat values may be accepted during the rolling window, but they are logged only as booleans and are not written to canonical state.

## Rollout and rollback

Recommended rollout order:

1. deploy the new control plane;
2. deploy operator/relay readers;
3. deploy host daemon producers;
4. verify every active device reports two typed values or an intentionally absent config value;
5. retain the isolated legacy reader for the bounded compatibility window;
6. remove it in a separate accepted slice.

Rollback remains compatible because the serialized representation is still an optional JSON string. Previous binaries deserialize new `b3:` values as opaque strings and accept `null` after legacy cleanup. No port, route, proxy protocol, tunnel selection, certificate pin, TLS digest or externally standardized digest changes.

## Acceptance evidence

Permanent tests must prove:

- field-specific domains produce different values for the same bytes;
- exact lowercase `b3:` parsing is fail-closed;
- config canonicalization is order-independent, duplicate-key rejecting and secret-independent;
- binary changes change the binary fingerprint;
- old opaque health/heartbeat/device values remain readable only through the migration adapter;
- legacy persisted values are removed once and stay removed across restart;
- current values retain the existing JSON string shape;
- unknown prefixes fail at both API and persistence boundaries;
- the legacy environment producer and raw `String` field declarations cannot return through the permanent digest policy gate.
