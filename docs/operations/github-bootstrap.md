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
| `acceptance-vultr` | Pre-release acceptance-only secret boundary; GitHub-hosted jobs only; exact acceptance evidence required; item 17 permits only credential/key validation and one `GET /v2/account`; no final-production authority or VM lifecycle. |
| `production-vultr` | Final-production boundary; protected tag-only `v*`, no reviewer/wait timer/admin bypass; GitHub-hosted jobs only. |
| `iamaman11/mobile-proxy-production` | Private execution satellite; Actions/Issues available; no canonical project policy. |
| Private control Issue | `iamaman11/mobile-proxy-production#1`, reserved as command/audit transport only. |
| Phone runner | Private-repo only; labels `self-hosted`, `Linux`, `X64`, `android-production`. |

The machine-readable requirements are:

- [`project-authority-v1.json`](../../contracts/operations/project-authority-v1.json)
- [`github-control-plane-v1.json`](../../contracts/operations/github-control-plane-v1.json)
- [`production-topology-v1.json`](../../contracts/operations/production-topology-v1.json)
- [`acceptance-authority-v1.json`](../../contracts/operations/acceptance-authority-v1.json)
- [`vultr-readonly-preflight-v1.json`](../../contracts/operations/vultr-readonly-preflight-v1.json)

## Credential boundary

Both `acceptance-vultr` and `production-vultr` use the encrypted environment-secret names
`VULTR_API_KEY` and `VULTR_SSH_PRIVATE_KEY`, but they grant different authority. Their values are
never committed, printed, copied to the phone runner or used by a pull-request workflow.

`acceptance-vultr` is available only to the GitHub-hosted read-only preflight after exact immutable
acceptance-authority evidence has been verified. In item 17 it may validate secret presence, parse
the SSH private key locally and perform exactly one authenticated `GET /v2/account`; the response
body is discarded and no provider account data is evidence. It cannot list or mutate VMs and cannot
be treated as final production authority.

`production-vultr` remains protected by the final release-tag gate. A pre-release candidate cannot
use it merely because the same provider credentials may ultimately be needed for production.

Local Secret Vault may bootstrap/recover a GitHub secret but is not part of the standard
GitHub-hosted Vultr runtime path.

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

The immutable pre-release acceptance authority is implemented and live-proven for an exact
canonical candidate. The next bounded gate is the GitHub-hosted Vultr read-only account/key
preflight in `acceptance-vultr`. VM lifecycle remains unavailable until the typed ownership adapter
and its rejection tests are implemented in the following baseline item.

The legacy public deployment workflow is intentionally blocked. Before production deployment is
enabled, the canonical repository must implement and verify:

- an agent-invokable final release control entrypoint;
- protected annotated-tag/release provenance flow after physical acceptance;
- typed Vultr lifecycle satisfying the [VM ownership boundary](../architecture/vm-ownership-boundary.md);
- GitHub-hosted Vultr preflight/apply/verify/evidence/rollback under the staged acceptance/final-production authority split;
- private-caller phone preflight/apply/verify/evidence/rollback;
- existing Android signing identity discovery before any signing-key replacement;
- deterministic rollback and safe evidence correlation by immutable release tuple.

The private read-only phone preflight itself is complete: the private caller ran on the exact
`android-production` Linux runner, proved its required tools and the single registered ADB device,
and produced bounded evidence without publishing the device identifier or mutating the phone.
This is a runtime proof only; it does not make a mutable phone command available. The canonical
record and remaining Android signing/lifecycle gate are in
[phone GitOps runtime](phone-gitops-runtime.md).

No bootstrap step authorizes creating a VM, installing an APK, changing phone networking, or
running an arbitrary SSH/ADB/provider command. Those operations become available only through the
ordered baseline gates.

Release immutability remains disabled until the release workflow publishes only after all intended
assets, checksums, SBOM and attestations/provenance are attached.

## Reconciliation procedure

GitHub environment/secret bootstrap is external encrypted configuration. Re-run it only with an
administrator credential and compare live state against the versioned contracts. Record only
presence/result metadata in the canonical tracker; do not record secret material or unsafe
provider/device identifiers.

Some live properties cannot be independently read through every agent connector. Secret presence,
runner online/idle state and physical ADB state therefore require bounded GitHub Actions preflights
for runtime proof rather than claims based on chat or manual observation.
