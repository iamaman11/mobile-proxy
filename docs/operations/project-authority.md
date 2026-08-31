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

Only after physical acceptance succeeds may the final production chain continue:

```text
protected main / accepted candidate
  -> protected annotated v* tag
  -> immutable release artifacts + checksum/SBOM/provenance
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

The current protected state is later than the original PR #94 authority/bootstrap checkpoint.
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
  `d151dbdd156279e32a5361d304c90f996bd2d565`, then deterministically deleted the proof VM and
  reached durable terminal state. That terminal Item 19 ownership intent is not reusable;
- Item 20 protected non-live orchestration/readiness foundations exist, including pure admission-core
  exact consumption of the bounded readiness result and a bounded readiness-artifact verifier;
- Item 20 session-workflow composition remains incomplete and live Item 20 execution remains
  fail-closed while signing-continuity gate #115 is OPEN;
- the signing identity of the currently installed Android application has not been recovered into
  the private GitHub execution boundary, so mutable Android update/rollback remains intentionally
  unavailable;
- final annotated release publication, release immutability and `production-vultr` promotion remain
  pending and are forbidden before Item 20 succeeds;
- legacy public production deployment remains blocked fail-closed; GCP/workstation/manual SSH/raw
  ADB/provider CLI are not authorised acceptance or production shortcuts.

This checkpoint records architecture and control boundaries only. It grants no current VM or phone
mutation authority.
