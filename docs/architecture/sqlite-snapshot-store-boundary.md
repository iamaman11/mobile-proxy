# SQLite Snapshot Store Boundary

Status: Phase B migration/storage slice; not active as the production runtime store  
Baseline source: `e8f8345e49e3d61c4eb4d5f6b47d265dde15807f`

## Purpose

The accepted SQLite schema and typed control-plane snapshot mapping now have an explicit persistence boundary. This slice proves that the complete closed baseline inventory can be written to and rehydrated from the four accepted SQLite relations without losing replay evidence, changing pending queue order or publishing a partially written candidate.

The running control plane is not switched to SQLite by this change. JSON remains the production canonical mutable store until deterministic import, parity validation, compatibility export and runtime cutover are accepted separately.

## Public boundary

`SqliteStore` exposes two typed operations:

- `replace_snapshot(&ControlPlaneSnapshot)` validates the complete candidate and replaces all four relations inside one `IMMEDIATE` SQLite transaction;
- `load_snapshot()` reads the four relations in deterministic order, parses typed identifiers and JSON records, and applies the accepted cross-relation snapshot validation before returning state.

The boundary accepts and returns domain/application types. Raw SQL rows, generic connections and unvalidated JSON are not exposed to callers.

Whole-snapshot replacement is approved only for migration, import and bounded parity/recovery workflows. It is not the per-request production mutation design and must not be used as a high-frequency runtime write path.

## Atomic replacement order

The transaction deletes existing rows in foreign-key-safe order:

1. pending commands;
2. idempotency claims;
3. durable command results;
4. devices.

It inserts the candidate in dependency order:

1. devices;
2. durable command results;
3. idempotency claims;
4. pending commands.

Success is returned only after commit. A SQL constraint, trigger, serialization or commit failure drops the transaction and preserves the previous complete snapshot.

## Fail-closed rehydration

Reads are ordered by canonical keys and reject:

- malformed `DeviceRecord` or `DeviceCommand` JSON;
- invalid BLAKE3 digest text;
- invalid command UUID text;
- queue positions outside the supported `u32` range;
- missing, duplicated or mismatched cross-table relations;
- changed request fingerprints, command identities, device bindings or queue order.

Database foreign keys remain the first protection layer. Typed snapshot validation remains mandatory so state also fails closed if corruption was introduced while foreign-key enforcement was bypassed externally.

## Evidence

Focused tests prove:

- exact snapshot persistence, file reopen and canonical rehydration parity;
- deterministic pending queue order after restart;
- complete deletion of relations omitted by a replacement candidate;
- rollback of all deletes and partial inserts when a later pending-command insert fails;
- rejection of malformed typed JSON and invalid digest text;
- rejection of cross-table corruption even when it was inserted with foreign keys disabled.

Permanent CI remains responsible for architecture enforcement, rustfmt, strict Clippy and the full workspace suite on one unchanged source SHA.

## Explicit non-goals

This slice does not:

- connect `services/control-plane` to SQLite;
- perform JSON import, dual-write or diagnostic JSON export;
- define per-request runtime mutation transactions;
- change any HTTP endpoint, proxy protocol, public port, tunnel transport or WireGuard rollback path;
- add tables, schema versions, lease concepts, outbox records or event sourcing;
- claim restart durability for the running service, rollback completion, backup/restore or physical-device acceptance.

## Next bounded slice

The next delivery item is deterministic import of the normalized legacy JSON state into this typed boundary, followed by canonical parity validation and restart proof. Runtime cutover remains prohibited until that import path and the read-only diagnostic/rollback compatibility window are accepted.
