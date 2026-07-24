# Explicit Control-Plane State Backend Selection

Status: Phase B runtime cutover preparation; JSON remains the production default  
Baseline source: `02031e1481fcfeb5721ee1e57e681ff2ba66059f`

## Purpose

The control plane now has accepted SQLite migration, import/export, snapshot I/O and stale-writer-safe row-level persistence primitives. The running daemon still uses JSON exclusively. The next safe step is an explicit backend switch that exercises the existing application transitions against SQLite without changing the production default or removing the JSON rollback implementation.

## Selection contract

The daemon accepts:

```text
--state-backend json|sqlite
```

and the equivalent `CONTROL_PLANE_STATE_BACKEND` environment variable.

`json` remains the default. Existing deployments that do not set the option continue to use the same state path, legacy normalization, file format and write-before-publication ordering.

`sqlite` is opt-in. The selected state path must already be an existing regular SQLite file produced or validated by the migration utility. A missing path fails startup and is never initialized as an empty database implicitly.

Runtime SQLite access opens the file read-write without the SQLite `CREATE` flag. The current schema version and exact table inventory are verified before WAL or connection settings are established. An empty, unmigrated, removed or replaced path therefore fails closed instead of being initialized or recreated by a request.

The production composition root always calls `load_with_backend` with the parsed selection. The legacy `AppState::load` wrapper is compiled only for tests so production startup cannot bypass backend selection accidentally.

## Shared application behavior

Registration, heartbeat, public-probe updates, command issuance and successful acknowledgement continue to execute the same application-owned transition code. Each transition clones the current in-memory state into an expected snapshot and builds one candidate state.

Persistence then dispatches by backend:

- JSON writes the candidate with the existing synchronized temporary-file replacement;
- SQLite converts expected and candidate into typed snapshots and invokes the accepted row-level compare-and-swap boundary.

Only after the selected backend reports durable success are the device and command mutex projections replaced with the candidate. A persistence error leaves both in-memory projections unchanged.

Read-only command polling continues to use the in-memory projection loaded from the selected canonical backend at startup.

## SQLite startup and rehydration

SQLite startup:

1. requires an existing regular file;
2. opens read-write without permission to create a database;
3. requires the current schema version and exact table inventory without applying migrations;
4. establishes the accepted WAL, foreign-key, synchronous and busy-timeout settings;
5. validates typed relations;
6. reconstructs the legacy-compatible in-memory `CommandState` projection from canonical replay records;
7. validates that legacy claim keys, canonical result keys and retention order are exact.

No JSON file is read or written while SQLite is explicitly selected.

## Stale-writer behavior

The in-process device and command locks serialize mutations. SQLite additionally compares the complete current relations against the expected pre-transition state inside one `IMMEDIATE` transaction. An external writer or second daemon instance therefore causes a bounded persistence failure instead of overwriting newer state.

The failed candidate is not published in memory. Restarting from the SQLite file rehydrates the externally committed canonical state. If the database disappears after startup, later mutations fail without recreating it, including when the expected in-memory state is empty.

## Evidence

Tests prove:

- selecting SQLite with a missing path fails without creating a database;
- an existing but unmigrated empty file is rejected without changing its bytes;
- deleting the selected database after startup makes the next mutation fail without recreating the file or publishing the candidate in memory;
- registration, heartbeat, public probe, issue, exact replay, polling and acknowledgement preserve their existing outcomes;
- pending delivery disappears after acknowledgement while replay survives daemon restart;
- device health and public-probe projections survive restart;
- an external SQLite writer makes a later local mutation fail without publishing the local candidate;
- existing JSON tests continue to exercise the unchanged default backend.

Permanent CI remains responsible for architecture enforcement, rustfmt, strict Clippy and the complete workspace suite on one unchanged source SHA.

## Explicit non-goals

This slice does not:

- change the default backend from JSON;
- automatically import JSON during daemon startup;
- dual-write JSON and SQLite;
- delete, rename or retire a JSON state file;
- add a fallback from SQLite to JSON after startup failure;
- change application transition outcomes or public API shapes;
- change any proxy protocol, public port, tunnel transport or WireGuard rollback path;
- declare production SQLite cutover, rollback completion, backup/restore or physical-device acceptance.

## Next bounded slice

The next item is controlled process-level SQLite backend acceptance and rollback: start the real daemon against migrated SQLite state, execute protected mutation/read paths, restart, then start the previous JSON backend against the preserved source during the compatibility window. The production default may change only after that evidence is accepted.
