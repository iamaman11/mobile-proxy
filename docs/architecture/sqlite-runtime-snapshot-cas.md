# SQLite Runtime Snapshot Compare-and-Swap

Status: Phase B runtime persistence preparation; not active in the production daemon  
Baseline source: `ac70938bbe3f3575715af65e0bfd2382480f1021`

## Purpose

The accepted migration path can import, reopen and diagnostically export complete SQLite state, but normal control-plane mutations still write JSON. Runtime cutover cannot safely reuse whole-snapshot replacement for every request: it would rewrite unrelated rows, enlarge rollback scope and provide no exact stale-writer protection.

This slice adds a typed compare-and-swap persistence primitive. The application remains responsible for producing a validated `expected` snapshot and a validated `candidate` snapshot after applying one business transition. The SQLite adapter only checks authority and applies the relational difference.

## Boundary

`SqliteStore::compare_and_swap_snapshot(expected, candidate)` performs the following inside one `IMMEDIATE` transaction:

1. validate both typed snapshots before opening the transaction;
2. materialize their exact four-relation representations;
3. read the current raw SQLite relations;
4. reject the operation if the current relations differ from `expected`;
5. delete changed or removed rows in foreign-key-safe order;
6. upsert or insert only changed or new rows in dependency order;
7. reread the raw relations and require exact equality with `candidate`;
8. commit and return bounded row-change counts.

A stale expected state, SQL failure or post-write parity mismatch returns an error and drops the transaction. No candidate state is published partially.

## Ownership

The adapter does not decide registration, heartbeat, public-probe, command issuance, acknowledgement, capacity, idempotency or retention behavior. Those transitions remain application-owned. The compare-and-swap boundary receives only the already-decided before/after state and therefore does not introduce a second business implementation.

The returned counts describe persistence work only:

- device rows upserted or deleted;
- command-result rows inserted or deleted;
- idempotency-claim rows inserted or deleted;
- pending-command rows inserted or deleted.

They are bounded diagnostics and do not contain identifiers or payloads.

## Row ordering

Changed or removed rows are deleted in this order:

1. pending commands;
2. idempotency claims;
3. command results;
4. devices.

Changed or new rows are written in this order:

1. devices;
2. command results;
3. idempotency claims;
4. pending commands.

Queue-position changes rewrite only the affected pending rows. An acknowledgement-like candidate deletes the pending row while retaining its replay result and claim. Replay eviction deletes the claim before the result.

## Stale-writer and corruption behavior

The current database is compared against the exact canonical relational representation of `expected`, including serialized typed JSON, digest text, command IDs, request fingerprints and queue positions. A concurrent or externally modified database therefore fails as stale rather than being overwritten.

After writes, the same exact comparison is repeated against `candidate`. Triggers or other database behavior that changes a row during the transaction cause a bounded parity failure and rollback.

## Evidence

Focused tests prove:

- issue-like candidates update one device and insert only the new result, claim and pending row;
- acknowledgement-like candidates remove only pending delivery state and preserve replay evidence;
- replay eviction removes claim and result without rewriting the device;
- queue reorder rewrites pending positions without rewriting replay relations;
- complete deletion respects foreign-key order;
- stale expected state and exact no-op behavior are deterministic;
- a late pending-row insert failure rolls back prior device/result/claim writes;
- post-write trigger drift is detected before commit and rolled back.

Permanent CI remains responsible for architecture enforcement, rustfmt, strict Clippy and the full workspace suite on one unchanged source SHA.

## Explicit non-goals

This slice does not:

- connect the production daemon to SQLite;
- change current JSON writes or reads;
- define application transitions inside the persistence crate;
- use whole-snapshot replacement as a runtime write path;
- change the SQLite schema or table inventory;
- add leases, outbox records, event sourcing or generic jobs;
- change any API, proxy protocol, public port, tunnel transport or WireGuard rollback path;
- complete runtime rollback, backup/restore or physical-device acceptance.

## Next bounded slice

The next item is to route the existing control-plane mutation orchestration through this compare-and-swap boundary behind an explicit SQLite backend selection, while keeping JSON as the unchanged rollback implementation. Production default cutover remains a separate acceptance decision after restart and rollback evidence.
