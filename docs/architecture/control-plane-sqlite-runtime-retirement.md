# Control-Plane SQLite-Only Runtime and Previous-Release Rollback

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
