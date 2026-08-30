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

The canonical GitOps architecture/status tracker is `iamaman11/mobile-proxy#90`.

## One project, two trust zones

`iamaman11/mobile-proxy-production` is not a second project and is not a second source of truth. It
is a private **execution satellite** required only because a physical Android self-hosted runner
must not be attached to the public repository.

| Boundary | Authority | Purpose |
| --- | --- | --- |
| `iamaman11/mobile-proxy` | canonical | source, docs, contracts, CI, releases, reusable workflow logic, Vultr orchestration, safe evidence index |
| `production-vultr` | external runtime state | encrypted provider credentials and tag-only deployment gate for GitHub-hosted jobs |
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

A production action never means "latest" and never trusts a mutable branch. Both trust zones refer
to the same immutable release tuple:

- canonical repository: `iamaman11/mobile-proxy`;
- annotated semantic-version tag: `vMAJOR.MINOR.PATCH`;
- full Git commit SHA;
- release artifact name;
- artifact digest/checksum;
- provenance/attestation identity;
- deployment ID: `mobile-proxy-<tag>-<first12sha>`.

Before phone mutation, the private execution path must verify that the tag, SHA, artifact digest and
provenance agree with the canonical public release. Ambiguity, missing evidence or mismatch fails
closed before the self-hosted runner performs mutable work.

## Control and evidence flow

The normal autonomous flow is:

```text
user task
  -> canonical Issue / branch / PR
  -> Quality Gate
  -> protected main
  -> protected annotated v* tag
  -> immutable release artifacts + provenance
       |                         |
       |                         +-> private execution command transport
       |                              -> verify canonical release tuple
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

As of the canonical-authority checkpoint completed by PR #94:

- the canonical repository is public and protected by the `Quality Gate`/PR ruleset;
- `v*` tags have an active no-bypass deletion/non-fast-forward ruleset;
- public repository workflows are forbidden from using self-hosted runners or ADB;
- `production-vultr` is the intended tag-only GitHub-hosted Vultr boundary;
- `iamaman11/mobile-proxy-production` exists privately as the phone execution satellite;
- private Production Control Issue #1 is the command/audit transport and a thin read-only caller is enabled;
- the private Linux `android-production` runner has passed its bounded read-only Actions preflight
  against exactly the registered phone, without publishing the identifier or mutating the phone;
- legacy public production deployment is blocked fail-closed;
- live Vultr preflight proof is still pending;
- the typed Vultr lifecycle and final mutable phone deploy/verify/rollback workflows are still pending;
- the signing identity of the currently installed Android application has not been recovered into
  the private GitHub execution boundary, so Android update/rollback is intentionally unavailable;
- release immutability remains disabled until draft -> assets -> checksum/SBOM/attestation -> publish ordering is implemented.

This checkpoint records architecture and control boundaries only. It does not authorize VM or phone
mutation.
