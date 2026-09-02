# Transactional Operation State Machine v1

Status: canonical transaction model implemented by `scripts/operation_state_machine.py`; core fail-closed semantics are Quality-tested and are being production-proven adapter by adapter. This document does not itself authorize a production transition; public Issue #179 remains the execution cursor.

## Goal

Turn the evidence-derived control model into an executable lifecycle for real operations. The state machine is intentionally split into two layers:

1. `control_state_machine.py` answers **what is proven right now?**
2. `operation_state_machine.py` answers **what phase may execute next in this exact transaction?**

A phone is never globally `READY`. An operation progresses only when the exact predecessor phase has current CONTROL evidence in the same transaction.

The same rule is intended for later VM/provider adapters: there is no global infrastructure-ready flag to inherit. Each operation consumes exact current facts and emits exact postconditions/evidence for the next reducer pass.

## Core rule

Every real operation follows:

```text
OBSERVE -> VERIFY -> MUTATE -> INDEPENDENTLY VERIFY -> ACCEPT
```

Never:

```text
command returned success -> assume desired state -> continue
```

For destructive operations the first mutation creates a transaction boundary. Any unresolved failure after that boundary enters recovery. Recovery is a separate state path and cannot silently become acceptance.

### Fact-first transition rule

A transition is admissible only from independently proven current state. The orchestrator MUST distinguish three dimensions:

```text
operation_execution_result
postcondition_verification_result
evidence_persistence_result
```

They are intentionally not aliases:

- an operation command may succeed while the desired postcondition is not proven;
- the postcondition may be proven on the target while durable bounded evidence persistence fails;
- a workflow/job may conclude `success` while a reducer still classifies the operation as unaccepted, recovered, quarantined or unpersisted;
- a failed workflow may still contain valid bounded observations up to the exact failure stage, while all later stages remain unobserved.

Where a guard requires durable evidence, `evidence_persistence_result != success` blocks state promotion even if the target observation itself was valid. Missing durability must not be reconstructed later from narrative, logs or remembered operator state.

A canonical SHA advance also invalidates any prior SHA-bound admission for subsequent device operations. New source identity requires new current-SHA authority before later phone work can proceed.

## Android current-source clean-install lifecycle

The full operation contract is:

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
| `source_quality` | VERIFY | exact protected canonical SHA has exact successful Quality authority |
| `artifact_signed` | VERIFY | exact source-built release candidate, signing identity, version and typed digest are proven |
| `runner_assignment` | OBSERVE | exact self-hosted Android production job is assigned to the expected runner contract |
| `source_delivery` | VERIFY | exact immutable canonical operation logic is available in the executing job |
| `phone_access_initial` | VERIFY | registered-device CONTROL preflight proves the target before capability work |
| `capability_inventory` | VERIFY | every capability required by the operation is explicitly supported |
| `mutation_lock` | VERIFY | global production-phone mutation serialization is held by the exact job |
| `phone_access_boundary` | VERIFY | registered-device CONTROL proof is repeated in the same job immediately before mutation |
| `stop_owned_runtime` | MUTATE | only project-owned running runtime is stopped or definite absence is proven |
| `remove_owned_runtime` | MUTATE | only the explicitly-owned managed runtime namespace is removed/normalized |
| `uninstall_legacy_apk` | MUTATE | legacy package is definitely absent afterwards; legacy presence is not required beforehand |
| `install_new_apk` | MUTATE | Android package manager reports installation of the exact candidate attempt |
| `verify_new_apk` | VERIFY | independent installed version + installed APK typed digest equal the exact candidate |
| `materialize_runtime` | MUTATE | source-bound runtime/config is materialized in a fresh generation |
| `verify_runtime` | VERIFY | runtime file identity/integrity/current-generation binding are independently proven |
| `start_runtime` | MUTATE | supervisor/application service start commands were executed for the exact new generation |
| `structural_health` | ACCEPT | expected processes/services/local ports are structurally present for the exact generation |
| `functional_probe` | ACCEPT | a bounded real data-path probe succeeds through the intended application path |
| `accept` | ACCEPT | all preceding evidence belongs to the same transaction/generation and final acceptance is recorded |

`uninstall_legacy_apk=PASSED` never implies `install_new_apk=PASSED`.

`install_new_apk=PASSED` never implies `verify_new_apk=PASSED`.

`structural_health=PASSED` never implies `functional_probe=PASSED`.

## Phone access is an operation and a boundary invariant

A standalone access certification contract exists:

```text
source_quality
  -> runner_assignment
  -> source_delivery
  -> phone_access
```

A separate capability certification contract adds `capability_inventory` after access.

A previous successful access certification is useful evidence but cannot satisfy the destructive transaction boundary. `phone_access_boundary` must pass again inside the exact mutation job.

A phone-access proof is source-bound where the control contract binds it to canonical SHA. Once canonical `main` advances, that earlier proof remains historical evidence only and cannot silently authorize operations against the new source identity.

## Capability set for Android clean install

The adapter should classify at least:

- ADB shell;
- package manager query/uninstall/install;
- root/privilege execution when managed runtime requires it;
- project-owned managed-root visibility;
- bounded remove/create/rename operations in that owned root;
- push/pull;
- digest/stat/readlink tooling;
- process inspection;
- local network/port inspection;
- free-space inspection;
- ownership/mode operations required by runtime materialization.

Each required capability is `SUPPORTED`, `UNSUPPORTED`, or `UNKNOWN`. `UNKNOWN` never satisfies the clean-install guard.

## Normal operation states

The reducer emits these transaction states:

```text
PREPARING
READY_FOR_BOUNDARY_REPROOF
READY_TO_MUTATE
TRANSACTION_ACTIVE
ACCEPTED
REFUSED
CONFLICT
INVALID_TRACE
```

`READY_TO_MUTATE` only means all non-destructive prerequisites and the explicit same-transaction mutation-boundary proof have passed. It does not mean any mutation has happened.

`TRANSACTION_ACTIVE` means at least one destructive step has independently evidenced PASS.

`ACCEPTED` requires every normal phase including `functional_probe` and `accept`, plus any durability/admission requirement imposed by the enclosing production operation contract.

## Recovery model

The clean-install operation intentionally does not restore an obsolete application generation. Its recovery contract is a clean forward baseline:

```text
recovery_classify
  -> recovery_stop_owned_runtime
  -> recovery_remove_incomplete_runtime
  -> recovery_normalize_package
  -> recovery_verify_clean_baseline
```

Recovery states:

```text
RECOVERY_REQUIRED
RECOVERING
RECOVERED
QUARANTINED
```

Rules:

- any failure before the first destructive PASS is `REFUSED`; no recovery is required;
- any failure after a destructive PASS is `RECOVERY_REQUIRED`;
- recovery is explicit evidence, not an exception handler that assumes success;
- a failed/skipped recovery step is `QUARANTINED`;
- complete recovery is `RECOVERED`, not `ACCEPTED`;
- after `RECOVERED`, a new operation transaction is required for another install attempt;
- rollback to the old application generation is not part of this contract;
- if post-mutation verification becomes unavailable, do not infer the post-state from command success; retain recovery/quarantine semantics until independently classified;
- if recovery/cleanup observation proves the target is already absent, absence is a postcondition, not a reason to perform an unnecessary mutation.

## Evidence isolation

Every phase evidence item is bound to:

```text
step_id
status: PASSED | FAILED | SKIPPED
transaction_id
source_ref
authority
lifecycle
```

For state advancement:

- authority must be `CONTROL`;
- lifecycle must be `CURRENT`;
- transaction ID must equal the operation transaction;
- source reference must be non-empty;
- conflicting current evidence fails to `CONFLICT`;
- evidence from another transaction, DIAGNOSTIC evidence, AUDIT evidence, or STALE evidence cannot advance the transaction.

Durability is evaluated separately from phase truth. If an enclosing operation requires a durable bounded evidence artifact, a phase trace can be internally valid while the production-control classification remains unpersisted and therefore inadmissible for the next dependent transition.

## Trace validity

The reducer rejects impossible histories. In particular:

- a later phase cannot be `PASSED` while an earlier required phase is not `PASSED`;
- a destructive PASS without a passed mutation boundary is invalid;
- unknown step IDs are invalid;
- conflicting current status for one phase is conflict;
- post-boundary failure cannot fall back to `PREPARING` or `READY_TO_MUTATE`.

This is how the model prevents hand-written workflow narratives from manufacturing state.

## Execution architecture

The preferred production execution shape is one orchestration workflow with separate hosted and self-hosted jobs:

```text
HOSTED PREPARE
  resolve canonical main + exact Quality
  build/sign native + APK artifacts
  verify candidate evidence
  publish same-run immutable candidate artifacts

SELF-HOSTED MUTATION (global phone lock)
  fetch/verify exact canonical operation logic
  PHONE_ACCESS initial
  capability inventory
  acquire/confirm transaction metadata
  PHONE_ACCESS boundary reproof
  perform ordered mutation phases
  independently verify each postcondition
  perform structural + functional acceptance
  emit bounded operation evidence

EVIDENCE PERSISTENCE
  persist exactly the bounded evidence required by the operation contract
  classify persistence independently from device execution/postcondition state
  fail closed if required durability cannot be proven after bounded safe retry

RECOVERY HANDLER (same self-hosted job/context where possible)
  classify partial state
  normalize only project-owned state
  independently verify clean baseline
  emit RECOVERED or QUARANTINED evidence
```

Signing secrets remain in the hosted build/sign job unless an existing design explicitly requires otherwise. Provider credentials are not required for the local Android clean-install transaction.

## Production-proven semantics so far

The complete Android adapter is not yet accepted, but several state-machine distinctions have already been exercised by real production-control runs:

- a source-delivery transport failure before ADB correctly left phone access `UNOBSERVED` instead of inventing a phone failure;
- filesystem certification crossed into a bounded mutation transaction and correctly quarantined when safe completion/post-state could not be proven;
- a later read-only quarantine observation validated bounded target absence but its evidence-artifact upload failed; control correctly classified the result as observed-but-unpersisted rather than promoting durable absence or cleanup authority.

These are evidence that the fail-closed model is operationally necessary. They are not a claim that the full clean-install/runtime/data-path lifecycle is already accepted.

## Efficient certification order

The fastest reliable route to a proven adapter is:

1. evidence-persistence reliability for bounded CONTROL artifacts, including bounded retry only for explicitly safe persistence transport failures;
2. CONTROL phone-access certification on the exact current canonical SHA;
3. read-only capability inventory;
4. one bounded owned scratch/managed filesystem mutation with verify/delete/verify and explicit recovery/quarantine semantics;
5. package query lifecycle on the exact app;
6. current-source clean install through uninstall/install/verify;
7. runtime materialization + integrity proof;
8. process/service start and structural health;
9. real bounded functional data-path probe;
10. failure injection at pre-boundary, post-uninstall, post-install, runtime materialization and health stages;
11. recovery proof to `RECOVERED` or explicit `QUARANTINED`;
12. repeat clean transaction from recovered baseline;
13. restart/rehydration and protected transport fallback/return proof;
14. same-SHA soak/acceptance under the Production Baseline release gates;
15. only then generalize the proven operation primitives to a VM/provider adapter.

## Quality requirements

CI must permanently prove at least:

- every clean-install lifecycle phase exists and order is stable;
- uninstall/install/verify are distinct states;
- mutation cannot begin before same-transaction boundary reproof;
- command success never implies postcondition success;
- workflow success never substitutes for reducer acceptance;
- required evidence persistence is independent from operation/postcondition truth and unpersisted evidence cannot authorize the next dependent transition;
- structural health never substitutes for functional acceptance;
- pre-boundary failure is non-mutating refusal;
- post-boundary failure requires recovery;
- recovery failure quarantines;
- successful recovery is not acceptance;
- out-of-order traces are rejected;
- stale/diagnostic/other-transaction evidence cannot advance CONTROL state;
- canonical SHA advancement invalidates prior SHA-bound admission for later production execution;
- legacy rollback cannot silently reappear in the current-source clean-install contract.
