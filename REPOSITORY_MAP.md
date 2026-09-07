# Repository Map

## Authority

Mobile Proxy has one product and two authoritative planes. **Both repositories are public.**

- `iamaman11/mobile-proxy` = PRODUCT authority.
- `iamaman11/mobile-proxy-production` = DEPLOYMENT CONTROLLER authority.

PRODUCT owns source, shared product/domain architecture, Quality, product build/signing verification, annotated product tags, immutable Product Releases and product documentation.

DEPLOYMENT CONTROLLER owns Issue #1 deployment ingress, deployment State Machine / Transaction Kernel, target admission/serialization/observation, target adapters, durable mutation intent, exactly-once destructive dispatch, postconditions, recovery/quarantine and canonical runtime execution evidence.

Secrets, target bindings, raw identifiers, credentials and sensitive runtime evidence remain private despite public repository visibility.

See:

- `docs/operations/project-authority.md`
- `contracts/operations/project-authority-v2.json`
- `contracts/operations/github-control-plane-v2.json`
- `contracts/operations/production-topology-v2.json`
- `contracts/operations/product-release-authority-v2.json`

Historical v1 controller/execution-satellite wording does not override v2.

## Context recovery

Current work is never derived from this repository map. Use:

`AGENTS.md -> STAGE_WORKFLOW.md -> newest PRODUCT #179 checkpoint -> current Stage Issue`.

Static roadmap: `docs/PRODUCTION_STAGE_ROADMAP.md`. Planning backlog: PRODUCT #249. Architecture standard: `docs/architecture/ARCHITECTURE_STANDARD.md`.

## Top-level PRODUCT ownership

- `crates/foundation` — validated identifiers, digests and bounded primitives;
- `crates/application` — transport-independent PRODUCT/application ports and use cases;
- `crates/control-plane-sqlite` — PRODUCT durable SQLite state and migrations;
- `crates/proxy-core` — shared proxy/runtime compatibility contracts;
- `crates/runtime-domain` — pure product/runtime domain transitions;
- `crates/reverse-tunnel` — reverse-tunnel protocol, sessions, QUIC/TLS transport and forwarding rules;
- `services/control-plane` — PRODUCT control-plane service;
- `services/reverse-tunnel-server` — relay-side authenticated phone-session ingress and forwarding;
- `services/relay-gate` — relay readiness gate;
- `services/runtime-supervisor` — rooted phone runtime PRODUCT component;
- `services/host-daemon` — phone-local health, synchronization and runtime integration;
- `apps/operator-cli` — product/operator primitives, not production deployment authority;
- `apps/android-app` — Android PRODUCT component for Android-owned capabilities;
- `deploy/` — PRODUCT runtime layouts, templates/manifests and packaging inputs;
- `contracts/` — product, governance and cross-plane authority contracts;
- `docs/` — PRODUCT architecture/operations/reference documentation;
- `.github/workflows/` — PRODUCT CI/build/release plus historical/development acceptance surfaces; no production target mutation authority.

## Deployment Controller plane

Controller is not a second product source tree. It owns this responsibility:

```text
Issue #1 ingress
  -> deployment admission
  -> target-global serialization
  -> target observation/adapters
  -> durable mutation intent
  -> at most one destructive dispatch per intent
  -> independent postcondition
  -> recovery/quarantine
  -> canonical terminal evidence
```

Controller must not duplicate application/runtime source or independently build/sign/tag/release PRODUCT artifacts.

## Historical PRODUCT physical/controller surfaces

Historical public physical transaction/controller code may remain in Git history or transitional source, but presence does not grant runtime deployment authority. Its disposition follows current stage work and v2 ownership:

- genuine PRODUCT/shared-domain behavior stays with its PRODUCT owner;
- deployment-only behavior belongs only to Controller;
- obsolete/historical implementations are removed or isolated when their earliest active stage requires simplification.

Do not create a third shared controller framework merely to preserve historical duplication.

## Layering inside PRODUCT

### Foundation/domain/contracts

Pure rules and bounded values. No accidental ownership of deployment runtime state.

### Application

PRODUCT use cases over explicit ports. Does not include the Controller transaction ledger.

### Infrastructure/adapters

PRODUCT HTTP/database/process/Android integrations behind PRODUCT boundaries. Production target-mutation adapters belong to Controller.

### Composition/delivery

PRODUCT executables, packaging, CI/build/release. Runtime deployment composition belongs to Controller.

## Machine-enforced PRODUCT graph

`contracts/governance/module-boundaries-v1.json` declares current Rust workspace modules and allowed internal edges.

`contracts/governance/state-ownership-v1.json` declares PRODUCT/operational mutable-state owners where applicable. These contracts do not supersede v2 cross-repository deployment authority.

## Where new work belongs

- bounded PRODUCT types -> `crates/foundation` or the narrow existing owner;
- product use case/port -> `crates/application`;
- durable PRODUCT persistence -> `crates/control-plane-sqlite`;
- reverse-tunnel behavior -> `crates/reverse-tunnel`;
- rooted runtime PRODUCT behavior -> `services/runtime-supervisor` / `services/host-daemon`;
- Android PRODUCT behavior -> `apps/android-app`;
- build/release -> PRODUCT workflows;
- deployment admission/target observation/mutation/recovery -> Deployment Controller;
- repeatable Controller phone observation gap -> smallest Controller observer/adapter improvement when stage-relevant;
- inherently physical/UI/modem observation -> local-agent evidence boundary;
- provider/VM production mutation -> Controller Stage 6 adapter/lifecycle after #179 opens Stage 6.

A new crate/service/workflow is exceptional. Prefer existing ownership and deletion/consolidation before abstraction.

## Control surfaces

- PRODUCT #179 — sole dynamic stage/operations cursor;
- PRODUCT #249 — stage-mapped planning/acceptance backlog only;
- PRODUCT #90 — Product Release/tag command surface where required by current Product Release contract;
- Controller #1 — deployment command ingress and canonical runtime ledger.

Current stage, current Release and exact next action are intentionally absent here. Resolve them from the newest #179 checkpoint.
