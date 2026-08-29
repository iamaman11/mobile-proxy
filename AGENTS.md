# Agent operating contract

Start every repository task with:

    python3 scripts/repository_context.py
    git status --short --branch

The generated context is the bounded source for the current SHA, workspace layout, production data path, quality check and delivery workflows. Read deeper documents only when the task touches them.

## Canonical project authority

`iamaman11/mobile-proxy` is the only canonical repository for project information. The private
`iamaman11/mobile-proxy-production` repository is an execution satellite only; it is not a second
project and must not define independent architecture, roadmap, desired state, release policy,
acceptance policy or product behavior.

If chat history, local notes, provider state, a satellite repository or remembered intent conflicts
with this repository, fail closed and reconcile the canonical repository first through the normal
protected-`main` process. See `docs/operations/project-authority.md` and
`contracts/operations/project-authority-v1.json`.

## Sources of truth

All normative sources below live in the canonical repository:

- Product and operator behavior: README.md
- Current implementation roadmap: IMPLEMENTATION_PLAN.md -> docs/PRODUCTION_BASELINE_PLAN.md
- Runtime topology: RUNTIME_LAYOUT.md
- Git delivery and release policy: docs/GIT_DELIVERY.md
- Project authority and cross-repository boundary: docs/operations/project-authority.md
- GitHub bootstrap and control-plane split: docs/operations/github-bootstrap.md
- Project authority contract: contracts/operations/project-authority-v1.json
- GitHub desired-state contract: contracts/operations/github-control-plane-v1.json
- Production topology contract: contracts/operations/production-topology-v1.json
- Enforced architecture rules: contracts/governance/invariant-enforcement.json
- Current code and tests, not historical plans

Documents under docs/history describe completed investigations or superseded plans. They are evidence, not an active backlog.

## Change discipline

- Work on a topic branch; do not deploy an uncommitted tree.
- Keep Cargo.lock and the pinned Rust toolchain synchronized.
- Do not commit target directories, APK/build outputs, runtime binaries, credentials, generated GitHub credentials or raw acceptance logs.
- Secret values never belong in Git. `production-vultr` GitHub Environment secrets are the standard Vultr runtime source; local Secret Vault is bootstrap/recovery only and must not be reintroduced into the normal production path.
- The public repository has no self-hosted runner. Phone execution belongs only to the private
  `iamaman11/mobile-proxy-production` satellite; canonical phone workflow logic must remain here and
  be invoked from the private boundary through an immutable release/ref mechanism.
- Future Vultr lifecycle work belongs on a GitHub-hosted job in tag-only `production-vultr`.
- Production deployment is currently blocked fail-closed until the split workflows and typed
  Vultr adapter are implemented. Do not revive a workstation/ADB/GCP deployment shortcut.
- Manual SSH, raw ADB and provider CLI are not the standard production control plane.
- Keep production ports and client protocols compatible unless the user explicitly authorizes a breaking change.
- A production deployment is identified by an annotated semantic-version tag, immutable commit SHA, verified artifact/provenance and the deployment ID rule in the project-authority contract.

## Proportional verification

For docs and policy-only work:

    scripts/quality-gate.sh fast

For code or release changes:

    scripts/quality-gate.sh

GitHub has one aggregate required check named Quality Gate. Markdown-only changes run the
policy gate; every other path runs policy, Rust, supply-chain and Android jobs. Read the small
quality-summary artifact before inspecting individual logs. Open detailed logs only for failed
checks.

Live phone or VM mutation is allowed only when the task calls for deployment or live acceptance and
the canonical GitOps path for that target is implemented. Record the tag, SHA, release/deployment
ID and bounded pass/fail evidence; do not commit credentials or large logs.
