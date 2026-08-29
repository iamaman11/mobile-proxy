# GitHub control-plane bootstrap

`iamaman11/mobile-proxy` is the public, versioned and **sole canonical repository for project
information**. It contains desired control-plane state, contracts, workflow logic, release identity
and safe evidence policy. It does not contain credential values, private keys, mutable provider
bindings, physical-phone secrets or workstation paths; those are deliberately external runtime
state.

The private `iamaman11/mobile-proxy-production` repository is only an execution satellite for the
physical phone runner. It cannot define an independent roadmap, architecture, desired state or
release policy. See [project authority](project-authority.md).

## Reconciled GitHub state

| Boundary | Required state |
| --- | --- |
| `iamaman11/mobile-proxy` | Public canonical repository; zero self-hosted runners. |
| `main` | Active PR ruleset with `Quality Gate`, no bypass, no deletion/force push. |
| `v*` | Active tag ruleset with no bypass, no deletion or non-fast-forward movement. |
| Public Actions | Read-only default token; all external fork contributors require approval; fork write token/secrets forbidden. |
| `production-vultr` | Tag-only `v*`, no reviewer/wait timer/admin bypass; GitHub-hosted jobs only. |
| `iamaman11/mobile-proxy-production` | Private execution satellite; Actions/Issues available; no canonical project policy. |
| Private control Issue | `iamaman11/mobile-proxy-production#1`, reserved as command/audit transport only. |
| Phone runner | Private-repo only; labels `self-hosted`, `Linux`, `X64`, `android-production`. |

The machine-readable requirements are:

- [`project-authority-v1.json`](../../contracts/operations/project-authority-v1.json)
- [`github-control-plane-v1.json`](../../contracts/operations/github-control-plane-v1.json)
- [`production-topology-v1.json`](../../contracts/operations/production-topology-v1.json)

## Credential boundary

`production-vultr` contains the encrypted environment-secret names `VULTR_API_KEY` and
`VULTR_SSH_PRIVATE_KEY`. Their values are never committed, printed, copied to the phone runner or
used by a pull-request workflow. Local Secret Vault may bootstrap/recover a GitHub secret but is not
part of the standard GitHub-hosted Vultr runtime path.

The phone runner is intentionally separate because physical USB/ADB access cannot be supplied by a
GitHub-hosted runner. It must not receive Vultr credentials, an unrelated broad PAT or normal-job OS
administrative privilege.

## Private execution-satellite boundary

The private repository should remain as small as GitHub permits. Allowed content is a thin caller
or shim, private runner wiring, bounded private evidence and the command/audit transport. Canonical
phone orchestration logic belongs in `iamaman11/mobile-proxy` and should be invoked at an immutable
ref or delivered as a verified immutable release artifact.

A private GitHub Actions caller may use a reusable workflow stored in this public repository. For
self-hosted jobs, GitHub evaluates runner access from the caller context, allowing the canonical
workflow logic to remain public/versioned while the `android-production` runner remains private.

If private execution state conflicts with canonical project state, do not repair the canonical
state from the private repository. Stop and reconcile `iamaman11/mobile-proxy` first.

## Delivery status

The legacy public deployment workflow is intentionally blocked. Before production deployment is
enabled, the canonical repository must implement and verify:

- an agent-invokable release control entrypoint;
- protected annotated-tag/release provenance flow;
- typed Vultr lifecycle satisfying the [VM ownership boundary](../architecture/vm-ownership-boundary.md);
- GitHub-hosted Vultr preflight/apply/verify/evidence/rollback;
- private-caller phone preflight/apply/verify/evidence/rollback;
- existing Android signing identity discovery before any signing-key replacement;
- deterministic rollback and safe evidence correlation by immutable release tuple.

No bootstrap step authorizes creating a VM, installing an APK, changing phone networking, or
running an arbitrary SSH/ADB/provider command. Those operations become available only through
reviewed, tagged and verified workflows.

Release immutability remains disabled until the release workflow publishes only after all intended
assets, checksums, SBOM and attestations/provenance are attached.

## Reconciliation procedure

The GitHub bootstrap is an external configuration operation. Re-run it only with an administrator
credential and compare live state against the versioned contracts. Record only pass/fail metadata
in the canonical repository; do not record secret material or unsafe provider/device identifiers.

Some live properties cannot be independently read through every agent connector. Secret presence,
runner online/idle state and physical ADB state therefore require bounded GitHub Actions preflights
for runtime proof rather than claims based on chat or manual observation.
