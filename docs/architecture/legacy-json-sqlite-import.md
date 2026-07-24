# Legacy JSON to SQLite Import

Status: Phase B migration slice; production runtime cutover remains inactive  
Baseline source: `6c6444810f2c87e00a64a6f365718412be7f4b88`

## Purpose

The production control plane still stores mutable state in one legacy JSON file. The accepted SQLite schema, typed snapshot mapping and atomic snapshot I/O are not sufficient for cutover until representative legacy state can be normalized and imported deterministically without losing pending commands or exact replay behavior.

This slice adds an explicit compatibility importer. It does not connect normal control-plane reads or writes to SQLite.

## Accepted legacy shape

The importer accepts the current persisted JSON inventory only:

- device records keyed by `node_id`;
- per-device pending command queues;
- legacy idempotency claims keyed by `device_id:idempotency_key`;
- optional durable command results;
- optional result-retention order.

Unknown top-level or command-state fields fail closed. Legacy opaque config and binary fingerprints are accepted only through the existing bounded fingerprint compatibility parser and are dropped for typed heartbeat backfill. Unknown algorithm, domain or version prefixes fail closed.

## Deterministic normalization

Before any SQLite write, the importer:

1. validates device and command JSON through canonical types;
2. converts every result key to the BLAKE3 canonical idempotency scope;
3. recovers a missing durable result for every pending command;
4. recovers the exact legacy claim required by every result;
5. rejects conflicting results or claims;
6. removes redundant canonical keys from the legacy claim map;
7. preserves valid canonical retention entries, removes duplicates and appends missing scopes in lexical order;
8. applies the accepted replay bound without evicting a pending result;
9. rejects orphan claims whose original result cannot be reconstructed;
10. constructs and validates one `ControlPlaneSnapshot`.

The resulting snapshot is independent of JSON object ordering.

## Safe target semantics

The source JSON is read-only migration input. The importer never rewrites, renames or deletes it.

`SqliteStore::import_legacy_json` supports only three outcomes:

- empty target plus valid legacy state: atomically import the snapshot;
- target already contains the byte-equivalent canonical snapshot: return `AlreadyImported` without rewriting SQLite;
- target contains any different non-empty state: fail closed without replacement.

After a new import, the store is reloaded and its canonical snapshot bytes must match the normalized source snapshot. A mismatch is reported as a bounded parity failure.

## Evidence

Focused tests prove:

- representative legacy fingerprints, queues and claim-only state normalize and survive file close/reopen;
- missing command results and retention order are reconstructed deterministically;
- legacy and canonical result-key arrangements produce the same canonical snapshot;
- exact import replay is idempotent and does not rewrite SQLite;
- a different non-empty SQLite target is never overwritten;
- conflicting and orphan claims fail closed;
- unsupported fingerprints and malformed JSON fail before any SQLite write.

Permanent CI remains responsible for architecture enforcement, rustfmt, strict Clippy and the full workspace test suite on one unchanged source SHA.

## Compatibility boundary

This importer is an explicit temporary migration adapter. The current control-plane JSON loader remains authoritative until runtime cutover. At cutover, the service must invoke this importer rather than implement a second normalization algorithm; the old JSON normalization path is then retired after the documented rollback window.

## Explicit non-goals

This slice does not:

- switch runtime reads or writes to SQLite;
- modify or delete the source JSON file;
- add dual-write;
- add a CLI activation path;
- change the SQLite schema or table inventory;
- change any endpoint, proxy protocol, public port, tunnel transport or WireGuard rollback behavior;
- claim software rollback, backup/restore or physical-device completion.

## Next bounded slice

The next item is an explicit migration command and read-only diagnostic JSON export, followed by process-level import/restart parity. Runtime cutover remains prohibited until that compatibility and rollback window is exercised.
