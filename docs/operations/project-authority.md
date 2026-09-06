# Project authority: PRODUCT and Deployment Controller

Status: **normative authority-boundary document**  
Machine authority contract: `contracts/operations/project-authority-v2.json`  
Production topology: `contracts/operations/production-topology-v2.json`  
GitHub control plane: `contracts/operations/github-control-plane-v2.json`  
Product Release authority: `contracts/operations/product-release-authority-v2.json`

## One product, two authoritative planes

`iamaman11/mobile-proxy` and `iamaman11/mobile-proxy-production` are not competing copies of one repository. They have different authority domains. Both repositories are public; repository visibility is not the confidentiality boundary.

| Plane | Repository | Authority |
| --- | --- | --- |
| PRODUCT | `iamaman11/mobile-proxy` | application/runtime source, shared product/domain architecture, Quality, Linux/Android build, Android signing verification, annotated product tags, immutable Product Release v2 |
| DEPLOYMENT CONTROLLER | `iamaman11/mobile-proxy-production` | deployment ingress, State Machine / Transaction Kernel, target admission/serialization/observation, target adapters, mutation intent, exactly-once destructive dispatch, postconditions, recovery/quarantine, target bindings/secrets, canonical runtime execution evidence |

The PRODUCT repository is the canonical source and release plane. The Deployment Controller repository is the canonical deployment-execution plane. Neither plane may silently take over the other's responsibilities.

This supersedes both the older “private execution-only thin satellite” model and any assumption that controller confidentiality depends on repository visibility. The controller repository remains forbidden from copying application source or independently building/signing/publishing the product. Secrets, target bindings, raw device identifiers, credentials, private keys and sensitive runtime values remain private even though controller source and policy are public.

## PRODUCT authority

The PRODUCT repository owns:

- application and runtime source;
- shared product/domain contracts;
- protected PR delivery and public `Quality`;
- release-version contract;
- Linux product build;
- signed Android product build and verification;
- exact annotated semantic-version tag;
- immutable GitHub Product Release v2;
- release manifest, provenance and typed content-digest contract.

The PRODUCT plane must not:

- access the production phone;
- invoke ADB for deployment;
- mutate production VM/provider targets;
- hold private target bindings;
- own the deployment transaction ledger;
- perform exactly-once physical dispatch;
- classify ambiguous physical execution after the destructive boundary.

Public Issue #90 remains the product GitOps command surface for product-tag operations. Public Issue #179 is the migration/development execution cursor while the current hardening program is active; it is not normal runtime deployment identity. Public Issue #228 is backlog only and never overrides #179.

## Deployment Controller authority

The Deployment Controller owns the active deployment command surface on `iamaman11/mobile-proxy-production` Issue #1:

```text
/deploy <target> <vX.Y.Z>
/retry-deploy phone-production <vX.Y.Z> <prior-semantic-request-id>
```

Ordinary `/deploy` remains the normal deployment command and keeps its existing semantic request identity. `/retry-deploy` is not a generic replay mechanism: it creates a distinct semantic request bound to the exact prior semantic request id and is admitted only for an exact matching `phone-production` request whose trusted canonical history proves exactly one pre-mutation `REFUSED` terminal with `mutation_performed=false`, `recovery_required=false`, and no durable mutation intent. GitHub run/comment provenance never supplies retry identity. `UNKNOWN`, `RECOVERED`, `QUARANTINED`, mutation-bearing, intent-bearing, mismatched, malformed or non-terminal history is not eligible for this retry path. Retry is always explicit; it is never automatic.

The Deployment Controller owns:

- semantic deployment request identity;
- exact Product Release resolution;
- exact controller-revision binding;
- target-global serialization;
- precondition/admission classification;
- target observations and target adapters;
- durable mutation intent before destructive dispatch;
- exactly-once destructive dispatch;
- independent postcondition observation;
- read-only recovery when the destructive outcome is ambiguous;
- quarantine and terminal execution classification;
- canonical runtime execution evidence;
- bounded public GitHub Deployment status/history projection.

The controller must not:

- copy PRODUCT application/runtime source;
- independently create product artifacts;
- own Android product signing policy;
- create or replace Product Releases;
- create a competing product tag;
- rewrite an immutable Product Release asset;
- commit or publish secrets, raw device identifiers, private target bindings, credentials or sensitive runtime logs.

## Confidentiality boundary

Public controller source does not make production credentials public.

The following remain private operational inputs/state and must never be committed or emitted unredacted to public GitHub surfaces:

- repository/environment secret values;
- target/device bindings and raw device identifiers;
- private keys, tokens, passwords and provider credentials;
- sensitive rendered configuration;
- unbounded/raw ADB or production logs that can contain confidential material.

Public controller evidence must therefore be bounded and non-sensitive. Where a controller decision depends on a sensitive fact, store only the minimum safe classification/digest/boolean required by the admitted evidence contract.

## Runtime identity

Product identity and controller identity are intentionally separate.

```text
product_release
  = exact semantic product tag
  + exact annotated-tag target PRODUCT source SHA
  + exact immutable Product Release v2 asset contract

runtime_deployment_identity
  = product_release
  + exact admitted controller_revision
```

A controller repair or recovery-policy change therefore does not require rebuilding an unchanged product. Conversely, a new product release does not silently redefine the controller revision that executed it.

`latest`, a mutable branch, PRODUCT `main` alone, or Issue #179 alone are never sufficient runtime deployment identity.

## Product Release precedes deployment

The correct authority order is:

```text
protected PRODUCT main + exact successful Quality
  -> Product Release prerequisites
  -> annotated product tag
  -> signed PRODUCT build
  -> immutable Product Release v2
  -> Deployment Controller /deploy <target> <tag>
  -> controller admission / observation / possible mutation / verification / recovery
```

An explicitly admitted pre-mutation `REFUSED` retry remains inside the same Deployment Controller transaction authority and consumes the same immutable Product Release. It does not create or alter PRODUCT release authority and does not permit a second destructive effect for any request that reached mutation intent or an ambiguous physical boundary.

A Product Release is an input to deployment. Physical phone acceptance is therefore not a prerequisite for creating the Product Release; final operational acceptance happens after deployment of that immutable release.

Historical Item 19/Item 20 evidence remains historical acceptance/development evidence. It does not supply normal Product Release or runtime deployment authority under controller v2.

## Android product and deployment roles

The Android app is not the primary reverse-tunnel owner. The native rooted `first_party_reverse_tunnel` path remains primary. The app is a managed production auxiliary component when topology uses Android `Network.bindSocket()` cellular egress or the app-owned WireGuard compatibility path.

The PRODUCT plane builds and verifies the exact signed Android APK. The Deployment Controller decides, from target topology and observed target state, whether that immutable APK must be installed/updated and owns any physical mutation transaction.

Signing secrets used to create the PRODUCT artifact belong only to the protected PRODUCT release environment. Target/device secrets belong only to admitted controller execution environments. Signer material or raw fingerprints are never public Release/runtime evidence.

## Evidence authority

There are three different evidence roles and they must not be conflated:

1. **Product evidence** — PRODUCT Quality, Product Release v2 manifest/provenance/typed digests and GitHub immutability.
2. **Runtime execution truth** — Deployment Controller durable ledger and terminal classification.
3. **Public deployment projection** — bounded GitHub Deployment status/history for visibility only.

A public GitHub Deployment is not the execution ledger and cannot authorize a second physical dispatch. If public projection fails after a physical boundary, recovery is based on the controller durable ledger and read-only observation.

Sensitive runtime values remain private by design even though the controller repository is public.

## Failure semantics

Authority conflicts fail closed by domain:

- PRODUCT source/build/tag/Release ambiguity -> stop in PRODUCT plane;
- controller revision/request/target-state ambiguity before dispatch -> no mutation;
- a new explicit retry may be admitted only from trusted durable proof of an exact matching pre-mutation `REFUSED` terminal with no mutation intent;
- ambiguity after a durable destructive dispatch boundary -> no blind retry, read-only recovery only;
- Product Release missing or mutable -> controller deployment admission rejects it;
- controller cannot bind exact Product Release + exact controller revision -> no mutation;
- public projection failure -> never interpreted as permission to redispatch.

`RECOVERED` never retroactively converts the original deployment attempt into `ACCEPTED`.

## Current hardening path

The durable project path to operational acceptance is:

```text
A  Deployment Controller health
B  source ownership / authority convergence
C  Android secret-state and backup/D2D hardening
D  Android behavior and framework integration tests
E  supply-chain provenance + Product Release prerequisite hardening
F  new immutable Product Release
G  exactly one admitted deployment of that release
H  real-world phone + tunnel + provider + external-client acceptance
```

Issue #179 is the only cursor that may authorize the current bounded engineering or physical step. Issue #228 is the implementation backlog. Passing an earlier physical experiment never substitutes for Gate H on the final immutable release.

## Historical contracts

Older v1 contracts and Item 19/Item 20 artifacts remain in Git history/repository where useful for audit. They are not active Product Release/runtime authority when they conflict with the v2 contracts listed at the top of this document.

No phone, VM or provider mutation authority is granted by this document itself.
