# Mobile Proxy Implementation Plan

The sole canonical roadmap for current development is:

- [Production Baseline Plan](docs/PRODUCTION_BASELINE_PLAN.md)

All work must follow that one roadmap. This file is its concise execution entry point; it does not create a second backlog or a parallel development axis.

## Current milestone: physical-device control foundation

Status: **blocking prerequisite for further application growth**  
Authority: subordinate to `docs/PRODUCTION_BASELINE_PLAN.md`, `docs/operation-state-machine-v1.md` and current repository state

The next product milestone is **not** “finish filesystem, then add more application code”. The next milestone is to finish, prove and accept one production-grade State Machine that can reproducibly control the real physical Android device.

Until that milestone is accepted, feature growth, VM generalization, new orchestration frameworks and new governance machinery are frozen except for the smallest change strictly required to prove the next State Machine invariant.

There is one sequential development direction:

```text
FORMAL DEVICE STATE MODEL
  -> OPERATION GUARDS
  -> BOUNDED MUTATION
  -> INDEPENDENT POSTCONDITION OBSERVATION
  -> AMBIGUOUS-OUTCOME HANDLING
  -> RECOVERY / QUARANTINE
  -> CONTROLLER RESTART + DEVICE REBOOT
  -> REPRODUCIBLE CLEAN DEVICE STATE
  -> REAL-PHONE FOUNDATION ACCEPTANCE
  -> APPLICATION FEATURE GROWTH
  -> VM / PROVIDER GENERALIZATION
```

No later item is an independent workstream. A blocked foundational transition is solved before moving forward.

## Foundation acceptance contract

The State Machine foundation is accepted only when one coherent implementation can demonstrate all of the following on the real registered production phone.

### 1. Current reality is observed, not remembered

`control_state_machine.py` answers **what is independently proven and reusable now?**  
`operation_state_machine.py` answers **what exact transition may execute next in this transaction?**

The real phone is the authoritative observation oracle for device-verifiable Android reality. Workflow state, issue text, remembered progress and a green job are not device state.

No phone, runtime, package, VM or provider is globally `READY`. Permission is operation-specific and derived from admitted facts.

Git/GitHub remains the authority for canonical source, reviewed contracts, Quality, artifacts and execution admission. A Git SHA is **not** a global physical-device epoch.

### 2. Physical facts use causal validity, not global SHA invalidation

The model keeps three truth roles separate:

```text
Git/source authority
observed device facts
transaction evidence
```

A durable physical fact carries the exact dependencies that can make it unsafe to reuse, for example:

```text
target binding
observer contract/version
filesystem/package/runtime/process domain generation
boot or session identity when relevant
source identity only when the fact is source-relative
artifact identity only when the fact is artifact-relative
transaction identity when cross-transaction reuse is forbidden
```

The validity rule is deterministic:

```text
all declared dependencies still match -> VALID
any declared dependency changed        -> STALE
required current dependency unknown    -> UNKNOWN
wrong authority / malformed evidence   -> UNUSABLE or INVALID
required persistence missing           -> UNPERSISTED
```

Unrelated current-context changes are ignored. Therefore a docs-only merge does not invalidate a persisted filesystem observation merely because `main` moved.

The exact source SHA that produced an observation remains provenance. It becomes a freshness dependency only when the operation/fact contract explicitly says the claim is source-relative.

At the first destructive command that may have reached the phone, every affected physical domain advances to the new transaction generation before pre-mutation facts from that domain may be reused. This is true even if the runner/controller loses the result. Ambiguous execution therefore cannot fall back to an old “current” fact.

Do not introduce one global `DeviceEpoch`; invalidate only affected domains/coupled scopes.

See [ADR-003: Causal device-fact validity and Git authority](docs/architecture/ADR-003-causal-device-fact-validity-and-git-authority.md).

### 3. One transaction model owns mutation semantics

Every destructive operation follows:

```text
OBSERVE
  -> VERIFY GUARD
  -> ACQUIRE MUTATION AUTHORITY
  -> MUTATE
  -> INDEPENDENTLY OBSERVE POSTCONDITION
  -> ACCEPT
```

On unresolved post-boundary state:

```text
UNKNOWN / FAILED
  -> RE-OBSERVE
  -> RECOVER | QUARANTINE | ACCEPT ONLY FROM PROVEN POSTCONDITION
```

A command returning success is not a postcondition. A workflow returning success is not acceptance.

A reusable earlier phone fact may satisfy an operation precondition only if its causal dependencies and the operation contract allow reuse. It never substitutes for a fresh `phone_access_boundary` when the destructive operation requires same-transaction target reproof.

### 4. Three dimensions never collapse into one

The implementation must keep separate:

```text
operation_execution_result
verified_target_state
evidence_persistence_result
```

Any of these may succeed while another fails. State promotion consumes the exact dimensions required by the operation contract; no narrative shortcut may merge them.

### 5. Ambiguous controller/runner loss is a first-class state

If the runner, controller, transport or evidence channel disappears after a destructive command may have reached the phone, the system MUST NOT classify the target operation as simply failed or retry it blindly.

The State Machine must represent an explicit ambiguous execution outcome and require fresh read-only observation of the real phone before deciding whether the operation:

- did not happen;
- completed;
- partially completed and needs recovery;
- cannot be classified safely and must remain quarantined.

Non-idempotent mutation is never retried merely because the controller did not receive the result.

### 6. Recovery is part of the primary design

Recovery is not an exception-handler afterthought. Every destructive boundary must have a tested path to a known state:

```text
REFUSED
RECOVERY_REQUIRED
RECOVERED
QUARANTINED
ACCEPTED
```

A recovered transaction is not an accepted transaction. A fresh transaction is required after recovery when the original goal still needs to be performed.

### 7. Restart and reboot cannot depend on narrative memory

The controller may restart. The self-hosted runner may restart. The phone may reboot.

After restart/reboot, the next decision must be reconstructible from durable bounded transaction identity, current causal dependency context and fresh observation where the relevant fact became stale/unknown or the operation requires a fresh boundary proof. The system must not require a human to remember which command probably ran.

A derived cache may exist later for performance, but it cannot be independent authority and must be rebuildable from durable evidence.

### 8. Reproducibility is the foundation Definition of Done

The foundation is not complete because one mutation succeeded. It is complete when the project can repeatedly establish an allowed clean project-owned device state from current observations, perform an operation, independently verify it, survive injected interruption and recover or quarantine deterministically.

The acceptance matrix must cover at least the device-control dimensions needed by the product:

- phone identity/access;
- causal fact reuse/invalidation;
- capability inventory;
- project-owned filesystem/materialization;
- package query/install/uninstall/verification;
- runtime generation/integrity/current binding;
- process/service start/stop and structural health;
- bounded functional probe;
- connectivity loss/recovery;
- runner/controller loss at destructive boundaries;
- evidence-persistence loss;
- phone reboot and controller restart;
- recovery from partial mutation.

These are **State Machine dimensions to prove as one coherent control model**, not separate roadmaps to expand one after another with unrelated orchestration.

## Architecture rule: no complexity growth without uncertainty reduction

The application must remain understandable, modular, layered, extensible and independently verifiable by one developer.

The dependency direction remains:

```text
foundation <- domain/contracts <- application <- infrastructure/adapters <- composition/delivery
```

For the current milestone:

- prefer deletion and simplification before adding code;
- one concept has one authoritative owner;
- GitHub Actions, ADB, shell and provider APIs are adapters, not alternate state machines;
- Git source authority, physical observations and transaction traces must remain separate concepts;
- do not create generic frameworks for hypothetical future targets;
- do not add wrappers around wrappers;
- do not add a checker only to verify another checker/test exists or ran;
- do not add tests whose primary subject is other tests rather than product/state-machine behavior;
- do not add a global device-state database/event-sourcing layer while durable bounded evidence plus pure reducers is sufficient;
- add a new abstraction only after a real current requirement cannot be expressed clearly in the existing model;
- every new module or mechanism must identify the concrete uncertainty it removes and its deletion path.

See [Architecture Quality Standard](docs/architecture/ARCHITECTURE_STANDARD.md).

## Bootstrap-state policy: protect boundaries, not the current instance

Until reproducible device control is accepted, the current installed APK, runtime generation, project-owned files and project-owned configuration on the phone are **disposable bootstrap state**.

We do not optimize the architecture around preserving that incidental current state. If the safest reproducible State Machine operation needs to remove and rebuild project-owned state, that is acceptable when the operation is explicitly authorized, bounded to project ownership and independently verified afterward.

This means:

- do not spend foundation-stage engineering effort preserving an unreproducible current installation;
- do not make correctness depend on the current package, runtime files or device-local project secrets surviving;
- prefer revocable/test credentials for foundation experiments where practical;
- defer elaborate secret-continuity, migration and preservation mechanisms unless they are required to prove the control model itself.

It does **not** mean “ignore security”. Real credentials must never be logged, committed or deliberately disclosed. Non-project-owned phone state must not be touched. Provider/account mutations remain separately bounded and authorized. The rule is **reproducibility before preservation**, not confidentiality reduction.

## Single sequential execution order

1. **Freeze non-essential feature/framework growth.** Remove or simplify unnecessary scaffolding when it obstructs local reasoning.
2. **Specify the complete State Machine.** Enumerate state dimensions, causal fact dependencies/invalidation, operation contracts, destructive boundaries, ambiguous outcomes, recovery states and invariants before adding more domain-specific orchestration.
3. **Prove deterministic reducer behavior offline.** Core fact-validity, state, guard and recovery logic must be deterministic and side-effect free where possible.
4. **Prove real-phone observation.** Device identity and every device-verifiable pre/postcondition must come from bounded real-phone observation; persist the causal dependency identities required for safe reuse.
5. **Prove mutation semantics.** For each representative destructive boundary, advance affected domain generation, then prove guard -> mutation -> independent observation without inferring post-state from command success.
6. **Prove interruption semantics.** Inject controller/runner disconnect and evidence-persistence failure before, during and after destructive boundaries. Ambiguous outcome must stale the pre-mutation affected-domain view and force re-observation rather than blind retry.
7. **Prove recovery/quarantine.** Every injected partial state must converge to `RECOVERED`, `QUARANTINED` or independently proven `ACCEPTED`; nothing remains narratively “probably okay”.
8. **Prove restart/reboot.** Restart controller/runner and reboot the phone; reconstruct authority from durable transaction identity plus causal fact context and fresh observation where required.
9. **Prove reproducible clean state.** Re-establish the defined project-owned baseline more than once without depending on hand-maintained device state.
10. **Accept the physical-device control foundation.** Record bounded evidence for the unchanged exact candidate and no unresolved transition ambiguity.
11. **Only then resume application growth.** APK/runtime/data-path/release work must use the accepted State Machine rather than extend workflow-specific control logic.
12. **Only after the phone implementation proves reusable primitives, generalize to VM/provider targets.** Reuse demonstrated invariants; do not pre-build a generic multi-target framework.

The current public Issue #179 remains the live execution cursor inside this sequence and may authorize only the exact next safe production transition. It does not authorize skipping the foundation gate.

## Quality and evidence discipline

Use the smallest verification that directly proves the independent invariant under change.

For docs and policy-only work:

```text
scripts/quality-gate.sh fast
```

For code or release changes:

```text
scripts/quality-gate.sh
```

Do not increase check count as a proxy for confidence. Prefer transition tables, deterministic reducer tests, property/invariant tests where they add unique value, and bounded real-phone fault-injection acceptance over meta-tests that verify test/check presence.

Production evidence remains bounded and must not expose credentials, raw device identifiers or secret-derived values.

## Related normative artifacts

- [Production Baseline Plan](docs/PRODUCTION_BASELINE_PLAN.md) — the sole canonical development/release roadmap
- [Evidence-Derived Control State Machine v1](docs/control-state-machine-v1.md)
- [Transactional Operation State Machine v1](docs/operation-state-machine-v1.md)
- [Architecture Quality Standard](docs/architecture/ARCHITECTURE_STANDARD.md)
- [ADR-003: Causal device-fact validity and Git authority](docs/architecture/ADR-003-causal-device-fact-validity-and-git-authority.md)
- [Project Authority and Execution Satellites](docs/operations/project-authority.md)
- [Machine-readable Project Authority Contract](contracts/operations/project-authority-v1.json)
- [Machine-readable Module Boundaries](contracts/governance/module-boundaries-v1.json)
- [Machine-readable State Ownership](contracts/governance/state-ownership-v1.json)

`iamaman11/mobile-proxy` remains the only canonical project repository. `iamaman11/mobile-proxy-production` remains an execution satellite only and cannot expand, replace or reinterpret this roadmap.

Repository state, the canonical Production Baseline and machine-derived evidence take precedence over chat history, remembered progress and private execution-satellite narrative.
