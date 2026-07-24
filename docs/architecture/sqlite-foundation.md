# SQLite Schema and Transaction Foundation

Status: Phase B foundation; not active as the production canonical store  
Baseline source: `d4b1cdcdec684ad00f6564ddde7d95d65064bf7f`

## Purpose

The current control plane persists its complete mutable state as one JSON file. The first Phase B slice introduces a bounded SQLite persistence foundation so later migration work can use explicit transactions without mixing schema design, JSON import and runtime cutover in one change.

This slice does not wire SQLite into `control-plane`. JSON remains the only production canonical mutable store until the later migration and rollback slices are separately accepted.

## Ownership and dependency direction

`mobile-proxy-control-plane-sqlite` is an infrastructure adapter crate. It owns SQLite connection configuration, schema migration and durable transaction mechanics. It does not own command, device, replay or routing business decisions.

The crate accepts already-validated identifiers and canonical JSON records from future application adapters. It contains no Axum, Android, tunnel or operator-surface dependencies.

## Connection contract

Every file-backed store establishes:

- WAL journal mode;
- foreign-key enforcement;
- a bounded five-second busy timeout;
- `FULL` synchronous durability;
- explicit `PRAGMA user_version` migration state.

A database with a schema version newer than the supported version fails closed with a bounded error. Version `0` is migrated atomically to version `1`; reopening version `1` is idempotent.

## Closed version 1 inventory

The schema contains exactly four application tables:

1. `devices` — one canonical serialized device record per `node_id`;
2. `command_results` — the durable original command result used for exact replay evidence;
3. `idempotency_claims` — the request fingerprint bound to one exact command result;
4. `pending_commands` — ordered pending delivery records bound to durable command results.

No lease, identity, rotation, credential, audit-ledger, outbox, event-sourcing or generic job table is present.

`PRAGMA user_version` is the only schema metadata in this slice. The adapter validates that the supported table inventory is exact after migration.

## Transaction boundary

`SqliteStore::write` begins an `IMMEDIATE` transaction and exposes only bounded inventory operations through `WriteTransaction`.

The caller receives success only after SQLite commit succeeds. Any closure error, constraint failure or dropped transaction rolls back all prior writes in the candidate. A future runtime adapter must update its in-memory projection only after `SqliteStore::write` returns success.

The schema deliberately fails closed on conflicting replay evidence:

- `scope_key` and `command_id` are unique in durable command results;
- an idempotency claim must reference the exact matching durable result;
- a pending command must reference an existing durable command result;
- per-device queue positions are unique;
- arbitrary replacement of claims or command results is not exposed by the transaction API.

## Evidence

Focused tests prove:

- file-backed WAL, foreign keys, busy timeout and schema version;
- idempotent reopen of the accepted schema;
- rejection of a future schema version;
- atomic commit of device, result, claim and pending-command state;
- restart persistence of the committed candidate;
- rollback of earlier writes when a later foreign-key operation fails;
- fail-closed conflicting replay evidence;
- pending-command deletion within the same write boundary while durable replay evidence remains.

The permanent workspace workflow remains responsible for architecture validation, formatting, strict Clippy and all Rust tests on one unchanged SHA.

## Explicit non-goals

This slice does not:

- switch production reads or writes from JSON to SQLite;
- import, export or delete JSON state;
- add a dual-write path or a second runtime source of truth;
- expose a generic SQL connection to application code;
- define application state transitions inside the persistence crate;
- change any HTTP shape, proxy port, protocol, tunnel transport or operator behavior;
- claim backup, restore or rollback acceptance;
- activate any future-roadmap bounded context.

## Next bounded slice

After this foundation is accepted, the next delivery item remains device and command-state migration. That work must define the adapter mapping, prove deterministic import and restart parity, preserve the read-only JSON diagnostic/rollback window and avoid publishing any in-memory state before the SQLite transaction commits.