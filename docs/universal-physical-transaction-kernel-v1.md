# Universal Physical Transaction Kernel v1

Status: hosted-foundation contract for the Android production control path. This document does not authorize phone access or physical mutation. Public Issue #179 remains the live execution cursor.

## Purpose

There is one physical transaction engine.

Package, runtime, filesystem, provider and reboot operations are bindings/adapters of the same transaction model. They are not independent State Machines and must not invent incompatible authority, idempotency, retry or terminal semantics.

## Canonical implementation boundaries

- `scripts/transaction_runner.py` — universal imperative invariant ordering;
- `scripts/operation_state_machine.py` — pure operation/evidence reducer;
- `scripts/control_state_machine.py` — causal `ObservedFact` validity and targeted freshness;
- operation bindings — request interpretation, one physical dispatch and one independent postcondition observer only.

The existing `android.apk-install.v1` path is the first physical vertical slice through this kernel. Migrated operations declare `KernelStepRoles` so operation-specific step names map onto the universal lifecycle without creating a second transaction engine.

## Universal lifecycle

```text
REQUESTED
  -> AUTHORIZED
  -> OBSERVED/PREFLIGHT
  -> INTENT_PERSISTED
  -> DISPATCHED
  -> POSTCONDITION_VERIFIED
  -> ACCEPTED | REFUSED | UNKNOWN | QUARANTINED
```

The detailed pure reducer may retain more specific recovery states such as `RECOVERY_REQUIRED`, `RECOVERING`, `RECOVERED`, `CONFLICT` and `INVALID_TRACE`. At the physical-kernel boundary:

- `ACCEPTED` means the desired physical postcondition is independently proven;
- `REFUSED` means the request was rejected before a physical effect was established;
- `UNKNOWN` means a physical dispatch may have reached the target but its result or required postcondition observation is ambiguous;
- `QUARANTINED` means a post-dispatch state is known to be non-accepted, contradictory, invalid or requires explicit recovery/classification before another mutation.

Every terminal classification is written through `persist_terminal`. In particular, an ambiguous dispatch or an unavailable/invalid postcondition observation after dispatch produces a durable `UNKNOWN` terminal record; it is never silently reduced to a transient workflow exception and never rewritten as failure merely because a result channel, observer transport or supplemental artifact upload was lost.

A binding may return `PostconditionProof(passed=False, ...)` only for a valid observation that positively proves the desired postcondition is not satisfied. Observer transport failure, ambiguous output, missing capture, malformed evidence or inability to establish the observation must propagate as an observation error so the kernel preserves the `DISPATCHED` replay barrier and terminalizes `UNKNOWN`. This prevents “unobserved” from being misreported as a known physical failure.

## Semantic request identity

The canonical semantic identity contract is:

```text
schema = production-control-request.v1

desired_generation = sha256(
  operation,
  normalized_arguments
)

control_request_id = sha256(
  schema,
  operation,
  normalized_arguments,
  authority_cursor,
  desired_generation
)
```

The private Issue #1 router is the accepted ingress boundary that constructs these digests. The public canonical repository defines the contract above and the physical kernel consumes and validates the routed typed envelope. It deliberately does not introduce a second raw digest implementation in first-party Python; repository digest policy requires typed/approved digest boundaries rather than arbitrary local hashing.

The public kernel validates at least:

- exact schema;
- normalized operation name and arguments;
- exact `issue179-comment-<n>` authority-cursor shape;
- typed `req-sha256:<64 lowercase hex>` request identity;
- typed `gen-sha256:<64 lowercase hex>` desired generation.

GitHub comment ID, workflow run ID and run attempt are provenance only and are deliberately excluded from semantic identity.

A physical subtransaction derives a stable, non-provenance identity from:

```text
physical-tx-v1
+ control_request_id digest payload
+ physical_operation_id
+ desired_generation digest payload
```

This permits one outer semantic control request to orchestrate more than one physical-domain operation without allowing a new comment or Actions rerun to manufacture a different identity for the same physical effect.

## Declarative operation contract

`OperationContract` supplies the physical transaction semantics that are independent of workflow provenance:

- operation type and target;
- ordered operation/recovery steps;
- reusable observed facts;
- freshness requirements;
- affected physical domains;
- destructive boundary;
- postcondition and acceptance steps;
- retry and recovery semantics.

`KernelStepRoles` maps operation-specific step identifiers to the universal lifecycle roles:

```text
authority
mutation scope
causal preflight
intent persistence
dispatch
postcondition verification
acceptance
```

A physical mutation binding cannot opt into blind retry at the kernel layer.

## Causal preflight

The kernel admits multiple declared fact requirements and supports both freshness classes:

- `CAUSAL_REUSE_ALLOWED` — an already durable fact is reusable while every dependency it declared still matches current causal context;
- `SAME_TRANSACTION` — the fact must additionally carry the exact `transaction/<id>` dependency of the current transaction.

For every requirement the kernel verifies that the proof:

- matches the declared subject and predicate;
- belongs to the operation target;
- has the required dependency kinds exactly once;
- is durable `CONTROL` evidence;
- is `CURRENT` under `control_state_machine.classify_observed_fact`;
- is true for the guard being satisfied.

Extra current-context values that a fact did not declare are ignored. Therefore an unrelated public Git SHA change cannot stale a source-independent physical fact. Source identity participates only when the fact explicitly declares a `source/...` dependency.

## Targeted domain generations

Every destructive operation declares its affected physical domains.

Before a physical dispatch is allowed, the kernel calculates:

```text
domain/<affected-domain> = transaction_id
```

and includes those generation transitions in the durable mutation intent.

Only declared domains advance. There is no global `DeviceEpoch`, and a Git commit is never used as a physical generation.

Examples:

- package mutation advances `domain/package`;
- runtime mutation may advance `domain/runtime`;
- provider mutation may advance `domain/provider`;
- reboot may advance a reboot-sensitive domain/generation declared by its contract;
- filesystem-only mutation does not stale package facts unless the operation contract explicitly declares a coupled package effect.

Once intent/generation invalidation is durable, prior facts depending on an affected generation cannot be reused even if the controller later loses the dispatch result.

## Exactly-once physical dispatch

The required order is:

```text
semantic request identity
  -> resolve authority
  -> acquire global mutation scope
  -> causal/same-transaction preflight
  -> persist mutation intent and affected generations
  -> establish DISPATCHED replay boundary from the durable intent
  -> dispatch physical mutation exactly once
  -> independently observe postcondition when dispatch result is known
  -> persist classifiable terminal record
```

The global production execution plane remains responsible for using the single lock:

```text
production-phone-global-mutation
cancel-in-progress: false
```

The durable mutation intent is written before the `DISPATCHED` evidence boundary and before the operation binding is invoked. A `DISPATCHED` trace is therefore a may-have-reached-target replay barrier. If the dispatch result is lost, or dispatch returns but its mandatory postcondition cannot be validly observed, the replay barrier remains the authoritative execution state and the transaction is classified and persisted as:

```text
UNKNOWN
blind retry = FORBIDDEN
```

A successful dispatch receipt is not itself release acceptance and is not promoted to a completed reducer step until the postcondition observer returns a valid proof. This ensures an observer crash cannot leave a non-terminal transaction or authorize a retry of an already dispatched physical effect.

The same mutation is not invoked again merely because:

- the workflow was retried;
- a new GitHub comment was added;
- a new Actions run/attempt exists;
- supplemental artifact upload failed;
- the controller restarted.

Transport retry is permitted only when the execution plane can prove the physical dispatch has not occurred.

## Binding responsibility

A migrated physical operation binding owns only:

1. typed request decoding;
2. mutation subject/target reference;
3. exactly one physical dispatch implementation;
4. an independent postcondition observation that distinguishes a valid negative proof from inability to observe;
5. explicit `KernelStepRoles`.

A binding does not own:

- source/control authority;
- mutation locking;
- causal fact freshness;
- domain-generation invalidation;
- mutation-intent durability;
- replay/idempotency policy;
- terminal classification.

Those are kernel/control-plane invariants and must not be copied into separate operation-specific State Machines.

## Hosted acceptance for this foundation

The hosted foundation is accepted only when tests prove at least:

- the public typed semantic envelope accepts an independent golden vector of the private C.0o router algorithm;
- semantic request identity is independent of GitHub comment/run/attempt provenance;
- malformed routed semantic identity fails closed;
- a generic non-APK multi-domain mutator uses the same kernel;
- multiple reusable and same-transaction preflight facts are admitted through the same causal validity engine;
- an unrelated source/Git context change does not stale a source-independent fact;
- a changed declared domain generation durably refuses the transaction before intent or dispatch;
- mutation intent advances only the operation's declared affected domains;
- exactly one physical dispatch occurs on the accepted path;
- dispatch ambiguity is durably terminalized as `UNKNOWN`;
- postcondition observer ambiguity after dispatch is durably terminalized as `UNKNOWN` rather than misreported as a known failed postcondition;
- an existing `UNKNOWN`/`DISPATCHED` trace forbids blind retry before any new authority/lock/device call;
- the existing APK binding and reducer tests remain green, including known-negative vs unobserved postcondition separation.

This stage proves architecture and hosted transaction semantics only. It does not prove current phone state and does not authorize a phone observer or mutation.
