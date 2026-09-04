# Quick Reference

## Authority in 30 seconds

Mobile Proxy has one product and two authoritative planes:

- **PRODUCT** — `iamaman11/mobile-proxy`: source, product/domain architecture, public Quality, product build/signing verification, annotated tags, immutable Product Releases and product documentation.
- **DEPLOYMENT CONTROLLER** — `iamaman11/mobile-proxy-production`: private Issue #1 deployment ingress, deployment State Machine / Transaction Kernel, target admission/serialization/observation, target adapters, durable mutation intent, exactly-once destructive dispatch, postconditions, recovery/quarantine, private bindings/secrets and canonical runtime execution evidence.

The private repository is not a thin execution satellite and is not a second product source. It is authoritative only inside the deployment domain.

Normative contracts:

1. `docs/operations/project-authority.md`
2. `contracts/operations/project-authority-v2.json`
3. `contracts/operations/github-control-plane-v2.json`
4. `contracts/operations/production-topology-v2.json`
5. `contracts/operations/product-release-authority-v2.json`

Older v1 authority/topology/control-plane wording is historical when it conflicts with v2.

## Start here after context loss

Read:

1. `AGENTS.md` — operating contract and safety boundaries;
2. `IMPLEMENTATION_PLAN.md` — concise current development sequence;
3. `docs/PRODUCTION_BASELINE_PLAN.md` — active 10/10 roadmap;
4. `REPOSITORY_MAP.md` — code/ownership map;
5. `RUNTIME_LAYOUT.md` — product runtime topology;
6. `docs/GIT_DELIVERY.md` — Product Release -> Deployment Controller handoff;
7. newest authoritative checkpoint in public Issue #179.

Do not reconstruct current execution authority from older issue bodies, historical Item19/Item20 wording or chat memory.

## Current control surfaces

- public Issue **#179** — authoritative migration/development checkpoint stream; exactly one bounded engineering item at a time;
- public Issue **#228** — 10/10 PRODUCT-hardening backlog only; no runtime authority;
- public Issue **#90** — product tag/release command surface where required by the current product-release contract;
- private Issue **#1** — Deployment Controller command surface and canonical runtime ledger.

A `/deploy`, phone/ADB action, provider/VM mutation, signing action or release rewrite is forbidden unless the newest #179 checkpoint and the owning v2 authority plane explicitly permit it.

## Product/release boundary

Public PRODUCT flow:

```text
protected main + exact successful Quality
  -> annotated product tag
  -> signed PRODUCT build
  -> immutable Product Release v2
```

Deployment flow:

```text
exact immutable Product Release
+ exact admitted private controller revision
  -> private deployment request
  -> admission/serialization/observation
  -> possible exactly-once mutation
  -> independent postcondition
  -> canonical private terminal evidence
```

Public GitHub Deployment status is projection only. It is never the canonical runtime ledger.

## Current 10/10 hardening order

Issue #228 is the backlog; Issue #179 decides which item is actually executable now.

The intended order is:

1. remove active v1 authority drift from normative entry points;
2. classify and then simplify/remove duplicate public deployment-controller ownership;
3. close Android secret-state / backup-D2D gaps;
4. add the smallest strong Android behavior coverage;
5. finish Product Release prerequisite/tag hardening;
6. establish complete WireGuard AAR upstream provenance;
7. clean stale normative trackers/docs;
8. only when separately authorized, execute live deployment/acceptance through the private controller.

Do not create a third shared controller framework to reconcile public/private duplication.

## Existing public physical/controller surfaces

Files such as:

- `scripts/transaction_runner.py`
- `scripts/control_state_machine.py`
- `scripts/operation_state_machine.py`
- `scripts/atomic_physical_contracts.py`
- `scripts/physical_operation_plan.py`
- `scripts/operations/*`
- `scripts/clean_install_android_production.py`
- `scripts/run_android_filesystem_certification.py`
- `scripts/run_physical_phone_acceptance.py`
- public phone/Item19/Item20/deployment workflows

are not current runtime authority merely because they remain in the public tree. Their bounded PRODUCT/shared-domain vs deployment-only vs historical disposition is handled in the source-ownership migration through #179.

## Runtime safety invariants

The private Deployment Controller must preserve:

- target-global serialization;
- durable mutation intent before destructive dispatch;
- at most one destructive dispatch per durable intent;
- independent target postcondition observation;
- no blind retry after an ambiguous destructive boundary;
- read-only UNKNOWN recovery;
- `RECOVERED != ACCEPTED`;
- semantic request identity independent of GitHub run/comment provenance;
- canonical private terminal evidence.

## Development quality

```bash
scripts/quality-gate.sh fast  # docs/policy-sized changes
scripts/quality-gate.sh       # code/release changes
```

GitHub requires the aggregate `Quality Gate`. Read the compact quality summary before opening large logs.

## Hard boundaries

- public PRODUCT workflows do not access the production phone or invoke deployment ADB;
- private controller does not copy/build/sign/tag/publish the product;
- manual SSH/raw ADB/workstation provider CLI are not normal production control paths;
- secret values, raw device identifiers and sensitive private runtime evidence do not belong in public Git/evidence;
- `latest`, mutable branches and public Deployment status are never runtime identity.
