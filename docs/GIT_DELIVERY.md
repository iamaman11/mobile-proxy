# Git delivery and production control

`iamaman11/mobile-proxy` is the only canonical repository for project information: desired
configuration, source, dependency locks, release versions, quality evidence, contracts, workflow
logic, architecture decisions and acceptance policy. Credential values, private keys, mutable
provider bindings and sensitive physical-device state remain outside Git.

See [project authority](operations/project-authority.md) for the rule that satellite repositories,
chat history, provider consoles and workstation state are non-authoritative when they conflict with
this repository.

Current delivery status is owned by [`PRODUCTION_BASELINE_PLAN.md`](PRODUCTION_BASELINE_PLAN.md).
Exact machine-readable execution/control-plane state is owned by
[`github-control-plane-v1.json`](../contracts/operations/github-control-plane-v1.json) and
[`production-topology-v1.json`](../contracts/operations/production-topology-v1.json). Status
summaries in this document are orientation only and must not become a parallel roadmap.

## Control-plane split

| Boundary | Required responsibility |
| --- | --- |
| `iamaman11/mobile-proxy` | Canonical public project repository; CI, release source, reusable workflow logic, safe evidence index and GitHub-hosted Vultr orchestration. It has zero self-hosted runners. |
| Vultr pre-release acceptance authority | Exact full candidate SHA plus successful canonical `Quality` push evidence and matching release-candidate artifact. GitHub-hosted only; it is not final production authority and does not use `production-vultr` merely to authorize acceptance. |
| `production-vultr` | Final-production GitHub Environment that admits only protected tag `v*`; no reviewer, wait timer or administrator bypass. It provides encrypted provider credentials only to GitHub-hosted jobs after final release authority exists. |
| `iamaman11/mobile-proxy-production` | Private execution satellite only; thin phone caller/shim, private runner access, bounded private execution evidence and command/audit transport. It is not a source of project truth. |
| `android-production` | The private-repository runner for the registered physical phone. It has no Vultr credential and no administrative OS privilege for normal jobs. |

The exact machine-readable desired state is:

- [`project-authority-v1.json`](../contracts/operations/project-authority-v1.json)
- [`github-control-plane-v1.json`](../contracts/operations/github-control-plane-v1.json)
- [`acceptance-authority-v1.json`](../contracts/operations/acceptance-authority-v1.json)
- [`production-topology-v1.json`](../contracts/operations/production-topology-v1.json)

Bootstrap and recovery guidance is [GitHub bootstrap](operations/github-bootstrap.md).

## One project across two repositories

The private repository exists solely to keep the physical self-hosted runner outside the public
fork/PR trust boundary. It must not duplicate application source, manifests, architecture,
roadmaps, release policy or acceptance rules.

The preferred phone architecture is a thin private caller invoking canonical workflow logic from
`iamaman11/mobile-proxy` at an immutable ref, or executing a verified immutable artifact produced by
this repository. GitHub supports a private caller invoking a reusable workflow from a public
repository; self-hosted runner assignment is then evaluated in the caller's context.

Final production uses one immutable release tuple:

- repository `iamaman11/mobile-proxy`;
- annotated semantic tag `vMAJOR.MINOR.PATCH`;
- full Git SHA;
- artifact name and digest;
- provenance/attestation identity;
- deployment ID `mobile-proxy-<tag>-<first12sha>`.

Pre-release acceptance deliberately has a different authority: one exact full candidate SHA plus
its successful canonical Quality/release-candidate evidence. Acceptance never upgrades a candidate
to final production authority by creating a semantic release tag early or by entering
`production-vultr` simply to make testing convenient.

There is no production or acceptance meaning for `latest`. Mutable branches, branch names, short
SHAs, approximate versions, unverified artifacts or conflicting satellite state fail closed.

`iamaman11/mobile-proxy#90` is the canonical GitOps architecture/status tracker.
`iamaman11/mobile-proxy-production#1` is only the private command/audit transport. Meaningful safe
results are referenced back to the canonical project; private raw evidence is supporting evidence,
not an independent decision record.

## Public GitHub governance

- `main` requires a pull request, current successful `Quality Gate`, review-thread resolution and
  an up-to-date branch. It rejects deletion and non-fast-forward updates, with no bypass actor.
- `v*` release tags reject deletion and movement, with no bypass actor.
- Public Actions default to read-only repository/package permissions, cannot approve pull
  requests, and require approval for every external fork contributor. Fork workflows receive no
  write token or secret.
- Secret scanning, push protection, Dependabot alerts and Dependabot security updates are enabled
  where GitHub provides them for public repositories.
- Public workflows do not target self-hosted runners or execute ADB.

## Delivery chain

    topic branch
      -> pull request
      -> Quality Gate
      -> protected main
      -> exact immutable candidate SHA
      -> successful canonical Quality push + release-candidate artifact
      -> /accept-candidate <full_sha> on canonical Issue #90
      -> GitHub-hosted pre-release acceptance authority
      -> read-only Vultr preflight
      -> typed Vultr ownership adapter
      -> just-in-time acceptance VM
      -> physical acceptance of the exact candidate
      -> protected annotated vMAJOR.MINOR.PATCH tag
      -> verified GitHub Release + checksum/SBOM/provenance
      -> production-vultr promotion from final release authority
      -> bounded safe evidence back to canonical tracking

The command `/accept-candidate <full_sha>` accepts exactly one lowercase 40-character candidate SHA.
The gate uses the default branch's protected canonical workflow logic, finds the successful
`Quality` push on `main` for that exact SHA, verifies the exact
`software-release-candidate-<sha>` artifact, and emits a bounded
`vultr-acceptance-authority-<sha>` artifact. The evidence explicitly records that final production
authority, Vultr API access, VM mutation, phone mutation and final release-tag creation are false
at this authority-only stage.

## Current migration state

Production deployment remains **blocked fail-closed** until the later Production Baseline gates are
completed. The historical public deployment route combined a workstation runner with a GCP adapter
and is not the target architecture. The checked-in migration-gate workflow intentionally refuses
deployment.

Production Baseline Items 15–19 are **COMPLETE**. Item 20 is the first unfinished delivery item.
The following pre-release foundations are already protected and proven:

- the private Linux `android-production` runner and registered-device binding passed a bounded
  read-only Actions preflight with `mutation_performed=false`;
- immutable pre-release acceptance authority is implemented and proven for exact candidate
  identities;
- the GitHub-hosted Vultr read-only account/key preflight is implemented and proven;
- provider-neutral lifecycle policy plus the typed Vultr UUID/exact-tags/ownership/generation-CAS
  adapter is implemented;
- Item 19 lifecycle run `33342000338` deployed and verified immutable candidate
  `d151dbdd156279e32a5361d304c90f996bd2d565` on one controlled proof VM, deterministically deleted
  that VM, confirmed provider absence and reached durable terminal state. The terminal Item 19
  ownership intent is not reusable;
- Item 20 has protected non-live orchestration/readiness foundations. The bounded readiness result
  is exact-matched by the pure admission core, and a pure readiness-artifact selector/verifier is
  present. Session-workflow wiring remains explicitly incomplete and grants no live authority.

The remaining baseline work is bounded to the first unfinished item and its successors:

1. finish the protected non-live Item 20 session/workflow composition without weakening admission;
2. satisfy #115 by recovering and independently verifying the existing Android signing identity,
   delivering it only through the private execution boundary, and protecting signed immutable APK
   update/verify/rollback logic with certificate continuity and retained rollback artifacts;
3. when #115 and the same-window private phone preflight permit a mutable physical window, run one
   fresh Item 20 JIT acceptance session and the normative physical A–F sequence on the exact
   immutable candidate, followed by deterministic provider cleanup and bounded evidence;
4. only after successful physical acceptance, create the final draft -> assets ->
   checksum/SBOM/attestation -> publish sequence and protected annotated `vMAJOR.MINOR.PATCH` tag;
5. only from that accepted final release tuple, perform `production-vultr` promotion and prove the
   bounded deterministic production rollback/fix-forward path.

Until the relevant target path is implemented and verified, no release event, manual dispatch,
SSH, raw ADB, provider CLI or workstation command is an authorised production shortcut. Do not
create an Item 20 VM or mutate the phone merely to keep work moving while #115 remains OPEN.

## Normal development and release

1. Create a topic branch from current protected `main`.
2. Commit a bounded change with tests and open a pull request.
3. Merge only after the aggregate `Quality Gate` succeeds.
4. For a release candidate, use the exact protected-main SHA and its successful canonical Quality
   release-candidate evidence; never substitute `main`, `latest`, a branch name or a short SHA.
5. Execute the acceptance path under the distinct pre-release authority and complete physical
   acceptance before creating a final semantic tag.
6. For a final release, change the workspace version in a reviewed pull request as required, then
   create exactly one annotated protected tag matching that version through the canonical release
   control path only after physical acceptance succeeds.
7. Build immutable artifacts, checksums, SBOM and provenance/attestation before publication.
8. Never move or reuse a release tag; fix forward with a new patch release.

Release immutability remains disabled until the release workflow implements draft -> asset ->
checksum/SBOM/attestation -> publish ordering.

## Secret and evidence policy

See [secret boundaries](operations/secret-boundaries.md). A workflow may report safe metadata such
as tag, SHA, workflow run identity and bounded pass/fail checks. It must never report a secret value,
length, hash, prefix/suffix, SSH material or unverified provider resource identifier.

If secret scanning reports a genuine credential, treat it as disclosed: revoke or rotate at the
provider first, then remove it from source/history and record only the safe remediation result.

Exact live secrets, runner online/busy state, physical USB/ADB state and unsafe-to-publish provider
bindings are external runtime values. The canonical repository remains authoritative for their
schema, required names, allowed locations, invariants and safe evidence format.

## Token and time economy

- `AGENTS.md` and `repository_context.py` replace repeated repository discovery.
- One aggregate Quality Gate avoids duplicate test work and exposes a compact summary artifact.
- Versioned contracts prevent agents from rediscovering repository, runner and secret boundaries.
- Raw physical acceptance logs remain outside public Git; publish only bounded non-secret evidence.
- Private satellite content stays minimal so context recovery always starts from this repository.
