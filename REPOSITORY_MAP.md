# Repository Map

Updated: 2026-08-30  
Canonical repository: `iamaman11/mobile-proxy`

## Authority

This repository is the only canonical repository for project information. The private
`iamaman11/mobile-proxy-production` repository is an execution satellite only and must not become a
second architecture, roadmap, manifest or product-code source. See
`docs/operations/project-authority.md`.

The repository must be readable as a layered system rather than a collection of workstation
scripts or runtime snapshots.

The normative architecture quality rules are in `docs/architecture/ARCHITECTURE_STANDARD.md`.
The exact current Rust workspace dependency graph is machine-readable in
`contracts/governance/module-boundaries-v1.json`. Current authoritative/operational mutable-state
ownership is registered in `contracts/governance/state-ownership-v1.json`. Both are enforced by the
required Quality Gate.

## Top-level ownership

- `crates/foundation`
  - validated identifiers, digests and other bounded primitives;
- `crates/application`
  - transport-independent application ports and orchestration boundaries;
- `crates/control-plane-sqlite`
  - canonical durable SQLite state and migrations;
- `crates/proxy-core`
  - shared proxy/runtime compatibility contracts still being narrowed over time;
- `crates/runtime-domain`
  - pure runtime state transitions;
- `crates/reverse-tunnel`
  - reverse-tunnel protocol, sessions, QUIC/TLS transport and forwarding rules;
- `services/control-plane`
  - control-plane service using the durable application/persistence boundary;
- `services/reverse-tunnel-server`
  - relay-side authenticated phone-session ingress and public stream forwarding;
- `services/relay-gate`
  - narrowly scoped relay readiness gate;
- `services/runtime-supervisor`
  - rooted phone process/recovery supervisor;
- `services/host-daemon`
  - phone-local health, control-plane synchronization and rotation/runtime integration;
- `apps/operator-cli`
  - operator/application orchestration commands and reusable deployment primitives;
- `apps/android-app`
  - Android application boundary for Android-owned capabilities; not a home for generic domain logic;
- `deploy/`
  - versioned deployable layouts, templates and manifests;
- `contracts/`
  - machine-readable compatibility, governance, project-authority and production-control invariants;
- `docs/`
  - canonical architecture/operations documents; superseded material belongs under `docs/history/`;
- `.github/workflows/`
  - public CI/release/GitHub-hosted orchestration only; no public self-hosted runner/ADB path.

## Project control-plane boundary

```text
iamaman11/mobile-proxy (PUBLIC, canonical)
  -> PR / Quality Gate / protected main
  -> annotated protected release tag
  -> release artifacts + provenance
  -> GitHub-hosted Vultr execution
  -> private phone execution command

iamaman11/mobile-proxy-production (PRIVATE, execution-only)
  -> thin caller/shim
  -> android-production self-hosted runner
```

The private repository is not represented as an application/source module here because it is not a
second source tree. Canonical phone workflow logic should remain in this repository and be invoked
at an immutable ref or delivered as a verified immutable release artifact.

## Layering rules

### Foundation/domain/contracts

Pure rules, bounded values and canonical contracts. No HTTP, database, provider, Android, filesystem
or process ownership. Existing narrower pure-crate restrictions remain independently enforced.

### Application

Use cases and sequencing over explicit ports. Owns orchestration semantics, not platform commands.

### Infrastructure/adapters

HTTP/database/process/Android/provider implementations behind typed application/domain boundaries.

### Composition/delivery

Executable services, packaging and GitHub-controlled deployment. Composition roots may wire concrete
implementations but do not become alternative domain owners.

## Machine-enforced Rust module graph

`contracts/governance/module-boundaries-v1.json` declares every current Rust workspace member, its
architectural role and the exact internal package dependencies it currently uses.

The policy gate fails closed when:

- a Cargo workspace member is added without classification;
- a declared module disappears or names a different Cargo package;
- a module introduces an internal dependency not present in its allowlist;
- the allowlist contains a stale edge no longer present in Cargo metadata;
- an allowed dependency points to an unknown module;
- the internal graph contains a cycle.

The contract describes existing justified edges; it is not blanket permission to add every edge
that a layer could theoretically tolerate. New edges must still satisfy the architecture standard
and the smallest-current-design rule.

## Mutable-state ownership

`contracts/governance/state-ownership-v1.json` assigns one authority to each currently registered
canonical or operational mutable-state group. It distinguishes the behavior owner from policy/type
modules and, for durable state, from the persistence adapter.

The current registry covers:

- canonical control-plane devices, runtime projections, commands/results and replay/idempotency state;
- relay reverse-tunnel session/liveness/connection/control/pending/reserve state;
- host-daemon local health/job/proxy/tunnel runtime projection;
- durable host-daemon reverse-tunnel event counters;
- runtime-supervisor lifecycle/readiness and repair-cooldown state.

The policy gate rejects duplicate resource ownership, unknown owner modules, state writers outside
the declared authority, and durable state without a declared persistence owner. A policy crate such
as `runtime-domain` may define deterministic transitions without becoming a second mutable-state
owner.

This registry is an explicit inventory, not a magical semantic scanner. A future source file could
still invent a new mutable state concept without the checker understanding its meaning; that residual
discovery gap remains recorded in the invariant-enforcement matrix rather than being disguised as
fully solved.

## Where new work belongs

- shared bounded types: `crates/foundation` or the existing owning contract crate;
- application use case/port: `crates/application`;
- durable control-plane persistence: `crates/control-plane-sqlite`;
- reverse-tunnel protocol/session behavior: `crates/reverse-tunnel`;
- phone process supervision: `services/runtime-supervisor`;
- phone-local service behavior: `services/host-daemon`;
- relay ingress: `services/reverse-tunnel-server`;
- operator orchestration primitive: `apps/operator-cli`;
- provider/device adapter: the layer selected by the canonical architecture/roadmap, never a
  workstation script shortcut;
- production workflow logic: canonical repository first; private phone repo only gets the minimum
  execution shim GitHub requires.

A new crate or service is exceptional, not the default response to a new feature. Reuse an existing
owner when that preserves cohesion; create a new module only when it establishes a real independent
responsibility and document its dependency/ownership/deletion boundaries in the same pull request.
New authoritative or operational mutable state must be added to the ownership registry in the same
change.

## Current production-control status

The codebase has a working legacy runtime and canonical SQLite/reverse-tunnel components, but the
new production-control migration is intentionally incomplete:

- public GitHub governance and trust-zone contracts are established;
- legacy public deployment is blocked fail-closed;
- typed Vultr provider lifecycle is still pending;
- live read-only Vultr preflight is pending;
- private phone execution workflow and live read-only phone preflight are pending;
- autonomous release-control entrypoint and corrected immutable-release publication are pending.

Do not interpret existing `operator-cli`, GCP manifests or historical ADB/SSH procedures as an
authorised production shortcut while those gates are pending.

## Root-document rule

The root contains only current navigation/contract entry points. Detailed architecture and
operations belong under `docs/`; historical workstation/provider observations belong under
`docs/history/` or Git history and are non-authoritative.
