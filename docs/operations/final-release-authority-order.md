# Product Release v2 and deployment authority order

Status: **normative ownership and execution-order contract**  
Canonical PRODUCT repository: `iamaman11/mobile-proxy`  
Deployment Controller repository: `iamaman11/mobile-proxy-production`  
Machine contract: `contracts/operations/product-release-authority-v2.json`  
Canonical product-tag command surface: public Issue #90  
Migration/development audit tracker: public Issue #179  
Runtime deployment command surface: private Issue #1

## Purpose

This document defines the corrected ownership boundary accepted by the Deployment Controller v2 migration.

The public repository owns the PRODUCT:

- application/runtime source;
- public Quality;
- Android and Linux product build;
- Android product signing verification;
- exact annotated semantic-version product tag;
- immutable Product Release assets, manifest, provenance and checksums.

The private repository owns DEPLOYMENT CONTROL:

- `/deploy <target> <vX.Y.Z>` ingress on private Issue #1;
- target admission and serialization;
- target observation;
- deployment State Machine / Transaction Kernel;
- mutation intent, exactly-once destructive dispatch, recovery and quarantine;
- durable canonical execution result/evidence;
- bounded public GitHub Deployment status projection.

Public Issue #179 is a development/migration audit tracker. It is not a runtime execution cursor for normal deployments.

## Core ordering rule

A Product Release is an **input to deployment**, not an output of prior physical phone acceptance.

The accepted order is:

```text
exact protected public main SHA
  -> exact successful Quality push on that same main SHA
  -> owner /release-tag command on public #90
  -> exact annotated vMAJOR.MINOR.PATCH tag bound to that SHA
  -> tag Quality succeeds
  -> public PRODUCT workflow builds Linux + exact signed Android APK from tag target SHA
  -> release-manifest.json format v2
  -> provenance.json format v2
  -> SHA256SUMS over the exact bundle
  -> create GitHub Release as draft
  -> attach and verify the exact five Release v2 assets
  -> publish the verified draft
  -> verify GitHub Release immutable == true
  -> verify GitHub Release/asset integrity
  -> only now may private /deploy <target> <tag> consume that Product Release
  -> private controller observes / admits / mutates / verifies / recovers / classifies target
  -> public GitHub Deployment receives bounded status/history projection only
```

The old ordering

```text
phone/signing migration -> physical Item 20 acceptance -> final tag -> Release
```

is superseded for Product Release authority. Physical acceptance belongs to deployment/runtime control after the immutable Product Release exists.

## Product identity

Product Release identity is:

```text
product_release = exact semantic tag + exact annotated-tag target source SHA + exact immutable Release v2 asset set
```

For one Product Release:

```text
protected main SHA selected for tagging
  == annotated tag target SHA
  == source SHA recorded in release-manifest.json
  == source SHA recorded in provenance.json
```

The private Deployment Controller revision is deliberately **not** part of Product Release identity. Runtime deployment identity is the pair:

```text
product_release + exact controller_revision
```

This permits controller fixes and recovery logic to evolve without rebuilding an unchanged product, while still preserving exact execution provenance.

## Product tag authority

The public `.github/workflows/release-tag.yml` is the only automated final product-tag creator.

It must require:

1. repository-owner command `/release-tag vX.Y.Z <full_sha>` on public Issue #90;
2. exact 40-character lowercase SHA;
3. requested SHA equals the exact current protected public `main` SHA;
4. at least one completed successful `Quality` push on `main` for that exact SHA;
5. Cargo/Android version contract matches the requested semantic version;
6. requested tag does not already exist;
7. created tag object is annotated and resolves exactly to the requested SHA.

It must **not** require:

- Item 20 / public #135 physical acceptance completion;
- public #115 phone signing-generation migration completion;
- `final_accepted_candidate_sha` from a physical tracker;
- phone access;
- deployment execution;
- provider mutation.

Creating the product tag authorizes only Product Release publication from that exact source. It does not authorize target mutation.

## Product Release v2 publication

The public `.github/workflows/release.yml` owns the Product Release build/publication plane.

The protected public GitHub Environment is `product-release`.

The workflow must fail closed before Release creation unless repository immutable Releases are enabled. The read-only settings check uses a separately scoped secret `PRODUCT_RELEASE_SETTINGS_TOKEN` that requires only repository **Administration: read**. Normal Release publication continues to use the workflow `GITHUB_TOKEN` with bounded `contents: write` permission.

The public environment also supplies the existing Android product signing secrets:

- `ANDROID_RELEASE_KEYSTORE_B64`;
- `ANDROID_RELEASE_KEYSTORE_PASSWORD`;
- `ANDROID_RELEASE_KEY_ALIAS`;
- `ANDROID_RELEASE_KEY_PASSWORD`.

Secret values, signing material and signer fingerprints are never written to public Release evidence.

### Required exact Release v2 assets

For tag `vX.Y.Z` the published Release has exactly five assets:

```text
mobile-proxy-linux-x86_64-vX.Y.Z.tar.gz
mobile-proxy-android-vX.Y.Z.apk
release-manifest.json
provenance.json
SHA256SUMS
```

`release-manifest.json` format v2 records the exact source SHA and artifact SHA-256 values. The Android entry also records `com.example.mobileproxy`, `versionName` and `versionCode`.

`provenance.json` format v2 records the same exact source/tag identity, builder/workflow identity, and artifact SHA-256 values without secret/signing/phone fields.

`SHA256SUMS` covers Linux, Android APK, manifest and provenance. The checksum file does not recursively hash itself.

### Draft-first immutability boundary

Publication is deliberately two-phase:

1. create/reuse one exact draft;
2. verify its complete asset set and remote SHA-256 digests against local bytes;
3. only then publish it.

Once published, the workflow must require `immutable == true` from the exact GitHub Release response. A mutable published Release is never accepted as deployable.

An exact already-published immutable Release is an idempotent success only when every expected asset and digest still matches the locally rebuilt exact bundle. An existing mismatched draft, mismatched published Release, duplicate exact-tag Release, extra asset or missing asset fails closed. The workflow never overwrites or replaces Release assets.

GitHub immutable Release verification and local asset verification are additional postconditions, not substitutes for the manifest/digest contract.

## Deployment authority begins after Product Release

The first runtime mutation authority appears only in the private Deployment Controller after it resolves an exact immutable Product Release v2.

The active command surface is:

```text
/deploy <target> <vX.Y.Z>
```

The controller must resolve the exact tag/Release; `latest` or any moving alias is forbidden. The controller also binds the exact controller revision that is executing the request.

A valid Product Release does not imply deployment success. It only supplies immutable product input. Target state, target admission, destructive dispatch, postcondition verification, recovery, `UNKNOWN`, `RECOVERED`, `QUARANTINED` and terminal execution classification remain private controller responsibilities.

`RECOVERED` never retroactively means the original deployment was `ACCEPTED`.

## Public GitHub Deployment projection

A public GitHub Deployment may be created/updated as bounded status/history projection after private controller admission. It is not the canonical transaction ledger and does not authorize execution.

If public projection is unavailable or delayed, the private durable controller ledger remains canonical. Projection failure must not cause a second physical dispatch.

## Forbidden ownership regressions

The public PRODUCT workflows must never:

- access the phone;
- invoke ADB;
- acquire target-global deployment locks;
- perform target mutation or recovery;
- mutate provider/VM resources;
- dispatch the private controller;
- derive deployability from a mutable Release;
- create a directly-published Release before verifying all draft assets;
- replace assets on an existing Release;
- use `latest` as deployment identity.

The private controller must never become the canonical source/build/signing owner for PRODUCT artifacts.

Historical public physical-kernel work may remain as immutable history, but active deployment-control ownership belongs private. Product code/runtime logic remains public.

## Failure semantics

Any ambiguity fails closed:

- requested tag SHA differs from exact protected main -> reject tag creation;
- exact source SHA lacks successful main Quality -> reject tag creation/publication;
- tag is lightweight, ambiguous or resolves to a different SHA -> reject;
- public Android signing verification fails -> no Release creation;
- immutable Releases setting cannot be positively proven enabled -> no Release creation;
- draft asset set/digest differs -> do not publish;
- published Release is mutable -> not deployable;
- Release v2 lacks Linux/APK/manifest/provenance/checksums -> not deployable;
- private controller cannot bind exact Product Release + controller revision -> no target mutation;
- execution outcome becomes ambiguous after destructive boundary -> read-only recovery, never blind retry.

The recovery path for product publication is idempotent verification/reuse of the exact matching draft or immutable Release. The recovery path for deployment remains the private controller State Machine. These are separate trust domains and must not be collapsed.
