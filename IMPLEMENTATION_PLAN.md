# Mobile Proxy Implementation Plan

The sole canonical roadmap for current development is:

- [Production Baseline Plan](docs/PRODUCTION_BASELINE_PLAN.md)

All work must begin by reading that document. It defines the active delivery order, protected compatibility surface, system invariants, module responsibilities, strict development protocol, Definition of Done and context-loss recovery procedure.

## Current execution checkpoint

Status: **temporary execution focus**  
Activated: **2026-08-30**  
Updated: **2026-09-03 — Android physical-reality authority promoted**  
Authority: subordinate to `docs/PRODUCTION_BASELINE_PLAN.md` and current repository state  
Removal condition: delete this entire section after software-complete release-candidate acceptance is recorded on one immutable Git SHA, or when an explicit product decision supersedes this focus.

The state-ownership governance slice is complete. The current priority is now to produce, exercise and accept a functional production-baseline candidate before undertaking further architecture or governance expansion.

### Fact-first execution spine

The existing evidence-derived state machines are the execution spine for all further production work:

- [`docs/control-state-machine-v1.md`](docs/control-state-machine-v1.md) answers **what is independently proven right now?**;
- [`docs/operation-state-machine-v1.md`](docs/operation-state-machine-v1.md) answers **what exact phase may execute next in this transaction?**.

Development MUST advance from the current `CONTROL` projection and exact blocking predicates, not from remembered state, issue narrative, workflow names, a green job, or an assumption that the phone/runtime/provider is globally ready.

The active working rules are:

1. Current production state is derived from current, scoped `CONTROL` evidence. Where the operation contract requires durable evidence, state promotion also requires successful durable persistence of that exact bounded evidence.
2. **Operation execution result**, **independent postcondition verification**, and **evidence persistence** are three separate dimensions. Success in one does not imply success in either of the others.
3. `UNKNOWN`, `STALE`, `CONFLICT`, invalid scope, other-transaction evidence and required-but-unpersisted evidence fail closed and cannot advance production state.
4. No phone, runtime, VM or provider is globally `READY`. Authority is operation-specific, exact-SHA, exact-transaction and, for mutation, exact-boundary scoped.
5. Every mutation follows `OBSERVE -> VERIFY -> MUTATE -> INDEPENDENTLY VERIFY -> ACCEPT`. Any unresolved post-boundary state enters explicit recovery or quarantine; recovery never silently becomes acceptance.
6. Phone access is re-proved immediately before a destructive boundary in the exact mutating job. A canonical source SHA advance invalidates prior SHA-bound phone admission for subsequent production execution.
7. The private execution repository transports commands, secrets and bounded evidence; it does not manufacture project truth or reinterpret the public state machine.
8. Android is the first adapter to be proven end to end. VM/provider generalization comes only after the phone baseline demonstrates which operation primitives are actually reusable.

### Android physical-reality authority

The real registered production phone is the authoritative observation oracle for Android device reality. Hosted `Quality`, unit/integration tests, workflow state and private orchestration can prove software/policy coherence, reducer behavior and execution transport, but they cannot by themselves prove the current filesystem, package, signer, runtime, process, service, network or functional data-path state of the real Android target.

If an Android predicate or postcondition can be verified on the real production phone, the dependent production state MUST NOT be completed or promoted solely from hosted/offline evidence. It requires bounded device-backed `CONTROL` evidence from an authorized real-phone operation, with the exact source/transaction scope, freshness and durable persistence required by that operation contract. Offline tests may prove that the observer/reducer is correct; they do not substitute for observing the device.

Infrastructure or control-plane hardening may run ahead of the phone only to remove a demonstrated blocker to the next safe device-backed operation. Closing that blocker is not Android state progress by itself. Once the blocker is closed, execution returns immediately to the real-phone certification loop instead of expanding orchestration, governance or framework work without a new demonstrated device blocker.

This doctrine is not a new parallel architecture. It promotes the already implemented `control_state_machine.py` and `operation_state_machine.py` contracts as the normal way the project reasons about reality, with the real phone as the source of Android physical-state observations.

### Current execution order

1. Treat non-essential architecture/governance framework expansion as temporarily closed.
2. Close the demonstrated evidence-persistence blocker with the smallest safe bounded fix; do not retry or replay the phone operation merely to persist its evidence.
3. Return immediately to the real phone: prove current-SHA phone admission, then perform one fresh read-only quarantine observation of the exact quarantined transaction set.
4. Let durable device facts decide the next transition. If the quarantined paths are durably proven absent, skip cleanup; otherwise perform only the separately authorized bounded cleanup and independently verify its postcondition.
5. Repeat bounded Android filesystem certification so create/write/read/compare/delete/post-absence and recovery/quarantine behavior are proven from real-phone evidence.
6. Move APK/signing work through the same transaction model: exact signed candidate -> pre-mutation device observation -> boundary reproof -> controlled package mutation -> independent real-phone signer/version/digest verification -> explicit recovery/quarantine on uncertainty.
7. Move native runtime deployment through the same model: materialize exact generation -> verify integrity/current binding on the phone -> start -> structural health -> bounded functional probe -> restart/rehydration -> recovery proof.
8. Exercise the complete product data path on one unchanged candidate SHA:

   ```text
   startup
     -> state recovery
     -> control plane
     -> phone
     -> QUIC
     -> proxy 1080 / 1081 / 3128
     -> forced TLS/TCP fallback
     -> return to QUIC
     -> restart
     -> restore / rollback
   ```

9. Execute the required failure/restart/recovery matrix and soak only while exact candidate identity and current authority remain valid; re-derive blockers after every transition instead of carrying narrative readiness forward.
10. Record software-complete and physical acceptance only from the same immutable candidate with all required durable device-backed evidence, then follow the protected release ordering in the Production Baseline Plan.
11. Only after the functional phone baseline is accepted, generalize the proven operation primitives to VM/provider adapters and perform a fresh architecture re-audit. Do not create a speculative generic execution framework before the Android evidence shows what is actually common.

The ordering above is an execution discipline inside the active Production Baseline. It does not waive or reorder mandatory Item 20 provider, signing, acceptance or release-authority gates defined by `docs/PRODUCTION_BASELINE_PLAN.md`; the stricter prerequisite always wins.

At activation time, known incomplete evidence includes the remaining explicit SQLite startup/integrity-corruption check represented by `PERSIST-002`, the health-surface split represented by `OPS-003`, and any later Production Baseline acceptance items that remain incomplete. Backup plus clean restore/process recovery already have permanent test coverage; this sentence is orientation only, not a second backlog. The Production Baseline Plan, invariant matrix, current `CONTROL` projection and repository state always win.

### Temporary architecture freeze

Until this checkpoint is removed, do not introduce architecture or governance refactoring merely to improve theoretical purity. In particular, do not bulk-migrate governance JSON contracts to Protocol Buffers, introduce gRPC, add generic plugin/extension frameworks or perform broad structural rewrites unless a concrete active-baseline blocker demonstrates that the current design cannot satisfy a required invariant.

This freeze does **not** block architecture work required by a demonstrated correctness, security, durability, compatibility, recovery or operational defect. The smallest complete fix remains preferred.

When the removal condition is reached, delete this section rather than moving it to `docs/history/`. Git history is the archive for this temporary sequencing decision.

Project-level authority is defined separately by:

- [Project Authority and Execution Satellites](docs/operations/project-authority.md)
- [Machine-readable Project Authority Contract](contracts/operations/project-authority-v1.json)

`iamaman11/mobile-proxy` is the only canonical repository for project information. The private
`iamaman11/mobile-proxy-production` repository is an execution satellite only and cannot expand,
replace or reinterpret this roadmap.

The previous broad platform roadmap is retained only as distant-future product direction:

- [Distant-Future Ultimate Implementation Plan](docs/future/ULTIMATE_IMPLEMENTATION_PLAN.md)

The future document is not an active backlog and does not authorize implementation work. Activating any part of it requires a separate product decision and an explicit update to the Production Baseline Plan.

Related bounded normative artifacts:

- [Evidence-Derived Control State Machine v1](docs/control-state-machine-v1.md)
- [Transactional Operation State Machine v1](docs/operation-state-machine-v1.md)
- [ADR-001: Bounded Contexts and Clean Dependency Rules](docs/architecture/ADR-001-bounded-contexts-and-clean-dependencies.md)
- [ADR-002: Cryptographic Hashing, Password Hashing and KDF Policy](docs/architecture/ADR-002-cryptographic-hashing-and-kdf-policy.md)
- [Architecture Quality Standard](docs/architecture/ARCHITECTURE_STANDARD.md)
- [Digest Inventory and Migration Matrix](docs/architecture/digest-inventory-and-migration.md)
- [Engineering Guardrails](docs/architecture/engineering-guardrails.md)
- [Foundation Identifiers, Request Lineage and Deadlines](docs/architecture/foundation-primitives.md)
- [Invariant Enforcement Audit](docs/architecture/invariant-enforcement.md)
- [Machine-readable Invariant Enforcement Matrix](contracts/governance/invariant-enforcement.json)
- [Machine-readable Module Boundaries](contracts/governance/module-boundaries-v1.json)
- [Machine-readable State Ownership](contracts/governance/state-ownership-v1.json)
- [Protected Proxy Compatibility Contract](contracts/compatibility/proxy-surface-v1.json)

Repository state, the canonical baseline plan and current machine-derived evidence take precedence over external checkpoints, chat history, private execution-satellite content or remembered intent.
