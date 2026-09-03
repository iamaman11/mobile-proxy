# Transactional Operation State Machine v1

Status: canonical transaction model implemented in part by `scripts/operation_state_machine.py`; existing fail-closed semantics are Quality-tested, but the **physical-device control foundation is not yet accepted**. This document defines the target foundation that must be completed before further application feature growth. It does not itself authorize a production transition; public Issue #179 remains the live execution cursor inside the single Production Baseline roadmap.

## Goal

Turn the evidence-derived control model into one deterministic lifecycle for physical-device operations.

The model has two responsibilities, not two roadmaps:

1. `control_state_machine.py` answers **what is independently proven and reusable right now?**
2. `operation_state_machine.py` answers **what transition may execute next in this exact transaction?**

A phone is never globally `READY`. Filesystem, package, runtime, process, connectivity, reboot and recovery observations are dimensions of current device state consumed by operation-specific guards.

GitHub Actions, shell, ADB and later provider APIs are adapters/executors. They do not own independent transition truth.

## Blocking foundation rule

Before further application feature growth, the project MUST complete and accept this State Machine as the reproducible control foundation for the real physical Android device.

The sequential milestone is:

```text
FORMAL STATE MODEL
  -> OPERATION GUARDS
  -> BOUNDED MUTATION
  -> INDEPENDENT POSTCONDITION OBSERVATION
  -> AMBIGUOUS-OUTCOME HANDLING
  -> RECOVERY / QUARANTINE
  -> CONTROLLER RESTART + DEVICE REBOOT
  -> REPRODUCIBLE CLEAN PROJECT-OWNED DEVICE STATE
  -> REAL-PHONE FOUNDATION ACCEPTANCE
  -> APPLICATION FEATURE GROWTH
  -> VM / PROVIDER GENERALIZATION
```

Filesystem, package, runtime and connectivity are not separate development lanes. They are representative effect domains through which the same transaction engine must be proven.

A blocked foundation invariant is not permission to create more orchestration, policy or feature code elsewhere.

## Core transaction rule

Every real operation follows:

```text
OBSERVE -> VERIFY -> MUTATE -> INDEPENDENTLY VERIFY -> ACCEPT
```

Never:

```text
command returned success -> assume desired state -> continue
```

For destructive operations, the first mutation creates a transaction boundary. Any unresolved state after that boundary must be independently re-observed and then accepted, recovered or quarantined.

Recovery is a primary state path, not an exception-handler assumption.

## Three independent result dimensions

The orchestrator MUST distinguish:

```text
operation_execution_result
postcondition_verification_result
evidence_persistence_result
```

They are intentionally not aliases:

- a command may report success while the intended target postcondition is false or unproven;
- a target postcondition may be proven while durable bounded evidence persistence fails;
- a workflow/job may report success while the reducer still classifies the operation as unaccepted, recovered, quarantined or unpersisted;
- a failed workflow may contain valid bounded observations only up to the exact failure boundary.

Missing durability must not be reconstructed later from narrative, logs or remembered operator state.

Where a guard requires durable evidence, `evidence_persistence_result != success` blocks that dependent transition even if the underlying device fact was observed successfully.

## Ambiguous execution outcome

Controller/runner/transport loss after a destructive command may have reached the phone is not equivalent to target-operation failure.

The State Machine MUST represent an explicit:

```text
UNKNOWN_EXECUTION_OUTCOME
```

for the transaction/step when the controller cannot determine whether the side effect occurred.

From `UNKNOWN_EXECUTION_OUTCOME`, the only safe next action for target-state classification is fresh read-only observation of the real target. The reducer then classifies the observed result as one of:

```text
NOT_APPLIED
APPLIED_AND_VERIFIED
PARTIAL_RECOVERY_REQUIRED
QUARANTINED
```

Rules:

- non-idempotent mutation is never retried merely because the controller did not receive its result;
- controller loss cannot be rewritten as target failure;
- evidence-upload failure cannot cause replay of a device mutation merely to recreate evidence;
- a retry is allowed only when the operation contract proves it idempotent for the freshly observed state and exact transaction scope.

## Android physical-reality rule

The real registered production phone is the authoritative observation oracle for Android device reality. Whenever an Android precondition, postcondition or acceptance predicate is technically observable on that phone, the phase may be completed only from bounded device-backed `CONTROL` evidence produced by the authorized real-phone operation.

Hosted `Quality`, unit/integration tests and workflow policy prove software/policy coherence, transaction ordering and observer/reducer behavior. They do not prove the phone's current filesystem, package/signer, runtime generation, process/service state, network state or functional path.

Infrastructure/control-plane work may interrupt the device sequence only to remove a demonstrated blocker to the next safe real-phone foundation transition. Once the blocker is closed, work returns to that transition rather than expanding an independent framework lane.

A canonical SHA advance changes **source authority**, not physical reality. It invalidates prior SHA-bound admission only for later source-bound operations/facts whose contract declares source identity as a dependency. It MUST NOT globally stale unrelated persisted device facts merely because `main` moved.

## Git authority and causal physical-fact validity

The State Machine keeps three truth roles separate:

```text
GIT / SOURCE AUTHORITY
  exact canonical source, Quality, artifacts and reviewed operation contracts

OBSERVED DEVICE FACTS
  bounded physical claims reusable only while declared causal dependencies match

TRANSACTION EVIDENCE
  exact ordered evidence for one operation transaction
```

Git is the control/software authority. The phone is the physical observation authority. Durable bounded evidence connects the two.

### Durable observed facts

A cross-transaction reusable physical fact is conceptually:

```text
ObservedFact
  subject
  predicate
  value
  target
  observation_ref
  source_ref              # provenance
  authority
  persisted
  dependencies[]
```

Each dependency is one scoped opaque identity:

```text
scope -> identity
```

Supported scope families are intentionally small:

- `target/...` — registered logical target-binding generation;
- `observer/...` — semantic observer contract/version;
- `domain/...` — physical mutation-domain generation;
- `boot/...` — boot generation for reboot-sensitive facts;
- `session/...` — runner/ADB/control session for ephemeral facts;
- `source/...` — source identity only when the claim is source-relative;
- `artifact/...` — exact artifact identity when required;
- `transaction/...` — exact transaction when reuse outside it is forbidden.

`source_ref` remains useful audit provenance even when `source/...` is not a validity dependency.

### Validity algorithm

`control_state_machine.py` must classify an admitted observed fact deterministically:

```text
wrong authority        -> UNUSABLE
malformed dependencies -> INVALID
required persistence missing -> UNPERSISTED
required current dependency context missing -> UNKNOWN
any declared dependency changed -> STALE
all declared dependencies match -> VALID
```

Current-context entries that the fact did not declare are ignored. Therefore an unrelated docs/code merge does not invalidate a source-independent filesystem/package/runtime observation.

### Domain-scoped invalidation

Each destructive operation declares the physical domains it may change. Do not use one global `DeviceEpoch`.

At the first destructive command that may have reached the target, every affected domain generation advances to a transaction-scoped identity **before pre-mutation facts in that domain may be reused**. This is true even if the result path is lost.

Example:

```text
old package fact depends on:
  domain/package = pkg-generation-8

transaction tx-9 may reach package manager:
  current domain/package = tx-9

old package fact -> STALE
```

The next safe path is fresh package observation under the new generation, followed by `NOT_APPLIED`, `APPLIED_AND_VERIFIED`, `PARTIAL_RECOVERY_REQUIRED` or `QUARANTINED` classification as appropriate.

A mutation invalidates only affected/coupled domains declared by its contract. A filesystem-only mutation must not globally stale package facts; a reboot may explicitly invalidate boot/session/process/connectivity-dependent facts.

### Observer-version invalidation

Observer semantics have their own identity. If a defect or semantic change makes old observations unsafe to interpret, the observer contract identity changes. Only facts depending on that observer become stale.

Do not use the whole repository SHA as an implicit observer version; that would reintroduce global invalidation through unrelated edits.

### Fresh destructive boundary remains mandatory

Causal reuse removes unnecessary re-observation; it does not weaken mutation safety.

An earlier valid access observation may be useful for planning or an initial guard. A destructive operation still requires the fresh `phone_access_boundary`/target proof declared by the exact transaction immediately before mutation.

See `docs/architecture/ADR-003-causal-device-fact-validity-and-git-authority.md`.

## Authoritative transaction state

The reducer must be able to distinguish at least:

```text
PREPARING
READY_FOR_BOUNDARY_REPROOF
READY_TO_MUTATE
TRANSACTION_ACTIVE
UNKNOWN_EXECUTION_OUTCOME
ACCEPTED
REFUSED
RECOVERY_REQUIRED
RECOVERING
RECOVERED
QUARANTINED
CONFLICT
INVALID_TRACE
```

Meaning:

- `PREPARING` — non-destructive prerequisites are still being established;
- `READY_FOR_BOUNDARY_REPROOF` — static prerequisites pass but destructive authority must be re-proved immediately before mutation;
- `READY_TO_MUTATE` — all required guards and same-transaction mutation-boundary authority pass;
- `TRANSACTION_ACTIVE` — at least one destructive postcondition is independently proven for this transaction;
- `UNKNOWN_EXECUTION_OUTCOME` — a destructive command may have reached the target but its result is not classifiable without re-observation;
- `ACCEPTED` — all required target postconditions and enclosing admission/durability predicates pass;
- `REFUSED` — a safe pre-boundary guard failed and no destructive effect is proven;
- `RECOVERY_REQUIRED` — partial post-boundary state is proven and must be normalized;
- `RECOVERING` — explicit recovery transaction steps are in progress;
- `RECOVERED` — the recovery postcondition is independently proven; this is not acceptance of the original goal;
- `QUARANTINED` — safe classification/recovery cannot currently be proven;
- `CONFLICT` — contradictory current evidence exists;
- `INVALID_TRACE` — the evidence sequence violates the operation contract.

## Operation contract shape

Each mutating operation declares, explicitly and in one place:

```text
operation_id
transaction_id
target_identity
source_identity / artifact_identity when applicable
required_observations
reusable_fact_requirements / freshness requirements
affected_physical_domains
operation_guard
destructive_boundary
mutation_effect
independent_postcondition_observer
idempotency_rule
ambiguous_outcome_reobservation
recovery_contract
evidence_contract
terminal_states
```

An operation must not rely on a workflow name, job conclusion or issue sentence as an implicit field in this contract.

## Concrete Android clean-install operation

The clean-install lifecycle is one concrete operation family used to prove the generic transaction semantics. It is **not** the project roadmap.

```text
source_quality
  -> artifact_signed
  -> runner_assignment
  -> source_delivery
  -> phone_access_initial
  -> capability_inventory
  -> mutation_lock
  -> phone_access_boundary
  -> stop_owned_runtime
  -> remove_owned_runtime
  -> uninstall_legacy_apk
  -> install_new_apk
  -> verify_new_apk
  -> materialize_runtime
  -> verify_runtime
  -> start_runtime
  -> structural_health
  -> functional_probe
  -> accept
```

### Meaning of each phase

| Phase | Kind | What PASS means |
| --- | --- | --- |
| `source_quality` | VERIFY | exact protected canonical SHA has exact successful Quality authority when required |
| `artifact_signed` | VERIFY | exact source-built candidate, signing identity, version and typed digest are proven |
| `runner_assignment` | OBSERVE | exact self-hosted Android job is assigned to the expected runner contract |
| `source_delivery` | VERIFY | exact immutable canonical operation logic is available in the executing job |
| `phone_access_initial` | VERIFY | registered-device CONTROL observation proves the target before capability work |
| `capability_inventory` | VERIFY | every capability required by this operation is `SUPPORTED`; `UNKNOWN` does not satisfy the guard |
| `mutation_lock` | VERIFY | global production-phone mutation serialization is held by the exact transaction/job |
| `phone_access_boundary` | VERIFY | target identity/access is freshly re-proved immediately before mutation |
| `stop_owned_runtime` | MUTATE | project-owned running runtime is stopped or definite absence is independently proven |
| `remove_owned_runtime` | MUTATE | only explicitly project-owned managed runtime state is removed/normalized |
| `uninstall_legacy_apk` | MUTATE | package absence is independently proven afterward |
| `install_new_apk` | MUTATE | package-manager install attempt ran for the exact candidate; this alone is not verification |
| `verify_new_apk` | VERIFY | installed version/signer/digest equal the exact candidate on the real phone |
| `materialize_runtime` | MUTATE | exact source/artifact-bound runtime/config is materialized in a fresh generation |
| `verify_runtime` | VERIFY | runtime file identity/integrity/current-generation binding are independently proven on device |
| `start_runtime` | MUTATE | start command ran for the exact generation; this alone is not health |
| `structural_health` | VERIFY | expected project-owned process/service/local-port structure is independently observed |
| `functional_probe` | ACCEPT | bounded real data-path probe succeeds through the intended application path |
| `accept` | ACCEPT | all required preceding evidence belongs to the same exact transaction/generation and enclosing gates pass |

`uninstall_legacy_apk=PASSED` never implies `install_new_apk=PASSED`.

`install_new_apk=PASSED` never implies `verify_new_apk=PASSED`.

`start_runtime=PASSED` never implies `structural_health=PASSED`.

`structural_health=PASSED` never implies `functional_probe=PASSED`.

## Phone access and capability inventory

Standalone phone access is an observation operation:

```text
source_quality
  -> runner_assignment
  -> source_delivery
  -> phone_access
```

A capability observation adds `capability_inventory`.

A previous successful access observation may remain a valid fact for the scope declared by its dependencies. Reachability itself is ephemeral and therefore must use the appropriate session/boot/transaction freshness scope when reused. In all cases it cannot satisfy a later destructive boundary when that operation contract requires fresh target reproof.

The adapter should classify at least:

- ADB shell;
- package-manager query/uninstall/install;
- root/privilege execution where the managed runtime requires it;
- project-owned managed-root visibility;
- bounded project-owned remove/create/rename;
- push/pull;
- digest/stat/readlink tooling;
- process inspection;
- local network/port inspection;
- free-space inspection;
- ownership/mode operations required by runtime materialization.

Each required capability is `SUPPORTED`, `UNSUPPORTED`, or `UNKNOWN`. `UNKNOWN` never satisfies the operation guard.

## Recovery model

Recovery normalizes only project-owned state required by the operation contract.

For clean-install, the forward-clean recovery contract is:

```text
recovery_classify
  -> recovery_stop_owned_runtime
  -> recovery_remove_incomplete_runtime
  -> recovery_normalize_package
  -> recovery_verify_clean_baseline
```

Rules:

- a failure before any destructive effect is proven is `REFUSED`;
- a proven partial destructive state is `RECOVERY_REQUIRED`;
- an ambiguous destructive result is `UNKNOWN_EXECUTION_OUTCOME` until re-observation classifies it;
- pre-mutation facts in affected domains are stale once a destructive command may have reached the target;
- recovery consists of explicit operations and independent postcondition observations;
- failed/skipped required recovery produces `QUARANTINED`;
- complete recovery produces `RECOVERED`, not `ACCEPTED`;
- after `RECOVERED`, a fresh transaction is required to retry the original goal;
- if an admitted current observation already proves the cleanup target absent under the current dependency generation, absence satisfies the postcondition and no unnecessary cleanup mutation runs.

Recovery must be testable from every destructive boundary, including controller loss after the command was issued but before the result/evidence was received.

## Protect boundaries, not bootstrap state

During physical-device foundation work, the current installed APK, runtime generation, project-owned files and project-owned configuration are disposable bootstrap state.

The operation model MUST NOT depend on preserving that incidental state in place. An authorized bounded operation may wipe/reinstall/re-materialize project-owned state when doing so produces a more reproducible contract and the resulting state is independently verified.

Do not create elaborate in-place migration or secret-continuity mechanisms solely to preserve unreproducible current device state before the control foundation exists.

This does not weaken containment or confidentiality:

- real credentials must not be logged, committed or deliberately exposed;
- prefer revocable/test credentials for foundation experiments where practical;
- non-project-owned phone state is outside mutation authority;
- provider/account mutations remain separately authorized;
- correctness must not depend on a device-local project secret surviving.

## Evidence isolation

There are two evidence shapes with different purposes.

### Reusable observed facts

Cross-transaction physical facts are admitted through the causal-validity model owned by `control_state_machine.py`. They retain observation/source provenance and a dependency vector. They are `VALID`, `STALE`, `UNKNOWN`, `UNPERSISTED`, `UNUSABLE` or `INVALID` according to current causal context.

Only a fact that the exact operation contract permits to reuse may satisfy a guard. A fresh-boundary requirement cannot be satisfied by cross-transaction reuse.

### Transaction phase evidence

Every phase evidence item for `operation_state_machine.py` is bound to at least:

```text
step_id
status
transaction_id
source_ref
authority
lifecycle
target_identity_scope
```

For transaction state advancement:

- required authority is `CONTROL`;
- required lifecycle is `CURRENT`;
- transaction ID must match the operation transaction;
- target/source/artifact scope must satisfy the operation contract;
- conflicting current evidence produces `CONFLICT`;
- another transaction's phase evidence cannot advance the current transaction;
- diagnostic/audit/stale phase evidence cannot satisfy mutation guards.

Strict transaction isolation MUST NOT be weakened merely because a separate durable physical fact is causally reusable.

For Android device-verifiable phases, current CONTROL evidence must be device-backed by the real registered production phone.

Durability is evaluated separately from target truth. A valid device observation may remain unusable for a later guard when the enclosing contract requires durable evidence and persistence failed.

## Trace validity

The reducer rejects impossible histories, including:

- a later required phase proven while an earlier required phase is not proven;
- destructive postcondition evidence without required mutation-boundary authority;
- unknown step IDs;
- contradictory current statuses for the same scoped fact;
- post-boundary uncertainty silently falling back to pre-mutation readiness;
- a pre-mutation affected-domain fact being reused after a command may have mutated that domain;
- controller loss being rewritten as target-operation failure without re-observation;
- `RECOVERED` being promoted to `ACCEPTED` without a fresh successful operation transaction.

## Execution architecture

The production execution shape remains deliberately thin:

```text
HOSTED PREPARE
  resolve exact source identity and required Quality authority
  build/sign exact artifacts where required
  publish bounded immutable inputs

CONTROL FACT ADMISSION
  resolve durable bounded observations
  reconstruct required dependency context
  classify each candidate fact by causal validity
  reuse only facts explicitly admitted by the operation contract

SELF-HOSTED DEVICE EXECUTION
  fetch/verify exact canonical operation logic
  observe target + required capabilities where fresh evidence is required
  acquire mutation serialization
  re-observe target at destructive boundary
  advance affected domain generation when mutation may reach the target
  execute only the authorized operation effect
  independently observe postcondition on the real phone
  emit bounded operation evidence + resulting fact dependencies

AMBIGUITY HANDLER
  if controller/runner/result path is lost after possible mutation:
    never fall back to old affected-domain facts
    do not blind-retry
    re-observe target read-only
    classify applied / not-applied / partial / quarantine

RECOVERY
  normalize only project-owned state
  independently verify recovery postcondition
  emit RECOVERED or QUARANTINED

EVIDENCE PERSISTENCE
  persist only the bounded evidence required by the enclosing contract
  classify persistence independently from device truth
```

No additional workflow layer should exist merely to mirror these states. The State Machine is authoritative; workflows execute it.

## Foundation proof sequence

The physical-device control foundation is proven in one sequential order:

1. **Specify the complete model** — state dimensions, causal fact dependencies/invalidation, operation contracts, invalid combinations, terminal states and recovery semantics are explicit.
2. **Prove deterministic reducer/guard behavior offline** — causal fact validity and transaction logic are side-effect-free and directly tested without workflow narrative.
3. **Prove real-phone observation** — target identity and device-verifiable facts are observed on the real phone with bounded dependency metadata required for safe reuse.
4. **Prove representative effect domains through the same engine** — filesystem, package, runtime/process and connectivity operations use the same guard/mutation/generation/verification semantics without separate workflow truth.
5. **Inject controller/runner loss** before, during and after destructive boundaries; affected-domain pre-mutation facts become stale and `UNKNOWN_EXECUTION_OUTCOME` requires re-observation before non-idempotent retry.
6. **Inject evidence-persistence failure** after valid observation; device mutation is not replayed merely to obtain an artifact.
7. **Prove recovery/quarantine** from every representative partial state.
8. **Restart controller/runner and reboot the phone**; reconstruct the next decision from durable transaction identity, causal dependency context and fresh observation where required.
9. **Reproduce the clean project-owned device baseline repeatedly** without depending on incidental prior installation state.
10. **Accept the foundation on the real phone** only when no defined transition requires narrative inference and no unresolved destructive ambiguity remains.
11. **Only then grow application behavior through this engine.**
12. **Only after phone acceptance generalize proven primitives to VM/provider adapters.**

## Foundation Definition of Done

The State Machine foundation is complete only when:

- every admitted state/operation combination has deterministic guard behavior;
- unknown/invalid/conflicting combinations fail closed;
- unrelated Git/source changes do not invalidate source-independent physical facts;
- every reusable fact has explicit causal dependencies and every required dependency mismatch/missing context is handled deterministically;
- every mutating operation declares affected physical domains and prevents pre-mutation affected-domain fact reuse after possible mutation;
- every destructive boundary has an ambiguity classification and recovery/quarantine path;
- command success never substitutes for independent target verification;
- workflow success never substitutes for reducer acceptance;
- required evidence persistence remains separate from target truth;
- no non-idempotent blind-retry path remains;
- controller/runner restart and phone reboot do not require human narrative to recover transaction meaning;
- the allowed project-owned phone baseline is reproducible more than once;
- no correctness assumption depends on preserving the current incidental installation;
- the model remains understandable as `admitted facts -> guard -> transaction -> effect -> independent observation -> resulting facts/state` without workflow-specific parallel truth.

## Quality requirements

Verification should directly prove behavior or an independent invariant. Do not add tests/checkers whose primary purpose is to verify that other tests/checkers exist or ran.

Permanent automated evidence should focus on:

- deterministic causal fact-validity behavior;
- deterministic reducer and guard behavior;
- impossible-trace rejection;
- separation of execution/postcondition/persistence results;
- mutation-boundary authority;
- affected-domain invalidation after possible mutation;
- ambiguous outcome requiring re-observation;
- recovery/quarantine semantics;
- idempotency rules;
- source/transaction/target evidence isolation.

Real-phone acceptance should focus on the physical boundaries that hosted tests cannot prove: current target facts, actual effects, postconditions, disconnect ambiguity, reboot/restart and reproducible recovery.

Prefer a small number of strong transition/fault tests over layers of tests that only assert policy wording or test invocation.
