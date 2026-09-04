# Repository Map

## Authority

This repository is the public **PRODUCT** authority. The private `iamaman11/mobile-proxy-production` repository is the **DEPLOYMENT CONTROLLER** authority.

Public PRODUCT owns source, shared product/domain architecture, Quality, product build/signing verification, annotated product tags, immutable Product Releases and product documentation.

Private DEPLOYMENT CONTROLLER owns deployment ingress, runtime State Machine / Transaction Kernel, target admission/serialization/observation, target adapters, durable mutation intent, exactly-once destructive dispatch, postconditions, recovery/quarantine, private target bindings/secrets and canonical runtime execution evidence.

See:

- `docs/operations/project-authority.md`
- `contracts/operations/project-authority-v2.json`
- `contracts/operations/github-control-plane-v2.json`
- `contracts/operations/production-topology-v2.json`

The public tree may temporarily contain legacy physical/deployment-controller code during the v2 source-ownership migration. Presence does not make that code runtime authority.

## Top-level PRODUCT ownership

- `crates/foundation`
  - validated identifiers, digests and bounded primitives;
- `crates/application`
  - transport-independent product/application ports and use cases;
- `crates/control-plane-sqlite`
  - PRODUCT control-plane durable SQLite state and migrations;
- `crates/proxy-core`
  - shared proxy/runtime compatibility contracts;
- `crates/runtime-domain`
  - pure product/runtime domain transitions;
- `crates/reverse-tunnel`
  - reverse-tunnel protocol, sessions, QUIC/TLS transport and forwarding rules;
- `services/control-plane`
  - PRODUCT control-plane service;
- `services/reverse-tunnel-server`
  - relay-side authenticated phone-session ingress and public stream forwarding;
- `services/relay-gate`
  - relay readiness gate;
- `services/runtime-supervisor`
  - rooted phone runtime product component;
- `services/host-daemon`
  - phone-local health, control-plane synchronization and rotation/runtime integration;
- `apps/operator-cli`
  - product/operator primitives; not normal production deployment authority;
- `apps/android-app`
  - Android PRODUCT component for Android-owned capabilities;
- `deploy/`
  - PRODUCT runtime layouts, templates/manifests and packaging inputs;
- `contracts/`
  - product, governance and cross-plane authority contracts;
- `docs/`
  - PRODUCT architecture/operations documentation;
- `.github/workflows/`
  - public PRODUCT CI/build/release plus historical/development acceptance surfaces; no production self-hosted runner/ADB mutation.

## Private Deployment Controller plane

The private repository is intentionally not represented as a second product source tree. It owns a different responsibility:

```text
private Issue #1 ingress
  -> deployment admission
  -> target-global serialization
  -> target observation/adapters
  -> durable mutation intent
  -> exactly-once destructive dispatch
  -> independent postcondition
  -> recovery/quarantine
  -> canonical private terminal evidence
```

The private controller must not duplicate application/runtime source or independently build/sign/tag/release the PRODUCT.

## Current public physical/deployment surface status

The following families are present in the public tree but are **not current runtime deployment authority**:

- `scripts/transaction_runner.py`;
- `scripts/control_state_machine.py`;
- `scripts/operation_state_machine.py`;
- `scripts/atomic_physical_contracts.py`;
- `scripts/physical_operation_plan.py`;
- `scripts/operations/*`;
- `scripts/clean_install_android_production.py`;
- `scripts/run_android_filesystem_certification.py`;
- `scripts/run_physical_phone_acceptance.py`;
- public phone/Item19/Item20/deployment workflows and their deployment-specific tests.

Their final disposition is handled through Issue #179 source-ownership migration:

- **PRODUCT/shared-domain** — stays public if it is genuinely product/domain behavior without deployment runtime authority;
- **deployment-only** — private controller is/will be the sole owner; duplicate public implementation is removed once explicitly authorized;
- **historical** — retained only as history/evidence or removed from active navigation/code once safe.

Do not create a third shared controller framework simply to preserve duplication.

## Layering rules inside PRODUCT

### Foundation/domain/contracts

Pure rules and bounded values. No accidental ownership of deployment runtime state.

### Application

PRODUCT use cases and sequencing over explicit ports. This does not include the private Deployment Controller transaction ledger.

### Infrastructure/adapters

PRODUCT HTTP/database/process/Android/provider implementations behind typed product/application/domain boundaries. A production target-mutation adapter belongs to the private Deployment Controller unless the v2 authority contract explicitly says otherwise.

### Composition/delivery

PRODUCT executables, packaging, CI/build/release. Runtime deployment composition belongs to the private controller.

## Machine-enforced PRODUCT graph

`contracts/governance/module-boundaries-v1.json` declares the current Rust workspace modules and allowed internal edges.

`contracts/governance/state-ownership-v1.json` declares current PRODUCT/operational mutable-state owners where applicable. These governance contracts do not supersede the v2 cross-repository deployment authority split.

## Where new work belongs

- shared bounded PRODUCT types: `crates/foundation` or an existing owning product/domain module;
- product use case/port: `crates/application`;
- durable PRODUCT control-plane persistence: `crates/control-plane-sqlite`;
- reverse-tunnel product behavior: `crates/reverse-tunnel`;
- rooted runtime product behavior: `services/runtime-supervisor` / `services/host-daemon`;
- Android product behavior: `apps/android-app`;
- product build/release: public PRODUCT workflows;
- deployment admission/target observation/mutation/recovery: private Deployment Controller;
- provider/VM production mutation: private controller adapter once proven and authorized.

A new crate/service/workflow is exceptional. Prefer an existing owner and delete duplicate authority before adding abstraction.

## Control surfaces

- public Issue #179 — migration/development checkpoint stream;
- public Issue #228 — 10/10 PRODUCT-hardening backlog only;
- private Issue #1 — runtime deployment command surface and canonical ledger.

The newest #179 checkpoint decides the exact next bounded work item.
