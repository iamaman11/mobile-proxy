# ADR-003: Causal device-fact validity and Git authority

Status: **accepted architecture direction; physical-device foundation still under acceptance**  
Date: 2026-09-03  
Owners: canonical control-state model and transactional operation model

## Context

`mobile-proxy` is developed, reviewed, released and operated through Git/GitHub. The public canonical repository owns source, architecture, operation contracts and release policy. The private execution repository is an execution satellite for the physical phone. GitHub Actions carries immutable source/artifacts to a private self-hosted runner, and the real registered phone is the observation oracle for Android physical reality.

The first State Machine implementation correctly made source identity, transaction identity and bounded evidence explicit. It also introduced `CURRENT`/`STALE` evidence and exact source references. That is necessary inside one operation transaction, but it is not sufficient as a long-lived model of physical truth.

A repository SHA is the identity of software/control logic. It is **not** the clock of the physical phone. If every merge to `main` invalidated every previously proven phone fact, then a documentation-only change would force a new ADB observation of unrelated filesystem/package/runtime state. The system would repeatedly verify facts that had no causal reason to change, and reproducibility would degrade into verification churn.

At the opposite extreme, reusing physical evidence forever is unsafe: package installation invalidates package facts; runtime replacement invalidates runtime facts; reboot invalidates process/session facts; a changed device binding invalidates facts about the prior target; a discovered observer defect may invalidate facts interpreted by that observer; and an ambiguous destructive command must invalidate the pre-mutation view of every affected domain even when its result was lost.

The State Machine therefore needs a small, explicit causal-validity rule rather than either global SHA invalidation or narrative freshness decisions.

## Decision

The control architecture has three distinct truth roles.

```text
GIT / SOURCE AUTHORITY
  exact canonical source, contracts, Quality, artifacts and execution admission

OBSERVED DEVICE FACTS
  bounded claims about the physical target, reusable only while their declared causal dependencies match

TRANSACTION EVIDENCE
  exact ordered trace of one operation, strictly bound to its transaction/source/artifact requirements
```

These roles are related but MUST NOT be collapsed.

### 1. Git is authority for control logic, not a physical-device epoch

The current canonical Git SHA answers questions such as:

- which operation implementation is authorized;
- which contract/version is being executed;
- which Quality result and built artifact belong to that implementation;
- whether a source-bound operation may start or continue.

It does **not** by itself answer whether an already-observed path still exists, which APK is installed, whether a runtime generation is present, or whether a quarantine residue is absent.

A Git SHA is always retained as provenance when useful. It becomes a **validity dependency** only when the fact or operation is semantically source-relative.

Therefore this rule is forbidden:

```text
current_git_sha != observed_fact.source_sha
  -> mark every physical fact stale
```

The required rule is:

```text
for each declared dependency of the fact:
  compare observed dependency identity with current dependency identity

all match        -> VALID
any mismatch     -> STALE
context missing  -> UNKNOWN
```

Unrelated current-context changes are ignored.

### 2. Durable physical facts declare a dependency vector

A reusable device fact is represented conceptually as:

```text
ObservedFact
  subject
  predicate
  value
  target
  observation_ref
  source_ref              # provenance, not automatic invalidation
  authority
  persisted
  dependencies[]
```

Each dependency is:

```text
scope -> opaque identity token
```

The initial supported dependency kinds are deliberately small:

- `target/...` — logical registered-target binding generation;
- `observer/...` — semantic observer contract/version;
- `domain/...` — latest generation of a physical mutation domain;
- `boot/...` — boot generation when a fact cannot survive reboot;
- `session/...` — runner/ADB/control session when a fact is session-scoped;
- `source/...` — canonical source identity when the fact is source-relative;
- `artifact/...` — artifact identity when the fact is artifact-relative;
- `transaction/...` — exact transaction when cross-transaction reuse is forbidden.

The identity token is opaque. It may be a transaction ID, accepted mutation evidence ID, boot-observation token, target-binding generation, semantic observer version, Git SHA or typed artifact digest. The State Machine compares identity for equality; it does not infer meaning from the token format.

Do not introduce a global `DeviceEpoch`. Independent domains prevent unrelated mutations from invalidating each other.

### 3. Source provenance is separate from source dependency

Every real-phone observation may record the exact source revision that produced it for auditability. That does not make the fact source-bound.

Example: a durable observation that exact quarantine path `X` is absent may depend on:

```text
target/android-production -> target-binding-generation
observer/filesystem-quarantine -> observer-v1
domain/filesystem -> filesystem-generation
```

It need not depend on:

```text
source/canonical -> repository-sha
```

A documentation-only merge can therefore advance `main` without invalidating the observed path absence.

By contrast, the assertion “the installed runtime equals the runtime produced from canonical source S” is source/artifact-relative and must include the corresponding source/artifact dependency.

### 4. Mutation advances only affected domain generations

Every mutating operation contract declares the physical domains it may change. Typical domains are:

```text
filesystem
package
runtime
process
connectivity
```

The first destructive command that may have reached the target advances the affected domain generation(s) to a transaction-scoped new identity **before the old domain facts may be reused**.

This remains true when the controller loses the result.

Therefore:

```text
old fact: domain/package = generation A
mutation may have reached phone
current domain/package = transaction B

old package fact -> STALE
```

This rule is what makes `UNKNOWN_EXECUTION_OUTCOME` safe. The system cannot accidentally reuse a pre-mutation fact while the target outcome is ambiguous.

Fresh postcondition/recovery observation then establishes facts under the new domain generation.

A mutation in one domain does not automatically invalidate facts in unrelated domains unless the operation contract explicitly declares the coupling. For example, reboot may invalidate `boot`, `session`, `process` and connectivity-dependent facts while leaving immutable package identity facts reusable if their contract says reboot cannot change them.

### 5. Observer semantics are versioned independently of repository SHA

An observer has a semantic contract identity such as:

```text
observer/filesystem-quarantine -> android.filesystem-quarantine-observer.v1
```

Refactoring unrelated code or documentation does not require an observer-version change.

If a defect or semantic change means previous observations can no longer be interpreted safely, the observer contract identity MUST change. Facts depending on the old observer identity then become stale without invalidating unrelated facts.

This is intentionally simpler and more precise than hashing the entire repository or invalidating on every implementation edit.

### 6. Ephemeral facts use session/boot/transaction dependencies instead of arbitrary global TTLs

Some facts can change without a project mutation. Reachability, ADB shell availability, process liveness and network connectivity are examples.

They must therefore depend on the narrow context that bounds their safe reuse, for example a `session/...`, `boot/...` or `transaction/...` identity. The control model does not pretend such facts are durable merely because they were persisted.

A planning observation may still be useful history, but a destructive operation always performs the fresh target/access proof required by its own mutation-boundary contract.

This is the distinction:

```text
fact reuse for planning/guards where dependencies still match
!=
fresh same-transaction mutation-boundary proof
```

### 7. Transaction evidence remains strict

`PhaseEvidence` in `operation_state_machine.py` is an ordered trace for one exact transaction. Its strict transaction/source/artifact isolation remains correct.

Cross-transaction durable physical facts are evaluated by `control_state_machine.py` before they are projected into current/stale control facts. Transaction evidence MUST NOT be broadened merely to reuse an old physical observation.

One operation may consume a reusable physical fact only when its contract permits that fact class. A destructive boundary requiring fresh proof cannot be satisfied by a reusable historical observation.

### 8. Persistence is separate from physical truth and from validity

The system continues to distinguish:

```text
operation_execution_result
postcondition_verification_result
evidence_persistence_result
```

A fact may have been observed on the device but remain unusable for a later durable guard because persistence failed.

Causal validity is evaluated only after evidence admission. For a durable control guard:

```text
wrong authority        -> UNUSABLE
malformed dependencies -> INVALID
not persisted          -> UNPERSISTED
missing context        -> UNKNOWN
dependency mismatch    -> STALE
all dependencies match -> VALID
```

No workflow conclusion can override those states.

### 9. Restart reconstructs from durable evidence plus current dependency context

The controller and runner are disposable execution processes. They do not own canonical state in memory.

After restart:

1. resolve durable bounded CONTROL evidence;
2. reconstruct current dependency identities from authoritative bindings and durable mutation/boot/session evidence;
3. classify reusable facts by causal dependencies;
4. re-observe only facts whose required context is unknown/stale or whose operation contract requires fresh boundary proof;
5. derive the next transaction step.

A derived cache of current facts/generations may be added later for performance, but it is never independent authority and must be rebuildable from durable evidence.

During the phone foundation, no new database, event-sourcing platform or background state service is introduced for this purpose.

## Git/GitHub execution model

The industrial control path remains:

```text
PUBLIC CANONICAL GIT
  source + contracts + architecture + Quality
        |
        v
PRIVATE EXECUTION GIT/GITHUB
  exact binding + owner CONTROL command + serialized execution
        |
        v
SELF-HOSTED RUNNER
  verify immutable operation source/artifact
        |
        v
REAL PHONE
  observe / mutate bounded project-owned state / independently observe
        |
        v
BOUNDED CONTROL EVIDENCE
  operation result + device facts + persistence result + dependency identities
        |
        v
PURE REDUCERS
  classify reusable facts + derive exact next transaction state
```

Git is therefore the control and software authority. The phone remains physical truth. Durable evidence connects the two without pretending that a Git commit itself changed the phone.

## Minimal implementation boundary

The current implementation keeps two owners rather than adding a framework:

- `scripts/control_state_machine.py`
  - owns fact admission, conflicts and causal validity/reuse;
  - may project admitted reusable facts into the existing `CURRENT`/`STALE` reducer surface;
- `scripts/operation_state_machine.py`
  - owns ordered transaction state, mutation boundary, ambiguity, recovery and terminal state.

GitHub Actions, Issue #179, private Issue #1, ADB and shell remain adapters/cursors/transports. They must not implement a parallel freshness model.

No new runtime service, persistence database, message bus, generic plugin system or third State Machine is introduced by this decision.

## Examples

### Documentation merge

Before:

```text
main = A
filesystem generation = fs-17
path X absent = VALID
```

After docs-only merge:

```text
main = B
filesystem generation = fs-17
path X absent = VALID
```

The source SHA changed; the causal dependencies of the filesystem fact did not.

### Package mutation

Before:

```text
package generation = pkg-8
installed version = 1.1.0
```

Mutation transaction `tx-9` may reach the package manager:

```text
package generation = tx-9
old installed-version fact = STALE
```

If the command result is lost, the next safe action is package re-observation under `tx-9`, not reuse of the `pkg-8` fact and not blind retry.

### Observer defect

A bug is found in `filesystem-quarantine-observer.v1` that can misclassify symlinks as absent.

```text
observer identity: v1 -> v2
facts depending on v1 -> STALE
unrelated package/runtime facts -> unchanged
```

### Destructive boundary

A valid earlier `PHONE_ACCESS_PROVEN` may be useful for planning. The operation contract still requires:

```text
mutation lock
-> fresh phone_access_boundary in the same transaction
-> mutate
```

because target access can change independently of Git.

## Alternatives rejected

### Global Git-SHA invalidation

Rejected because unrelated source/docs changes would cause false staleness and endless phone re-observation.

### Re-observe the entire phone before every operation

Rejected because it is expensive, obscures real dependencies, increases failure surface and encourages verification-of-verification.

### TTL-only freshness

Rejected as the primary model because elapsed time is not the causal reason most durable filesystem/package/runtime facts become false. Time may still be part of a specific ephemeral observation contract when genuinely required.

### One global device generation

Rejected because a filesystem mutation should not automatically invalidate unrelated package/artifact facts. Domain-scoped generations provide the required isolation with less churn.

### Mutable human-maintained device-state file in Git

Rejected because Git desired/control state must not be confused with observed physical truth. Any cache committed or stored for convenience would remain derived evidence, never manually asserted authority.

### Full event-sourcing/state database now

Rejected because it adds permanent operational machinery before the phone foundation demonstrates that it is necessary. Durable bounded CONTROL evidence plus pure reducers is sufficient for the current stage.

## Consequences

Positive:

- documentation and unrelated code merges no longer force unnecessary physical rechecks;
- every re-observation has an explicit causal or transaction-freshness reason;
- ambiguous mutation cannot reuse pre-mutation facts from affected domains;
- controller restart can reconstruct decisions without narrative memory;
- source authority and physical truth remain cleanly separated;
- the same model can later be reused for VM/provider targets without making them current dependencies.

Costs:

- observation producers must eventually emit the small dependency vector required by their fact class;
- operation contracts must declare affected domains and fresh-boundary requirements;
- semantic observer changes require deliberate observer-version changes.

These costs are accepted because they replace global staleness and repeated manual reasoning with one small deterministic rule.

## Acceptance criteria for this decision

This architecture is considered correctly implemented when direct reducer tests prove at least:

- an unrelated source change does not stale a source-independent device fact;
- a source-bound fact stales when source identity changes;
- a domain fact stales when its domain generation changes;
- a target-binding change stales target facts;
- an observer-version change stales only dependent facts;
- missing dependency context stays `UNKNOWN` rather than being guessed;
- unpersisted or wrong-authority evidence cannot satisfy a durable CONTROL guard;
- destructive operation traces still require same-transaction boundary reproof.

Real-phone foundation acceptance additionally requires the execution adapters to emit and consume these dependencies without creating a second workflow-specific freshness model.
