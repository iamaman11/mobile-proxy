# Acceptance VM durable binding store

Status: Production Baseline item 19 Slice A; implementation only, **no live provider mutation is exposed by this slice**.

Canonical lifecycle contract: `contracts/governance/vm-ownership-v1.json`.
Provider-neutral policy: `crates/proxy-core/src/provider_lifecycle.rs`.
Concrete store: `apps/operator-cli/src/github_vm_binding_store.rs`.
Typed Vultr transport: `apps/operator-cli/src/vultr_client.rs` over `apps/operator-cli/src/vultr_lifecycle.rs`.

## Purpose

Item 18 deliberately stopped at the `VmBindingStore` port. A GitHub-hosted runner is ephemeral, so process memory or a runner-local file cannot safely bind a Vultr instance across retry or restart. Item 19 uses a minimal append-only GitHub Deployment ledger as owner-controlled state outside Git version control.

The ledger is intentionally specific to the JIT acceptance VM lifecycle. It is not a generic infrastructure-state platform.

## Exact ledger identity

Each candidate has one immutable ownership intent:

```text
scope=acceptance
intent=candidate:<exact full lowercase 40-character SHA>
```

Deployment records use a fixed task and non-production environment identity. Every payload contains:

- format version;
- exact `project=mobile-proxy` and `managed-by=mobile-proxy` identity;
- exact candidate SHA;
- exact acceptance scope and intent ID;
- predecessor deployment ID;
- transition (`bind`, `replace`, or `clear`);
- exact expected binding, when present;
- exact replacement binding, when present.

A binding contains only the provider-assigned canonical Vultr UUID and positive generation. Names, labels, IPs, provider list order and arbitrary caller-provided IDs are not reconstructed as authority.

## Recovery and compare-and-swap

A runner restart reconstructs state by reading the complete bounded deployment ledger for the exact candidate and validating every record. The implementation rejects:

- a record whose GitHub `ref`/resolved SHA is not the exact candidate;
- wrong task/environment/project/manager/scope/intent;
- malformed or non-canonical provider UUIDs;
- duplicate or non-linear predecessor chains;
- a record whose `expected` value is not the reconstructed prior binding;
- replacement that is not exactly generation `current + 1` with a new provider UUID;
- a stale compare-and-swap expected value;
- any record after terminal clear.

`clear` is terminal for an immutable candidate intent. The same `candidate:<sha>` intent cannot silently restart at generation 1 after cleanup. A later lifecycle therefore needs a distinct immutable ownership intent rather than erasing monotonic history.

The GitHub Deployment API is durable storage, not a standalone locking primitive. The live item-19 workflow must compose this store with one repository-wide acceptance-lifecycle `concurrency` group and `cancel-in-progress: false`. Within that serialized writer boundary, each transition performs exact read/compare/append/re-read verification. If an unexpected competing writer nevertheless creates a fork, reconstruction fails closed and no subsequent provider mutation is authorized.

This serialized-writer requirement is part of the concrete CAS design and must be present before the first live VM mutation.

## Typed Vultr execution boundary

`VultrAcceptanceClient` is an HTTP executor for the existing typed `VultrLifecycleAdapter`; it does not reimplement ownership selection in workflow or shell. It:

- uses the adapter's typed list/create/delete request descriptors;
- accepts `PlannedCreate` for create and `VerifiedMutationTarget` for destructive delete;
- rejects production scope before HTTP mutation;
- treats provider response bodies as bounded transport data and never includes them in error messages.

Slice A deliberately exposes no CLI command and no GitHub workflow invoking the client. Before a live create, the item-19 coordinator must still re-list provider state, use `plan_present`, verify the returned/re-listed exact ownership and specification, and CAS-persist the provider-assigned UUID before declaring success. Before delete, it must re-list and re-authorize the exact bound target, delete only that UUID, confirm provider absence, then CAS-clear the binding.

## JIT readiness gate

No acceptance VM is created merely because this store/client exists. The first live mutation additionally requires all of the following on the then-current protected `main` SHA:

1. successful canonical Quality `push` and exact immutable release-candidate evidence;
2. fresh immutable acceptance-authority evidence for that exact SHA;
3. fresh Vultr read-only preflight for that exact SHA;
4. a ready physical-phone acceptance window;
5. the bounded item-19 workflow with serialized concurrency and exact lifecycle verification.

Issue #115 currently blocks the physical window because Android signing continuity has not been recovered into the private GitHub execution boundary. No phone mutation, signing-key replacement shortcut or idle paid acceptance VM is permitted while that blocker remains.

`production-vultr`, final `v*` release creation, production promotion, GCP and manual provider/SSH control are outside this boundary.
