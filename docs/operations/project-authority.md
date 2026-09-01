# Project authority and execution satellites

## Canonical repository

`https://github.com/iamaman11/mobile-proxy` is the **only canonical repository for project information**.

It is authoritative for product behavior, architecture, roadmap/scope decisions, contracts, desired
configuration, release identity, workflow logic, acceptance policy and safe deployment evidence.
Chat history, local notes, provider consoles, workstation state and satellite repositories may supply
observations, but they never override the canonical repository.

If any external or satellite state conflicts with the canonical repository, production must fail
closed. Reconcile the decision or desired state in `iamaman11/mobile-proxy` first, through the normal
protected-`main` pull-request process.

The canonical GitOps architecture/status tracker is `iamaman11/mobile-proxy#90`. Active delivery
status is owned by `docs/PRODUCTION_BASELINE_PLAN.md`, and exact machine-readable execution state is
owned by `contracts/operations/production-topology-v1.json` and
`contracts/operations/github-control-plane-v1.json`.

Final release authority ordering is additionally protected by
`contracts/operations/final-release-authority-v1.json` and documented in
`docs/operations/final-release-authority-order.md`.

## One project, two trust zones

`iamaman11/mobile-proxy-production` is not a second project and is not a second source of truth. It
is a private **execution satellite** required only because a physical Android self-hosted runner
must not be attached to the public repository.

| Boundary | Authority | Purpose |
| --- | --- | --- |
| `iamaman11/mobile-proxy` | canonical | source, docs, contracts, CI, releases, reusable workflow logic, Vultr orchestration, safe evidence index |
| pre-release `acceptance-vultr` capability | external runtime state | encrypted provider credentials for bounded GitHub-hosted acceptance workflows after exact immutable acceptance authority; never final production authority |
| `production-vultr` | external runtime state | encrypted provider credentials and tag-only final deployment gate for GitHub-hosted jobs after final release authority |
| `iamaman11/mobile-proxy-production` | execution-only | thin caller/shim, private phone runner access, bounded private execution evidence |
| `android-production` | execution-only | physical phone access; never project policy or Vultr authority |

The satellite must not independently define architecture, roadmap, release policy, manifests,
provider desired state, acceptance rules or product code. Where GitHub requires a workflow file in
the private repository, that file should remain a thin caller/shim. Canonical phone workflow logic
should live in this public repository as a reusable workflow pinned by the private caller to an
immutable ref, or be delivered as a verified immutable release artifact.

GitHub supports this split: a private caller can invoke a reusable workflow stored in a public
repository, and a called workflow owned by the same user can access self-hosted runners available
to the private caller. This lets the workflow logic stay canonical while runner access stays
private.

## Cross-repository release identity

Final production never means "latest" and never trusts a mutable branch. Both trust zones refer to
the same immutable final-release tuple:

- canonical repository: `iamaman11/mobile-proxy`;
- annotated semantic-version tag: `vMAJOR.MINOR.PATCH`;
- full Git commit SHA;
- release artifact name;
- artifact digest/checksum;
- provenance/attestation identity;
- deployment ID: `mobile-proxy-<tag>-<first12sha>`.

Pre-release acceptance deliberately uses a separate exact immutable candidate identity plus bounded
acceptance evidence. A moving protected `control_plane_sha` may contain newer orchestration/policy
without redefining the immutable `candidate_sha`; these are separate semantic roles, with no rule
requiring their values to differ. Final semantic release authority is not created until physical
acceptance succeeds.

Android version metadata used to build the explicitly authorized signing-generation migration is
also not final release authority. In particular, a protected SHA may carry Android/workspace version
`0.1.4` and produce an exact retained signed migration candidate while the final annotated `v0.1.4`
tag remains absent. #162 consumes exact SHA + signed-candidate evidence, not a final `v*` tag.

Before mutable phone work, the private execution path must verify the exact canonical identity and
required artifact/signing/provenance evidence for that stage. Ambiguity, missing evidence or mismatch
fails closed before the self-hosted runner performs mutable work.

## Control and evidence flow

Pre-release acceptance is intentionally separate from final production authority:

```text
user task
  -> canonical Issue / branch / PR
  -> Quality Gate
  -> protected main
  -> exact immutable candidate + bounded acceptance authority
  -> GitHub-hosted acceptance-vultr lifecycle
  -> exact candidate server verification
  -> private android-production physical acceptance
  -> bounded acceptance evidence back to canonical tracking
```

The one-time Android signing-generation reset is a pre-Item20 prerequisite with a narrower authority:

```text
protected exact canonical SHA
  -> off-phone signing proof + exact signed Android candidate
  -> private retained candidate evidence
  -> #162 serialized registered-phone migration
  -> bounded health / rollback proof
  -> #115 completed only when its acceptance criteria are satisfied
```

That path creates no final tag, GitHub Release, provider authority or production promotion.

Only after physical Item 20 acceptance succeeds may the final production chain continue:

```text
completed Item 20 + exact final_release_control_plane_sha
  -> owner release-tag command on canonical #90
  -> protected annotated v* tag
  -> exact tag Quality success
  -> immutable release artifacts + provenance
       |                         |
       |                         +-> private execution command transport
       |                              -> verify canonical final release tuple
       |                              -> android-production runner
       |                              -> phone verify / rollback
       |
       +-> production-vultr GitHub-hosted workflow
              -> typed UUID/tags/generation-CAS binding
              -> VM verify / rollback
  -> safe bounded result recorded back in canonical project tracking
```

`iamaman11/mobile-proxy-production#1` is reserved as a private command/audit transport. It is not a
project roadmap or decision log. A safe summary/reference of meaningful production results belongs
back in the canonical repository; private raw evidence remains supporting evidence only.

No cross-repository PAT is required merely to let the agent operate both repositories: the agent
can use GitHub-native repository/Issue operations in each trust zone. Future workflow-to-workflow
cross-repository automation must not introduce a broad long-lived token merely for convenience.

## External state that cannot live in the canonical repository

"Single source of project information" does not mean committing secrets or live infrastructure
state. The following remain external by design:

- secret values and private keys;
- live runner online/busy state;
- physical USB/ADB connection state;
- mutable provider resource identifiers/bindings where publication is unsafe;
- raw credential-bearing or device-sensitive logs.

The canonical repository owns the schema, invariant, expected name, allowed location and safe
evidence format for those values. External systems own only the runtime value.

## Current checkpoint

Production Baseline Items 15–19 are **COMPLETE** and Item 20 is the first unfinished delivery item.
The canonical roadmap and machine-readable topology remain authoritative if this summary ever ages.

Current proven/protected boundaries:

- the canonical repository is public and protected by the `Quality Gate`/PR ruleset;
- `v*` tags have an active no-bypass deletion/non-fast-forward ruleset;
- public repository workflows are forbidden from using self-hosted runners or ADB;
- the private Production Control Issue #1 remains command/audit transport and the private
  `android-production` runner/registered-device read-only preflight has passed without publishing
  the identifier or mutating the phone;
- immutable pre-release acceptance authority and the GitHub-hosted Vultr read-only account/key
  preflight are implemented and proven;
- provider-neutral lifecycle policy plus the typed Vultr UUID/ownership/generation-CAS adapter is
  implemented;
- Item 19 provider proof run `33342000338` deployed and verified immutable candidate
  `d151dbdd156279e32a5361d304c90f996bd2d565`, then deterministically deleted its proof VM and
  reached durable terminal state. That terminal Item 19 ownership intent is not reusable;
- Item 20 protected non-live orchestration/readiness foundations exist, including pure admission-core
  exact consumption of the bounded readiness result and exact verified readiness-artifact
  consumption by the non-live session workflow;
- a typed Item 20 lifecycle entrypoint is protected and compile-checked, while live Item 20 provider
  and phone execution remains disabled;
- the historical signer of the currently installed Android application remains unrecoverable, but a
  replacement production signing identity has been proven usable offline in the private execution
  boundary and the repository owner explicitly approved the narrow destructive #162 signing-lineage
  migration;
- canonical Android 0.1.4 build/sign/migration logic is protected; the first off-phone signed build
  failed closed on an `apksigner` v3.1 output-format parser assumption, and that parser was corrected
  through the normal public PR/Quality path without phone access or mutation;
- the next signing-generation step is to rebuild and retain the exact signed candidate from the next
  synchronized protected SHA, then execute #162 only through its exact gates; #115 remains OPEN until
  its acceptance criteria actually pass;
- no mutable phone operation has yet occurred in this signing-generation work;
- no final `v0.1.4` tag/release exists or is authorized before Item 20 completion; final release
  creation is now separately fail-closed on #115/#135 completion plus the exact Item 20 release SHA
  marker;
- legacy public production deployment remains blocked fail-closed; GCP/workstation/manual SSH/raw
  ADB/provider CLI are not authorised acceptance or production shortcuts.

This checkpoint records architecture and control boundaries only. It grants no current Item 20 VM,
endpoint-handoff or unrelated phone mutation authority.
