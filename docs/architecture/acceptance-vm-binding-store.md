# Acceptance VM durable lifecycle state

Status: Production Baseline item 19 Slice A; implementation only, **no live provider mutation is exposed by this slice**.

Canonical lifecycle contract: `contracts/governance/vm-ownership-v1.json`.  
Provider-neutral policy: `crates/proxy-core/src/provider_lifecycle.rs`.  
Concrete durable state: `apps/operator-cli/src/github_vm_binding_store.rs`.  
Typed Vultr transport: `apps/operator-cli/src/vultr_client.rs` over `apps/operator-cli/src/vultr_lifecycle.rs`.

## Purpose

Item 18 deliberately stopped at provider-neutral lifecycle policy and the typed Vultr adapter. A GitHub-hosted runner is ephemeral, so process memory or a runner-local file cannot safely bind a provider resource across retry or restart.

Item 19 uses a small append-only GitHub Deployment ledger as owner-controlled runtime state outside Git version control. It is specific to the single JIT acceptance VM lifecycle and is not a generic infrastructure-state platform.

## Exact lifecycle identity

Each software candidate has one immutable acceptance ownership intent:

```text
scope=acceptance
intent=candidate:<exact full lowercase 40-character SHA>
```

Every durable deployment record contains the exact candidate SHA, static `project=mobile-proxy` / `managed-by=mobile-proxy` identity, acceptance scope, exact intent, predecessor deployment ID, generation and transition payload.

A bound resource contains only the provider-assigned canonical Vultr UUID and positive generation. VM name, label, IP address, provider list order and arbitrary caller-provided identifiers are never mutation authority.

## Durable lifecycle state machine

The ledger reconstructs exactly one of these states:

1. `Empty` — this immutable intent has never begun a provider create attempt.
2. `CreatePrepared { generation }` — create has been reserved durably but no provider POST is authorized yet.
3. `CreateDispatched { generation }` — the one create dispatch has been durably fenced before the provider call.
4. `Bound(binding)` — an exact provider UUID and generation have been verified and committed.
5. `DeletePrepared(binding)` — exact deletion has been reserved after target verification.
6. `DeleteDispatched(binding)` — delete dispatch has been durably fenced before the provider call.
7. `Terminal { last_generation }` — provider deletion has been confirmed and the immutable intent is permanently closed.

The same `candidate:<sha>` intent cannot return from `Terminal` to generation 1.

### Why create dispatch is fenced before HTTP

There is no documented Vultr create-instance idempotency contract that this project can rely on. Therefore an ambiguous `POST /v2/instances` transport outcome must never be followed by a blind second POST.

The coordinator must persist `CreateDispatched` **before** sending the create request. If the process or runner then disappears:

- retry reconstructs `CreateDispatched` rather than seeing an apparently clean `None` binding;
- the generic `VmBindingStore::load()` projection returns an in-progress error, so `plan_present(None, ...)` cannot silently authorize another create;
- a second `mark_create_dispatched` call fails closed;
- recovery re-enumerates provider state and may commit the provider-assigned UUID only when exactly one resource has the expected ownership intent/generation and exact desired specification;
- zero resources after an ambiguous dispatched state is not permission to send another create automatically.

This deliberately prefers a safe stuck state over duplicate paid infrastructure.

### Delete recovery

Delete is also fenced before HTTP. A retry reconstructs the exact binding and generation. It must re-list the provider, re-authorize the exact UUID/ownership/generation, and then either:

- reissue delete only for that same verified UUID when it still exists; or
- when provider absence is confirmed, CAS-clear to `Terminal`.

Binding clear before provider-confirmed deletion is forbidden.

## Compare-and-swap and fork handling

GitHub Deployments provide durable append-only records; they are not themselves a lock primitive. Item 19 composes the ledger with one repository-wide acceptance-lifecycle GitHub Actions `concurrency` group using `cancel-in-progress: false`.

Inside that serialized writer boundary, every transition performs:

1. read and reconstruct the complete bounded ledger;
2. compare exact predecessor state/generation/binding;
3. append one transition record;
4. re-read and verify that the new record is the unique head and produces the expected state.

If an unexpected competing writer creates a non-linear predecessor chain, reconstruction fails closed as a fork before any subsequent provider mutation is authorized.

The durable state therefore distinguishes never-created, in-progress, bound, deleting and terminal states instead of projecting all non-bound states to `None`.

## Complete provider enumeration

Mutation safety depends on seeing every relevant Vultr instance, not merely the first API page. The typed acceptance client requests the maximum supported page size (`per_page=500`), follows cursor pagination with a fixed page bound, rejects repeated/oversized cursors, and fails closed when pagination cannot prove a complete listing.

Provider response bodies are read through a hard byte bound instead of being fully buffered before the size check.

Every returned instance still passes through `VultrLifecycleAdapter` for canonical UUID parsing, exact ownership-tag decoding and specification fingerprinting.

## Typed Vultr execution boundary

`VultrAcceptanceClient` is the concrete HTTP transport for item 19. It:

- uses typed request descriptors from `VultrLifecycleAdapter`;
- accepts `PlannedCreate` for create and `VerifiedMutationTarget` for destructive delete;
- rejects production scope before mutation transport;
- has no arbitrary endpoint passthrough;
- performs bounded full instance enumeration;
- emits bounded typed errors and never includes provider response bodies, tokens or credential-derived identifiers in errors.

Slice A exposes no CLI command and no GitHub workflow that invokes live mutation. The item-19 coordinator/workflow remains a later slice and must consume the durable state machine before a create/delete call is reachable.

## JIT readiness gate

No acceptance VM is created merely because Slice A exists. Before the first live mutation on the then-current protected `main` SHA, all of the following are required:

1. successful canonical `Quality` push and exact immutable release-candidate evidence;
2. fresh immutable `/accept-candidate <sha>` authority for that exact SHA;
3. fresh `/vultr-readonly-preflight <sha>` evidence for that exact SHA;
4. a ready physical-phone acceptance window under the canonical phone GitOps policy;
5. the bounded item-19 workflow with serialized concurrency, durable dispatch fencing and exact lifecycle verification.

Issue #115 currently blocks the mutable physical-phone window because Android signing continuity has not been recovered into the private GitHub execution boundary. The fact that a particular physical test step may not install `apps/android-app` is not authority to bypass that fail-closed gate.

`production-vultr`, final `v*` release creation, production promotion, GCP and manual provider/SSH control are outside item 19 Slice A.
