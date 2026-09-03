# Atomic Physical Mutation Plan v1

Status: hosted control-foundation contract. This document does not authorize phone access, physical mutation, provider access or reboot. Public Issue #179 remains the only execution cursor.

## Why this layer exists

The accepted Universal Physical Transaction Kernel gives one physical transaction a durable replay boundary around exactly one destructive dispatch role. Several legacy workflows predate that rule and combine multiple semantically independent destructive effects in one workflow/job.

Examples include current-source clean install and filesystem certification. Treating either legacy multi-effect contract as one kernel binding would create a false exactly-once claim: the Python/workflow wrapper might be invoked once while several physical effects inside it would still lack independent intent, generation, postcondition and terminal boundaries.

C.0q therefore introduces **decomposition, not a second State Machine**:

- `scripts/transaction_runner.py` remains the one imperative physical transaction kernel;
- `scripts/operation_state_machine.py` remains the pure operation/evidence reducer;
- `scripts/atomic_physical_contracts.py` defines canonical atomic `OperationContract` instances and their kernel-role metadata;
- `scripts/physical_operation_plan.py` is a pure composite-plan reducer over atomic operation IDs and terminal results.

No operation-specific workflow is allowed to invent a parallel lifecycle.

## Kernel atomicity invariant

A kernel-bound primary physical transaction MUST contain exactly one destructive step in `contract.steps`, and that step MUST be the `KernelStepRoles.dispatch_step_id`.

The kernel validates this before request interpretation, authority lookup, mutation locking, phone access or any operation port call.

Destructive recovery steps are outside this primary-dispatch cardinality rule; recovery remains separately authorized/classified and is never an implicit retry of the original dispatch.

Legacy reducers with more than one primary destructive step may remain for historical evidence interpretation, but they cannot be bound wholesale to the kernel.

## Atomic contract shape

New atomic physical mutation contracts use the same seven universal roles:

```text
resolve_authority
  -> mutation_scope
  -> phone_access_boundary
  -> mutation_intent
  -> <one destructive dispatch>
  -> <independent postcondition>
  -> accept
```

Every atomic contract:

- has exactly one primary destructive dispatch;
- declares at least one causal preflight fact;
- declares exact affected physical domains;
- is `retryable=False`;
- has no legacy rollback authority;
- separates dispatch from postcondition observation;
- inherits durable `REFUSED`, `UNKNOWN`, `QUARANTINED` and no-blind-retry semantics from the accepted kernel.

The catalog includes the already accepted `android.apk-install.v1` reference operation plus atomic package, runtime and filesystem operations required to decompose current legacy mutators.

## Composite plan semantics

A composite plan is an ordered list of atomic operation IDs. It does not execute device commands and does not own physical transaction state.

For each plan step the machine-readable form exposes:

- atomic operation ID;
- exact accepted predecessor prefix;
- affected physical domains;
- causal fact requirements and freshness class;
- independent postcondition step;
- whether a separately proven already-satisfied desired state may skip the mutation;
- the required predicate for such a skip.

Only two forms of progress are allowed:

1. the atomic subtransaction terminal is `ACCEPTED`;
2. the step explicitly permits a skip and a separate current proof establishes its named desired-state predicate.

A step may never be skipped merely because a prior workflow ran or because a Git/SHA/run identifier changed.

## Stop rules

The composite layer is deliberately fail-closed:

```text
ACCEPTED -> next atomic step
REFUSED -> STOP
UNKNOWN -> STOP
QUARANTINED -> STOP
all steps ACCEPTED/proven satisfied -> COMPLETE
```

Out-of-order terminal/satisfied evidence is invalid. A later subtransaction cannot advance while an earlier required predecessor is unresolved.

`UNKNOWN` never means “try the plan again”. It preserves the atomic subtransaction's `DISPATCHED` replay barrier and requires explicit observation/recovery before any later mutation can be authorized.

## Current decompositions

### Current-source clean install

```text
runtime-stop
  -> runtime-remove
  -> package-remove
  -> apk-install
  -> runtime-materialize
  -> runtime-start
```

`runtime-stop`, `runtime-remove` and `package-remove` may be skipped only when their explicit current desired-state predicates are independently proven (`runtime_stopped`, `runtime_absent`, `package_absent`). The install/materialize/start steps are not implicitly skippable.

### Filesystem certification

The four legacy destructive probes become four separate atomic transactions:

```text
filesystem-scratch-roundtrip
  -> filesystem-scratch-atomic-replace
  -> filesystem-managed-root-write
  -> filesystem-managed-atomic-replace
```

Each transaction has its own filesystem generation invalidation and postcondition.

### Runtime reconstruction

```text
runtime-stop
  -> runtime-materialize
  -> runtime-start
```

This is a local-runtime plan only. It grants no provider access and no full-serving/final-release authority.

## Bounded private-mutator inventory

C.0q records a non-secret inventory snapshot against accepted private execution SHA:

```text
4842a6455c44e8f549fd5ea37c2fa28349fc72bb
```

The snapshot is architecture evidence, not copied private source. Every currently classified private phone mutator is assigned exactly one disposition:

- atomic operation;
- composite plan;
- explicitly hard-blocked.

Current mapping:

| Private workflow | C.0q disposition |
| --- | --- |
| `android-signing-migration.yml` | hard-blocked |
| `phone-clean-install.yml` | current-source clean-install composite plan |
| `phone-filesystem-certification.yml` | filesystem-certification composite plan |
| `phone-filesystem-quarantine-cleanup.yml` | atomic filesystem quarantine cleanup |
| `phone-runtime-recovery.yml` | hard-blocked legacy existing-layout recovery |
| `phone-runtime-binary-repair.yml` | atomic runtime binary repair |
| `runtime-reconstruction-execution.yml` | runtime-reconstruction composite plan |

The hard blocks are preserved; C.0q does not revive either path.

## Provider and reboot

The composite plan model is generic over atomic operation specs, so future provider and reboot effects must first obtain their own reviewed atomic `OperationContract`, affected-domain set, causal facts, postcondition and kernel role mapping before they can be added to any plan.

No provider or reboot operation is invented or authorized merely to populate the catalog. Their exact semantics remain deferred until a later #179 cursor defines the desired physical effect and acceptance boundary.

## Hosted acceptance

C.0q is accepted only when hosted tests prove:

- every atomic catalog entry has exactly one primary destructive dispatch;
- the kernel rejects a multi-destructive binding before request/authority/lock/port calls;
- legacy clean-install and filesystem-certification contracts are demonstrably non-atomic and are decomposed rather than wrapped;
- plan progress is prefix-ordered and fail-closed;
- `REFUSED`, `UNKNOWN` and `QUARANTINED` stop a composite plan;
- already-satisfied skips are explicit and predicate-bound;
- machine-readable plans expose domains, freshness requirements and postconditions;
- all seven private mutators on the accepted private SHA are mapped or explicitly hard-blocked;
- no private workflow is rewired and no phone access/mutation occurs in this stage.
