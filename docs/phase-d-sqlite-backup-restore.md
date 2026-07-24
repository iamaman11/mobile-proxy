# Phase D SQLite Backup and Restore Drill

Status: delivery item 13 implementation candidate  
Issue: #60  
Scope: canonical SQLite operational recovery only

## Decision

The control plane now has one explicit backup utility for its sole canonical mutable store:

`control-plane-state-backup`

Supported operations:

- `backup --sqlite <source> --backup <artifact>`;
- `verify --sqlite <artifact>`;
- `restore --backup <artifact> --sqlite <clean-target>`.

JSON remains diagnostic and rollback interchange only. Backup and restore use standalone SQLite database artifacts.

## Backup guarantees

Backup:

1. requires an existing regular SQLite source;
2. validates supported schema and rehydrates the complete typed snapshot;
3. rejects overlapping source/target paths and any existing target or temporary artifact;
4. uses SQLite `VACUUM INTO` to materialize one consistent standalone database from the live WAL-backed source;
5. validates the candidate through the same SQLite-only schema and snapshot path;
6. compares canonical typed state before publishing;
7. publishes by atomic rename and syncs the parent directory;
8. preserves the source database unchanged.

## Restore guarantees

Restore:

1. validates the standalone backup before touching the target;
2. requires a clean, absent target path and rejects overwrite;
3. copies into a new temporary artifact and syncs file contents;
4. validates schema and complete typed state on the candidate;
5. requires exact canonical parity with the backup source;
6. atomically publishes into the clean environment and syncs the parent directory;
7. fails closed for missing, corrupt, overlapping or pre-existing targets.

Operation output is one bounded JSON summary containing operation, schema version, inventory counts and artifact size. It does not emit credentials, raw rows or canonical state content.

## Permanent clean-environment drill

`services/control-plane/tests/state_backup_cli.rs` executes the complete operational sequence:

1. create representative canonical SQLite state with device inventory, pending work and replay/idempotency state;
2. create a standalone backup;
3. verify source preservation and exact canonical backup parity;
4. verify the backup through the public CLI;
5. restore into a previously absent clean path;
6. prove exact canonical restored parity;
7. prove repeated restore refuses to overwrite the target;
8. start a real control-plane process against the restored database;
9. require `/readyz` to become ready;
10. read the restored device through the authenticated admin API;
11. poll the restored pending command through the authenticated device API;
12. prove corrupt and overlapping restore inputs fail without creating a target.

## Compatibility and scope boundary

The control-plane runtime remains SQLite-only and retains its existing production path, migration utility, previous-release JSON rollback export and API contracts. Protected proxy ports, QUIC-first transport, certificate-pinned TLS/TCP reserve and WireGuard rollback are unchanged.

No physical phone, release-candidate decision, Android runtime replacement, protocol migration or future-platform scope is introduced.

## Stop condition

After acceptance, delivery item 13 is complete. Proceed only to delivery item 14: immutable-SHA software acceptance and release-candidate closeout before physical-phone acceptance.
