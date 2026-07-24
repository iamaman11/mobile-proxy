# Historical Control-Plane SQLite Process Acceptance

Status: accepted historical Phase B process-evidence slice; superseded by [`control-plane-sqlite-runtime-retirement.md`](control-plane-sqlite-runtime-retirement.md)
Baseline source: `f88746574640de66a415b4e498fcba713ea89805`

## Historical purpose

Before SQLite became the production default, this slice exercised migration, the real daemon, authenticated HTTP reads and mutation, process termination, restart, exact replay, conflicting replay and JSON compatibility through compiled binaries.

The preserved pre-cutover JSON proved compatibility but became stale after SQLite accepted later writes. The subsequent default-cutover slice therefore added `rollback-export` for current state.

## Superseding decision

The current daemon no longer exposes JSON compatibility. SQLite is its sole runtime mutable store and the retired backend option is rejected before state access.

The current process suite retains and strengthens the accepted evidence: it proves SQLite-only restart/replay, fail-closed startup, retired-option rejection, current-state rollback export and round-trip validation of the previous-release artifact without starting a JSON backend in the current binary.
