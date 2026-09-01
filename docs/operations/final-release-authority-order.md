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

- Android release **version metadata** (`versionName=0.1.4`, `versionCode=1004`, workspace version `0.1.4`) may exist on a protected pre-release SHA so an exact signed migration candidate can be built and verified;
- final **release authority** (`v0.1.4` annotated tag, GitHub Release, and any production-promotion authority derived from that tag) does not exist until Item 20 physical acceptance has completed on that same exact SHA.

Version metadata is not release authority.

## One release identity

The 10/10 release chain has one software identity:

```text
accepted candidate SHA == exact protected `main` SHA == final tag target SHA == source SHA of published artifacts
```

There is no independent final-release control-plane SHA. `candidate_sha` and `control_plane_sha` may remain separate typed fields where useful for boundary validation, but Item 20 admission and final release require their values to be exactly equal. If protected `main` advances after candidate admission or physical acceptance, the acceptance window is stale and must be repeated for the new exact SHA before a final tag can be created.

Historical Item 19 candidate `d151dbdd156279e32a5361d304c90f996bd2d565` remains immutable historical provider-lifecycle evidence only. It is not active Item 20 candidate authority and is not eligible for the final release unless it independently became the exact current protected-main candidate and all candidate-specific evidence were regenerated, which is not the current plan.

## Required order

The only accepted order is:

```text
exact protected canonical main SHA selected as candidate
  -> exact main Quality success
  -> fresh software release-candidate evidence for that SHA
  -> fresh acceptance authority and Vultr read-only preflight for that SHA
  -> fresh provider proof required by Item 20 for that SHA
  -> off-phone production signing proof
  -> exact signed Android 0.1.4 candidate + typed digest/provenance retention
  -> #162 narrow signing-generation migration on the registered phone
  -> verify new signing generation / bounded local health
  -> close #115 completed when its acceptance criteria are actually satisfied
  -> Item 20 fresh JIT acceptance session + physical A-F acceptance on the same SHA
  -> recovery/repetition matrix and soak on the same SHA
  -> close #135 completed and record final_accepted_candidate_sha
  -> require protected main still equals that accepted candidate
  -> owner command on canonical #90
  -> annotated v0.1.4 tag at that exact accepted SHA
  -> exact tag Quality success
  -> GitHub Release publication from that exact tag target SHA
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

Item 20 remains the physical acceptance gate. A completed #162 migration only establishes the Android signing generation required to make the Item 20 phone workflow safe; it does not itself accept the complete product release.

When Item 20 completes, #135 must be closed with state reason `completed` and its canonical body must contain exactly one line of the form:

```text
final_accepted_candidate_sha: <40 lowercase hexadecimal characters>
```

That marker is not populated early. It is written only at Item 20 closeout and identifies the exact candidate that completed the same-SHA software, provider, phone, recovery and soak acceptance window.

The release-tag workflow must independently require:

1. owner command `/release-tag vX.Y.Z <sha>` on canonical tracker #90;
2. #115 closed `completed`;
3. #135 closed `completed`;
4. exactly one `final_accepted_candidate_sha` in #135 and it equals the requested SHA;
5. exact protected `main` still resolves to that SHA, not merely an ancestor containing it;
6. an exact successful `Quality` push on `main` for that SHA;
7. the Git/Cargo/Android release-version contract matches the requested semantic version;
8. the tag does not already exist;
9. the created tag object is annotated and resolves to the exact requested SHA.

Only the successful `v*` tag Quality run may trigger normal release publication. Release publication must build or package from the exact tag target SHA and record that exact SHA in its release manifest/provenance. Rebuilding from another branch/control-plane revision is forbidden. Reusing already accepted immutable artifacts is stronger when their digest/provenance is verified, but any published artifact must still be provably bound to the same accepted source SHA.

## Evidence and trust zones

The public repository remains the only architecture, policy, roadmap and release authority. The private `mobile-proxy-production` repository remains execution-only.

The signing-generation migration may retain private APK artifacts and bounded evidence, but private retention does not create public release authority. Conversely, the later public `v0.1.4` tag does not retroactively authorize a migration that did not already pass its exact SHA/build/device gates.

No secret, signer fingerprint, device identifier, runner machine name, provider identifier or plaintext transport endpoint is added to this ordering contract or to public closeout evidence.

## Failure semantics

Any mismatch in order fails closed:

- final tag before Item 20 completion -> reject;
- #162 migration requiring or discovering a final `v0.1.4` tag -> reject;
- missing/ambiguous `final_accepted_candidate_sha` -> reject;
- protected `main` advanced after accepted evidence -> reject and re-run candidate-specific acceptance;
- release command from #162 rather than #90 -> reject;
- requested release SHA without exact successful main Quality -> reject;
- final tag target other than accepted candidate -> reject;
- published artifact source SHA other than final tag target -> reject;
- migration build and migration caller from different private revisions -> reject.

The fix for an ordering failure is always to reconcile canonical Git/contracts first. Manual tagging, manual ADB, manual provider control, or a private-repository policy override is not an accepted recovery path.
