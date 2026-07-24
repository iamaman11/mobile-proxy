# Control-Plane SQLite Default Cutover and JSON Rollback

Status: Phase B production-default cutover; Phase B closeout remains separate  
Baseline source: `74de2fbf429b052db115ff1f34e4e7c5d1e3eb7c`

## Named production risk

SQLite migration, row-level compare-and-swap and real daemon process acceptance are already proven, but JSON remaining the implicit default would leave normal production writes on the legacy mutable store. Changing only the enum default without a backend-specific path contract or a current-state rollback procedure would create ambiguous startup behavior and could lose acknowledged SQLite-era operations during rollback.

## Selection and path contract

The daemon continues to accept `--state-backend json|sqlite` and `CONTROL_PLANE_STATE_BACKEND`.

- no backend selection means `sqlite`;
- default SQLite state path is `/var/lib/mobile-relaycontrolpoint/control-plane-state.sqlite3`;
- explicit `json` selection uses `/var/lib/mobile-relaycontrolpoint/control-plane-state.json` when no state path is supplied;
- `--state-path` or `CONTROL_PLANE_STATE_PATH` overrides the backend-specific default path;
- unknown backend values fail during CLI parsing.

SQLite remains fail closed. Runtime startup requires an existing regular database produced or validated by the migration utility. The daemon does not create a missing database, run migrations, import JSON automatically, fall back to JSON or dual-write.

JSON is no longer an implicit production backend. It remains available only through explicit rollback selection.

## Activation procedure

1. Stop the JSON-backed control-plane process before migration so the source cannot change during import.
2. Preserve the existing JSON source at its current path.
3. Import it into a distinct SQLite target and publish a distinct diagnostic export:

```text
control-plane-state-migrate import \
  --legacy-json /var/lib/mobile-relaycontrolpoint/control-plane-state.json \
  --sqlite /var/lib/mobile-relaycontrolpoint/control-plane-state.sqlite3 \
  --diagnostic-json /var/lib/mobile-relaycontrolpoint/control-plane-state-imported.json
```

4. Require a successful bounded import report and verify that the source JSON remains unchanged.
5. Start the new control plane. With the canonical paths above, no backend or state-path argument is required; explicit `--state-backend sqlite` is equivalent.
6. Verify authenticated device inventory, pending delivery and one durable mutation/restart path before considering activation successful.

A missing, empty, unsupported or corrupt SQLite target stops startup. Operators must repair or repeat the explicit migration; the daemon never chooses JSON automatically.

## Current-state rollback procedure

The preserved pre-cutover JSON is migration evidence, not a safe rollback source after SQLite accepts new writes. Starting it after post-cutover mutations could discard acknowledged operations.

To roll back without losing current canonical state:

1. Stop the SQLite-backed daemon so the export observes a stable source.
2. Export the latest SQLite snapshot atomically to a new JSON path:

```text
control-plane-state-migrate export \
  --sqlite /var/lib/mobile-relaycontrolpoint/control-plane-state.sqlite3 \
  --diagnostic-json /var/lib/mobile-relaycontrolpoint/control-plane-state-rollback.json
```

3. Start the rollback implementation explicitly:

```text
control-plane \
  --state-backend json \
  --state-path /var/lib/mobile-relaycontrolpoint/control-plane-state-rollback.json
```

4. Verify device inventory, pending-command state, exact replay and conflicting replay before reopening normal traffic.

The rollback export is a separate artifact. The original migration source is not overwritten, and no automatic reverse migration occurs during daemon startup.

## Permanent acceptance evidence

The process test uses compiled production binaries and TCP HTTP requests to prove:

- omitted backend selection starts SQLite against a migrated database;
- omitted backend selection with a missing database exits and does not create the path;
- authenticated reads and acknowledgement work through the default backend;
- acknowledgement and durable replay survive process restart;
- conflicting idempotency reuse still returns HTTP `409`;
- the latest SQLite state exports to canonical JSON after the mutation;
- explicit JSON rollback starts from that current-state export;
- the acknowledged command remains absent while exact replay and conflict behavior remain intact;
- the preserved original JSON source remains byte-for-byte unchanged.

## Compatibility and non-goals

This cutover does not change API shapes, authentication, application transition outcomes, proxy ports, QUIC/TLS tunnel behavior or the WireGuard rollback path. It does not add automatic migration, fallback, dual-write, JSON deletion, backup/restore completion or physical-device acceptance.

## Next bounded slice

Perform Phase B closeout and reassessment against the canonical plan. The closeout must verify that SQLite is the only normal mutable store, the documented current-state rollback is exercised, no unresolved P0/P1 defect remains, and the protected compatibility surface is unchanged. Only then may work advance to Phase C pending-stream lifecycle and bounds.
