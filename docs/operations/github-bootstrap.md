# GitHub control-plane bootstrap

This document describes the GitHub trust/configuration boundary for the accepted v2 authority model.

## Two authoritative planes

- Public `iamaman11/mobile-proxy` = **PRODUCT** authority.
- Private `iamaman11/mobile-proxy-production` = **DEPLOYMENT CONTROLLER** authority.

The private repository is not a thin execution satellite and not a second product source. It owns deployment-controller code/policy and canonical runtime execution evidence, while remaining forbidden from copying/building/signing/tagging/publishing the product.

Normative contracts:

- [`project-authority-v2.json`](../../contracts/operations/project-authority-v2.json)
- [`github-control-plane-v2.json`](../../contracts/operations/github-control-plane-v2.json)
- [`production-topology-v2.json`](../../contracts/operations/production-topology-v2.json)
- [`product-release-authority-v2.json`](../../contracts/operations/product-release-authority-v2.json)
- [Project authority](project-authority.md)

Older v1 control-plane/topology bootstrap wording is historical when it conflicts with v2.

## Required GitHub state

| Boundary | Required state |
| --- | --- |
| public `iamaman11/mobile-proxy` | public PRODUCT repository; no production self-hosted runner |
| public `main` | protected PR delivery with required `Quality Gate`; no destructive ref rewrite |
| protected `v*` | immutable product-tag identity; never delete/move/reuse |
| public Actions | least privilege; no production target access from fork/PR trust boundary |
| `product-release` environment | protected PRODUCT release/signing inputs only; no target/provider mutation |
| private `iamaman11/mobile-proxy-production` | private Deployment Controller repository; Actions/Issues; canonical controller runtime evidence |
| private Issue #1 | owner-controlled deployment ingress and canonical runtime ledger |
| `android-production` runner | private controller runner for the registered phone |
| `vm-production` | fail-closed until a controller-owned VM adapter is proven end-to-end |

The exact current machine-readable desired state is in the v2 contracts above.

## Public PRODUCT credential boundary

The public `product-release` environment owns only PRODUCT build/release credentials required by the Product Release contract, including the configured Android product signing inputs.

Rules:

- secret values are never committed or emitted as evidence;
- public PR/fork workflows cannot receive production signing secrets;
- product release jobs have no production phone/ADB/provider mutation authority;
- release prerequisite proof should inspect only the minimum configuration metadata necessary and must not load signing secret values merely to prove names exist once that hardening is implemented.

Local/workstation secret stores are bootstrap/recovery aids only, never the normal production execution path.

## Private Deployment Controller boundary

The private repository owns the deployment runtime control plane:

```text
private Issue #1
  -> semantic deployment request
  -> exact Product Release resolution
  -> target-global serialization
  -> target observation/admission
  -> durable mutation intent
  -> at most one destructive dispatch per intent
  -> independent postcondition
  -> canonical terminal / recovery / quarantine evidence
```

It may contain:

- Deployment Controller source/policy;
- private runner wiring;
- target adapters/observers;
- private target bindings/secrets;
- bounded canonical runtime evidence;
- recovery/quarantine logic.

It must not contain a copied PRODUCT source tree or independent product build/sign/tag/release authority.

## Phone runner boundary

The phone runner exists privately because physical target access cannot be supplied by a public GitHub-hosted runner.

Normal production jobs must:

- bind the exact private `android-production` target/runner contract;
- obtain target authority through the private controller, not raw/manual ADB;
- keep provider credentials off the phone runner unless a future explicit adapter contract requires a separate bounded boundary;
- never publish the raw device identifier or sensitive target values;
- preserve exactly-once destructive dispatch and read-only ambiguous-outcome recovery.

The existence or online state of a runner is not itself deployment authority.

## Product Release -> deployment handoff

The handoff is:

```text
protected public source + Quality
  -> annotated product tag
  -> immutable Product Release v2
  -> private /deploy <target> <tag>
```

The controller independently binds the exact Product Release and exact admitted controller revision.

A public GitHub Deployment object is a bounded visibility projection only. It is never the controller ledger.

## Re-entry / recovery

If a prior request has ambiguous history, never infer permission from workflow failure or public Deployment status.

The private controller rereads its canonical ledger:

- terminal exists -> semantic duplicate/no second mutation;
- durable intent exists without terminal -> recovery-only/read-only reconciliation as allowed by controller semantics;
- neither exists -> a fresh semantic execution may be eligible only when separately authorized;
- no old workflow run is manually rerun as a destructive retry mechanism.

## Control surfaces

- public Issue #179 = development/migration checkpoint authority;
- public Issue #228 = 10/10 backlog only;
- public Issue #90 = product tag/release surface where required by Product Release policy;
- private Issue #1 = deployment ingress/runtime ledger.

Always reread the newest #179 checkpoint before any GitHub state change that could affect production authority.

## Reconciliation procedure

When GitHub configuration needs reconciliation:

1. identify the owning plane;
2. compare live safe metadata against the matching v2 contract;
3. change only the minimum required setting/secret binding;
4. never print/read secret values merely to prove configuration;
5. run bounded hosted proof where live connector visibility is insufficient;
6. checkpoint only non-sensitive result metadata.

No bootstrap/reconciliation action itself authorizes phone, VM or provider mutation.
