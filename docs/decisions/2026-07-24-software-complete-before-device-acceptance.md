# Decision: Complete the software baseline before physical-device acceptance

Status: accepted product and execution decision  
Decision date: 2026-07-24  
Baseline `main`: `e8ce5be9cfc0c8eb05ea05945e3bdda423e6183c`

## Demonstrated reason

The current development environment can implement, compile and exercise repository, process, persistence, migration, recovery, backup/restore and controlled tunnel behavior, but it is not expected to have a physical phone attached.

Treating device absence as a blocker for earlier work would leave the application in an unnecessarily transitional state, including JSON as the production canonical store, even though those changes can be proved independently through deterministic tests and process-level acceptance.

## Decision

All software-completable Production Baseline work must be completed now, including:

- typed device and command-state mapping;
- deterministic JSON import and parity validation;
- production runtime cutover so SQLite is the only canonical mutable store;
- read-only JSON diagnostic export during the compatibility window;
- tested software rollback and restore procedures;
- pending-stream lifecycle and capacity verification;
- exact device/session binding verification;
- controlled QUIC-to-TLS/TCP failover and recovery tests using repository/process test infrastructure;
- liveness/readiness separation and durable-store health reporting;
- clean-environment SQLite backup/restore drills;
- an immutable software release-candidate closeout with an executable physical-device runbook.

Physical-phone acceptance remains required for final baseline completion, but it is the sole deferred external gate. It must not block implementation or merge of the preceding software work.

## Invariant impact

No compatibility, state, routing, security or architecture invariant is weakened.

Operational acceptance is split into two explicit states:

1. `software-complete release candidate` — all source-controlled and process-testable criteria pass on one immutable SHA;
2. `baseline complete` — the physical-phone sequence also passes on the immutable candidate SHA, or on a later immutable SHA after all software evidence is rerun.

The prohibition on combining acceptance evidence from different source revisions remains unchanged.

## Added scope

Only the following planning and evidence scope is added:

- an explicit software-complete release-candidate checkpoint;
- a source-controlled physical-device acceptance script/runbook;
- clarification that controlled process-level tunnel failover evidence is completed before the physical confirmation run.

## Removed scope

No product capability is removed. Physical-device acceptance is not removed or weakened; it is isolated as the final external gate.

## Compatibility, migration and rollback impact

- Public proxy ports, protocols, API schemas and tunnel precedence remain unchanged.
- SQLite runtime cutover is now explicitly required before device access is available.
- JSON remains migration input and read-only diagnostic export after cutover, not a second mutable source of truth.
- Rollback must be exercised with representative state before the software-complete checkpoint.
- Any code change after software closeout invalidates the immutable candidate evidence and requires the relevant software suite to be rerun before physical acceptance.

## Non-goals

This decision does not activate any item from `docs/future/`, add a first-party Android runtime, replace WireGuard, create a fleet rollout platform or relax the requirement for final physical-phone evidence.
