# Atomic SQLite Snapshot I/O

Status: Phase B infrastructure adapter slice; production runtime cutover is not active  
Baseline source: `e8f8345e49e3d61c4eb4d5f6b47d265dde15807f`

## Named production risk

The accepted SQLite schema and typed snapshot mapping do not by themselves prove that one complete control-plane state can be replaced and reloaded atomically. Independent row writes or non-transactional reads could expose a mixture of old and new devices, replay claims and pending queues, while stale rows could survive a smaller replacement.

## Scope

`SqliteStore` gains two typed adapter operations:

- `replace_snapshot` validates a complete `ControlPlaneSnapshot`, deletes the prior four-relation inventory in foreign-key-safe order and writes the candidate in one `BEGIN IMMEDIATE` transaction;
- `load_snapshot` reads all four relations in one deferred transaction, parses every identifier, digest and JSON payload into canonical types, then applies the existing cross-relation snapshot validation before returning any state.

## Atomicity and failure behavior

A replacement transaction performs:

1. delete pending commands;
2. delete idempotency claims;
3. delete durable command results;
4. delete devices;
5. insert devices;
6. insert command results;
7. insert idempotency claims;
8. insert pending commands;
9. commit once.

Any serialization, SQLite constraint, trigger or commit failure rolls back the complete candidate, including preceding deletes. A successful smaller snapshot therefore removes every stale row; a failed candidate leaves the previously committed snapshot byte-equivalent after rehydration.

A load fails closed for:

- malformed typed JSON despite syntactically valid SQLite JSON;
- invalid `CommandId`, BLAKE3 scope or request fingerprint text;
- queue positions outside the supported `u32` range;
- any missing, duplicated, mismatched or non-contiguous relation rejected by `ControlPlaneSnapshot`.

No partially decoded state is returned.

## Evidence

Focused tests cover:

- loading a valid empty database;
- complete snapshot replacement, close, reopen and byte-exact canonical rehydration;
- stale relation cleanup after replacing a populated snapshot with an empty one;
- forced database failure after delete initiation with full rollback to the prior snapshot;
- corrupt typed relation values failing closed during load.

## Non-goals

This slice does not:

- connect SQLite to the running control-plane service;
- import, dual-write or remove the legacy JSON state file;
- alter schema version `1` or add tables;
- change command semantics, HTTP endpoints, proxy ports, tunnel behavior or WireGuard rollback;
- claim process restart, backup/restore, rollback or physical-device acceptance.

The next bounded slice is a startup-only legacy JSON import into an empty SQLite store with deterministic equivalence checks and no ongoing dual-write.
