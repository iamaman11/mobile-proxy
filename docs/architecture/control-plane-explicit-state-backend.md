# Historical Explicit Control-Plane State Backend Selection

Status: accepted historical Phase B compatibility slice; superseded by [`control-plane-sqlite-runtime-retirement.md`](control-plane-sqlite-runtime-retirement.md)
Baseline source: `02031e1481fcfeb5721ee1e57e681ff2ba66059f`

## Historical purpose

This slice temporarily introduced explicit `json|sqlite` runtime selection so SQLite application behavior could be exercised before the production cutover. At that time JSON remained the default and both persistence implementations were reachable from the daemon composition root.

It proved existing migrated-file requirements, SQLite schema validation, row-level compare-and-swap, restart behavior and failure-before-publication without changing the then-current default.

## Superseding decision

The compatibility window is closed for the current binary. The production daemon is SQLite-only, `--state-backend` is retired, and JSON runtime loading/writing is no longer owned by the daemon.

JSON remains only in migration and export tooling. `rollback-export` creates current state for the previous accepted release; it is not an alternate backend for the current release. Current startup and rollback requirements are defined only by the runtime-retirement document linked above.
