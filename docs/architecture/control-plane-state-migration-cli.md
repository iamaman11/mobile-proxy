# Control-Plane State Migration Utility

Status: Phase B compatibility and process-acceptance slice; production daemon cutover remains inactive  
Baseline source: `53fd1e9ccbf377a87b2208a52a30a7d516652df4`

## Purpose

The deterministic legacy JSON importer is accepted, but an operator still needs an explicit, separately executable path to invoke it and inspect the resulting SQLite state. Embedding migration implicitly in normal daemon startup before process-level acceptance would combine migration, runtime cutover and rollback risk.

This slice adds `control-plane-state-migrate` as a separate binary target in the existing control-plane package. The normal `control-plane` daemon entry point, state path and JSON-backed behavior are unchanged.

## Commands

### Import

```text
control-plane-state-migrate import \
  --legacy-json <source.json> \
  --sqlite <target.sqlite3> \
  --diagnostic-json <canonical.json>
```

The command:

1. rejects overlapping input, database and output paths;
2. reads and fully normalizes the legacy JSON before opening the SQLite target;
3. invokes the accepted empty-target/exact-replay/conflict import contract;
4. reloads the SQLite snapshot after import;
5. writes its canonical snapshot JSON atomically;
6. prints one bounded JSON report containing counts, outcome and migration counters.

The legacy source is never rewritten, renamed or deleted. A failed import does not publish a new diagnostic document and does not modify a previously published diagnostic document.

### Export

```text
control-plane-state-migrate export \
  --sqlite <source.sqlite3> \
  --diagnostic-json <canonical.json>
```

The command requires an existing regular SQLite source file, loads and validates its complete snapshot, writes canonical JSON atomically and prints only bounded inventory counts. A missing or non-file source fails closed without creating a new database or diagnostic document. The export is diagnostic output, not a second mutable source of truth.

## Atomic diagnostic publication

Diagnostic output is written to a sibling temporary file, synchronized, renamed into place and followed by a parent-directory synchronization on Unix. A failed write never publishes a partial canonical document. Input, database and output paths must be distinct.

## Process-level evidence

Integration tests invoke the compiled binary as separate operating-system processes and prove:

- representative legacy JSON imports into a new SQLite file;
- source JSON bytes remain unchanged;
- the diagnostic document equals a fresh SQLite rehydration byte-for-byte;
- a second import process returns `already_imported`;
- a later export process produces the same canonical bytes;
- importing different state into a non-empty target fails without changing the database or prior diagnostic;
- malformed or unsupported legacy input fails before the SQLite file is created;
- a missing export source fails without creating a database or diagnostic document;
- overlapping paths fail before any file is accessed.

This is process-level migration and restart evidence, but it is not production runtime cutover evidence.

## Security and observability

The utility prints no device record body, command body, token, proxy URL or unbounded error payload. Reports contain only operation class, bounded outcome, inventory counts, canonical byte length and migration counters. Detailed failures remain in the process error chain for operator execution and are not exposed through a network endpoint.

## Explicit non-goals

This slice does not:

- change the normal daemon startup command;
- make SQLite the production canonical mutable store;
- add dual-write;
- delete or retire the legacy JSON source;
- define per-request SQLite mutation boundaries;
- complete the rollback compatibility window;
- change any API, proxy protocol, public port, tunnel transport or WireGuard rollback path;
- claim backup/restore or physical-device completion.

## Next bounded slice

The next delivery item is the production composition cutover preparation: wire the daemon to choose SQLite only through an explicit migration-complete state, preserve read-only diagnostic export, and prove restart plus rollback behavior before JSON writes are disabled. Runtime cutover must remain a separately accepted slice.
