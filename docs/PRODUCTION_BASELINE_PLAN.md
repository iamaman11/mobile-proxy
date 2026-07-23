# Production Baseline Plan

Status: canonical near-term implementation roadmap  
Repository: `iamaman11/mobile-proxy`  
Scope: complete the minimum production baseline without turning the working proxy into a speculative platform

## 1. Decision

The near-term objective is not to complete the former Ultimate Implementation Plan. The application already provides a useful working proxy surface, so development must now be limited to changes that remove concrete reliability, durability, recovery or tunnel-correctness risks.

The former long-horizon platform roadmap has been moved to [`future/ULTIMATE_IMPLEMENTATION_PLAN.md`](future/ULTIMATE_IMPLEMENTATION_PLAN.md). It is not normative for current development and must not be used to expand a production slice unless the roadmap is explicitly reactivated by a separate decision.

## 2. Protected compatibility surface

The following behavior must remain available throughout the baseline work:

- mixed proxy on public port `1080`;
- SOCKS5 proxy on public port `1081`;
- HTTP proxy, including CONNECT, on public port `3128`;
- QUIC-first reverse tunnel;
- certificate-pinned TLS/TCP reserve tunnel;
- controlled WireGuard compatibility and rollback path;
- existing operator CLI and operator/admin API behavior unless an explicit compatibility migration is approved.

A baseline change must not silently remove, rename or replace any protected endpoint, protocol, port or rollback path.

## 3. Scope discipline

Current work is governed by these rules:

1. Fix a demonstrated production risk, not a hypothetical future platform requirement.
2. Prefer the smallest complete vertical slice.
3. Preserve working behavior unless the change is required for correctness or recovery.
4. Do not add new governance layers, inventories or policy machinery unless an existing permanent control cannot enforce a required invariant.
5. Do not introduce multi-consumer lease, credential-broker, gRPC, identity-consensus or first-party Android-runtime scope into this baseline.
6. Every phase ends with an explicit stop-and-reassess decision before more work begins.

## 4. Baseline phases

### Phase A — finish clean application boundaries

Goal: complete the already-started separation of transport handlers from application behavior, then stop expanding architecture work.

Required work:

1. Extract the remaining heartbeat handler behind a transport-independent application port.
2. Extract the remaining public-probe handler behind a transport-independent application port.
3. Keep Axum handlers limited to authentication, input decoding, request context, port invocation and response mapping.
4. Preserve current request and response compatibility.
5. Keep existing dependency-boundary validation, but do not create additional governance frameworks.

Completion criteria:

- registration, command issuance, polling, acknowledgement, heartbeat and public probe all enter through explicit application ports;
- transport handlers contain no persistence ordering, idempotency classification or canonical state mutation;
- architecture validation and the existing workspace quality suite pass;
- no new speculative bounded context is introduced.

Explicitly deferred:

- lease domain;
- consumer policy engine;
- credential broker;
- gRPC canonical API;
- new audit-ledger architecture;
- broader governance expansion.

### Phase B — minimum durable state

Goal: replace JSON as canonical mutable state with a small, recoverable SQLite store while retaining safe compatibility and rollback.

Required work:

1. Introduce SQLite with WAL, foreign keys, bounded busy timeout and explicit schema migrations.
2. Persist only the state currently required by the working application: devices, current health/projection data, commands, command replay/idempotency evidence and other existing canonical control-plane state.
3. Define transaction boundaries so a successful mutation cannot publish in memory before its durable commit.
4. Import existing JSON state, validate parity and preserve a read-only diagnostic export during the compatibility window.
5. Provide a tested rollback path to the previous release while the schema is still in the expansion-compatible stage.
6. Add startup integrity checking and fail-closed handling of unsupported or corrupt schema state.

Completion criteria:

- normal writes use SQLite as the only canonical mutable store;
- crash/restart tests prove no acknowledged operation disappears;
- replay and idempotency behavior survives restart;
- migration from representative existing JSON state is deterministic and tested;
- rollback procedure is documented and exercised;
- no lease, outbox or event-sourcing tables are added merely because they appeared in the future roadmap.

### Phase C — critical reverse-tunnel correctness

Goal: address the concrete tunnel failure modes that can misroute traffic, leak pending state or make reserve transport unreliable.

Required work:

1. Remove pending TCP stream registrations on success, cancellation and timeout.
2. Apply explicit global and per-device bounds to pending streams.
3. Give every pending registration a bounded expiry.
4. Remove any arbitrary “first device” selection when a specific device is required.
5. Bind stream routing to the exact device and tunnel session; include runtime generation where already available and useful for stale-session rejection.
6. Verify real QUIC-to-TLS/TCP failover by blocking the QUIC path and proving reserve operation.
7. Restore QUIC and prove new connections return to the primary transport.

Completion criteria:

- capacity exhaustion fails closed without evicting a live unrelated stream;
- stale, expired or mismatched registrations cannot receive traffic;
- device/session mismatch is rejected deterministically;
- mixed, SOCKS5, HTTP and CONNECT succeed over both QUIC and TLS/TCP reserve during the acceptance test;
- WireGuard remains available as the rollback path;
- no first-party Android tunnel replacement is attempted in this phase.

### Phase D — minimum operations and physical acceptance

Goal: prove the resulting system can be operated, restored and trusted on a real device.

Required work:

1. Define separate liveness and readiness semantics that do not conflate process health with phone availability.
2. Ensure health output identifies durable-store health, tunnel state, active transport and freshness without exposing secrets or unbounded labels.
3. Implement and document SQLite backup and restore.
4. Run a restore drill into a clean environment and verify the restored state.
5. Run a physical-phone acceptance sequence on one immutable Git SHA:
   - clean startup;
   - all three proxy surfaces plus HTTP CONNECT;
   - phone or service reboot;
   - state rehydration;
   - QUIC operation;
   - forced TLS/TCP fallback;
   - return to QUIC;
   - WireGuard rollback availability.
6. Record any unresolved P0/P1 defect and do not declare the baseline complete while one remains.

Completion criteria:

- backup and restore are repeatable and documented;
- liveness remains healthy when the process is healthy even if no phone is available;
- readiness accurately reflects critical storage and worker dependencies;
- physical acceptance passes on one unchanged commit;
- the resulting release is suitable for continued real use without requiring the future platform roadmap.

## 5. Explicit non-goals

The production baseline does not include:

- a general multi-consumer lease platform;
- exclusive network leases, epochs or fencing tokens;
- short-lived per-lease proxy credentials;
- Protocol Buffers or gRPC as the canonical API;
- network-identity consensus across several observers;
- durable rotation jobs and full rotation orchestration;
- a new first-party Android VpnService or embedded tunnel runtime;
- replacement of working WireGuard paths;
- complete SBOM, provenance and fleet rollout infrastructure beyond existing release-integrity controls;
- a new governance document for every implementation detail.

These items require a new product or operational justification before activation.

## 6. Delivery order

The required order is:

1. heartbeat application port;
2. public-probe application port;
3. Phase A closeout and reassessment;
4. SQLite schema and transaction boundary;
5. device and command-state migration;
6. JSON import, parity and rollback proof;
7. Phase B closeout and reassessment;
8. pending-stream lifecycle and bounds;
9. exact device/session binding;
10. forced QUIC/TLS fallback and recovery proof;
11. Phase C closeout and reassessment;
12. health semantics;
13. backup/restore drill;
14. immutable-SHA physical acceptance;
15. final baseline closeout.

No later item should be pulled forward merely to keep work moving.

## 7. Definition of Done

A baseline slice is complete when:

- it addresses a named current risk;
- compatibility impact is explicit;
- durable publication ordering is tested where state changes;
- errors are bounded and secrets are not exposed;
- focused unit/integration/process tests pass;
- existing permanent architecture and Rust quality gates pass;
- temporary builder inputs and workflows are absent from the production diff;
- documentation states both what was completed and what remains deferred.

Not every slice requires a new governance contract, inventory or architectural abstraction.

## 8. Stop conditions

Development must stop for reassessment when any of the following is true:

- all four baseline phases are complete;
- a proposed change belongs only to the future roadmap;
- implementation cost is no longer proportional to a demonstrated operational risk;
- compatibility can no longer be preserved without a product decision;
- physical evidence shows the existing simpler path is already sufficient.

Completion of this baseline does not automatically authorize implementation of the future platform plan.
