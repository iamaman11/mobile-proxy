# Architecture Quality Standard

Status: **normative**  
Authority: protected `main` in `iamaman11/mobile-proxy`  
Enforcement entrypoint: `scripts/check_architecture_boundaries.py`  
Machine-readable Rust module graph: `contracts/governance/module-boundaries-v1.json`

## 1. Purpose

This standard defines the architectural quality floor for `mobile-proxy`. It exists to keep the cost of change growing materially slower than the size of the system while preserving correctness, security, compatibility and operational reliability.

Architecture is not accepted merely because code is split into folders, crates, traits or layers. A rule is meaningful only when it has a clear owner and, where practical, a fail-closed automated fitness function in the required `Quality Gate`.

The project explicitly rejects complexity for its own sake. New abstractions, dependencies, services, state stores, workflows and extension mechanisms require a concrete current need and must be cheaper than the problem they solve.

The project is currently developed by one primary developer. The architecture MUST therefore optimize for local reasoning, one sequential development direction and a small number of authoritative concepts. Parallel roadmaps, duplicated policy planes and framework layers that require a team to keep them synchronized are architectural defects.

## 2. Decision priority

When architecture goals conflict, use this order unless a more specific accepted contract says otherwise:

1. correctness and data integrity;
2. deterministic control and recovery of physical targets;
3. security and containment of external impact;
4. backward compatibility and safe migration where preservation is actually required;
5. architectural boundaries and ownership;
6. simplicity, comprehensibility and operational cost;
7. performance supported by evidence;
8. implementation convenience.

A lower-priority goal must not silently weaken a higher-priority one.

During the physical-device-control foundation stage, reproducibility of control is more important than preserving an incidental current installation. This does **not** permit secret disclosure or uncontrolled mutation; see §9.

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

Physical-device control is one state-machine problem, not a collection of workflow-specific readiness flags. Filesystem, package, runtime, process, connectivity, reboot and recovery observations are dimensions consumed by operation guards; they are not independent global `READY` states.

## 5. Side effects and determinism

Side effects must remain visible and isolated:

- domain code: deterministic rules, state transitions and bounded values; no network, storage, process, environment, Android or wall-clock ownership;
- application code: sequences use cases over explicit ports and typed outcomes;
- infrastructure/adapters: perform database, network, provider, filesystem, process and platform effects;
- composition roots: construct concrete implementations and runtime wiring.

Time, randomness, identity generation, environment, filesystem, process execution, external APIs and persistence are dependencies, not hidden globals, when they affect business or recovery semantics.

The State Machine owns transition semantics. GitHub Actions, shell scripts, ADB transport and provider APIs are adapters/executors. They MUST NOT become alternative state machines by encoding independent transition truth in workflow names, job success, ad-hoc flags or narrative checkpoints.

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

Complexity must be justified, not merely permitted. The preferred architectural change is the smallest one that **removes uncertainty or removes code** while preserving the required behavior.

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

1. what current demonstrated problem requires the added complexity;
2. why deletion, reuse or a simpler concrete implementation is insufficient;
3. what uncertainty or failure mode the added code removes;
4. what new failure modes and operational cost are introduced;
5. how the component can be replaced or deleted;
6. how the behavior is tested and rolled back.

Do not introduce speculative interfaces, factories, registries, plugins or generic frameworks solely because a second implementation might exist someday. A concrete implementation is preferred until an abstraction has demonstrated value.

### 7.1 No code for code

A change is architecturally invalid when its main effect is to increase framework, orchestration, policy or test machinery without closing a concrete active uncertainty.

Forbidden patterns include:

- adding wrappers around wrappers without reducing the number of concepts a developer must understand;
- introducing a generic framework before two proven concrete cases require the same invariant;
- duplicating state or policy so that multiple files/workflows must be kept manually synchronized;
- adding a checker whose only purpose is to confirm that another checker/test exists or ran;
- adding tests that primarily test the presence, wording or invocation of other tests instead of product/state-machine behavior;
- expanding CI merely to obtain more green checks rather than to enforce an independently meaningful invariant;
- retaining obsolete compatibility or migration code when no accepted requirement needs it.

One independent invariant may have one proportionate fitness function. Meta-verification is justified only when it protects a genuinely separate trust boundary, not when it rechecks the existence of an existing check.

### 7.2 Complexity deletion rule

Before adding a new architectural mechanism, ask in this order:

1. Can existing code be deleted or simplified?
2. Can the requirement be expressed as data in the existing model?
3. Can one existing module own it without a new abstraction?
4. Only then: is a new module/mechanism unavoidable?

A PR that adds substantial architecture should identify the complexity it removes or the otherwise-unavoidable capability it introduces.

## 8. Replaceability, deleteability and local reasoning

A healthy boundary can be replaced or removed without unrelated rewrites.

Changes should keep a capability understandable by reading a bounded portion of the repository. Editing one capability should not routinely require edits across unrelated services or crates. Broad cross-cutting edits are an architecture signal and require explanation.

The codebase must remain understandable by one developer following a single execution path from state -> guard -> operation -> effect -> independent observation -> resulting state. A normal operation must not require mentally joining several roadmaps, trackers and workflow-specific interpretations.

Optional capabilities must have a bounded deletion path. External providers and platform integrations must sit behind the narrowest useful boundary rather than leak provider vocabulary into canonical domain concepts.

## 9. Physical-device-control foundation and bootstrap-state policy

Before further application feature growth, the project MUST complete and accept a production-grade State Machine for reproducible control of the real physical Android device. This is a prerequisite inside the single canonical roadmap, not a parallel workstream.

The foundation is complete only when the model and implementation can deterministically:

- observe current device identity and required capabilities;
- derive operation-specific guards from current facts;
- serialize destructive mutation;
- execute bounded project-owned mutations;
- independently verify postconditions on the device;
- distinguish execution result, verified target state and evidence persistence;
- represent ambiguous controller/runner loss without guessing the target result;
- re-observe after ambiguity before retrying a non-idempotent mutation;
- recover or quarantine after interruption at every destructive boundary;
- survive controller restart and device reboot without narrative state reconstruction;
- reproduce a clean usable project-owned device state from an allowed baseline.

Until this foundation is accepted, do not grow application features, orchestration frameworks, VM generalization or long-lived migration machinery except for the smallest change strictly necessary to prove the next State Machine invariant.

### Protect boundaries, not bootstrap state

During this foundation stage, the current installed APK, runtime generation, project-owned files and project-owned configuration on the phone are **disposable bootstrap state**, not an architectural asset that must be preserved at the cost of reproducibility.

Therefore:

- the architecture MUST NOT depend on preserving the current installation in place;
- wipe/reinstall/re-materialize of project-owned state is acceptable when performed by an authorized bounded operation and followed by independent verification;
- prefer revocable/test credentials for foundation experiments where practical;
- do not build complex secret-continuity, migration or preservation mechanisms merely to protect an incidental current device state before reproducible control exists;
- correctness must never depend on a secret or artifact surviving on the current phone.

This rule does **not** relax basic security boundaries. Real credentials must never be logged, committed or deliberately disclosed; provider/account mutations remain bounded and authorized; non-project-owned phone state is outside the mutation boundary. The point is to avoid protecting an unreproducible instance, not to weaken confidentiality or containment.

## 10. Runtime and resource discipline

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

## 11. Testing and observability

Architecture should make core behavior testable without requiring the entire production environment. Domain/application behavior should be testable with deterministic substitutes for external effects.

Tests should prove externally meaningful behavior, state transitions, guards, recovery and invariants. Prefer a small number of strong transition/fault tests over layers of tests that merely assert wiring or that another test/check exists.

Production-relevant operations must expose enough structured, bounded evidence to determine what happened, where, under which immutable release identity and why a failure occurred without leaking secrets.

For physical-device State Machine acceptance, fault injection is mandatory at every destructive boundary and at controller/runner disconnect, evidence-persistence failure and reboot/restart boundaries. Ambiguous outcomes must be resolved by re-observation, never by narrative inference.

## 12. Git and change discipline

Architecture governance uses the existing protected delivery chain:

```text
topic branch -> pull request -> Quality Gate -> protected main
```

Direct architectural exceptions are not allowed. If a rule must change, change the normative document/contract and its enforcement together through the normal pull-request path.

Architecture-significant pull requests must state complexity added/removed, the simpler alternative considered, ownership impact, rollback/deletion path and ADR status. Documentation-only assertions do not override failing machine contracts.

During the State Machine foundation gate, pull requests should be sequential and narrowly scoped to the next unproven transition/recovery property. Do not open a second architecture lane to work around a blocked foundational property.

## 13. Supersession

This standard may be superseded only by an explicit reviewed change that preserves or deliberately migrates compatibility commitments and provides equal or stronger controls for correctness, deterministic device control, ownership, simplicity and recoverability.

Removing an automated fitness function requires the same level of justification as weakening the independent invariant it enforces.