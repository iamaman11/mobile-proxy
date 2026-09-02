# Evidence-Derived Control State Machine v1

Status: design candidate. This document is architecture only. It does not authorize phone access or mutation. Public Issue #179 remains the execution cursor.

## Purpose

Prevent production-control decisions from being made from assumptions, stale narrative, workflow names, partial failures, or unrelated observations.

The control state machine MUST be a deterministic projection of bounded evidence. A state is never asserted manually as truth.

Core rule:

> No evidence -> `UNKNOWN`. Expired evidence -> `STALE`. Conflicting fresh evidence -> `CONFLICT`. Invalid scope -> no promotion. No fail-open transition is allowed.

## The state machine is multidimensional

A single linear `READY / NOT_READY` state is unsafe because independent layers can be confused.

These inferences MUST be impossible by construction:

- `JOB_QUEUED_UNASSIGNED` -> `RUNNER_OFFLINE`;
- `RUNNER_ONLINE_IDLE` -> `PHONE_ACCESS_PROVEN`;
- `JOB_SKIPPED` -> runner failure;
- runner assigned -> ADB reached;
- ADB access proven -> package/runtime healthy;
- process/port healthy -> functional acceptance;
- historical success -> fresh mutation authority.

The machine keeps independent state regions and computes permission for each operation from their exact conjunction.

## Canonical fact model

Every observation that participates in a control decision MUST contain at least:

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
lifecycle
```

Semantics:

- `subject` identifies the exact observed object (`run`, `runner`, `phone`, source, artifact, transaction, etc.). Facts for one subject cannot satisfy another subject's predicate.
- `predicate` is typed, for example `runner_online`, `adb_device_count`, `registered_device_match`.
- `value` is bounded and non-secret. Raw serial, device IP, signing material, tokens and provider credentials are forbidden.
- `observer` identifies who made the observation.
- `method` identifies the exact observation operation.
- `observed_at` records when it happened.
- `valid_until` defines freshness for consumers that require current authority.
- `scope` binds the fact to exact SHA/run/job/transaction/target where applicable.
- `source_ref` binds facts produced by one bounded evidence record/probe.
- `sensitivity` is `PUBLIC` or `BOUNDED_PRIVATE`.
- `lifecycle` is one of `CURRENT`, `STALE`, `SUPERSEDED`, `CONFLICT`, `INVALID`.

A fact without required provenance or scope MUST NOT participate in a permission decision.

### Evidence rules

1. Two current authoritative values for the same scoped subject/predicate that disagree are `CONFLICT`.
2. A later observation from the same monotonic evidence stream may explicitly supersede an earlier one.
3. `STALE`, `CONFLICT` and `INVALID` never mean true or false; they fail closed.
4. Narrative issue comments are audit/cursor context. They do not become machine truth without bounded evidence references.
5. Facts from different bounded probes MUST NOT be combined to manufacture a proof that no single probe established.

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

A current `PHONE_ACCESS_PROVEN` requires one bounded probe scope/source reference proving all seven facts:

1. ADB command available;
2. inventory parse valid;
3. exactly one ADB-visible device;
4. exact match to private `ANDROID_PRODUCTION_SERIAL`, without recording raw serial;
5. registered inventory state is `device`;
6. `adb -s <registered> get-state == device`;
7. `adb -s <registered> shell true` succeeds.

All seven facts MUST originate from the same bounded phone-access probe. Facts from different probes cannot be combined.

Installed package/runtime/process/network observations MUST NOT participate in this derivation.

A complete previously proven probe whose facts have expired becomes `PHONE_ACCESS_STALE`. An incomplete set of stale observations remains `PHONE_ACCESS_UNOBSERVED`; it is not evidence that access once passed.

For every mutation, access MUST be re-proved in the same self-hosted mutation job immediately before the destructive boundary. Historical preflight evidence cannot satisfy that guard.

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

### 8. Observed target state

Desired state and observed state are separate.

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

`MUTATION_ELIGIBLE` is a derived permission state, not mutation authority by itself.

Before `TRANSACTION_ACTIVE`, every operation-specific guard must be current in the same transaction scope.

After the first destructive boundary, an unresolved failure transitions to `RECOVERY_REQUIRED` unless independent evidence proves the target was unchanged. If safe target state/recovery cannot be established, transition to `QUARANTINED`.

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

Example: immutable-source `curl` fails before the first ADB probe:

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

Every operation declares its own guard expression over current facts.

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
  AND mutation_lock_held
  AND phone_access_reproved_same_job
  AND required_capabilities_supported
  AND exact_test_namespace_bound
  AND path_confinement_proven
  AND mutation_authority_current
```

If any required term is absent, false, `UNKNOWN`, `STALE`, `CONFLICT` or invalid for the requested scope, permission is denied and exact blocking predicates are emitted.

## Operation contract

Every adapter/control operation declares:

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

Retries are allowed only when the contract explicitly classifies the failure as retryable and retry cannot widen mutation scope. Mutation commands are never automatically retryable.

## Desired vs observed

Every mutation follows:

```text
OBSERVE -> GUARD -> MUTATE -> INDEPENDENTLY OBSERVE -> CLASSIFY
```

Never:

```text
MUTATE -> assume success -> advance state
```

A successful command is an operation result, not proof of its postcondition.

## Real production example that motivated the model

Private read-only preflight run `33647329233` passed its hosted command gate and was assigned to exact production runner `mobile-proxy-phone-linux-production`. It then failed while fetching immutable canonical preflight logic with an SSL-connect transport error. All ADB/preflight steps were skipped.

Correct classification for that run is therefore:

```text
JOB_FAILED
runner assignment = PROVEN
SOURCE_FETCH_FAILED_TRANSPORT
failure_stage = SOURCE_FETCH
PHONE_ACCESS_UNOBSERVED
```

This is not `RUNNER_OFFLINE`, not `ADB_FAILED`, and not `PHONE_FAILED`.

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

## First implementation/certification sequence

1. fact/evidence schema and deterministic reducer;
2. command/job/runner/transport/source-fetch regions;
3. regression from exact real run `33647329233`;
4. Android `probe_access()` evidence with one-probe scope enforcement;
5. real access failure-mode certification;
6. capability inventory;
7. bounded scratch filesystem mutation certification;
8. privileged owned-root certification where proven safe;
9. package lifecycle;
10. runtime lifecycle;
11. process lifecycle;
12. structural + functional acceptance;
13. failure injection and recovery classification;
14. derive generic contracts from proven Android behavior;
15. VM adapter against the same contracts.

## Quality invariants

Offline Quality MUST permanently test at least:

- `JOB_SKIPPED` never maps to runner failure;
- queued-unassigned and assigned jobs are distinguishable;
- source-fetch failure leaves ADB/phone state unobserved;
- online runner and degraded transport can coexist;
- facts for different subjects cannot satisfy/conflict with one another;
- cross-probe ADB facts cannot be combined into `PHONE_ACCESS_PROVEN`;
- complete expired access proof becomes `PHONE_ACCESS_STALE`;
- partial stale access observations do not become proof;
- conflicting current facts fail closed;
- package/runtime health never affects `PHONE_ACCESS_PROVEN`;
- missing mutation evidence stays unknown rather than becoming `false`;
- command success never implies postcondition success;
- mutation cannot enter `TRANSACTION_ACTIVE` without same-job access reproof and lock;
- post-boundary unknown state cannot return to READY/ACCEPTED;
- forbidden sensitive values cannot enter bounded evidence.

## Rule for agents

A new agent MUST report control state as:

```text
OBSERVED FACTS
DERIVED STATES
UNOBSERVED / STALE / CONFLICTING FACTS
EXACT BLOCKING PREDICATES
NEXT SAFE OBSERVATION OR OPERATION
```

It MUST NOT collapse an upstream failure into assumptions about downstream layers.
