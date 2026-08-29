# GitHub control-plane bootstrap

This repository is the public, versioned source of truth for the desired control plane. It does
not contain credential values, private keys, mutable provider bindings, physical-phone secrets or
workstation paths. Those are deliberately external runtime state.

## Reconciled GitHub state

| Boundary | Required state |
| --- | --- |
| `iamaman11/mobile-proxy` | Public source repository; zero self-hosted runners. |
| `main` | Active PR ruleset with `Quality Gate`, no bypass, no deletion/force push. |
| `v*` | Active immutable tag ruleset with no bypass. |
| Public Actions | Read-only default token; all external fork contributors require approval. |
| `production-vultr` | Tag-only `v*`, no reviewer/wait timer/admin bypass; GitHub-hosted jobs only. |
| `iamaman11/mobile-proxy-production` | Private phone-control repository; Actions and Issues enabled. |
| Phone runner | Private-repo only; labels `self-hosted`, `Linux`, `X64`, `android-production`. |

The machine-readable requirements are
[`github-control-plane-v1.json`](../../contracts/operations/github-control-plane-v1.json) and
[`production-topology-v1.json`](../../contracts/operations/production-topology-v1.json).

## Credential boundary

`production-vultr` contains the encrypted environment-secret names `VULTR_API_KEY` and
`VULTR_SSH_PRIVATE_KEY`. Their values are never committed, printed, copied to the phone runner or
used by a pull-request workflow. Local Secret Vault may bootstrap or recover a GitHub secret, but
is not part of the GitHub-hosted Vultr runtime path.

The phone runner is intentionally separate because physical USB/ADB access cannot be supplied by
a GitHub-hosted runner. It has no Vultr credential, no unrelated PAT and no administrative OS
privilege for normal Actions jobs.

## Delivery status

The legacy public deployment workflow is intentionally blocked. A Vultr lifecycle adapter and
split GitHub workflows must be implemented before production deployment is enabled. The adapter
must first satisfy the [VM ownership boundary](../architecture/vm-ownership-boundary.md): durable
immutable UUID binding, exact ownership tags and fail-closed recreation/deletion semantics.

No bootstrap step authorizes creating a VM, installing an APK, changing phone networking, or
running an arbitrary SSH/ADB command. Those operations become available only through reviewed,
tagged and verified workflows.

## Reconciliation procedure

The GitHub bootstrap is an external configuration operation. Re-run it only with an administrator
credential and compare the live state against the two JSON contracts. Record only pass/fail
metadata in an Issue or deployment summary; do not record secret material or provider identifiers
that would weaken the public boundary.
