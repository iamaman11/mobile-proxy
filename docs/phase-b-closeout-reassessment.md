# Phase B Final Closeout and Reassessment

Status: Phase B complete; delivery item 8 authorized after this closeout is accepted  
Baseline `main`: `2b31d6edb5b6ff93948747a9832676296d2826fa`  
Delivery item closed: 7 — Phase B closeout and reassessment

## Decision

Phase B is complete.

The accepted SQLite schema, transaction boundary, migration, process acceptance, production-default cutover, previous-release rollback support and final JSON-runtime retirement together satisfy the canonical Production Baseline Plan. SQLite is now the sole canonical mutable control-plane runtime store. JSON is limited to explicit migration input, read-only diagnostic output and the current-state rollback artifact consumed by the previous accepted release.

The earlier compatibility residue is closed: the current production daemon has no runtime backend selector, JSON loader, JSON writer, fallback or dual-write path. This decision therefore authorizes the next delivery item from the canonical order: `pending-stream lifecycle and bounds`.

Authorization is bounded to auditing the existing pending-stream implementation, proving lifecycle removal and capacity/expiry bounds, and fixing only evidence-backed residual correctness gaps. It does not authorize later Phase C items, future-platform scope or unrelated architecture work.

## Completion criteria

The closeout reviewed current repository state and accepted immutable-SHA evidence against every Phase B criterion.

1. **SQLite is the only canonical mutable runtime store.**
   - the daemon accepts only an SQLite state path;
   - the default is `/var/lib/mobile-relaycontrolpoint/control-plane-state.sqlite3`;
   - backend selection and production JSON persistence are absent.
2. **Acknowledged operations survive crash and restart.**
   - process acceptance acknowledges pending work, terminates the daemon, restarts it and verifies that acknowledged work does not reappear.
3. **Replay and idempotency survive restart.**
   - exact replay returns the original command;
   - reuse of the same idempotency key with different effective parameters fails closed after restart.
4. **Representative JSON migration is deterministic.**
   - explicit stopped-source import validates representative state, preserves the source and produces the accepted SQLite projection.
5. **Diagnostic export remains available.**
   - `control-plane-state-migrate export` continues to emit the typed read-only diagnostic snapshot.
6. **Previous-release rollback is documented and tested.**
   - `rollback-export` materializes the latest SQLite state in the exact JSON contract of the previous accepted release;
   - the artifact preserves device inventory, pending removal, replay and conflict semantics through round-trip validation;
   - rollback means stopping the current daemon, exporting current state and starting the previous accepted release against that JSON artifact.
7. **Unsupported, corrupt and unexpected schema state fails closed.**
   - startup validates schema version, exact table inventory and typed relations;
   - missing or removed databases are not created automatically.
8. **JSON runtime is absent from the current daemon.**
   - `--state-backend` is rejected before state access;
   - no automatic import, fallback or dual-write is compiled into production runtime ownership.
9. **The durable inventory remains closed.**
   - no lease, outbox, event-sourcing or future-roadmap table was added.
10. **The protected compatibility surface is unchanged.**
    - mixed proxy `1080`, SOCKS5 `1081`, HTTP/CONNECT `3128`, QUIC-first transport, certificate-pinned TLS/TCP reserve and WireGuard rollback remain protected.
11. **No unresolved P0/P1 defect blocks closeout.**
    - accepted PRs have no unresolved review thread or known P0/P1 defect affecting the Phase B guarantees.

## Accepted evidence

### PR #46 — SQLite production default

- accepted source: `6ae11d56c6a6e9cab708d6f3b9ce29a195619216`;
- squash merge: `129a81bd2a4a12cb069025e57dfb3e799caf921a`;
- permanent `Rust Quality` run: `30113037025`;
- architecture enforcement, rustfmt, strict Clippy and complete workspace tests: successful.

### PR #47 — Phase B reassessment

- accepted source: `69702a57a03847b23cd7089b1a8c658dadf24949`;
- squash merge: `93ba1c5b77a2f7e95d3a85ee797cddf5005963c3`;
- permanent `Rust Quality` run: `30113663430`;
- decision: closeout remained blocked until JSON runtime ownership was retired.

### PR #48 — JSON runtime retirement

- accepted source: `559afe15334af15ca898a10105de7f0e622cc8cf`;
- squash merge: `2b31d6edb5b6ff93948747a9832676296d2826fa`;
- permanent `Rust Quality` run: `30119467005`;
- job: `89568215330`;
- architecture enforcement, rustfmt, strict Clippy and complete workspace tests: successful;
- branch lag before merge: `0`;
- review submissions: none;
- inline review threads: none;
- unresolved P0/P1 defects: none identified.

## Compatibility and scope result

Phase B changed only the control-plane durability implementation and its migration/rollback boundary. It did not change successful API shapes, authentication, application outcomes, protected proxy ports, tunnel priority or WireGuard compatibility.

Backup/restore, health semantics, physical-phone acceptance and all future-platform concepts remain outside this closeout. Backup/restore stays in its ordered Phase D slice and is not implied by SQLite durability or rollback-export.

## Exact next delivery item

Delivery item 8: `pending-stream lifecycle and bounds`.

The next production slice must first audit existing pending TCP stream registrations and prove removal on success, cancellation and timeout, plus explicit global/per-device capacity and bounded expiry. It must preserve exact routing, all protected proxy surfaces, QUIC-first behavior, TLS/TCP reserve and WireGuard rollback. It must not pull forward exact session binding, forced transport fallback, health, backup/restore or physical-device acceptance unless a demonstrated dependency requires a separate plan decision.
