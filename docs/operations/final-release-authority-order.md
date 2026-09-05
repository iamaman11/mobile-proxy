# Product Release v2 and deployment authority order

Status: **normative ownership and execution-order contract**  
Canonical PRODUCT repository: `iamaman11/mobile-proxy`  
Deployment Controller repository: `iamaman11/mobile-proxy-production`  
Machine contract: `contracts/operations/product-release-authority-v2.json`  
Canonical product-tag command surface: public Issue #90  
Migration/development audit tracker: public Issue #179  
Runtime deployment command surface: Deployment Controller Issue #1

## Purpose

This document defines the corrected ownership boundary accepted by the Deployment Controller v2 migration. Both repositories are public; sensitive target bindings, secrets and runtime values remain private operational data.

The PRODUCT repository owns:

- application/runtime source;
- public Quality;
- Android and Linux product build;
- Android product signing verification;
- exact annotated semantic-version product tag;
- immutable Product Release assets, manifest, provenance and typed content digests.

The Deployment Controller repository owns DEPLOYMENT CONTROL:

- `/deploy <target> <vX.Y.Z>` ingress on controller Issue #1;
- target admission and serialization;
- target observation;
- deployment State Machine / Transaction Kernel;
- mutation intent, exactly-once destructive dispatch, recovery and quarantine;
- durable canonical execution result/evidence;
- bounded public GitHub Deployment status projection.

Public Issue #179 is the engineering/migration execution cursor while the hardening program is active. It is not runtime deployment identity for normal deployments.

## Core ordering rule

A Product Release is an **input to deployment**, not an output of prior physical phone acceptance.

The accepted order is:

```text
exact protected PRODUCT main SHA
  -> exact successful Quality push on that same main SHA
  -> exact successful `Product Release prerequisites` push on that same main SHA
  -> owner /release-tag command on public #90
  -> exact annotated vMAJOR.MINOR.PATCH tag bound to that SHA
  -> tag Quality succeeds
  -> PRODUCT workflow builds Linux + exact signed Android APK from tag target SHA
  -> release-manifest.json format v2
  -> provenance.json format v2
  -> artifact-digests.json with typed Product Release content digests
  -> create GitHub Release as draft
  -> attach and verify the exact five Release v2 assets
  -> compare every draft asset against local exact bytes
  -> publish the verified draft
  -> verify GitHub Release immutable == true
  -> verify GitHub Release/asset integrity with GitHub-native verification
  -> only now may /deploy <target> <tag> consume that Product Release
  -> Deployment Controller observes / admits / mutates / verifies / recovers / classifies target
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

The Deployment Controller revision is deliberately **not** part of Product Release identity. Runtime deployment identity is the pair:

```text
product_release + exact controller_revision
```

This permits controller fixes and recovery logic to evolve without rebuilding an unchanged product, while still preserving exact execution provenance.

## Product tag authority

The PRODUCT `.github/workflows/release-tag.yml` is the only automated final product-tag creator.

It must require:

1. repository-owner command `/release-tag vX.Y.Z <full_sha>` on public Issue #90;
2. exact 40-character lowercase SHA;
3. requested SHA equals the exact current protected PRODUCT `main` SHA;
4. at least one completed successful `Quality` push on `main` for that exact SHA;
5. at least one completed successful `Product Release prerequisites` push on `main` for that exact SHA;
6. Cargo/Android version contract matches the requested semantic version;
7. requested tag does not already exist;
8. created tag object is annotated and resolves exactly to the requested SHA.

It must **not** require:

- Item 20 / public #135 physical acceptance completion;
- public #115 phone signing-generation migration completion;
- `final_accepted_candidate_sha` from a physical tracker;
- phone access;
- deployment execution;
- provider mutation.

Creating the product tag authorizes only Product Release publication from that exact source. It does not authorize target mutation.

## Product Release prerequisite proof

The single PRODUCT `.github/workflows/product-release-prerequisites.yml` is the hosted configuration/admission proof that runs for protected `main`.

It must prove that the `product-release` environment exists with the accepted deployment-ref policy, that repository immutable Releases are enabled, and that the environment exposes exactly these required secret **names**:

- `PRODUCT_RELEASE_SETTINGS_TOKEN`;
- `ANDROID_RELEASE_KEYSTORE_B64`;
- `ANDROID_RELEASE_KEYSTORE_PASSWORD`;
- `ANDROID_RELEASE_KEY_ALIAS`;
- `ANDROID_RELEASE_KEY_PASSWORD`.

The prerequisite proof uses only `PRODUCT_RELEASE_SETTINGS_TOKEN` for read-only GitHub API access. That token requires repository **Administration: read + Environments: read**. Android signing secret values are not loaded by the prerequisite proof; the signing values remain available only to the actual signed Product Release build/publication path.

A prerequisite run is tag-admissible only when it is a completed successful `push` run on `main` whose `head_sha` exactly equals the requested product-tag target SHA. Advancing `main` therefore invalidates older prerequisite evidence automatically.

## Product Release v2 publication

The PRODUCT `.github/workflows/release.yml` owns the Product Release build/publication plane.

The protected GitHub Environment is `product-release`.

The workflow must fail closed before Release creation unless repository immutable Releases are enabled. The read-only settings check uses a separately scoped secret `PRODUCT_RELEASE_SETTINGS_TOKEN` requiring repository **Administration: read + Environments: read**. Normal Release publication continues to use the workflow `GITHUB_TOKEN` with bounded `contents: write` permission.

The environment also supplies the existing Android product signing secrets:

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
artifact-digests.json
```

`release-manifest.json` format v2 records the exact source SHA and typed content digest for each product artifact. The Android entry also records `com.example.mobileproxy`, `versionName` and `versionCode`.

`provenance.json` format v2 records the same exact source/tag identity, builder/workflow identity and typed product-artifact digests without secret/signing/phone fields.

`artifact-digests.json` uses the canonical first-party digest policy:

```text
algorithm: blake3-256
domain: mobile-proxy/product-release-asset/v2
```

Its typed digests cover the Linux archive, Android APK, `release-manifest.json` and `provenance.json`. The digest-set file does not hash itself. First-party release code must not introduce a separate direct cryptographic primitive; all content identity goes through the typed foundation `ContentDigest` contract with domain separation.

GitHub may expose its own platform digest for uploaded Release assets. That external field is validated as GitHub metadata, but first-party code does not reimplement GitHub's hashing algorithm. For a draft, remote assets are downloaded through the authenticated asset API and compared to local files as exact bytes before publication. After publication, GitHub-native immutable Release and asset verification supplies the independent platform-integrity postcondition.

### Draft-first immutability boundary

Publication is deliberately two-phase:

1. create/reuse one exact draft;
2. verify its complete asset set and local typed-digest contract;
3. download each draft asset and compare it to the local asset as exact bytes;
4. only then publish it.

Once published, the workflow must require `immutable == true` from the exact GitHub Release response. A mutable published Release is never accepted as deployable.

An exact already-published immutable Release is an idempotent success only when every expected local typed digest is valid and GitHub-native Release/asset verification succeeds against the locally rebuilt bundle. An existing mismatched draft, mismatched published Release, duplicate exact-tag Release, extra asset or missing asset fails closed. The workflow never overwrites or replaces Release assets.

GitHub immutable Release verification, exact-byte draft comparison and typed content identity are independent postconditions; none is silently substituted for another.

## Deployment authority begins after Product Release

The first runtime mutation authority appears only in the Deployment Controller after it resolves an exact immutable Product Release v2.

The active command surface is:

```text
/deploy <target> <vX.Y.Z>
```

The controller must resolve the exact tag/Release; `latest` or any moving alias is forbidden. The controller also binds the exact controller revision that is executing the request.

A valid Product Release does not imply deployment success. It only supplies immutable product input. Target state, target admission, destructive dispatch, postcondition verification, recovery, `UNKNOWN`, `RECOVERED`, `QUARANTINED` and terminal execution classification remain Deployment Controller responsibilities.

`RECOVERED` never retroactively means the original deployment was `ACCEPTED`.

## Public GitHub Deployment projection

A public GitHub Deployment may be created/updated as bounded status/history projection after controller admission. It is not the canonical transaction ledger and does not authorize execution.

If public projection is unavailable or delayed, the durable controller ledger remains canonical. Projection failure must not cause a second physical dispatch.

## Confidentiality boundary

Controller repository visibility does not authorize publishing sensitive operational state. Secret values, target bindings, raw device identifiers, private keys, credentials, sensitive rendered config and unsafe raw production/ADB logs remain private. Public runtime evidence is bounded to the minimum non-sensitive classifications/digests/booleans required by the evidence contract.

## Forbidden ownership regressions

The PRODUCT workflows must never:

- access the phone;
- invoke ADB;
- acquire target-global deployment locks;
- perform target mutation or recovery;
- mutate provider/VM resources;
- dispatch the controller;
- derive deployability from a mutable Release;
- create a directly-published Release before verifying all draft assets;
- replace assets on an existing Release;
- bypass the canonical typed digest foundation with a first-party direct digest primitive;
- use `latest` as deployment identity.
