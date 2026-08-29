# Architecture Quality Standard

Status: **normative**  
Authority: protected `main` in `iamaman11/mobile-proxy`  
Enforcement entrypoint: `scripts/check_architecture_boundaries.py`  
Machine-readable Rust module graph: `contracts/governance/module-boundaries-v1.json`

## 1. Purpose

This standard defines the architectural quality floor for `mobile-proxy`. It exists to keep the cost of change growing materially slower than the size of the system while preserving correctness, security, compatibility and operational reliability.

Architecture is not accepted merely because code is split into folders, crates, traits or layers. A rule is meaningful only when it has a clear owner and, where practical, a fail-closed automated fitness function in the required `Quality Gate`.

The project explicitly rejects complexity for its own sake. New abstractions, dependencies, services, state stores, workflows and extension mechanisms require a concrete current need and must be cheaper than the problem they solve.

## 2. Decision priority

When architecture goals conflict, use this order unless a more specific accepted contract says otherwise:

1. correctness and data integrity;
2. security and least privilege;
3. backward compatibility and safe migration;
4. reliability and deterministic recovery;
5. architectural boundaries and ownership;
6. simplicity and operational cost;
7. performance supported by evidence;
8. implementation convenience.

A lower-priority goal must not silently weaken a higher-priority one.

## 3. Dependency and module boundaries

The conceptual dependency direction remains:

```text
foundation <- domain/contracts <- application <- infrastructure/adapters <- composition/delivery
```

The current Rust workspace is transitional, so exact permitted internal dependencies are declared in `contracts/governance/module-boundaries-v1.json`. That contract is the machine source for the current graph.

Rules:

- every Rust workspace member must be classified in the module-boundary contract;
- every declared module must exist and identify its exact Cargo package;
- an internal dependency is permitted only when explicitly allowlisted for the consuming module;
- unused/stale allowed edges are forbidden: the contract must describe the graph that actually exists;
- dependency cycles are forbidden;
- adding a crate without classifying it fails closed;
- removing or redirecting an internal edge requires updating the contract in the same change;
- domain/foundation restrictions in ADR-001 remain in force in addition to the full workspace graph.

The allowlist is not permission to create an edge without need. It records an existing justified edge.

## 4. Ownership and state

Every authoritative mutable behavior or state must have one owner. Cross-context mutation occurs only through an explicit typed application/domain boundary.

For new authoritative state, the change must identify:

- owning capability/module;
- mutation boundary;
- persistence owner, when durable;
- transaction/idempotency boundary;
- readers and writers;
- recovery and deletion path.

Two unrelated modules must not independently write the same canonical state.

## 5. Side effects and determinism

Side effects must remain visible and isolated:

- domain code: deterministic rules, state transitions and bounded values; no network, storage, process, environment, Android or wall-clock ownership;
- application code: sequences use cases over explicit ports and typed outcomes;
- infrastructure/adapters: perform database, network, provider, filesystem, process and platform effects;
- composition roots: construct concrete implementations and runtime wiring.

Time, randomness, identity generation, environment, filesystem, process execution, external APIs and persistence are dependencies, not hidden globals, when they affect business or recovery semantics.

## 6. Contracts and public surface

Public API is architecture.

- private by default;
- export only stable behavior another module genuinely needs;
- transport DTOs, persistence rows and domain values are separate concepts unless equivalence is deliberately proven;
- boundary inputs are validated and converted to typed values promptly;
- raw strings must not become an implicit error/status/protocol taxonomy;
- compatibility commitments are changed only through the existing versioned contracts and migration rules.

Generic `utils`, `common`, `misc`, `helpers`, `base` or `manager` dumping grounds are forbidden as ownership substitutes. Shared primitives belong to the narrowest real owner, such as `crates/foundation`, and only when genuinely shared.

## 7. Complexity budget and YAGNI

Complexity must be justified, not merely permitted.

The following are architecture-significant additions and require explicit justification in the pull request; an ADR is required when the change establishes or materially changes a long-lived architectural decision:

- a crate/module or runtime service/process;
- authoritative persistent state or a schema family;
- an external dependency with production impact;
- a queue, worker, scheduler or background execution model;
- a provider/protocol/trust boundary;
- a public compatibility surface;
- a new abstraction layer or plugin/extension mechanism;
- a release/deployment control-plane change.

The justification must answer, proportionally:

1. what current problem requires the added complexity;
2. why the simpler alternative is insufficient;
3. what failure modes and operational cost are added;
4. how the component can be replaced or deleted;
5. how the change is tested and rolled back.

Do not introduce speculative interfaces, factories, registries, plugins or generic frameworks solely because a second implementation might exist someday. A concrete implementation is preferred until an abstraction has demonstrated value.

## 8. Replaceability, deleteability and local reasoning

A healthy boundary can be replaced or removed without unrelated rewrites.

Changes should keep a capability understandable by reading a bounded portion of the repository. Editing one capability should not routinely require edits across unrelated services or crates. Broad cross-cutting edits are an architecture signal and require explanation.

Optional capabilities must have a bounded deletion path. External providers and platform integrations must sit behind the narrowest useful boundary rather than leak provider vocabulary into canonical domain concepts.

## 9. Runtime and resource discipline

New runtime components are exceptional because every process, listener, queue and state store creates permanent operational tax.

Any new runtime component must define, as applicable:

- health/readiness semantics;
- timeout and retry bounds;
- concurrency/capacity bounds;
- restart/idempotency behavior;
- observability and bounded error reasons;
- deployment and rollback behavior;
- ownership of credentials and mutable state.

Unbounded queues, retries, in-memory registries, logs, payloads or background task creation are forbidden.

## 10. Testing and observability

Architecture should make core behavior testable without requiring the entire production environment. Domain/application behavior should be testable with deterministic substitutes for external effects.

Production-relevant operations must expose enough structured, bounded evidence to determine what happened, where, under which immutable release identity and why a failure occurred without leaking secrets.

## 11. Git and change discipline

Architecture governance uses the existing protected delivery chain:

```text
topic branch -> pull request -> Quality Gate -> protected main
```

Direct architectural exceptions are not allowed. If a rule must change, change the normative document/contract and its enforcement together through the normal pull-request path.

Architecture-significant pull requests must state complexity added/removed, the simpler alternative considered, ownership impact, rollback/deletion path and ADR status. Documentation-only assertions do not override failing machine contracts.

## 12. Supersession

This standard may be superseded only by an explicit reviewed change that preserves or deliberately migrates compatibility commitments and provides equal or stronger controls for correctness, security, ownership, simplicity and recoverability.

Removing an automated fitness function requires the same level of justification as weakening the rule it enforces.
