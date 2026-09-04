# Git delivery and production control

Mobile Proxy uses one product with two authoritative planes.

- `iamaman11/mobile-proxy` is the public **PRODUCT** authority for source, Quality, build/signing verification, annotated product tags, immutable Product Releases and product documentation.
- `iamaman11/mobile-proxy-production` is the private **DEPLOYMENT CONTROLLER** authority for deployment ingress, runtime State Machine / Transaction Kernel, target admission/serialization/observation, target adapters, durable mutation intent, exactly-once destructive dispatch, recovery/quarantine and canonical runtime execution evidence.

See:

- [`project-authority-v2.json`](../contracts/operations/project-authority-v2.json)
- [`github-control-plane-v2.json`](../contracts/operations/github-control-plane-v2.json)
- [`production-topology-v2.json`](../contracts/operations/production-topology-v2.json)
- [`product-release-authority-v2.json`](../contracts/operations/product-release-authority-v2.json)
- [Project authority](operations/project-authority.md)

Older v1 control-plane/topology language is historical when it conflicts with v2.

## Trust boundaries

| Boundary | Responsibility |
| --- | --- |
| public `iamaman11/mobile-proxy` | PRODUCT source, public CI/Quality, product build/signing verification, product tags/releases; zero production self-hosted runners and no production phone/ADB mutation |
| public `product-release` environment | protected PRODUCT signing/release inputs; no target access/provider mutation |
| private `iamaman11/mobile-proxy-production` | Deployment Controller code/policy, private Issue #1 ingress, target bindings/secrets, canonical runtime execution evidence |
| private `android-production` runner | registered production-phone execution under controller admission; no public fork/PR trust exposure |
| `vm-production` | fail-closed until a private controller-owned VM adapter is proven end-to-end |

The private controller must not copy application source or independently build/sign/tag/release the product. The public PRODUCT plane must not own runtime target mutation or exactly-once dispatch authority.

## Public Git governance

- `main` changes through pull request and required `Quality Gate`.
- Protected `v*` product tags are immutable identifiers; never move/reuse them.
- Public Actions use least privilege and never expose production phone secrets/runner access to forked PRs.
- Public PRODUCT workflows do not run production ADB or mutate production targets.
- Secret values, raw device identifiers and private runtime evidence do not belong in public evidence.

## Product Release chain

The current v2 release order is:

```text
topic branch
  -> pull request
  -> exact PR-head Quality
  -> protected main
  -> exact successful main Quality
  -> Product Release prerequisite proof
  -> annotated semantic product tag
  -> signed/verified PRODUCT build
  -> immutable Product Release v2
```

A Product Release is public PRODUCT authority and exists **before** normal deployment admission. Physical target acceptance is not a prerequisite for creating that Product Release under v2.

Product release identity is exact and immutable. `latest`, a mutable branch, short SHA or unverified artifact is never equivalent.

## Deployment handoff

Deployment consumes:

```text
exact immutable Product Release v2
+ exact admitted private controller revision
```

Normal runtime ingress is private Issue #1:

```text
/deploy <target> <vX.Y.Z>
```

The private controller owns:

1. semantic request identity;
2. exact Product Release resolution;
3. controller revision binding;
4. target-global serialization;
5. target observation and admission;
6. durable mutation intent before destructive dispatch;
7. at most one destructive dispatch for one durable intent;
8. independent postcondition observation;
9. canonical terminal evidence;
10. read-only recovery/quarantine after ambiguous dispatch.

A public GitHub Deployment is status/history projection only. It is not the canonical execution ledger and cannot authorize a second destructive dispatch.

## Failure/re-entry semantics

Before destructive dispatch, ambiguity fails closed with no target mutation.

After durable destructive dispatch may have occurred:

```text
UNKNOWN
  -> read-only observation/reconciliation
  -> RECOVERED | QUARANTINED | separately proven terminal
```

Rules:

- no blind destructive retry;
- `RECOVERED != ACCEPTED`;
- GitHub run/comment/attempt identity does not redefine semantic request identity;
- evidence transport retry is never physical-effect retry;
- old failed workflow runs are not manually rerun as the deployment mechanism.

Re-entry eligibility is determined only from the canonical private ledger under current controller semantics.

## Control issues

- public Issue #179: migration/development checkpoint authority only; not the normal runtime ledger;
- public Issue #228: 10/10 PRODUCT-hardening backlog only;
- public Issue #90: product tag/release command surface where the accepted Product Release contract requires it;
- private Issue #1: Deployment Controller ingress and canonical runtime ledger.

The newest authoritative #179 checkpoint decides which engineering/production action is currently permitted.

## Existing legacy public execution surfaces

Public Item19/Item20/phone/deployment workflows and public physical-controller scripts remain in the repository during source-ownership migration. They are not current runtime deployment authority.

Their disposition is bounded by #179:

- PRODUCT/shared-domain behavior stays public;
- deployment-only controller/target mutation behavior moves to or is deleted in favor of the private controller;
- historical development/acceptance surfaces are retired or clearly marked historical.

Do not create a third shared controller framework to keep duplicated authority alive.

## Normal development

1. Create a topic branch from exact current protected `main`.
2. Make the smallest bounded change with direct verification.
3. Open a pull request.
4. Merge only after required Quality succeeds and the PR remains based on the expected state.
5. Revalidate exact post-merge `main`/Quality when the next authority decision depends on it.
6. For production release/deployment work, follow the v2 authority order above and the newest #179 checkpoint.

## Secret and evidence policy

Secret values never belong in Git or public logs/evidence. Safe public evidence may contain exact public SHA/tag/run/release identities and bounded booleans required by contract.

Private target bindings, credentials, raw device identifiers and sensitive runtime logs remain inside the private Deployment Controller boundary.

## Prohibited shortcuts

- raw/manual ADB as normal production control;
- workstation SSH/provider CLI deployment;
- public PRODUCT workflow target mutation;
- private controller independent product build/sign/tag/release;
- deployment from mutable/`latest` identity;
- public Deployment projection as canonical ledger;
- blind destructive retry after ambiguous dispatch.

## Quality

For docs/policy work:

```bash
scripts/quality-gate.sh fast
```

For code/release work:

```bash
scripts/quality-gate.sh
```

A green PRODUCT Quality result proves source-controlled PRODUCT coherence. It does not by itself prove current target state or grant deployment authority.
