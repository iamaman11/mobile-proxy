# Android signing migration and final release authority order

Status: **normative execution-order clarification**  
Canonical repository: `iamaman11/mobile-proxy`  
Machine contract: `contracts/operations/final-release-authority-v1.json`  
Android signing gate: #115  
Signing-generation migration tracker: #162  
Physical acceptance tracker: #135  
Canonical GitOps tracker: #90

## Purpose

This document resolves the boundary between the one-time Android signing-generation migration and the later final semantic release. It does not create a new roadmap stage and does not supersede `docs/PRODUCTION_BASELINE_PLAN.md`; it makes the already-required Item 20 -> Item 21 ordering explicit and machine-enforceable.

The critical distinction is:

- Android release **version metadata** (`versionName=0.1.4`, `versionCode=1004`, workspace version `0.1.4`) may exist on a protected pre-release control-plane SHA so an exact signed migration candidate can be built and verified;
- final **release authority** (`v0.1.4` annotated tag, GitHub Release, and any production-promotion authority derived from that tag) does not exist until Item 20 physical acceptance has completed.

Version metadata is not release authority.

## Required order

The only accepted order is:

```text
protected canonical SHA
  -> exact main Quality success
  -> off-phone production signing proof
  -> exact signed Android 0.1.4 candidate + typed digest/provenance retention
  -> #162 narrow signing-generation migration on the registered phone
  -> verify new signing generation / bounded local health
  -> close #115 completed when its acceptance criteria are actually satisfied
  -> Item 20 fresh JIT acceptance session + physical A-F acceptance
  -> close #135 completed and record final_release_control_plane_sha
  -> owner command on canonical #90
  -> annotated v0.1.4 tag at that exact recorded SHA
  -> exact tag Quality success
  -> GitHub Release publication
  -> later production promotion
```

A final `v*` tag is therefore an **output** of successful Item 20, never an input to #162.

## #162 authority

#162 is a narrowly authorized destructive migration from the unrecoverable historical Android signer to the already-proven private production signing identity.

Its authority is bounded to an exact canonical SHA plus a successful retained signed-candidate build from that same SHA. The migration may retain the currently installed old APK, uninstall the old package, install the exact verified 0.1.4 APK, perform the bounded runtime-supervisor reprovisioning already defined by the phone GitOps contract, and automatically restore the retained old APK if the new generation cannot pass the required post-install gate.

#162 does **not** authorize:

- creation of `v0.1.4` or any other final `v*` tag;
- GitHub Release publication;
- Item 20 provider lifecycle or endpoint handoff;
- unrelated phone/network mutation;
- production promotion.

The private execution satellite must fail closed if a final `v0.1.4` tag already exists before this migration. Such a tag would indicate that the required release ordering has been violated and must be reconciled in canonical Git first.

## Item 20 and final release authority

Item 20 remains the physical acceptance gate. A completed #162 migration only establishes the new Android signing generation required to make the Item 20 phone workflow safe; it does not itself accept the complete product release.

When Item 20 completes, #135 must be closed with state reason `completed` and its canonical body must contain exactly one line of the form:

```text
final_release_control_plane_sha: <40 lowercase hexadecimal characters>
```

That marker is not populated early. It is written only at Item 20 closeout and identifies the exact protected control-plane revision from the successful physical acceptance window that is eligible for Item 21 final release creation.

The release-tag workflow must independently require:

1. owner command `/release-tag vX.Y.Z <sha>` on canonical tracker #90;
2. #115 closed `completed`;
3. #135 closed `completed`;
4. `final_release_control_plane_sha` in #135 exactly equals the requested SHA;
5. an exact successful `Quality` push on `main` for that SHA;
6. the SHA is still in canonical `main` history;
7. the Git/Cargo/Android release-version contract matches the requested semantic version;
8. the tag does not already exist;
9. the created tag object is annotated and resolves to the exact requested SHA.

Only the successful `v*` tag Quality run may trigger normal release publication.

## Evidence and trust zones

The public repository remains the only architecture, policy, roadmap and release authority. The private `mobile-proxy-production` repository remains execution-only.

The signing-generation migration may retain private APK artifacts and bounded evidence, but private retention does not create public release authority. Conversely, the later public `v0.1.4` tag does not retroactively authorize a migration that did not already pass its exact SHA/build/device gates.

No secret, signer fingerprint, device identifier, runner machine name, provider identifier or plaintext transport endpoint is added to this ordering contract or to public closeout evidence.

## Failure semantics

Any mismatch in order fails closed:

- final tag before Item 20 completion -> reject;
- #162 migration requiring or discovering a final `v0.1.4` tag -> reject;
- missing/ambiguous Item 20 release SHA marker -> reject;
- release command from #162 rather than #90 -> reject;
- requested release SHA without exact successful main Quality -> reject;
- migration build and migration caller from different private revisions -> reject.

The fix for an ordering failure is always to reconcile canonical Git/contracts first. Manual tagging, manual ADB, manual provider control, or a private-repository policy override is not an accepted recovery path.
