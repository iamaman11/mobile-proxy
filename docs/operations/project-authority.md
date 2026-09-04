# Project authority: PRODUCT and Deployment Controller

Status: **normative authority-boundary document**  
Machine authority contract: `contracts/operations/project-authority-v2.json`  
Production topology: `contracts/operations/production-topology-v2.json`  
GitHub control plane: `contracts/operations/github-control-plane-v2.json`  
Product Release authority: `contracts/operations/product-release-authority-v2.json`

## One product, two authoritative planes

`iamaman11/mobile-proxy` and `iamaman11/mobile-proxy-production` are not competing copies of one repository. They have different authority domains.

| Plane | Repository | Authority |
| --- | --- | --- |
| PRODUCT | `iamaman11/mobile-proxy` | source, shared product/domain architecture, Quality, Linux/Android build, Android signing verification, annotated product tags, immutable Product Release v2 |
| DEPLOYMENT CONTROLLER | `iamaman11/mobile-proxy-production` | deployment ingress, State Machine / Transaction Kernel, target admission/serialization/observation, target adapters, mutation intent, exactly-once destructive dispatch, postconditions, recovery/quarantine, private bindings/secrets, canonical runtime evidence |

The public repository is the canonical PRODUCT source. The private repository is the canonical deployment-execution controller. Neither plane may silently take over the other's responsibilities.

This supersedes the older “private repository is execution-only thin satellite” model. The private repository remains forbidden from copying application source or independently building/signing/publishing the product, but its controller policy and runtime transaction state are authoritative inside the deployment domain.

## PRODUCT authority

The public repository owns:

- application and runtime source;
- shared product/domain contracts;
- protected PR delivery and public `Quality`;
- release-version contract;
- Linux product build;
- signed Android product build and verification;
- exact annotated semantic-version tag;
- immutable GitHub Product Release v2;
- release manifest, provenance and typed content-digest contract.

The public PRODUCT plane must not:

- access the production phone;
- invoke ADB for deployment;
- mutate production VM/provider targets;
- hold private target bindings;
- own the deployment transaction ledger;
- perform exactly-once physical dispatch;
- classify ambiguous physical execution after the destructive boundary.

Public Issue #90 remains the product GitOps command surface for product-tag operations. Public Issue #179 is the architecture/migration audit tracker, not a normal runtime deployment cursor.

## Deployment Controller authority

The private repository owns the active deployment command surface on private Issue #1:

```text
/deploy <target> <vX.Y.Z>
```

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
- canonical private runtime evidence;
- bounded public GitHub Deployment status/history projection.

The private controller must not:

- copy public application source;
- independently create product artifacts;
- own Android product signing policy;
- create or replace Product Releases;
- create a competing product tag;
- rewrite an immutable Product Release asset.

## Runtime identity

Product identity and controller identity are intentionally separate.

```text
product_release
  = exact semantic product tag
  + exact annotated-tag target public source SHA
  + exact immutable Product Release v2 asset contract

runtime_deployment_identity
  = product_release
  + exact controller_revision
```

A controller repair or recovery-policy change therefore does not require rebuilding an unchanged product. Conversely, a new product release does not silently redefine the controller revision that executed it.

`latest`, a mutable branch, public `main` alone, or public Issue #179 alone are never sufficient runtime deployment identity.

## Product Release precedes deployment

The correct authority order is:

```text
protected public main + exact successful Quality
  -> annotated product tag
  -> public signed PRODUCT build
  -> immutable Product Release v2
  -> private /deploy <target> <tag>
  -> private controller admission / observation / possible mutation / verification / recovery
```

A Product Release is an input to deployment. Physical phone acceptance is therefore not a prerequisite for creating the final Product Release.

Historical Item 19/Item 20 evidence remains historical acceptance/development evidence. It does not supply normal Product Release or runtime deployment authority under controller v2.

## Android product and deployment roles

The Android app is not the primary reverse-tunnel owner. The native rooted `first_party_reverse_tunnel` path remains primary. The app is a managed production auxiliary component when topology uses Android `Network.bindSocket()` cellular egress or the app-owned WireGuard compatibility path.

The public PRODUCT plane builds and verifies the exact signed Android APK. The private Deployment Controller decides, from target topology and observed target state, whether that immutable APK must be installed/updated and owns any physical mutation transaction.

Signing secrets used to create the public PRODUCT artifact belong only to the protected public `product-release` environment. Target/device secrets remain private. Signer material or fingerprints are never public Release evidence.

## Evidence authority

There are three different evidence roles and they must not be conflated:

1. **Product evidence** — public Quality, Product Release v2 manifest/provenance/typed digests and GitHub immutability.
2. **Runtime execution truth** — private Deployment Controller durable ledger and terminal classification.
3. **Public deployment projection** — bounded GitHub Deployment status/history for visibility only.

A public GitHub Deployment is not the execution ledger and cannot authorize a second physical dispatch. If public projection fails after a private physical boundary, recovery is based on the private durable ledger and read-only observation.

Sensitive runtime values remain private by design, including raw device identifiers, private target bindings, credentials, private keys and sensitive logs.

## Failure semantics

Authority conflicts fail closed by domain:

- PRODUCT source/build/tag/Release ambiguity -> stop in public product plane;
- controller revision/request/target-state ambiguity before dispatch -> no mutation;
- ambiguity after a durable destructive dispatch boundary -> no blind retry, read-only recovery only;
- Product Release missing or mutable -> private deployment admission rejects it;
- controller cannot bind exact Product Release + exact controller revision -> no mutation;
- public projection failure -> never interpreted as permission to redispatch.

`RECOVERED` never retroactively converts the original deployment attempt into `ACCEPTED`.

## Historical contracts

Older v1 contracts and Item 19/Item 20 artifacts remain in Git history/repository where useful for audit. They are not active Product Release/runtime authority when they conflict with the v2 contracts listed at the top of this document.

No phone, VM or provider mutation authority is granted by this document itself.
