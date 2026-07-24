# Typed Control-Plane Snapshot Mapping

Status: Phase B adapter mapping; production runtime cutover is not active in this slice  
Baseline source: `681646e79958a0d9582a9f6b8cfb12953f6ecb5c`

## Named production risk

The accepted SQLite foundation has an exact four-table schema, while the running control plane still owns a legacy whole-file JSON `StoredState`. Without one typed, fail-closed mapping between the canonical device/command model and those SQLite relations, later read/write or import work could silently drop replay evidence, reorder queues, accept ambiguous links or publish a state that cannot be rehydrated exactly.

## Scope

`mobile-proxy-control-plane-sqlite` now exposes a versioned `ControlPlaneSnapshot` and typed row inventory for:

- complete `DeviceRecord` values keyed by exact `node_id`;
- durable command results keyed by derived idempotency scope and typed `CommandId`;
- one exact request fingerprint claim for every durable result;
- per-device pending commands with explicit contiguous queue positions.

The mapping is an infrastructure adapter representation. It validates relationships already implied by the application idempotency contract; it does not define command transitions or HTTP behavior.

## Fail-closed validation

Rehydration rejects:

- mismatched or duplicate device keys;
- empty device identities;
- command-result row identities or scopes that differ from the serialized command;
- duplicate command IDs or replay scopes;
- missing, extra, duplicate or command-mismatched idempotency claims;
- request fingerprints that do not match the original effective request;
- pending commands with a different row identity, device or serialized result;
- pending commands without durable replay evidence;
- duplicate command IDs or per-device queue positions;
- non-contiguous queue positions, including a queue that does not start at zero;
- global and per-device capacity overflow;
- corrupt JSON, invalid typed identifiers/digests, unknown document fields and unsupported snapshot versions.

Every durable result must have exactly one claim. Every pending command must match one exact durable result. Durable completed results may remain after a pending row is removed so exact replay survives acknowledgement.

## Determinism

The canonical projection uses ordered maps for devices, replay scopes and device queues. Input row order is irrelevant. Serialization emits compact canonical JSON with:

- snapshot format version `1`;
- devices ordered by `node_id`;
- command results and claims ordered by derived scope;
- pending commands ordered by device and queue position.

Round-trip tests prove that valid rows rehydrate to one deterministic byte representation and preserve exact replay evidence and queue order.

## Activation and non-goals

This slice wires the typed API into the SQLite adapter crate but does not yet read or write the database tables through that API. It deliberately does not:

- switch production runtime reads or writes from JSON;
- import or export the legacy JSON file;
- add dual-write or a mutable JSON fallback;
- add schema tables, lease, outbox, event sourcing or future-roadmap concepts;
- change public endpoints, proxy ports, tunnel behavior or the WireGuard rollback path;
- claim restart, rollback, backup/restore or physical-device acceptance.

The next bounded slice is atomic SQLite snapshot write/read, including stale-row cleanup, rollback-on-error and deterministic reopen/rehydration.
