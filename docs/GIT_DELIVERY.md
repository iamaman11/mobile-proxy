# Git delivery and production control

`iamaman11/mobile-proxy` is the only canonical repository for project information: desired
configuration, source, dependency locks, release versions, quality evidence, contracts, workflow
logic, architecture decisions and acceptance policy. Credential values, private keys, mutable
provider bindings and sensitive physical-device state remain outside Git.

See [project authority](operations/project-authority.md) for the rule that satellite repositories,
chat history, provider consoles and workstation state are non-authoritative when they conflict with
this repository.

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

The phone execution foundation is proven and recorded in
[phone GitOps runtime](operations/phone-gitops-runtime.md): the private Linux runner is online,
the private read-only preflight passed on the registered device at one immutable canonical SHA, and
the bounded report confirms `mutation_performed=false`. This does **not** authorize installation,
network changes, restart, rollback or any other phone mutation.

The immutable acceptance-authority implementation is source-controlled as a distinct gate from
final `production-vultr`. Its completion evidence is the successful post-merge Quality run and a
successful live `/accept-candidate` run recorded in canonical Issues #90/#116. After that checkpoint,
the next bounded item is the GitHub-hosted Vultr **read-only** account/key preflight; VM mutation is
still forbidden until the typed ownership adapter is complete.

The remaining later work includes:

1. read-only live Vultr preflight proving environment-secret availability without exposing values;
2. provider-neutral lifecycle plus typed Vultr UUID/exact-tags/generation-CAS ownership adapter;
3. just-in-time acceptance VM only when physical acceptance is ready;
4. canonical phone install/update/verify/rollback logic invoked only through the private execution
   satellite and exact `android-production` runner;
5. recovery of the existing Android signing identity, followed by private GitHub-secret delivery
   without exposing it to the public repository, logs or evidence;
6. signed immutable APK handling, certificate-continuity validation and deterministic rollback to
   a previously accepted signed artifact (never a blind rebuild of an old source revision);
7. physical acceptance of the exact candidate before final semantic release authority;
8. final draft -> assets -> checksum/SBOM/attestation -> publish ordering, protected annotated tag,
   and only then `production-vultr` promotion;
9. bounded evidence and deterministic rollback across both targets.

Until the relevant target path is implemented and verified, no release event, manual dispatch,
SSH, raw ADB, provider CLI or workstation command is an authorised production shortcut. Do not
create a VM or install an APK merely to test bootstrap.

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
