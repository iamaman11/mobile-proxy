# Evidence-Derived Control State Machine v1

Status: design candidate. This document is architecture only. It does not authorize phone access or mutation. Public Issue #179 remains the execution cursor.

## Purpose

Prevent production control decisions from being made from assumptions, stale narrative, workflow names, partial failures, or unrelated observations.

The control state machine MUST be a deterministic projection of bounded evidence. A state is never asserted manually as truth.

The core rule is:

> No evidence -> `UNKNOWN`. Expired evidence -> `STALE`. Conflicting fresh evidence -> `CONFLICT`. No fail-open promotion is allowed.

## Why the machine is multidimensional

A single linear `READY / NOT_READY` state is unsafe because independent layers can be confused.

Examples that MUST be impossible by construction:

- `job=QUEUED_UNASSIGNED` must not imply `runner=OFFLINE`;
- `runner=ONLINE_IDLE` must not imply `PHONE_ACCESS=PROVEN`;
- `job=SKIPPED` must not imply runner failure;
- `runner assigned` must not imply ADB was reached;
- `ADB access proven` must not imply package/runtime health;
- process/port health must not imply functional acceptance;
- historical success must not satisfy fresh mutation authority.

The machine therefore keeps independent state regions and derives operation permission from their conjunction.

## Canonical fact model

Every observation used for a control decision MUST be represented as a fact with at least:

```text
fact_id
subject
predicate
value
observer
method
observed_at
valid_until
scope
source_ref
sensitivity
```

### Required semantics

- `subject`: exact thing observed, for example `public-source`, `private-runner`, `workflow-run:123`, `android-production-target`.
- `predicate`: typed property, for example `main_sha`, `quality_conclusion`, `runner_online`, `adb_device_count`, `registered_device_match`.
- `value`: typed bounded value. Secrets and raw device identifiers are forbidden.
- `observer`: component that made the observation, for example GitHub API, workflow job, canonical Android adapter, local runner diagnostic.
- `method`: exact observation operation.
- `observed_at`: when the observation was made.
- `valid_until`: when it may no longer be used as current authority. Historical evidence remains historical after expiry.
- `scope`: exact SHA/run/job/transaction/target binding needed to prevent evidence reuse in another context.
- `source_ref`: bounded evidence pointer such as workflow run, artifact, commit, or audit record.
- `sensitivity`: `PUBLIC` or `BOUNDED_PRIVATE`.

A fact without provenance or scope MUST NOT participate in a permission decision.

## Evidence lifecycle

Each fact is evaluated as exactly one of:

- `CURRENT` — valid and unambiguous for its scope;
- `STALE` — `valid_until` passed or a freshness rule rejects it;
- `SUPERSEDED` — replaced by a later fact from the same monotonic observation stream;
- `CONFLICT` — two current authoritative facts for the same scoped predicate disagree;
- `INVALID` — malformed, unverifiable, wrong scope, or forbidden sensitive content.

Rules:

1. Cross-observer disagreement is `CONFLICT`; do not silently choose the convenient value.
2. A later observation from the same monotonic stream may supersede an earlier one.
3. `STALE`, `CONFLICT`, and `INVALID` are never equivalent to false or true. They fail closed.
4. Narrative issue comments are audit/cursor context, not machine truth, unless they reference the underlying bounded evidence.

## State regions

The control state is the product of the following independent regions.

### 1. Source authority

```text
SOURCE_UNKNOWN
SOURCE_RESOLVED
QUALITY_UNKNOWN
QUALITY_FAILED
QUALITY_PROVEN
```

`QUALITY_PROVEN` requires exact equality between the intended canonical SHA and the successful Quality run SHA.

### 2. Command and workflow lifecycle

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

Derivation rules:

- `JOB_QUEUED_UNASSIGNED` requires queued job plus no assigned runner identity.
- `JOB_ASSIGNED` requires a concrete runner id/name on that exact job.
- `JOB_SKIPPED` is a terminal workflow-control outcome and says nothing about runner availability.
- failure location is recorded separately as `failure_stage`.

### 3. Runner registration and availability

```text
RUNNER_UNKNOWN
RUNNER_UNREGISTERED
RUNNER_LABEL_MISMATCH
RUNNER_OFFLINE
RUNNER_ONLINE_IDLE
RUNNER_ONLINE_BUSY
RUNNER_CONFLICT
```

Required facts include repository binding, expected runner identity, exact labels, online/offline and busy/idle.

Runner state never proves USB, ADB, or phone state.

### 4. Runner transport health

Transport is independent from runner registration:

```text
TRANSPORT_UNKNOWN
TRANSPORT_RECENTLY_HEALTHY
TRANSPORT_DEGRADED
TRANSPORT_FAILED
```

Examples of evidence:

- successful job assignment/listener communication;
- successful immutable-source fetch;
- TLS timeout / EOF / `SslStream` / SSL connect failures;
- repeated bounded retry outcome.

An online runner with fresh TLS failures may be `RUNNER_ONLINE_IDLE + TRANSPORT_DEGRADED` simultaneously.

### 5. Immutable source delivery

Phone jobs that fetch exact canonical scripts have their own region:

```text
SOURCE_FETCH_UNOBSERVED
SOURCE_FETCH_SUCCEEDED
SOURCE_FETCH_FAILED_TRANSIENT
SOURCE_FETCH_FAILED_PERMANENT
SOURCE_FETCH_DIGEST_MISMATCH
```

ADB MUST remain `UNOBSERVED` if execution failed before the ADB probe.

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

`PHONE_ACCESS_PROVEN` requires evidence from one bounded probe scope proving all of:

1. ADB command available;
2. inventory parse valid;
3. exactly one ADB-visible device;
4. exact match to private `ANDROID_PRODUCTION_SERIAL` without recording the raw serial;
5. inventory state is `device`;
6. `adb -s <registered> get-state == device`;
7. `adb -s <registered> shell true` succeeds.

Installed package/runtime/process/network observations MUST NOT participate in this derivation.

A historical `PHONE_ACCESS_PROVEN` may remain audit evidence but becomes `PHONE_ACCESS_STALE` when the consuming operation requires fresher evidence.

For every mutation, phone access MUST be re-proved in the same self-hosted mutation job immediately before the destructive boundary. Historical preflight evidence cannot satisfy that guard.

### 7. Android capabilities

Each capability is independent and tri-state:

```text
SUPPORTED
UNSUPPORTED
UNKNOWN
```

Initial capability set:

- shell;
- root/privilege model;
- package manager;
- push/pull;
- managed-root visibility;
- stat;
- readlink;
- digest tooling;
- process inspection;
- network inspection;
- required runtime directories;
- required shell utilities;
- ownership/permission operations;
- free-space inspection.

`UNKNOWN` never satisfies an operation requiring `SUPPORTED`.

### 8. Observed target state

Target state is observation, not desired state.

Package region:

```text
PACKAGE_UNKNOWN
PACKAGE_ABSENT
PACKAGE_PRESENT_IDENTITY_UNKNOWN
PACKAGE_PRESENT_IDENTITY_PROVEN
PACKAGE_CONFLICT
```

Runtime region:

```text
RUNTIME_UNKNOWN
RUNTIME_ABSENT
RUNTIME_PRESENT_INACTIVE
RUNTIME_ACTIVE_IDENTITY_UNKNOWN
RUNTIME_ACTIVE_IDENTITY_PROVEN
RUNTIME_CONFLICT
```

Process region:

```text
PROCESS_UNKNOWN
PROCESS_STOPPED
PROCESS_RUNNING_IDENTITY_UNKNOWN
PROCESS_RUNNING_IDENTITY_PROVEN
PROCESS_MULTIPLE
PROCESS_STALE
```

Network/acceptance observations are separate from these states.

### 9. Mutation transaction

```text
MUTATION_DISARMED
MUTATION_INELIGIBLE
MUTATION_ELIGIBLE
MUTATION_LOCK_HELD
MUTATION_BOUNDARY_REPROVED
TRANSACTION_ACTIVE
POSTCONDITION_VERIFYING
TRANSACTION_COMMITTED
REFUSED
RECOVERY_REQUIRED
QUARANTINED
```

`MUTATION_ELIGIBLE` is a derived permission state, not authority to mutate by itself.

Before entering `TRANSACTION_ACTIVE`, all operation-specific guards must be current in the same transaction scope.

After the first destructive boundary, any unresolved failure transitions to `RECOVERY_REQUIRED` unless independent evidence proves the target remained unchanged. Unknown post-boundary target state transitions to `QUARANTINED` when safe recovery cannot be proven.

### 10. Acceptance

```text
ACCEPTANCE_UNOBSERVED
STRUCTURE_FAILED
STRUCTURE_PROVEN
FUNCTION_FAILED
FUNCTION_PROVEN
ACCEPTED
```

`ACCEPTED` requires both `STRUCTURE_PROVEN` and `FUNCTION_PROVEN` for the same target generation and transaction.

A running process or open port cannot satisfy `FUNCTION_PROVEN`.

## Failure stage taxonomy

Every failed operation MUST name the earliest verified failure stage:

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

Example: if immutable-source `curl` fails before ADB, the correct projection is:

```text
JOB_ASSIGNED
RUNNER=<independently observed state>
TRANSPORT_DEGRADED or TRANSPORT_FAILED
SOURCE_FETCH_FAILED_TRANSIENT/PERMANENT
PHONE_ACCESS_UNOBSERVED
failure_stage=SOURCE_FETCH
mutation_performed=false
```

The machine MUST NOT infer an ADB or phone failure.

## Permission is a predicate, not a stored READY flag

There is no reusable global `READY=true`.

Every operation declares a guard expression over current facts.

Example read-only phone access probe:

```text
can_execute(probe_phone_access) :=
  command_qualified
  AND exact_source_sha_resolved
  AND matching_runner_job_assigned
  AND immutable_probe_logic_available
  AND no_forbidden_mutation_scope
```

Example future bounded filesystem mutation:

```text
can_execute(test_managed_write) :=
  exact_source_quality_proven
  AND command_qualified
  AND mutation_lock_held
  AND phone_access_reproved_same_job
  AND required_capabilities_supported
  AND exact_test_namespace_bound
  AND path_confinement_proven
  AND mutation_authority_current
```

If any term is `UNKNOWN`, `STALE`, `CONFLICT`, or false, permission is denied with the exact unsatisfied predicate list.

## Operation contract

Every adapter/control operation MUST declare:

```text
operation_id
kind: OBSERVE | VERIFY | MUTATE | ACCEPT | RECOVER
inputs
required_facts
freshness_requirements
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

Retries are permitted only where the operation contract explicitly classifies the failure as transient and where retry cannot widen mutation scope. Mutation commands are not automatically retryable.

## Desired state vs observed state

Desired state is a request. Observed state is evidence.

The reconciler may compute a plan from the difference, but it MUST NOT rewrite observed state because a command returned success.

Every mutation follows:

```text
OBSERVE -> GUARD -> MUTATE -> INDEPENDENTLY OBSERVE -> CLASSIFY
```

Never:

```text
MUTATE -> assume success -> advance state
```

## Current known example that motivated this model

A production read-only preflight may pass its hosted command gate, be assigned to the exact production runner, and still fail while fetching immutable canonical logic before any ADB command runs. In that case the state machine records runner assignment and source-delivery/transport failure while phone access remains unobserved.

This prevents a pre-device transport failure from being mislabeled as runner unavailability or phone failure.

## Machine-readable snapshot

A bounded current-state snapshot should contain only derived, non-secret state plus evidence references, for example:

```json
{
  "schema_version": 1,
  "target": "android-production",
  "authority": {
    "canonical_sha": "<sha>",
    "quality": "PROVEN"
  },
  "runner": {
    "registration": "RUNNER_ONLINE_IDLE",
    "transport": "TRANSPORT_DEGRADED"
  },
  "execution": {
    "run_id": 0,
    "job_state": "JOB_FAILED",
    "failure_stage": "SOURCE_FETCH"
  },
  "phone_access": "PHONE_ACCESS_UNOBSERVED",
  "mutation": "MUTATION_DISARMED",
  "mutation_performed": false,
  "evidence_refs": []
}
```

Raw serial, device IP, secrets, signing material and provider credentials are forbidden.

## First certification sequence

The implementation order for this state machine is deliberately narrow:

1. implement fact/evidence schema and deterministic reducer;
2. model command/job/runner/transport/source-fetch states;
3. feed the current read-only preflight evidence through the reducer;
4. implement Android `probe_access()` evidence;
5. certify access failure modes on the real topology;
6. implement capability inventory;
7. only then introduce bounded safe mutation states;
8. derive package/runtime/process and recovery transitions from real-device certification.

## Quality requirements

Offline Quality MUST permanently test at least:

- `SKIPPED` never maps to runner failure;
- queued unassigned and assigned jobs are distinguishable;
- source-fetch failure leaves ADB/phone state unobserved;
- online runner and degraded transport can coexist;
- stale evidence cannot satisfy mutation authority;
- conflicting facts fail closed;
- package/runtime health never affects `PHONE_ACCESS_PROVEN`;
- command success never implies postcondition success;
- mutation cannot enter `TRANSACTION_ACTIVE` without same-job access reproof and lock;
- post-boundary unknown state cannot return to READY/ACCEPTED;
- raw serial and other forbidden values cannot enter evidence output.

## Rule for agents

A new agent MUST report state in the form:

```text
OBSERVED FACTS
DERIVED STATES
UNOBSERVED / STALE / CONFLICTING FACTS
EXACT BLOCKING PREDICATES
NEXT SAFE OBSERVATION OR OPERATION
```

It MUST NOT collapse an upstream failure into assumptions about downstream layers.
