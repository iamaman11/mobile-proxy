# Git delivery and production control

Git is the public source of truth for desired configuration, source, dependency locks, release
versions, quality evidence, contracts and workflow definitions. Credential values, private keys,
mutable provider bindings and physical-device secrets remain outside Git.

## Control-plane split

| Boundary | Required responsibility |
| --- | --- |
| `iamaman11/mobile-proxy` | Public source repository; CI, release source and future GitHub-hosted Vultr orchestration. It has zero self-hosted runners. |
| `production-vultr` | GitHub Environment that admits only tag `v*`; no reviewer, wait timer or administrator bypass. It provides encrypted provider credentials only to GitHub-hosted jobs. |
| `iamaman11/mobile-proxy-production` | Private phone-control repository; Actions, Issues, phone workflows, evidence and rollback. |
| `android-production` | The private-repository runner for the registered physical phone. It has no Vultr credential and no administrative OS privilege for normal jobs. |

The exact machine-readable desired state is
[`github-control-plane-v1.json`](../contracts/operations/github-control-plane-v1.json) and
[`production-topology-v1.json`](../contracts/operations/production-topology-v1.json). Bootstrap
and recovery guidance is [GitHub bootstrap](operations/github-bootstrap.md).

## Public GitHub governance

- `main` requires a pull request, current successful `Quality Gate`, review-thread resolution and
  an up-to-date branch. It rejects deletion and non-fast-forward updates, with no bypass actor.
- `v*` release tags reject deletion and movement, with no bypass actor.
- Public Actions default to read-only repository/package permissions, cannot approve pull
  requests, and require approval for every external fork contributor. Fork workflows receive no
  write token or secret.
- Secret scanning, push protection, Dependabot alerts and Dependabot security updates are enabled
  where GitHub provides them for public repositories.

## Delivery chain

    topic branch
      -> pull request
      -> Quality Gate
      -> protected main
      -> annotated vMAJOR.MINOR.PATCH tag
      -> verified GitHub Release and provenance
      -> GitHub-hosted Vultr workflow
      -> verified owned VM
      -> private phone-control workflow
      -> verified Android device

The release ID is `git-<first 12 characters of tag commit SHA>`. It lets an operator identify the
deployed revision without relying on mutable branch names.

## Current migration state

Production deployment is **blocked fail-closed**. The checked-in legacy public deployment route
combines a workstation runner with a GCP adapter and is not the target architecture. It must be
replaced, in reviewed Git changes, by:

1. a GitHub-hosted `production-vultr` workflow and a typed Vultr adapter that satisfies the
   [VM ownership boundary](architecture/vm-ownership-boundary.md);
2. a private `mobile-proxy-production` phone workflow that targets only the registered device;
3. tag-bound verification, evidence and deterministic rollback across both boundaries.

Until then no release event, manual dispatch, SSH, raw ADB or provider CLI is an authorised
shortcut for deployment. Do not create a VM or install an APK merely to test bootstrap.

## Normal development and release

1. Create a topic branch from current `main`.
2. Commit a bounded change with tests and open a pull request.
3. Merge only after the aggregate `Quality Gate` succeeds.
4. Change the workspace version in a reviewed pull request, then create exactly one annotated tag
   matching that version.
5. Let the release workflow attach release artifacts, checksums, SBOM and provenance before
   publishing the release.

Release immutability remains disabled until the release workflow implements that draft → asset →
checksum/SBOM/attestation → publish order. Never move or reuse a release tag; fix forward with a
new patch release.

## Secret and evidence policy

See [secret boundaries](operations/secret-boundaries.md). A workflow may report safe metadata
such as tag, SHA, workflow run URL and pass/fail checks. It must never report a secret value,
length, hash, prefix/suffix, SSH material or unverified provider resource identifier.

If secret scanning reports a genuine credential, treat it as disclosed: revoke or rotate at the
provider first, then remove it from source/history and record only the safe remediation result.

## Token and time economy

- `AGENTS.md` and `repository_context.py` replace repeated repository discovery.
- One aggregate Quality Gate avoids duplicate test work and exposes a compact summary artifact.
- Versioned contracts prevent agents from rediscovering repository, runner and secret boundaries.
- Raw physical acceptance logs remain outside public Git; publish only bounded non-secret evidence.
