# Production Baseline Plan

Status: canonical near-term implementation roadmap  
Repository: `iamaman11/mobile-proxy`  
Scope: complete the minimum production baseline without turning the working proxy into a speculative platform

## 1. Decision

The near-term objective is not to complete the former Ultimate Implementation Plan. The application already provides a useful working proxy surface, so development must now be limited to changes that remove concrete reliability, durability, recovery or tunnel-correctness risks.

The former long-horizon platform roadmap has been moved to [`future/ULTIMATE_IMPLEMENTATION_PLAN.md`](future/ULTIMATE_IMPLEMENTATION_PLAN.md). It is not normative for current development and must not be used to expand a production slice unless the roadmap is explicitly reactivated by a separate decision.

This document is the sole canonical implementation roadmap for current development. Architecture ADRs and compatibility contracts remain normative for their bounded subjects, but they do not authorize work outside this baseline.

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
7. A future-roadmap concept may be referenced only to explain a non-goal or compatibility constraint; it may not become implementation scope implicitly.
8. When two designs satisfy the same invariant, prefer the one with fewer states, fewer persistence concepts, fewer runtime dependencies and a smaller rollback surface.

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

## 7. System invariants

These invariants apply to every baseline slice. They are stronger than implementation preference and must remain true across restarts, failures, retries and future maintenance.

### 7.1 Compatibility invariants

1. The protected proxy ports, protocols and rollback transports remain available until an explicit compatibility decision says otherwise.
2. Existing successful request and response shapes remain compatible unless a versioned migration is approved.
3. A change may add bounded diagnostics or typed errors, but may not silently reinterpret an existing successful operation.

### 7.2 State and durability invariants

1. There is exactly one canonical mutable source of truth for each piece of control-plane state.
2. After Phase B, SQLite is canonical; in-memory structures are projections or caches and JSON is migration input or diagnostic export only.
3. No successful acknowledgement is returned before the corresponding durable transaction commits.
4. A failed durable write must not publish a newer in-memory state.
5. Restart, duplicate delivery and exact replay must not duplicate a completed operation.
6. Reuse of an idempotency key with different effective parameters must fail closed.
7. Unsupported schema versions, corrupt canonical state and ambiguous migrations fail closed with bounded operator-visible errors.

### 7.3 Routing and tunnel invariants

1. Traffic intended for a specific device or tunnel session is never routed to an arbitrary available device.
2. A stale, expired, cancelled or mismatched pending stream cannot receive traffic.
3. Pending registrations, queues, retries and spawned work have explicit bounds.
4. Capacity exhaustion rejects new work deterministically; it does not evict unrelated live work silently.
5. QUIC is primary, certificate-pinned TLS/TCP is reserve, and downgrade to plaintext is forbidden.
6. Transport recovery must not reuse stale session authority.
7. A reported connected state is insufficient by itself; freshness and exact session identity must be considered wherever routing authority depends on them.

### 7.4 Security and observability invariants

1. Credentials, tokens, full proxy URLs, raw secret-bearing payloads and unbounded error text never enter logs, metrics labels or safe API errors.
2. Authentication is evaluated before protected request metadata is trusted or reflected.
3. Unknown external enum-like values are rejected or mapped to a bounded fail-closed class; they do not become new domain states or metric labels.
4. Health and metrics observe authoritative state; they do not create a second mutable source of truth.
5. Liveness describes process viability. Readiness describes ability to serve correctly. Phone availability alone must not define process liveness.

### 7.5 Architecture invariants

1. Dependency direction remains inward: pure types and business decisions do not depend on HTTP, database, filesystem, Android or process adapters.
2. Transport handlers decode, authenticate, invoke an application port and map the result; they do not own persistence ordering or canonical mutation rules.
3. Persistence adapters implement application-defined ports and do not define business semantics.
4. One behavior has one authoritative owner. A second implementation may exist only as an explicit compatibility adapter, projection or migration path.
5. New abstraction is justified only when it removes a demonstrated duplication, dependency violation or testability obstacle in current scope.

### 7.6 Operational invariants

1. Backup is not considered complete until restore into a clean environment succeeds.
2. Rollback is not considered supported until the documented procedure is exercised against representative state.
3. Physical acceptance evidence must identify one immutable Git SHA and must not combine results from different source revisions.
4. No release is declared baseline-complete with an unresolved P0 or P1 defect.

## 8. Module responsibility map

The following responsibility map prevents behavior from drifting between layers. Exact crate names may evolve, but ownership may not move implicitly.

| Responsibility | Authoritative layer | Must not be owned by |
| --- | --- | --- |
| validated IDs, deadlines and bounded value types | foundation | Axum handlers, SQL rows, Android UI |
| command/registration/heartbeat/probe orchestration | application ports and implementations | transport handlers |
| canonical durable state | SQLite adapter after Phase B | in-memory maps, JSON export |
| request authentication and wire decoding | transport adapter | domain or persistence crates |
| idempotency classification and replay decision | application behavior with durable evidence | HTTP response mapping |
| tunnel connection lifecycle and exact session authority | reverse-tunnel runtime | metrics renderer or health projection |
| compatibility projection for legacy surfaces | explicit compatibility adapter | canonical domain vocabulary |
| health and metrics rendering | observability adapters reading authoritative state | independent mutable counters unless the event source is authoritative |

A slice that changes ownership must state the old owner, new owner, migration mechanism and compatibility impact explicitly.

## 9. Strict development protocol

Every production slice follows this sequence:

1. Identify one named current risk and the invariant it threatens.
2. Record exact `main` SHA and confirm the branch starts from that state.
3. State bounded scope, explicit non-goals and protected compatibility impact before implementation.
4. Implement the smallest complete vertical slice through the correct owner layers.
5. Add tests for success, exact replay, conflicting replay, restart or failure ordering where applicable.
6. Run permanent architecture validation, formatting, strict Clippy and the complete applicable workspace suite.
7. Remove temporary builder inputs, temporary workflows, generated caches and diagnostic artifacts from the production branch.
8. Verify branch lag, final immutable head SHA, review submissions and unresolved inline threads.
9. Merge only the exact accepted head.
10. Update this plan only when phase status or a real scope decision changes; do not rewrite it to describe incidental implementation details.

A slice is rejected even when tests pass if it violates an invariant, expands a non-goal, creates a second source of truth or claims evidence from different SHAs.

## 10. Definition of Done

A baseline slice is complete when:

- it addresses a named current risk and names the protected invariant;
- compatibility impact and non-goals are explicit;
- authoritative ownership is clear and dependency direction remains valid;
- durable publication ordering is tested where state changes;
- retry, duplicate, conflict, restart and bounded-capacity behavior are tested where applicable;
- errors are bounded and secrets are not exposed;
- focused unit, integration and process tests pass;
- existing permanent architecture and Rust quality gates pass on the final unchanged head;
- temporary builder inputs and workflows are absent from the production diff;
- documentation states what was completed, what remains deferred and the exact next bounded slice;
- merge uses the exact accepted head after branch-lag and review-thread verification.

Not every slice requires a new governance contract, inventory or architectural abstraction. Existing enforcement should be extended only when a required invariant otherwise remains dependent on memory or manual review.

## 11. Context-loss recovery protocol

A new developer or agent must be able to resume correctly without relying on chat history, private notes or remembered intent.

Before changing code, the developer or agent must:

1. Read `IMPLEMENTATION_PLAN.md` and this document.
2. Treat this document as the active roadmap and `docs/future/` as non-active reference only.
3. Read the relevant ADRs and protected compatibility contract for the proposed slice.
4. Inspect current `main`, open PRs, latest permanent workflow runs, review submissions and unresolved inline threads.
5. Compare repository reality with the latest merged slice; repository state wins over any external checkpoint.
6. Identify the first unfinished item in Section 6 and verify that no earlier phase closeout is missing.
7. Restate before implementation:
   - exact baseline SHA;
   - current phase and delivery item;
   - named risk;
   - threatened invariants;
   - exact scope;
   - explicit non-goals;
   - compatibility surface;
   - required acceptance evidence.
8. Stop and request or record a product decision if the proposed work belongs to Section 5 or the future roadmap.

No external checkpoint may authorize skipping these steps.

### Required handoff checkpoint

Every merged production slice must leave a concise checkpoint in its PR body or closeout documentation containing:

- accepted source SHA and merge SHA;
- completed delivery item;
- invariant and risk addressed;
- compatibility result;
- permanent CI run on the accepted SHA;
- migration, restart, rollback or physical evidence when applicable;
- unresolved defects or explicit statement that none remain;
- exact next delivery item from Section 6;
- deferred non-goals that remain inactive.

This checkpoint is evidence, not a second roadmap. If it conflicts with this document or current repository state, this document and repository state take precedence.

## 12. Change-control rules for this plan

This plan may be changed only through a dedicated documentation decision that:

1. explains the demonstrated product or operational reason;
2. identifies which current invariant or non-goal changes;
3. states added and removed scope explicitly;
4. estimates compatibility, migration and rollback impact;
5. does not combine the plan change with unrelated runtime implementation.

Activating any item from `docs/future/` requires a separate decision and must not occur as an incidental follow-up inside a baseline PR.

## 13. Stop conditions

Development must stop for reassessment when any of the following is true:

- all four baseline phases are complete;
- a proposed change belongs only to the future roadmap;
- implementation cost is no longer proportional to a demonstrated operational risk;
- compatibility can no longer be preserved without a product decision;
- physical evidence shows the existing simpler path is already sufficient;
- a slice cannot identify its authoritative owner or would introduce a second source of truth;
- acceptance would require combining evidence from different Git SHAs.

Completion of this baseline does not automatically authorize implementation of the future platform plan.
