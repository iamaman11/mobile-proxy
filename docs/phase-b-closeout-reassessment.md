# Phase B Closeout Reassessment

Status: closeout blocked by one bounded compatibility residue  
Baseline `main`: `129a81bd2a4a12cb069025e57dfb3e799caf921a`  
Delivery item under review: Phase B closeout and reassessment

## Decision

Phase B is not yet closed. The SQLite durability, migration, default cutover and current-state rollback evidence satisfy the implementation completion criteria, but the current control-plane binary still exposes JSON as an alternate runtime backend.

The canonical plan's post-Phase-B state invariant is stricter: SQLite is canonical and JSON is migration input or diagnostic export only. Keeping a JSON runtime writer after declaring Phase B complete would preserve a second mutable implementation beyond the compatibility window and contradict the one-owner rule.

Development is therefore authorized for one final bounded Phase B slice: retire JSON from the current runtime while retaining deterministic JSON import, diagnostic export and current-state `rollback-export` for the previous release.

## Evidence reviewed

The reassessment was performed against current repository state and accepted GitHub evidence.

- SQLite schema migrations, WAL, foreign keys, bounded busy timeout and exact table inventory are accepted;
- device state, pending commands, durable command results, idempotency claims and replay evidence are represented in the closed SQLite inventory;
- application mutations construct one candidate, commit the selected durable state and publish in-memory projections only after success;
- representative JSON import and parity validation are deterministic and tested;
- missing, unsupported, corrupt or replaced SQLite state fails closed;
- daemon-process acceptance proves acknowledgement, restart, exact replay and conflicting replay through SQLite;
- SQLite is the implicit runtime default and the default path requires an existing migrated database;
- `rollback-export` materializes the latest SQLite state into the previous release's JSON runtime contract;
- explicit JSON rollback was exercised after SQLite-era mutation and restart;
- no lease, outbox, event-sourcing or future-roadmap persistence table was introduced;
- protected ports `1080`, `1081` and `3128`, QUIC-first behavior, TLS/TCP reserve and WireGuard rollback were not changed.

The final cutover slice was PR #46, `Make SQLite the default control-plane state backend`.

- accepted source: `6ae11d56c6a6e9cab708d6f3b9ce29a195619216`;
- squash merge: `129a81bd2a4a12cb069025e57dfb3e799caf921a`;
- permanent `Rust Quality` run: `30113037025`;
- architecture enforcement, rustfmt, strict Clippy and complete workspace tests: successful;
- review submissions: none;
- inline review threads: none;
- unresolved P0/P1 defects in the accepted cutover: none.

## Blocking residue

`StateBackend::Json`, `--state-backend json` and the JSON persistence dispatch remain compiled into the current production daemon. Although JSON is no longer implicit, it can still become a mutable runtime source of truth.

This is acceptable only during the cutover compatibility window. It is not the canonical post-Phase-B architecture described by the plan, where JSON is limited to migration input or export artifacts.

## Exact final Phase B slice

The next slice must:

1. remove runtime backend selection from the production control-plane CLI;
2. make the daemon open only the existing SQLite state path;
3. remove JSON persistence dispatch and production JSON loading/writing code that has no migration ownership;
4. retain JSON parsing needed by the migration utility and deterministic import tests;
5. retain diagnostic export and `rollback-export` so the previous accepted release can consume current state during the rollback window;
6. prove the current daemon rejects the retired `--state-backend` option rather than silently accepting it;
7. prove missing SQLite startup still fails closed without creating state;
8. preserve API, authentication, proxy, tunnel and WireGuard compatibility;
9. pass permanent architecture, rustfmt, strict Clippy and complete workspace tests on one unchanged source SHA.

## Explicit non-goals

The final slice must not:

- remove JSON import or rollback-export tooling;
- change SQLite schema or durable inventory;
- add automatic migration, fallback or dual-write;
- overwrite the preserved migration source;
- change application outcomes, API schemas or protected network surfaces;
- claim backup/restore, Phase C or physical-device completion.

## Stop condition

After the runtime retirement slice is accepted, perform a final Phase B closeout decision. Only that closeout may authorize Phase C pending-stream lifecycle and bounds.