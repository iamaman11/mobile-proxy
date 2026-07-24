# Control-Plane SQLite Process Acceptance and JSON Compatibility

Status: accepted historical Phase B process-evidence slice; superseded for current defaults and rollback operations by [`control-plane-sqlite-default-cutover.md`](control-plane-sqlite-default-cutover.md)  
Baseline source: `f88746574640de66a415b4e498fcba713ea89805`

## Historical purpose

This slice proved the complete operator path through real compiled processes before SQLite became the production default. At acceptance time JSON remained implicit and SQLite required explicit selection.

The current cutover contract additionally proves omitted backend selection, fail-closed default startup and rollback from an export of the latest SQLite state. Those current requirements are defined only by the default-cutover document linked above.

## Threatened invariants

- SQLite startup uses only an existing explicitly migrated database;
- authenticated mutation success survives daemon termination and restart;
- acknowledgement removes pending delivery without removing durable replay evidence;
- exact replay after restart returns the original result;
- conflicting idempotency reuse fails closed;
- the preserved JSON migration source remains independently readable during the compatibility window;
- neither path introduces dual-write or fallback behavior.

## Accepted process sequence

The permanent integration test used compiled binaries and TCP HTTP requests to:

1. write fully normalized JSON state with a device, pending command, durable result, compatibility claim and retention order;
2. invoke `control-plane-state-migrate import` in a subprocess;
3. prove the source JSON remained byte-for-byte unchanged;
4. start the real daemon with explicit SQLite selection;
5. read device and pending-command state through authenticated routes;
6. acknowledge the command and terminate the process;
7. restart on the same SQLite database;
8. prove pending removal, exact replay and HTTP `409` for conflicting replay;
9. start the real daemon with explicit JSON selection against the preserved source and prove compatibility readability.

This evidence used the production CLI, bearer authentication middleware, HTTP routes, migration binary and persistence implementations rather than an in-process router.

## Evidence boundary

The preserved pre-cutover JSON demonstrated compatibility but becomes stale once SQLite accepts later writes. It is not the current-state rollback artifact after cutover. The accepted default-cutover procedure therefore stops SQLite, exports the latest canonical snapshot to a new JSON file and starts explicit JSON rollback from that export.

## Historical non-goals

This slice did not change the default backend, prove omitted-backend startup, export current SQLite state for rollback, add automatic migration/fallback/dual-write, delete JSON, change proxy or tunnel behavior, claim backup/restore completion, or close Phase B.
