# Phase A Closeout and Reassessment

Status: accepted closeout decision  
Baseline `main`: `d3b783eaf524bfea6fef92e1d32f5c76ec23873a`  
Completed delivery item: Phase A closeout and reassessment

## Decision

Phase A is complete. Development may proceed to the first bounded Phase B item: SQLite schema and transaction boundary.

This decision does not expand the Production Baseline Plan. The delivery order, protected compatibility surface, explicit non-goals and stop conditions remain unchanged.

## Evidence reviewed

The closeout was performed against repository state rather than chat history or an external checkpoint.

- device registration enters through `RegisterDevicePort`;
- command issuance, polling and acknowledgement enter through typed command application ports;
- heartbeat enters through `HeartbeatPort`;
- public probe enters through `PublicProbePort`;
- the current mutating Axum handlers authenticate, decode input, invoke one application use case and map bounded outcomes;
- transport handlers do not own canonical persistence ordering, idempotency classification or direct canonical state mutation;
- durable JSON-era mutations persist the complete candidate before publishing the corresponding in-memory projection;
- protected request and response behavior remains compatible;
- no speculative bounded context or additional governance framework was introduced.

The final Phase A production slice was PR #33, `Extract public-probe application port`.

- accepted source: `883abecb550949ece783456af393b1a250dc28ce`;
- squash merge: `d3b783eaf524bfea6fef92e1d32f5c76ec23873a`;
- permanent `Rust Quality` run: `30060074913`;
- workflow conclusion: successful;
- review submissions: none;
- inline review threads: none;
- unresolved P0/P1 defects identified by the Phase A closeout: none.

## Risk closed

Before Phase A, HTTP transport handlers could own canonical mutation and persistence sequencing. That made behavior harder to test independently and made future persistence replacement more likely to create ordering regressions.

The current mutation inventory now enters through explicit application ports, preserving the architecture invariants that transport handlers remain thin and authoritative behavior has one owner.

## Reassessment result

The remaining demonstrated production risk is JSON as the canonical mutable control-plane store. Whole-file replacement is recoverable only within narrow assumptions and does not provide the transactional foundation required for durable command, replay and device-state evolution.

Proceeding to Phase B is therefore proportionate. The first Phase B slice is limited to SQLite schema and transaction-boundary foundation.

## Exact next slice

The next slice must:

1. introduce SQLite with WAL, foreign keys, a bounded busy timeout and explicit schema migrations;
2. define only the closed baseline inventory required by the working application;
3. establish transaction boundaries that commit durable state before any in-memory publication;
4. add focused tests for migration application, schema-version rejection, transaction commit and rollback behavior;
5. preserve all existing proxy ports, protocols, tunnel transports, operator surfaces and JSON-era runtime behavior until a later approved migration slice.

## Explicit non-goals for the next slice

The next slice must not:

- switch the production canonical store from JSON to SQLite;
- import or delete existing JSON state;
- remove the rollback path to the previous release;
- add lease, identity, rotation, credential, audit-ledger, outbox or event-sourcing tables;
- introduce gRPC, a first-party Android tunnel runtime or a new bounded context;
- change public request or response schemas;
- add a generic governance framework merely to support the storage change.

A later slice may activate SQLite as canonical only after the schema and transaction foundation is accepted on one immutable SHA and the Production Baseline delivery order authorizes the device and command-state migration.