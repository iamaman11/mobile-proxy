# Historical Control-Plane SQLite Default Cutover

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
control-plane-state-migrate import   --legacy-json /var/lib/mobile-relaycontrolpoint/control-plane-state.json   --sqlite /var/lib/mobile-relaycontrolpoint/control-plane-state.sqlite3   --diagnostic-json /var/lib/mobile-relaycontrolpoint/control-plane-state-imported.json
```

Rollback of the current release stops the daemon and creates an artifact for the previous accepted release:

```text
control-plane-state-migrate rollback-export   --sqlite /var/lib/mobile-relaycontrolpoint/control-plane-state.sqlite3   --rollback-json /var/lib/mobile-relaycontrolpoint/control-plane-state-rollback.json
```

The previous release, not the current daemon, consumes that rollback artifact. Current requirements and acceptance evidence are defined by the runtime-retirement document linked above.
