# Product Release v2 and deployment authority order

Status: **normative ownership and execution-order contract**  
Canonical PRODUCT repository: `iamaman11/mobile-proxy`  
Deployment Controller repository: `iamaman11/mobile-proxy-production`  
Machine contract: `contracts/operations/product-release-authority-v2.json`  
Canonical release-readiness/tag command surface: public Issue #90  
Migration/development audit tracker: public Issue #179  
Runtime deployment command surface: private Issue #1

## Purpose

The public repository owns PRODUCT source, Quality, product build/signing verification, annotated tags and immutable Product Release v2. The private repository owns deployment admission, target serialization/observation/adapters, the Deployment State Machine / Transaction Kernel, durable mutation intent, exactly-once destructive dispatch, postconditions, recovery/quarantine and canonical runtime evidence.

Public Issue #179 is a migration/development audit tracker, not a normal runtime cursor.

## Core ordering rule

A Product Release is an **input to deployment**, not an output of prior physical phone acceptance.

The accepted order is:

```text
exact protected public main SHA
  -> exact successful Quality push on that same main SHA
  -> owner /release-readiness on public #90
  -> read-only product-release environment/configuration proof on that same exact protected main SHA
  -> owner /release-tag vMAJOR.MINOR.PATCH <same-sha> on public #90
  -> exact successful same-SHA Product Release Readiness run is revalidated
  -> exact annotated vMAJOR.MINOR.PATCH tag bound to that SHA
  -> tag Quality succeeds
  -> public PRODUCT workflow builds Linux + exact signed Android APK from tag target SHA
  -> release-manifest.json format v2
  -> provenance.json format v2
  -> artifact-digests.json with typed Product Release content digests
  -> create GitHub Release as draft
  -> attach and verify the exact five Release v2 assets
  -> compare every draft asset against local exact bytes
  -> publish the verified draft
  -> verify GitHub Release immutable == true
  -> verify GitHub Release/asset integrity with GitHub-native verification
  -> only now may private /deploy <target> <tag> consume that Product Release
  -> private controller observes / admits / mutates / verifies / recovers / classifies target
  -> public GitHub Deployment receives bounded status/history projection only
```

The old ordering `phone/signing migration -> physical Item 20 acceptance -> final tag -> Release` is superseded for Product Release authority. Physical acceptance belongs to deployment/runtime control after the immutable Product Release exists.

## Read-only Product Release readiness

`.github/workflows/product-release-readiness.yml` is a non-mutating configuration proof. Only the repository owner may trigger it with exact command `/release-readiness` on public Issue #90.

The readiness run is bound to the current exact protected `main` SHA and requires an exact successful `Quality` push for that same SHA. It targets the `product-release` environment and proves all of the following without creating a tag or Release:

- the `product-release` environment resolves exactly;
- the environment has protection rules and a restrictive deployment branch policy;
- the environment exposes exactly the approved secret **names**;
- repository immutable Releases are enabled;
- no phone, provider, deployment, tag or Release mutation occurs.

The approved environment secret-name set is exactly:

```text
PRODUCT_RELEASE_SETTINGS_TOKEN
ANDROID_RELEASE_KEYSTORE_B64
ANDROID_RELEASE_KEYSTORE_PASSWORD
ANDROID_RELEASE_KEY_ALIAS
ANDROID_RELEASE_KEY_PASSWORD
```

The readiness workflow lists environment secret names without reading signing secret values. It does not inject the four Android signing secrets into the job. Only `PRODUCT_RELEASE_SETTINGS_TOKEN` is consumed for read-only GitHub API calls.

To support both readiness checks with one bounded token, `PRODUCT_RELEASE_SETTINGS_TOKEN` requires exactly these repository permissions:

- **Administration: read** — prove repository immutable Releases are enabled;
- **Environments: read** — list the `product-release` environment secret names without revealing encrypted values.

No write permission is required for that token.

A successful readiness run is configuration evidence only. It grants no Product tag, Release or target-mutation authority. `.github/workflows/release-tag.yml` independently requires an eligible successful `Product Release Readiness` issue-comment run whose `head_sha` equals the requested tag target and current protected `main`. Therefore a protected-main advance makes prior readiness evidence stale automatically.

## Product identity

Product Release identity is:

```text
product_release = exact semantic tag + exact annotated-tag target source SHA + exact immutable Release v2 asset set
```

For one Product Release, the protected main SHA selected for tagging equals the annotated tag target SHA and the source SHA recorded in `release-manifest.json` and `provenance.json`.

The private Deployment Controller revision is deliberately **not** part of Product Release identity. Runtime deployment identity is:

```text
product_release + exact controller_revision
```

This permits controller fixes/recovery logic to evolve without rebuilding unchanged product bytes while retaining exact execution provenance.

## Product tag authority

`.github/workflows/release-tag.yml` is the only automated final product-tag creator. It must require:

1. repository-owner command `/release-tag vX.Y.Z <full_sha>` on public Issue #90;
2. exact 40-character lowercase SHA;
3. requested SHA equals the exact current protected public `main` SHA;
4. at least one completed successful `Quality` push on `main` for that exact SHA;
5. at least one completed successful `Product Release Readiness` issue-comment run for that same exact SHA;
6. Cargo/Android version contract matches the requested semantic version;
7. requested tag does not already exist;
8. created tag object is annotated and resolves exactly to the requested SHA.

It must not require Item 20/#135 physical acceptance, #115 signing-generation completion, `final_accepted_candidate_sha`, phone access, deployment execution or provider mutation.

Creating the Product tag authorizes only Product Release publication from that exact source. It does not authorize target mutation.

## Product Release v2 publication

`.github/workflows/release.yml` owns the public Product Release build/publication plane and executes in the protected `product-release` environment.

Before Release creation it independently proves repository immutable Releases are enabled. Android signing secrets are used only by the product build/signing workflow. Secret values, signing material and signer fingerprints are never written to public Release evidence.

For tag `vX.Y.Z`, the exact Release v2 assets are:

```text
mobile-proxy-linux-x86_64-vX.Y.Z.tar.gz
mobile-proxy-android-vX.Y.Z.apk
release-manifest.json
provenance.json
artifact-digests.json
```

`release-manifest.json` format v2 binds exact source SHA and product artifact metadata. `provenance.json` format v2 binds the same exact source/tag identity and retry-stable builder/workflow identity without phone/signing-secret fields.

`artifact-digests.json` uses the canonical first-party digest policy:

```text
algorithm: blake3-256
domain: mobile-proxy/product-release-asset/v2
```

Typed content identity goes through the foundation `ContentDigest` contract. The digest set covers Linux archive, Android APK, `release-manifest.json` and `provenance.json`; it does not hash itself.

GitHub platform integrity is an independent postcondition. Draft assets are downloaded via the authenticated asset API and compared with local exact bytes before publication. After publication, GitHub-native immutable Release and asset verification is required.

## Draft-first immutability boundary

Publication is deliberately two-phase:

1. create/reuse one exact draft;
2. verify its complete asset set and local typed-digest contract;
3. download each draft asset and compare it to local exact bytes;
4. publish only the verified draft;
5. require the exact published Release response to report `immutable == true`;
6. verify Release and every local asset with GitHub-native verification.

An existing mismatched draft/published Release, duplicate exact-tag Release, missing/extra asset or mutable published Release fails closed. Release assets are never overwritten in recovery.

## Deployment authority begins after Product Release

The first target-mutation authority exists only in the private Deployment Controller after it resolves an exact immutable Product Release v2. Its active command surface is:

```text
/deploy <target> <vX.Y.Z>
```

`latest` or any moving alias is forbidden. A valid Product Release supplies immutable product input only; it does not imply deployment success. Target observation/admission, destructive dispatch, independent postcondition verification, `UNKNOWN`, read-only recovery, `RECOVERED`, quarantine and terminal classification remain private controller responsibilities. `RECOVERED` never retroactively means the original deployment was `ACCEPTED`.

## Public GitHub Deployment projection

A public GitHub Deployment is bounded status/history projection only. The private durable controller ledger remains canonical execution truth. Projection failure must never cause a second destructive dispatch.

## Failure semantics

Any ambiguity fails closed:

- requested tag SHA differs from exact protected main -> reject tag creation;
- exact source SHA lacks successful main Quality -> reject readiness/tag creation;
- exact source SHA lacks successful same-SHA Product Release Readiness -> reject tag creation;
- environment is missing/unprotected or secret-name set differs -> readiness fails and no tag authority exists;
- settings token lacks **Administration: read** or **Environments: read** -> readiness fails;
- immutable Releases cannot be positively proven enabled -> readiness fails, no tag authority exists and no Release creation occurs;
- tag is lightweight/ambiguous/different SHA -> reject;
- Android signing verification fails -> no Release creation;
- typed digest contract fails -> no Release creation/publication;
- draft asset set/bytes differ -> do not publish;
- published Release is mutable -> not deployable;
- private controller cannot bind exact Product Release + controller revision -> no target mutation;
- execution becomes ambiguous after destructive boundary -> read-only recovery, never blind retry.

Product publication recovery and deployment recovery are separate trust domains and must not be collapsed.
