# Evidence-Derived Control State Machine v1

Status: canonical evidence-derived production control model implemented by `scripts/control_state_machine.py` and protected by Quality invariants. Core fail-closed semantics have been exercised by real production-control runs; causal cross-transaction fact validity is now part of the canonical model, while individual Android/runtime/VM adapters still require their own evidence-backed certification. This document defines control semantics but does not itself authorize phone access or mutation. Public Issue #179 remains the execution cursor.

## Purpose

Prevent production-control decisions from being made from assumptions, stale narrative, workflow names, partial failures, unrelated observations, or blanket Git-SHA invalidation.

The control state machine MUST be a deterministic projection of bounded evidence. A state is never asserted manually as truth.

Core rule:

> No evidence -> `UNKNOWN`. Causally invalid evidence -> `STALE`. Conflicting admitted evidence -> `CONFLICT`. Invalid scope -> no promotion. No fail-open transition is allowed.

The production working model is fact-first: issue/checkpoint narrative may identify the single next authorized operation, but only the `CONTROL` projection and required durable evidence can prove the state that operation consumes. Workflow conclusion, remembered progress and historical success are not facts about current downstream state.

Git/GitHub is the canonical authority for source, reviewed contracts, Quality, artifacts and execution admission. It is **not** a global freshness clock for physical device state.

## The state machine is multidimensional

A single linear `READY / NOT_READY` state is unsafe because independent layers can be confused.

These inferences MUST be impossible by construction:

- `JOB_QUEUED_UNASSIGNED` -> `RUNNER_OFFLINE`;
- `RUNNER_ONLINE_IDLE` -> `PHONE_ACCESS_PROVEN`;
- `JOB_SKIPPED` -> runner failure;
- runner assigned -> ADB reached;
- ADB access proven -> package/runtime healthy;
- process/port healthy -> functional acceptance;
- historical success -> fresh mutation authority;
- canonical Git SHA changed -> every physical device fact became stale.

The machine keeps independent state regions and computes permission for each operation from their exact conjunction.

## Three truth roles

Physical control has three distinct evidence roles:

```text
GIT / SOURCE AUTHORITY
  source + reviewed contracts + Quality + artifacts + execution admission

OBSERVED DEVICE FACTS
  bounded physical claims whose reuse is controlled by causal dependencies

TRANSACTION EVIDENCE
  exact ordered trace of one operation transaction
```

`control_state_machine.py` owns fact admission, conflict handling and causal reuse. `operation_state_machine.py` owns ordered transaction semantics. Workflows, Issues and shell/ADB adapters do not own a parallel freshness model.

## Canonical observed-fact model

A raw observation record may contain richer audit metadata, but a reusable physical fact consumed by the reducer is conceptually:

```text
ObservedFact
  subject
  predicate
  value
  target
  observation_ref
  source_ref
  authority
  persisted
  dependencies[]
```

Semantics:

- `subject` identifies the exact observed object (`phone`, package, runtime, process, etc.). Facts for one subject cannot satisfy another subject's predicate.
- `predicate` is bounded/typed, for example `registered_device_match`, `quarantine_path_absent`, `installed_version`.
- `value` is bounded and non-secret. Raw serial, device IP, signing material, tokens and provider credentials are forbidden.
- `target` identifies the logical controlled target without recording sensitive raw identity.
- `observation_ref` identifies one bounded evidence record/probe; facts from incompatible probes cannot be combined into one proof.
- `source_ref` records which exact canonical source produced/interpreted the observation. It is provenance and is **not automatically a validity dependency**.
- `authority` is `CONTROL`, `DIAGNOSTIC` or `AUDIT`.
- `persisted` records whether the bounded evidence required by the consumer was durably stored.
- `dependencies` is the exact causal dependency vector governing safe reuse.

A fact without required provenance, dependency scope or durability MUST NOT participate in a permission decision.

### Causal dependency vector

Each dependency is:

```text
scope -> opaque identity
```

Supported scope families are intentionally narrow:

- `target/...` — logical registered-target binding generation;
- `observer/...` — semantic observer contract/version;
- `domain/...` — physical mutation-domain generation;
- `boot/...` — boot generation for reboot-sensitive facts;
- `session/...` — runner/ADB/control session for ephemeral facts;
- `source/...` — canonical source identity when the fact is source-relative;
- `artifact/...` — exact artifact identity when the fact is artifact-relative;
- `transaction/...` — exact transaction when cross-transaction reuse is forbidden.

Identity tokens are opaque. They may be transaction IDs, accepted mutation evidence IDs, target-binding generations, boot/session tokens, semantic observer versions, Git SHAs or typed artifact digests. The reducer compares identity; it does not infer semantics from token text.

There is no global `DeviceEpoch`.

### Causal validity classification

For an admitted fact and current dependency context:

```text
wrong authority                     -> UNUSABLE
malformed dependency contract       -> INVALID
required persistence missing        -> UNPERSISTED
required current dependency missing -> UNKNOWN
any declared dependency changed     -> STALE
all declared dependencies match     -> VALID
```

Current-context entries not declared by the fact are ignored.

Therefore:

```text
fact source_ref = old Git SHA
current main    = new Git SHA
fact dependencies do not include source/canonical

=> source movement alone does not stale the fact
```

If the fact is source-relative, its dependencies include `source/...`, and a source change correctly makes it stale.

### Mutation-domain invalidation

Each mutating operation declares the physical domains it may change, for example:

```text
filesystem
package
runtime
process
connectivity
```

Once a destructive command may have reached the target, every affected domain generation advances to a new transaction-scoped identity before pre-mutation facts in that domain can be reused. This applies even when command/result transport is lost.

That rule prevents this unsafe path:

```text
old package fact says version=old
install command may have executed
controller loses result
reuse old package fact as CURRENT
```

Instead:

```text
domain/package changes to transaction generation
old package fact -> STALE
fresh real-phone package observation required
```

Only affected/coupled domains declared by the operation are invalidated. A filesystem-only change does not globally stale package/artifact facts.

### Observer semantic identity

Observers are versioned by semantic contract, not by the whole repository SHA.

If a defect or semantic change makes previous observations unsafe to interpret, the relevant `observer/...` identity changes. Facts depending on that observer become stale. Unrelated facts remain unaffected.

A docs-only merge or unrelated implementation refactor does not require a phone recheck merely because the source SHA changed.

### Ephemeral facts

Reachability, process liveness and network connectivity may change without a project mutation. Those facts require `session/...`, `boot/...`, `transaction/...` or another explicit freshness dependency appropriate to their operation contract.

Do not pretend an ephemeral fact becomes indefinitely current merely because its evidence artifact was persisted.

## Evidence authority

`CONTROL` facts are produced by the accepted Git-driven control path and are the only facts allowed to satisfy production operation guards.

`DIAGNOSTIC` facts may come from a bounded local/operator diagnostic. They can explain a blocker or choose the next safe observation, but they MUST NOT authorize install, delete, reconstruction, activation, rollback or any other production mutation.

`AUDIT` facts are retained historical evidence. They may explain what happened but cannot authorize a current operation.

A reducer may project each authority class independently. A `DIAGNOSTIC` projection can say `PHONE_ACCESS_PROVEN` for diagnosis while the `CONTROL` projection remains `PHONE_ACCESS_UNOBSERVED`. Mutation permission always consumes the `CONTROL` projection.

## Android device-reality authority

The real registered production phone is the authoritative observation oracle for Android device reality. `CONTROL` describes the authority of a fact; it does not permit hosted or synthetic evidence to invent a physical Android fact that is directly observable on the target device.

If an Android predicate or postcondition can be observed on the real production phone, a dependent production transition MUST consume bounded device-backed `CONTROL` evidence from an authorized real-phone operation. That evidence must carry the target/dependency scope, freshness and durability required by the operation contract.

Hosted `Quality`, unit/integration tests and private orchestration can prove source identity, observer/reducer behavior, workflow policy and transport. They cannot by themselves prove the Android filesystem, installed package/signer, runtime generation, process/service state, network state or functional data path. If device observation is blocked, the Android predicate remains `UNKNOWN`/unproven; the blocker may authorize the smallest infrastructure repair, but completing that repair does not promote the blocked Android predicate.

## Evidence rules

1. Two admitted authoritative values for the same exact scoped subject/predicate/dependency generation that disagree are `CONFLICT`.
2. A later observation in a newer causally relevant generation may supersede an older fact without rewriting history.
3. `STALE`, `UNKNOWN`, `CONFLICT`, `INVALID`, `UNPERSISTED` and `UNUSABLE` never mean true or false; they fail closed where current proof is required.
4. Narrative issue comments are audit/cursor context. They do not become machine truth without bounded evidence references.
5. Facts from different bounded probes MUST NOT be combined to manufacture a proof that no single compatible probe established.
6. Facts from different authority classes MUST NOT be combined to satisfy one control predicate.
7. If an operation contract requires a durable bounded artifact, a validated observation with failed artifact persistence remains unpersisted for dependent guards. Logs or narrative MUST NOT reconstruct missing durable authority.
8. Operation execution outcome, independent postcondition observation and evidence persistence are separate facts. No one dimension may silently stand in for another.
9. Hosted/offline evidence MUST NOT replace device-backed evidence for an Android fact or postcondition directly verifiable on the real phone.
10. Source provenance alone MUST NOT globally invalidate a physical fact; source identity participates in validity only when declared by the fact/guard.
11. Once a destructive command may have reached the target, pre-mutation facts in every affected domain MUST NOT remain reusable under the old generation.

## State regions

### 1. Source authority

```text
SOURCE_UNKNOWN
SOURCE_RESOLVED
QUALITY_UNKNOWN
QUALITY_FAILED
QUALITY_PROVEN
```

`QUALITY_PROVEN` requires exact equality between the intended canonical SHA and the successful Quality run SHA.

Source-bound operation authority is not portable across canonical revisions unless the operation contract explicitly permits it. Advancing `main` therefore requires new exact source/Quality admission for operations against the new source. This rule applies to source authority; it is not a blanket invalidation of unrelated physical facts.

### 2. Command / workflow lifecycle

```text
COMMAND_UNOBSERVED
COMMAND_REJECTED
COMMAND_QUALIFIED
JOB_NOT_CREATED
JOB_SKIPPED
JOB_QUEUED_UNASSIGNED
JOB_ASSIGNED
JOB_RUNNING
JOB_SUCCEEDED
JOB_FAILED
JOB_CANCELLED
JOB_TIMED_OUT
```

Rules:

- `JOB_QUEUED_UNASSIGNED` requires a queued exact job with no runner assigned yet.
- `JOB_ASSIGNED` requires concrete runner identity on that exact job.
- `JOB_SKIPPED` is a workflow-control outcome; it says nothing about runner availability.
- failure location is independent and recorded as `failure_stage`.
- `JOB_SUCCEEDED` is a workflow lifecycle fact, not `ACCEPTED`, not a verified target postcondition and not proof that required evidence was durably persisted.

### 3. Runner registration / availability

```text
RUNNER_UNKNOWN
RUNNER_UNREGISTERED
RUNNER_LABEL_MISMATCH
RUNNER_OFFLINE
RUNNER_ONLINE_IDLE
RUNNER_ONLINE_BUSY
RUNNER_CONFLICT
```

Required facts include repository registration, expected identity, exact labels, online/offline and busy/idle.

Runner state never proves USB, ADB or phone state.

### 4. Runner transport

```text
TRANSPORT_UNKNOWN
TRANSPORT_RECENTLY_HEALTHY
TRANSPORT_DEGRADED
TRANSPORT_FAILED
```

Transport is independent from runner registration. An online/idle runner may simultaneously have degraded outbound transport.

Relevant evidence includes successful runner/listener communication, successful immutable-source delivery, TLS timeout/EOF/`SslStream`/SSL-connect failures and bounded retry exhaustion.

### 5. Immutable canonical source delivery

```text
SOURCE_FETCH_UNOBSERVED
SOURCE_FETCH_SUCCEEDED
SOURCE_FETCH_FAILED_TRANSPORT
SOURCE_FETCH_FAILED_TRANSIENT
SOURCE_FETCH_FAILED_PERMANENT
SOURCE_FETCH_DIGEST_MISMATCH
```

`SOURCE_FETCH_FAILED_TRANSPORT` means the delivery attempt failed because of observed transport behavior, without inventing whether the underlying fault is transient or permanent.

If execution stops here, ADB and phone access remain `UNOBSERVED`.

### 6. Android phone access

```text
PHONE_ACCESS_UNOBSERVED
ADB_TOOL_UNAVAILABLE
ADB_INVENTORY_INVALID
ADB_ZERO_DEVICES
ADB_MULTIPLE_DEVICES
ADB_WRONG_DEVICE
ADB_REGISTERED_DEVICE_OFFLINE
ADB_GET_STATE_FAILED
ADB_SHELL_FAILED
PHONE_ACCESS_PROVEN
PHONE_ACCESS_STALE
PHONE_ACCESS_CONFLICT
```

A `PHONE_ACCESS_PROVEN` probe requires one bounded probe scope/source reference proving all seven facts:

1. ADB command available;
2. inventory parse valid;
3. exactly one ADB-visible device;
4. exact match to private `ANDROID_PRODUCTION_SERIAL`, without recording raw serial;
5. registered inventory state is `device`;
6. `adb -s <registered> get-state == device`;
7. `adb -s <registered> shell true` succeeds.

All seven facts MUST originate from the same bounded phone-access probe. Facts from different probes cannot be combined.

Installed package/runtime/process/network observations MUST NOT participate in this derivation.

For reusable access evidence, the corresponding observed facts must carry the target/session/boot/transaction dependencies required by the consuming contract. If that dependency context no longer matches, access becomes stale/unknown for that consumer.

For every mutation, access MUST be re-proved as `CONTROL` evidence in the same self-hosted mutation job immediately before the destructive boundary. Historical/reusable/diagnostic access evidence cannot satisfy that fresh boundary guard.

### 7. Android capabilities

Every capability is independently classified:

```text
SUPPORTED
UNSUPPORTED
UNKNOWN
```

Initial set:

- shell;
- root/privilege model;
- package manager;
- push/pull;
- managed-root visibility;
- stat/readlink/digest tooling;
- process inspection;
- network inspection;
- runtime-directory visibility;
- required shell utilities;
- ownership/permission operations;
- free-space inspection.

`UNKNOWN` never satisfies a `SUPPORTED` requirement.

Capability facts must declare whichever target/observer/domain/boot/session dependencies can causally change the capability. Do not globally invalidate the entire inventory on an unrelated Git merge.

### 8. Observed target state

Desired state and observed state are separate. For Android subjects, any state below that is directly observable on the real production phone must be derived from bounded device-backed `CONTROL` evidence rather than hosted/offline inference.

Package:

```text
PACKAGE_UNKNOWN
PACKAGE_ABSENT
PACKAGE_PRESENT_IDENTITY_UNKNOWN
PACKAGE_PRESENT_IDENTITY_PROVEN
PACKAGE_CONFLICT
```

Runtime:

```text
RUNTIME_UNKNOWN
RUNTIME_ABSENT
RUNTIME_PRESENT_INACTIVE
RUNTIME_ACTIVE_IDENTITY_UNKNOWN
RUNTIME_ACTIVE_IDENTITY_PROVEN
RUNTIME_CONFLICT
```

Process:

```text
PROCESS_UNKNOWN
PROCESS_STOPPED
PROCESS_RUNNING_IDENTITY_UNKNOWN
PROCESS_RUNNING_IDENTITY_PROVEN
PROCESS_MULTIPLE
PROCESS_STALE
```

Filesystem/package/runtime/process facts are admitted in the relevant physical domain generation. A mutation in that domain stales the previous generation before the new postcondition is known.

### 9. Mutation transaction

```text
MUTATION_DISARMED
MUTATION_INELIGIBLE
MUTATION_ELIGIBLE
MUTATION_LOCK_HELD
MUTATION_BOUNDARY_REPROVED
TRANSACTION_ACTIVE
UNKNOWN_EXECUTION_OUTCOME
POSTCONDITION_VERIFYING
TRANSACTION_COMMITTED
REFUSED
RECOVERY_REQUIRED
QUARANTINED
```

`MUTATION_ELIGIBLE` is a derived permission state, not mutation authority by itself.

Before `TRANSACTION_ACTIVE`, every transaction-scoped guard required by the operation contract must be admitted `CONTROL` evidence. Reusable physical facts may satisfy only guards that explicitly permit reuse.

At the first command that may produce a destructive effect, affected physical-domain generation(s) advance to the transaction identity. If controller/result transport is then lost, the state is `UNKNOWN_EXECUTION_OUTCOME`; old affected-domain facts cannot reappear as current.

After the first destructive boundary, an unresolved failure transitions to re-observation/recovery semantics unless independent evidence proves the target outcome. If safe target state/recovery cannot be established, transition to `QUARANTINED`.

### 10. Acceptance

```text
ACCEPTANCE_UNOBSERVED
STRUCTURE_FAILED
STRUCTURE_PROVEN
FUNCTION_FAILED
FUNCTION_PROVEN
ACCEPTED
```

`ACCEPTED` requires both structural and real functional acceptance for the same target generation/transaction. A running process or open port cannot satisfy `FUNCTION_PROVEN`.

Where the production operation contract additionally requires durable bounded evidence, durable persistence is also an admission requirement before the accepted result may authorize a dependent transition.

## Failure-stage taxonomy

Every failed operation identifies the earliest verified failure stage:

```text
COMMAND_GATE
SOURCE_AUTHORITY
RUNNER_ASSIGNMENT
RUNNER_TRANSPORT
SOURCE_FETCH
ADB_TOOL
ADB_INVENTORY
DEVICE_IDENTITY
ADB_STATE
ADB_SHELL
CAPABILITY
ARTIFACT
MUTATION_AUTHORITY
MUTATION_LOCK
MUTATION_BOUNDARY
MUTATION_EXECUTION
POSTCONDITION
STRUCTURAL_ACCEPTANCE
FUNCTIONAL_ACCEPTANCE
RECOVERY
```

Later stages remain `UNOBSERVED`, not failed.

Example: immutable-source transport fails before the first ADB probe:

```text
JOB_FAILED
runner assignment = independently proven
TRANSPORT_DEGRADED or TRANSPORT_FAILED
SOURCE_FETCH_FAILED_TRANSPORT
PHONE_ACCESS_UNOBSERVED
failure_stage = SOURCE_FETCH
mutation_performed = false (only if explicitly evidenced)
```

The machine MUST NOT infer runner unavailability, ADB failure or phone failure from that event.

## Permission is a predicate, never a stored global READY flag

Every operation declares its own guard expression over admitted `CONTROL` facts and transaction evidence.

Example read-only phone-access probe:

```text
can_execute(probe_phone_access) :=
  command_qualified
  AND exact_source_sha_resolved
  AND matching_runner_job_assigned
  AND immutable_probe_logic_available
  AND no_forbidden_mutation_scope
```

Future bounded filesystem mutation:

```text
can_execute(test_managed_write) :=
  exact_source_quality_proven
  AND command_qualified
  AND admitted_required_filesystem_facts
  AND mutation_lock_held
  AND phone_access_reproved_same_job
  AND required_capabilities_supported
  AND exact_test_namespace_bound
  AND path_confinement_proven
  AND mutation_authority_current
```

If any required term is absent, false, `UNKNOWN`, `STALE`, `CONFLICT`, `UNPERSISTED`, diagnostic-only, audit-only or invalid for the requested scope, permission is denied and exact blocking predicates are emitted.

## Operation contract

Every adapter/control operation declares:

```text
operation_id
kind: OBSERVE | VERIFY | MUTATE | ACCEPT | RECOVER
inputs
required_facts
reusable_fact_requirements
freshness_requirements
affected_physical_domains
mutation_scope
lock_requirement
timeout
retry_policy
idempotency
preconditions
postconditions
evidence_schema
failure_stage_mapping
failure_transition
compensation
```

Retries are allowed only when the contract explicitly classifies the failure as retryable and retry cannot widen mutation scope. Mutation commands are never automatically retryable.

Evidence-persistence transport retries are a separate concern from retrying the device operation itself. They may be bounded only when the evidence artifact is immutable/bounded, the retry cannot repeat or widen phone mutation, and exhaustion remains explicitly unpersisted rather than accepted.

## Desired vs observed

Every mutation follows:

```text
ADMIT/OBSERVE -> GUARD -> MUTATE -> INDEPENDENTLY OBSERVE -> CLASSIFY
```

Never:

```text
MUTATE -> assume success -> advance state
```

A successful command is an operation result, not proof of its postcondition.

For Android, fresh `OBSERVE` and `INDEPENDENTLY OBSERVE` mean real-phone device-backed observation whenever the relevant predicate is technically observable on the registered production phone. Hosted success does not satisfy that physical observation.

Causally valid persisted facts may be reused where the exact operation contract permits them; this reduces unnecessary observation but never substitutes for required destructive-boundary proof.

## Real production examples that motivate and validate the model

Private read-only preflight run `33647329233` passed its hosted command gate and was assigned to exact production runner `mobile-proxy-phone-linux-production`. It then failed while fetching immutable canonical preflight logic with an SSL-connect transport error. All ADB/preflight steps were skipped.

Correct control classification for that run is therefore:

```text
JOB_FAILED
runner assignment = PROVEN
SOURCE_FETCH_FAILED_TRANSPORT
failure_stage = SOURCE_FETCH
PHONE_ACCESS_UNOBSERVED
```

This is not `RUNNER_OFFLINE`, not `ADB_FAILED`, and not `PHONE_FAILED`.

Later production filesystem work exercised additional distinctions:

- a bounded filesystem transaction that could not prove safe completion entered explicit quarantine rather than being inferred successful from partial command progress;
- read-only quarantine observation run `33682071376` validated its bounded observation on the phone, but required evidence artifact upload failed. The correct control result remained observed-but-unpersisted, so durable absence and cleanup authority were not inferred from the successful device observation or job narrative;
- after persistence/source-transport hardening, read-only quarantine observation run `33692515684` durably proved the two exact quarantined transaction paths already absent. That physical absence is a filesystem/target/observer fact; a later docs-only canonical SHA advance is provenance movement, not by itself a physical filesystem mutation.

These examples prove why state regions, evidence durability and causal validity must remain independent. They do not claim that the complete Android runtime/data-path adapter is already accepted.

## Machine-readable snapshot

A bounded snapshot contains only derived non-secret state plus evidence references. Unknown values stay explicit; for example, if mutation status was not observed, it must be `null`/unknown rather than silently `false`.

```json
{
  "schema_version": 1,
  "target": "android-production",
  "derived": {
    "command_job": "JOB_FAILED",
    "runner": "RUNNER_UNKNOWN",
    "transport": "TRANSPORT_DEGRADED",
    "source_fetch": "SOURCE_FETCH_FAILED_TRANSPORT",
    "phone_access": "PHONE_ACCESS_UNOBSERVED",
    "failure_stage": "SOURCE_FETCH"
  },
  "blocking_predicates": [
    "source_fetch=SOURCE_FETCH_SUCCEEDED"
  ],
  "mutation_performed": false
}
```

Raw serial, device IP, secrets, signing material and provider credentials are forbidden.

Reusable physical facts may be stored/referenced separately from one-operation snapshots. Any derived cache of current facts/generations is convenience only and must be reconstructible from durable bounded evidence; no manual state file becomes physical authority.

## First implementation/certification sequence

1. fact/evidence schema and deterministic reducer;
2. causal dependency-vector validity and direct reducer tests;
3. command/job/runner/transport/source-fetch regions;
4. bounded durable-evidence persistence semantics, including explicit unpersisted state after safe retry exhaustion;
5. real-phone `probe_access()` and exact target/session freshness semantics;
6. durable quarantine observation/reuse with filesystem target/observer/domain dependencies;
7. perform cleanup only if admitted device-backed facts require it; proven absence skips mutation;
8. certify capability inventory and bounded scratch/managed-root filesystem mutation with domain-generation advancement, verify/delete/post-absence and recovery/quarantine semantics;
9. inject ambiguous mutation/result loss and prove old affected-domain facts cannot be reused before re-observation;
10. package query and clean-install lifecycle;
11. runtime lifecycle;
12. process/service lifecycle;
13. structural + real functional acceptance;
14. failure injection and recovery classification;
15. restart/rehydration and reboot/transport fallback proof from durable evidence + current dependency context;
16. repeated clean-baseline reproduction and physical acceptance;
17. derive generic contracts from proven Android behavior;
18. VM adapter against the same proven contracts.

Infrastructure/control-plane work may interrupt this sequence only to close a concrete blocker to the next safe real-phone observation or mutation. When the blocker is closed, certification resumes at that device-backed step; the infrastructure fix is not counted as completion of the Android state it unblocks.

## Quality invariants

Offline Quality MUST permanently test at least:

- `JOB_SKIPPED` never maps to runner failure;
- queued-unassigned and assigned jobs are distinguishable;
- source-fetch failure leaves ADB/phone state unobserved;
- online runner and degraded transport can coexist;
- facts for different subjects cannot satisfy/conflict with one another;
- cross-probe ADB facts cannot be combined into `PHONE_ACCESS_PROVEN`;
- causally stale access evidence cannot satisfy a fresh access guard;
- package/runtime health never affects `PHONE_ACCESS_PROVEN`;
- `DIAGNOSTIC` evidence cannot elevate the `CONTROL` projection;
- missing mutation evidence stays unknown rather than becoming `false`;
- command success never implies postcondition success;
- workflow success never implies operation acceptance;
- required-but-unpersisted evidence cannot authorize a dependent transition;
- hosted/unit/integration evidence cannot substitute for device-backed CONTROL evidence for an Android predicate verifiable on the real production phone;
- mutation cannot enter `TRANSACTION_ACTIVE` without same-job access reproof and lock;
- post-boundary unknown state cannot return to READY/ACCEPTED;
- source-bound authority becomes stale on a source dependency change;
- source-independent physical facts remain valid across unrelated canonical SHA changes;
- domain facts become stale when the affected domain generation changes;
- target/observer dependency changes stale only dependent facts;
- missing dependency context stays `UNKNOWN`;
- possible destructive mutation prevents reuse of old affected-domain facts;
- forbidden sensitive values cannot enter bounded evidence.

Do not add another checker solely to verify these tests exist. Direct reducer/transition tests in the existing Quality path are the proportionate protection.

## Rule for agents

A new agent MUST report control state as:

```text
OBSERVED FACTS
FACT VALIDITY / CAUSAL DEPENDENCIES
DERIVED STATES
UNOBSERVED / STALE / CONFLICTING / UNPERSISTED FACTS
EXACT BLOCKING PREDICATES
NEXT SAFE OBSERVATION OR OPERATION
```

It MUST identify the authority class of observations, distinguish Git/source authority from physical-fact validity, distinguish required evidence persistence from target observation, distinguish hosted software/policy proof from real-phone Android physical-state proof, and MUST NOT collapse an upstream failure into assumptions about downstream layers.

It MUST NOT request a new phone observation solely because `main` changed. It must identify the dependency/freshness rule that makes the previous fact unusable or the transaction-boundary rule that requires a fresh observation.
