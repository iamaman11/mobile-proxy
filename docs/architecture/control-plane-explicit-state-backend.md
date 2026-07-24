# Explicit Control-Plane State Backend Selection

Status: accepted historical Phase B slice; superseded for current defaults by [`control-plane-sqlite-default-cutover.md`](control-plane-sqlite-default-cutover.md)  
Baseline source: `02031e1481fcfeb5721ee1e57e681ff2ba66059f`

## Historical purpose

This slice introduced the explicit `json|sqlite` runtime selection while JSON was still the production default. It was intentionally a pre-cutover compatibility step: the running daemon could exercise the accepted SQLite migration and row-level compare-and-swap implementation without yet changing implicit production startup.

The current backend default, backend-specific paths, activation procedure and rollback procedure are defined only by the default-cutover document linked above.

## Accepted selection boundary

The daemon accepts `--state-backend json|sqlite` and `CONTROL_PLANE_STATE_BACKEND`. Unknown values are rejected during CLI parsing before state access.

The production composition root always passes the parsed backend to `AppState::load_with_backend`. Runtime SQLite access:

1. requires an existing regular file;
2. opens read-write without the SQLite `CREATE` flag;
3. requires the supported schema version and exact table inventory without applying migrations;
4. enables the accepted WAL, foreign-key, synchronous and busy-timeout settings;
5. validates typed relations and reconstructs the application projection.

Missing, empty, unsupported, corrupt, removed or replaced SQLite state therefore fails closed. Runtime access does not import JSON, create a database, apply migrations, fall back or dual-write.

## Shared application behavior

Registration, heartbeat, public-probe updates, command issuance and successful acknowledgement execute the same application-owned transitions for both implementations.

- JSON persists the candidate through synchronized temporary-file replacement.
- SQLite converts the expected and candidate states into typed snapshots and invokes row-level compare-and-swap.

Only a successful durable write publishes the candidate in memory. A persistence failure leaves the previous in-memory projection unchanged.

## Accepted evidence

Tests proved:

- explicit SQLite selection rejects missing and unmigrated paths without creating or changing them;
- deleting the selected database after startup causes later mutation failure without recreating the file or publishing the candidate;
- registration, heartbeat, public probe, issue, exact replay, polling and acknowledgement preserve application outcomes;
- pending delivery disappears after acknowledgement while replay survives restart;
- device health and public-probe projections survive restart;
- external SQLite drift fails without stale local publication;
- the then-default JSON implementation retained its existing behavior.

## Historical non-goals

This slice did not change the default backend, perform process-level cutover acceptance, automatically import or delete JSON, add fallback or dual-write, change API/proxy/tunnel behavior, or claim rollback, backup/restore or physical-device completion.
