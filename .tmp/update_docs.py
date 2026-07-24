from pathlib import Path

root = Path.cwd()
(root / "docs/architecture/control-plane-sqlite-runtime-retirement.md").write_text('''# Control-Plane SQLite-Only Runtime and Previous-Release Rollback

Status: final Phase B runtime-retirement slice; Phase B closeout remains separate  
Baseline source: `93ba1c5b77a2f7e95d3a85ee797cddf5005963c3`

## Named production risk

SQLite was already the implicit canonical backend, but the current daemon still accepted an explicit JSON runtime selection. That retained a second mutable implementation beyond the intended compatibility window and conflicted with the post-Phase-B invariant that JSON is migration input or export output only.

## Runtime contract

The current `control-plane` daemon is SQLite-only.

- the only state option is `--state-path` or `CONTROL_PLANE_STATE_PATH`;
- the default path is `/var/lib/mobile-relaycontrolpoint/control-plane-state.sqlite3`;
- the path must already be an existing regular SQLite database produced or validated by the migration utility;
- `--state-backend` and `CONTROL_PLANE_STATE_BACKEND` are retired;
- a retired backend argument is rejected during CLI parsing before state access;
- startup never creates a missing database, imports JSON, applies migrations, falls back or dual-writes.

The application state owner loads only SQLite and every candidate mutation uses the accepted row-level compare-and-swap transaction before the in-memory projection is published. JSON loading, JSON runtime writing, backend dispatch and daemon-owned legacy fingerprint migration are removed from production composition.

## Migration and rollback boundary

JSON remains supported only by `control-plane-state-migrate`:

- `import` consumes the preserved legacy JSON source and creates or validates canonical SQLite state;
- `export` writes the typed read-only diagnostic snapshot format;
- `rollback-export` writes the latest SQLite state in the exact JSON contract consumed by the previous accepted release.

The current daemon does not consume `rollback-export`. A production rollback therefore stops the SQLite-only daemon, creates a current-state rollback artifact and starts the previous accepted release against that artifact. This preserves rollback without carrying a second mutable backend in the new binary.

## Permanent acceptance evidence

The process suite uses compiled binaries and authenticated TCP HTTP requests to prove:

1. a missing SQLite database fails startup without creating state;
2. the retired `--state-backend json` option is rejected before state access;
3. representative legacy JSON imports deterministically into SQLite while the source remains unchanged;
4. the SQLite-only daemon reads pending state, acknowledges it, terminates and restarts;
5. pending removal, exact replay and conflicting replay survive restart;
6. `rollback-export` materializes the latest post-mutation state;
7. that previous-release artifact round-trips through the accepted importer into a second SQLite database;
8. the round-tripped state preserves device inventory, pending removal, exact replay and conflict behavior;
9. no JSON runtime daemon path, fallback or dual-write is exercised or available.

Unit and adapter tests continue to prove stale-writer rejection, fail-closed schema handling, bounded state, transaction-before-publication and unchanged application outcomes through SQLite.

## Compatibility and non-goals

This slice does not change API shapes, authentication, application outcomes, public proxy ports `1080`, `1081` or `3128`, QUIC-first transport, certificate-pinned TLS/TCP reserve or WireGuard rollback. It does not change the SQLite schema, remove migration/export tooling, implement backup/restore, advance Phase C or claim physical-device acceptance.

## Next bounded slice

Perform final Phase B closeout and reassessment. The closeout must verify that SQLite is the sole runtime mutable store, JSON is limited to migration/diagnostic/rollback artifacts, permanent CI is accepted on one immutable source SHA, no P0/P1 defect remains and the protected compatibility surface is unchanged. Only that decision may authorize Phase C pending-stream lifecycle and bounds.
''')

(root / "docs/architecture/control-plane-explicit-state-backend.md").write_text('''# Historical Explicit Control-Plane State Backend Selection

Status: accepted historical Phase B compatibility slice; superseded by [`control-plane-sqlite-runtime-retirement.md`](control-plane-sqlite-runtime-retirement.md)  
Baseline source: `02031e1481fcfeb5721ee1e57e681ff2ba66059f`

## Historical purpose

This slice temporarily introduced explicit `json|sqlite` runtime selection so SQLite application behavior could be exercised before the production cutover. At that time JSON remained the default and both persistence implementations were reachable from the daemon composition root.

It proved existing migrated-file requirements, SQLite schema validation, row-level compare-and-swap, restart behavior and failure-before-publication without changing the then-current default.

## Superseding decision

The compatibility window is closed for the current binary. The production daemon is SQLite-only, `--state-backend` is retired, and JSON runtime loading/writing is no longer owned by the daemon.

JSON remains only in migration and export tooling. `rollback-export` creates current state for the previous accepted release; it is not an alternate backend for the current release. Current startup and rollback requirements are defined only by the runtime-retirement document linked above.
''')

(root / "docs/architecture/control-plane-sqlite-default-cutover.md").write_text('''# Historical Control-Plane SQLite Default Cutover

Status: accepted historical Phase B cutover slice; superseded by [`control-plane-sqlite-runtime-retirement.md`](control-plane-sqlite-runtime-retirement.md)  
Baseline source: `74de2fbf429b052db115ff1f34e4e7c5d1e3eb7c`

## Historical purpose

This slice changed the implicit daemon backend from JSON to SQLite, introduced the canonical `.sqlite3` default path, preserved fail-closed startup and added `rollback-export` so acknowledged SQLite-era operations could be represented for the previous JSON release.

During that bounded cutover window, explicit JSON runtime selection remained available in the new binary. Process acceptance proved SQLite mutation/restart/replay and explicit rollback from an export of the latest state.

## Superseding decision

The current daemon is now SQLite-only. Backend selection and JSON runtime loading/writing are retired. The canonical state path is:

```text
/var/lib/mobile-relaycontrolpoint/control-plane-state.sqlite3
```

Activation still requires an explicit stopped-source import from the preserved legacy JSON file:

```text
control-plane-state-migrate import \
  --legacy-json /var/lib/mobile-relaycontrolpoint/control-plane-state.json \
  --sqlite /var/lib/mobile-relaycontrolpoint/control-plane-state.sqlite3 \
  --diagnostic-json /var/lib/mobile-relaycontrolpoint/control-plane-state-imported.json
```

Rollback of the current release stops the daemon and creates an artifact for the previous accepted release:

```text
control-plane-state-migrate rollback-export \
  --sqlite /var/lib/mobile-relaycontrolpoint/control-plane-state.sqlite3 \
  --rollback-json /var/lib/mobile-relaycontrolpoint/control-plane-state-rollback.json
```

The previous release, not the current daemon, consumes that rollback artifact. Current requirements and acceptance evidence are defined by the runtime-retirement document linked above.
''')

(root / "docs/architecture/control-plane-sqlite-process-acceptance.md").write_text('''# Historical Control-Plane SQLite Process Acceptance

Status: accepted historical Phase B process-evidence slice; superseded by [`control-plane-sqlite-runtime-retirement.md`](control-plane-sqlite-runtime-retirement.md)  
Baseline source: `f88746574640de66a415b4e498fcba713ea89805`

## Historical purpose

Before SQLite became the production default, this slice exercised migration, the real daemon, authenticated HTTP reads and mutation, process termination, restart, exact replay, conflicting replay and JSON compatibility through compiled binaries.

The preserved pre-cutover JSON proved compatibility but became stale after SQLite accepted later writes. The subsequent default-cutover slice therefore added `rollback-export` for current state.

## Superseding decision

The current daemon no longer exposes JSON compatibility. SQLite is its sole runtime mutable store and the retired backend option is rejected before state access.

The current process suite retains and strengthens the accepted evidence: it proves SQLite-only restart/replay, fail-closed startup, retired-option rejection, current-state rollback export and round-trip validation of the previous-release artifact without starting a JSON backend in the current binary.
''')

p = root / "RUNTIME_LAYOUT.md"
s = p.read_text().replace(
    "  - `/var/lib/mobile-relaycontrolpoint/control-plane-state.json`",
    "  - `/var/lib/mobile-relaycontrolpoint/control-plane-state.sqlite3` (canonical runtime)\n"
    "  - `/var/lib/mobile-relaycontrolpoint/control-plane-state.json` (preserved migration input only)",
)
p.write_text(s)

p = root / "TEN_OUT_OF_TEN_VALIDATION_PLAN.md"
s = p.read_text().replace(
    "control-plane state exists at `/var/lib/mobile-relaycontrolpoint/control-plane-state.json` after registration/heartbeat and survives service restart",
    "control-plane state exists at `/var/lib/mobile-relaycontrolpoint/control-plane-state.sqlite3` after explicit migration, registration/heartbeat and service restart; a missing or invalid database fails startup without JSON fallback",
)
p.write_text(s)

p = root / "RUST_ONLY_ULTIMATE_PLAN.md"
s = p.read_text().replace(
    "Current state: control-plane loads and persists registry/command state as JSON at `CONTROL_PLANE_STATE_PATH`, defaulting to `/var/lib/mobile-relaycontrolpoint/control-plane-state.json`.",
    "Current state: control-plane loads and persists registry/command state only in the existing SQLite database at `CONTROL_PLANE_STATE_PATH`, defaulting to `/var/lib/mobile-relaycontrolpoint/control-plane-state.sqlite3`; JSON is limited to migration and export artifacts.",
)
p.write_text(s)
