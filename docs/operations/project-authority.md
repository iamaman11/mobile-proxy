# Project authority and execution satellites

## Canonical repository

`https://github.com/iamaman11/mobile-proxy` is the **only canonical repository for project information**.

It is authoritative for product behavior, architecture, active roadmap/scope, contracts, desired configuration, release identity, workflow/policy logic, acceptance policy and safe deployment evidence. Chat history, local notes, provider consoles, workstation state and satellite repositories may supply observations, but they never override the canonical repository.

If external or satellite state conflicts with the canonical repository, production fails closed. Reconcile desired state in `iamaman11/mobile-proxy` first through protected `main` and normal pull-request delivery.

The canonical GitOps tracker is #90. Active delivery status is owned by `docs/PRODUCTION_BASELINE_PLAN.md`; machine-readable execution state is owned by `contracts/operations/production-topology-v1.json` and `contracts/operations/github-control-plane-v1.json`. Final release ordering is protected by `contracts/operations/final-release-authority-v1.json`.

## One project, two trust zones

`iamaman11/mobile-proxy-production` is not a second project and not a second source of truth. It is a private **execution satellite** required because physical-phone secrets and the `android-production` self-hosted runner must stay outside the public fork/PR trust boundary.

| Boundary | Authority | Purpose |
| --- | --- | --- |
| `iamaman11/mobile-proxy` | canonical | source, docs, contracts, CI, releases, reusable implementation/workflow policy, Vultr orchestration, safe evidence index |
| `acceptance-vultr` | bounded external credential/runtime boundary | GitHub-hosted pre-release acceptance after exact canonical authority; never final production authority |
| `production-vultr` | bounded external credential/runtime boundary | tag-only final production deployment after final release authority |
| `iamaman11/mobile-proxy-production` | execution-only | thin caller/shim, private secrets, phone runner access, bounded private execution evidence |
| `android-production` | execution-only | registered physical phone access; never project policy or provider authority |

The satellite must not independently define architecture, roadmap, release policy, provider desired state, acceptance rules, evidence schemas or product code. Where GitHub requires private YAML, it should remain a minimal caller/wrapper that pins and invokes canonical public implementation by exact immutable SHA or verified release artifact. Policy decisions belong in the public repository.

## Cross-repository and final release identity

Final production never means `latest` and never trusts a mutable branch. For the active 10/10 Item 20 -> Item 21 chain:

```text
candidate_sha
  == control_plane_sha
  == exact protected public main SHA during the acceptance window
  == final_accepted_candidate_sha
  == final annotated tag target SHA
  == source SHA of published artifacts
```

`candidate_sha` and `control_plane_sha` remain useful typed boundary fields, but their values must be exactly equal. A protected-main advance invalidates stale candidate acceptance and requires fresh candidate-specific evidence before release.

Historical Item 19 candidate `d151dbdd156279e32a5361d304c90f996bd2d565` remains immutable historical provider proof only. It does not define the active Item 20 candidate and its terminal ownership intent is not reusable.

The final immutable release tuple contains the canonical repository, annotated semantic-version tag, full accepted Git SHA, artifact names/digests, provenance identity and deployment ID `mobile-proxy-<tag>-<first12sha>`.

Android version metadata used by #162 is not final release authority. A protected candidate may carry workspace/Android `0.1.4` and produce a retained signed migration artifact while final `v0.1.4` remains absent. #162 consumes exact public SHA plus retained signed-candidate evidence, not a final tag.

## Android production role

The Android app is not the primary reverse-tunnel owner. The native rooted `first_party_reverse_tunnel` path remains primary. The app is a managed production auxiliary component when topology uses Android `Network.bindSocket()` cellular egress or the app-owned WireGuard compatibility path.

A topology that does not consume an app capability does not require APK installation. A topology that does must bind exact package/version/signer-match/install state and retained signed artifact provenance to the same accepted public SHA. Signing continuity and managed migration/update are production lifecycle requirements for that path.

## Control and evidence flow

Architecture/policy reconciliation and software delivery:

```text
canonical Issue / branch / PR
  -> exact PR-head Quality
  -> protected main merge
  -> exact post-merge main Quality
  -> exact protected main selected as active candidate/control-plane SHA
```

Pre-release candidate evidence then uses that same SHA for software artifacts, acceptance authority, Vultr read-only preflight and any fresh provider proof required by Item 20.

The one-time Android signing-generation migration is a bounded pre-Item20 prerequisite:

```text
same exact canonical SHA
  -> off-phone signing proof + retained signed Android candidate
  -> #162 serialized registered-phone migration
  -> package/version/signer/runtime + rollback proof
  -> #115 completed only when its acceptance criteria pass
```

That path creates no final tag, GitHub Release, provider authority or production promotion.

Only after Item 20 physical acceptance, recovery matrix and soak complete on that same SHA may the final chain continue:

```text
completed Item 20 + final_accepted_candidate_sha
  -> verify exact protected main still equals accepted candidate
  -> owner release-tag command on #90
  -> annotated v* tag at accepted candidate
  -> exact tag Quality
  -> release artifacts/provenance from exact tag target SHA
       |-> private execution verifies exact release tuple before phone work
       +-> production-vultr verifies exact release tuple before VM work
```

`iamaman11/mobile-proxy-production#1` is private command/audit transport only. Safe canonical result references return to public tracking; sensitive raw evidence remains private.

## External state that cannot live in canonical Git

The following remain external by design:

- secret values/private keys;
- live runner status;
- physical USB/ADB state;
- mutable provider identifiers/bindings where publication is unsafe;
- raw credential-bearing or device-sensitive logs.

The canonical repository owns the schema, invariant, allowed location and safe evidence format. External systems own only runtime values.

## Stable checkpoint semantics

Operational moving SHA/run status must not be hand-maintained here as “current authority.” Exact execution state is resolved from protected GitHub state, machine contracts and dedicated evidence records at execution time.

Stable facts:

- public canonical authority and protected PR/Quality delivery are required;
- private phone repository/runner remain execution-only;
- Item 19 provider proof is historical-complete and immutable;
- Item 20 requires a fresh same-SHA acceptance window on exact protected main;
- #115/#162 remain hard gates for applicable Android mutation/signing lifecycle;
- no final `v0.1.4` release authority exists before same-SHA Item 20 acceptance;
- legacy GCP/workstation/manual SSH/raw ADB/provider CLI paths are not authorized shortcuts.

This document grants no VM, endpoint-handoff or phone mutation authority by itself.
