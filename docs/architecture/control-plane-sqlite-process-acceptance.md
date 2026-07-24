# Control-Plane SQLite Process Acceptance and JSON Rollback

Status: Phase B runtime cutover evidence; production default remains JSON  
Baseline source: `f88746574640de66a415b4e498fcba713ea89805`

## Named production risk

The control plane can explicitly select a pre-migrated SQLite backend and its unit-level tests prove restart and stale-writer behavior, but the complete operator path had not yet been exercised through real daemon processes. Changing the production default without process-level evidence could hide CLI wiring, authentication, HTTP lifecycle, restart or rollback defects that in-process tests cannot expose.

## Threatened invariants

- SQLite startup must use only an existing, explicitly migrated database;
- authenticated mutation success must survive daemon termination and restart;
- acknowledgement must remove pending delivery without removing durable replay evidence;
- exact replay after restart must return the original result;
- conflicting reuse of the same idempotency key must fail closed;
- the preserved JSON source must remain independently startable as the rollback implementation during the compatibility window;
- neither acceptance path may create dual-write or fallback behavior.

## Accepted process sequence

The permanent integration test performs the following sequence through compiled binaries and TCP HTTP requests:

1. write one fully normalized JSON state containing a device, pending command, durable result, legacy compatibility claim and canonical retention order;
2. invoke `control-plane-state-migrate import` in a subprocess;
3. verify the source JSON remains byte-for-byte unchanged and the diagnostic export is created;
4. start the real `control-plane` binary with `--state-backend sqlite` and authenticated admin/device tokens;
5. read the device inventory and pending command through HTTP;
6. acknowledge the command through HTTP and terminate the process;
7. restart the daemon on the same SQLite database;
8. verify pending delivery is absent, exact replay returns the original command and conflicting replay returns HTTP `409`;
9. terminate SQLite runtime and verify the preserved JSON source is still unchanged;
10. start the real daemon with `--state-backend json` against that preserved source and verify the device and pending command remain readable;
11. terminate the rollback process and verify the source remains byte-for-byte unchanged.

This evidence uses the same application routes, bearer authentication middleware, CLI parsing, migration binary and persistence implementations that production composition uses. It does not simulate the daemon through an in-process router.

## Compatibility result

No API shape, protected proxy surface, tunnel transport, WireGuard rollback path or application transition changes in this slice. JSON remains the default runtime backend. SQLite remains explicit and requires a preexisting migrated file. The test dependency is development-only.

## Explicit non-goals

This slice does not:

- change the default backend to SQLite;
- automatically import JSON during daemon startup;
- dual-write JSON and SQLite;
- delete or rename the preserved JSON source;
- add fallback after SQLite startup or persistence failure;
- claim backup/restore completion;
- change proxy, tunnel or physical-device behavior;
- close Phase B by itself.

## Next bounded slice

After this process evidence is accepted, make SQLite the production default canonical mutable backend while keeping JSON available only through explicit rollback selection during the compatibility window. That cutover must require an existing migrated SQLite file, preserve fail-closed startup, document deployment activation and rollback, and prove the permanent quality suite on one unchanged source SHA. Phase B closeout remains separate until the default cutover and exercised rollback criteria are satisfied.
