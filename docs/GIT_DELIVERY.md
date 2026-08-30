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
| `production-vultr` | GitHub Environment that admits only tag `v*`; no reviewer, wait timer or administrator bypass. It provides encrypted provider credentials only to GitHub-hosted jobs. |
| `iamaman11/mobile-proxy-production` | Private execution satellite only; thin phone caller/shim, private runner access, bounded private execution evidence and command/audit transport. It is not a source of project truth. |
| `android-production` | The private-repository runner for the registered physical phone. It has no Vultr credential and no administrative OS privilege for normal jobs. |

The exact machine-readable desired state is:

- [`project-authority-v1.json`](../contracts/operations/project-authority-v1.json)
- [`github-control-plane-v1.json`](../contracts/operations/github-control-plane-v1.json)
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

Every production action across both trust zones uses one immutable release tuple:

- repository `iamaman11/mobile-proxy`;
- annotated semantic tag `vMAJOR.MINOR.PATCH`;
- full Git SHA;
- artifact name and digest;
- provenance/attestation identity;
- deployment ID `mobile-proxy-<tag>-<first12sha>`.

There is no production meaning for "latest". A mutable branch, approximate version, unverified
artifact or conflicting satellite state fails closed.

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
      -> agent-invokable release control
      -> protected annotated vMAJOR.MINOR.PATCH tag
      -> verified GitHub Release + checksum/SBOM/provenance
      -> GitHub-hosted Vultr workflow
      -> verified owned VM
      -> private phone execution command
      -> verify canonical release tuple
      -> canonical reusable workflow/artifact on android-production
      -> verified Android device
      -> bounded safe evidence back to canonical tracking

## Current migration state

Production deployment is **blocked fail-closed**. The historical public deployment route combined
a workstation runner with a GCP adapter and is not the target architecture. The checked-in
migration-gate workflow intentionally refuses deployment.

The phone execution foundation is proven and recorded in
[phone GitOps runtime](operations/phone-gitops-runtime.md): the private Linux runner is online,
the private read-only preflight passed on the registered device at one immutable canonical SHA, and
the bounded report confirms `mutation_performed=false`. This does **not** authorize installation,
network changes, restart, rollback or any other phone mutation.

The remaining implementation work is:

1. agent-invokable GitHub-native release control that creates/uses one protected annotated tag
   without requiring a manual UI button;
2. draft -> assets -> checksum/SBOM/attestation -> publish release ordering, followed by enabling
   release immutability;
3. GitHub-hosted `production-vultr` workflows and a typed Vultr adapter satisfying the
   [VM ownership boundary](architecture/vm-ownership-boundary.md);
4. read-only live Vultr preflight proving environment-secret availability without exposing values;
5. canonical phone install/update/verify/rollback logic invoked only through the private
   execution satellite and exact `android-production` runner;
6. recovery of the existing Android signing identity, followed by private GitHub-secret delivery
   of that identity without exposing it to the public repository, logs or evidence;
7. signed immutable APK handling, certificate-continuity validation and deterministic rollback to
   a previously accepted signed artifact (never a blind rebuild of an old source revision);
8. bounded evidence and deterministic rollback across both targets.

Until the relevant target path is implemented and verified, no release event, manual dispatch,
SSH, raw ADB, provider CLI or workstation command is an authorised production shortcut. Do not
create a VM or install an APK merely to test bootstrap.

## Normal development and release

1. Create a topic branch from current protected `main`.
2. Commit a bounded change with tests and open a pull request.
3. Merge only after the aggregate `Quality Gate` succeeds.
4. For a release, change the workspace version in a reviewed pull request.
5. Create exactly one annotated protected tag matching that version through the canonical release
   control path once implemented.
6. Build immutable artifacts, checksums, SBOM and provenance/attestation before publication.
7. Never move or reuse a release tag; fix forward with a new patch release.

Release immutability remains disabled until the release workflow implements draft -> asset ->
checksum/SBOM/attestation -> publish ordering.

## Secret and evidence policy

See [secret boundaries](operations/secret-boundaries.md). A workflow may report safe metadata such
as tag, SHA, deployment ID, workflow run URL and bounded pass/fail checks. It must never report a
secret value, length, hash, prefix/suffix, SSH material or unverified provider resource identifier.

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
