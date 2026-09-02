# Android Adapter Certification v1

Status: planned; execution is controlled only by public Issue #179.

This document defines the reality-first development order for production control. It does not authorize phone access or mutation by itself and must never be treated as an execution cursor.

## Goal

Build the production state machine from operations that have first been proved against the real Android production topology through GitHub Actions and the private self-hosted runner. Android is the first reference adapter. VM support comes only after the Android operation contract is proven.

## Non-negotiable architecture

- Public `iamaman11/mobile-proxy` is canonical source, tests, device primitives and architecture.
- Private `iamaman11/mobile-proxy-production` is execution orchestration, repository secrets, bounded evidence, rollback metadata and the private self-hosted runner.
- Public Issue #179 is the only execution cursor. Its freshest authoritative checkpoint and exactly one `NEXT ALLOWED ITEM` control what may happen next.
- No operation may touch the phone merely because it exists in source. Real-device execution requires explicit authorization from #179.
- `Quality` proves source/repository correctness. It does not prove phone access or production readiness.
- Real-device checks are separate certification stages.
- Unknown state always fails closed.
- Every mutating operation must hold the global production-phone mutation lock, re-prove target access immediately before the destructive boundary, bind exact authority/artifacts, and emit bounded machine-readable evidence.

## Development order

1. Android adapter API.
2. Read-only real-device certification.
3. Safe filesystem mutation certification in an isolated adapter-test namespace.
4. Delete/replace/atomicity/path-confinement certification.
5. Android package install/uninstall/reinstall certification.
6. Runtime release lifecycle certification.
7. Managed process lifecycle certification.
8. Structural and functional network acceptance certification.
9. Failure injection and recovery classification.
10. Derive the generic operation contract from proven Android behavior.
11. Derive the production state machine from those operation contracts.
12. Add an offline simulator/fault matrix to `Quality`.
13. Implement the VM adapter against the same generic contracts.

## Android adapter surface

The adapter should expose bounded operations rather than an unrestricted arbitrary shell API.

### Observation

- `probe_access()`
- `probe_capabilities()`
- `package_state()`
- `runtime_state()`
- `process_state()`
- `network_state()`

### Managed filesystem

- `create_managed_dir()`
- `write_managed_file()`
- `read_managed_file()`
- `verify_managed_digest()`
- `atomic_replace_managed_file()`
- `create_managed_symlink()`
- `read_managed_symlink()`
- `remove_managed_file()`
- `remove_managed_tree()`

All managed-path operations must enforce path confinement and reject traversal, root deletion and symlink escape.

### Package lifecycle

- `install_package()`
- `verify_package_identity()`
- `uninstall_package()`
- `verify_package_absent()`

### Runtime lifecycle

- `stage_runtime_release()`
- `verify_runtime_release()`
- `activate_runtime_release()`
- `remove_inactive_runtime_release()`

Deleting an active release must fail closed unless a specifically authorized transaction defines that transition.

### Process lifecycle

- `start_managed_process()`
- `stop_managed_process()`
- `restart_managed_process()`
- `verify_managed_process_identity()`

### Acceptance

- `verify_structure()`
- `verify_function()`

Structural acceptance and functional acceptance are separate facts.

## Certification stages

### A. ACCESS

Prove on the real registered production phone:

- required self-hosted runner is present;
- ADB exists;
- exactly one device is exposed;
- connected device matches registered binding;
- ADB state is `device`;
- shell probe succeeds;
- repeated probe succeeds;
- timeout/OSError/offline/wrong-device/multiple-device conditions fail closed.

Output state: `ANDROID_ACCESS_PROVEN`.

### B. CAPABILITIES

Read-only capability inventory, each classified as `SUPPORTED`, `UNSUPPORTED` or `UNKNOWN`:

- shell;
- privilege/root model;
- package manager;
- push/pull;
- managed filesystem visibility;
- stat/readlink/digest tools;
- process inspection;
- network inspection;
- runtime directory visibility;
- available shell utilities;
- permissions/ownership;
- free disk.

`UNKNOWN` must never be treated as `SUPPORTED`.

### C. SAFE FILESYSTEM MUTATION

Start only in an isolated transaction namespace such as `/data/local/tmp/mobile-proxy-adapter-test/<transaction-id>/`.

Prove create/write/read/digest/chmod/rename/atomic replace/copy/move/symlink/readlink/overwrite/delete/cleanup and verify state after every mutation.

Negative tests must include nonexistent target, wrong permission, timeout, partial write, wrong digest, traversal, symlink escape and interrupted command.

### D. PRIVILEGED MANAGED-ROOT MUTATION

After C succeeds, repeat only inside a bounded owned test namespace under the production managed root if the real privilege model proves it is safe.

Mandatory guards:

- target path is under owned root;
- resolved path remains under owned root;
- no `..` traversal;
- no root deletion;
- no symlink escape;
- exact transaction identifier.

### E. PACKAGE LIFECYCLE

Prove real Android package-manager semantics:

`ABSENT -> install -> INSTALLED -> identity verified -> uninstall -> ABSENT -> reinstall -> INSTALLED`.

Verify package path, version, signer, exact APK digest, uninstall result and definite absence. Package-manager uncertainty fails closed.

### F. RUNTIME LIFECYCLE

Prove release-directory creation, runtime file write, digests, `current` activation, readback, service/process start/stop/restart, inactive release deletion and refusal to delete active release.

### G. PROCESS LIFECYCLE

Prove exact managed process identity, executable identity/digest where applicable, single-instance behavior, stop confirmation, restart, stale-process detection and multiple-instance detection.

### H. FUNCTIONAL ACCEPTANCE

`STRUCTURE_OK` and `FUNCTION_OK` are independent. An open port or running process is not functional acceptance. Functional acceptance must execute the real expected data path and verify the expected response/behavior.

### I. FAILURE / RECOVERY

Intentionally classify failures at each boundary: write succeeds then activation fails; install succeeds then verification fails; runtime copies then start fails; process starts then health fails; delete is interrupted; network disappears; ADB disappears.

Recovery states are derived from observed reality, not assumed in advance. Expected generic classes include `REFUSED`, `RECOVERY_REQUIRED`, `CLEAN_REINSTALL_REQUIRED` and `QUARANTINED`.

## Operation contract to derive after Android certification

Every generic operation must eventually have:

- `operation_id`;
- operation kind (`OBSERVE`, `VERIFY`, `MUTATE`, `ACCEPT`, `RECOVER`);
- preconditions;
- exact inputs and authority binding;
- mutation scope;
- timeout;
- retry policy;
- idempotency classification;
- postconditions;
- evidence schema;
- failure transition;
- compensation/recovery semantics.

## State-machine direction

The generic state machine is derived only after Android semantics are proven. Expected coarse states:

`UNQUALIFIED -> SOURCE_QUALIFIED -> ARTIFACTS_QUALIFIED -> CONTROL_PLANE_QUALIFIED -> TARGET_ACCESS_PROVEN -> FULL_CYCLE_READY -> ARMED -> MUTATION_AUTHORITY_FRESH -> TRANSACTION_ACTIVE -> TARGET_PREPARED -> SOFTWARE_INSTALLED -> RUNTIME_MATERIALIZED -> ACTIVATED -> STRUCTURALLY_ACCEPTED -> FUNCTIONALLY_ACCEPTED -> ACCEPTED`.

Failure states include `REFUSED`, `RECOVERY_REQUIRED` and `QUARANTINED`.

## Quality workflow responsibility

`.github/workflows/quality.yml` remains an off-device source gate. It should evolve to validate:

- Android adapter unit tests;
- path-confinement invariants;
- operation contracts;
- state-transition invariants;
- read-only vs mutation separation;
- workflow-to-operation binding;
- mutation-lock policy;
- authority-boundary policy;
- evidence schemas;
- timeout/error classification;
- fault-injection simulations;
- package/runtime lifecycle mocks;
- deletion safety.

It must not use production secrets, the production serial, ADB access to the production phone, production root access or perform production mutation.

## Rule for future development

No new operation is allowed to become part of production orchestration until both are true:

1. its implementation and failure semantics pass offline `Quality` tests; and
2. where the operation is device-dependent, its behavior has a bounded real-device certification accepted through Issue #179.

## Current execution note

This roadmap never supersedes the current cursor in Issue #179. A new agent must first read the freshest authoritative checkpoint in #179 and execute only its single `NEXT ALLOWED ITEM`, even if this roadmap describes later stages.
