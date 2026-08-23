# Git delivery and production control

Git is the source of truth for code, dependency locks, release versions, quality evidence and the exact revision deployed to production. Secrets and mutable runtime state remain outside Git.

## Live GitHub governance

As of 2026-08-23:

- `main` requires a pull request, a current successful `Quality Gate`, resolved review
  threads, and rejects force-push and deletion;
- `v*` release tags reject force updates and deletion;
- Dependabot security updates, secret scanning and push protection are enabled;
- the `production` environment requires approval by `iamaman11` and accepts only `v*`
  tags;
- production device, tunnel-owner and SSH-user values are environment variables, not
  duplicated in workflow code;
- the repository is private and the dedicated `mobile-proxy-production` runner is the
  only host allowed to access local ADB, gcloud and Secret Vault state.

The private repository is the production trust boundary. Pull-request jobs continue to run on
GitHub-hosted runners; only the manually dispatched, production-environment-gated job can
target the persistent production runner. The runner starts with inherited proxy variables
removed so a stale local proxy cannot break GitHub control-plane traffic.

## Delivery chain

    topic branch
      -> pull request
      -> Quality Gate
      -> protected main
      -> annotated vMAJOR.MINOR.PATCH tag
      -> verified GitHub Release and provenance attestation
      -> approved production environment
      -> trusted self-hosted runner
      -> VM, then Android device

The release ID installed on the VM and phone is git- followed by the first 12 characters of the tag commit SHA. This makes the running revision directly searchable with git show.

## Repository settings to enable once

Create a ruleset for main:

- require a pull request;
- while there is only one maintainer, require zero approvals so the repository remains operable;
- as soon as a second maintainer is added, require one approval and code-owner review for critical paths;
- require conversation resolution;
- require the Quality Gate status check;
- require branches to be current before merge;
- block force pushes and branch deletion;
- include administrators;
- enable the merge queue if concurrent changes become common.

The Quality workflow listens for merge_group, so it remains compatible with the merge queue.

Create a tag ruleset for v*:

- restrict creation and update to release maintainers;
- block deletion and force updates;
- require annotated tags; signed tags are the next hardening step after a signing identity is provisioned.

Create a production environment:

- add a required reviewer and prevent self-review where the GitHub plan supports it;
- restrict deployment branches and tags to protected v* tags;
- define PRODUCTION_DEVICE_SERIAL as R58T10QKGBE;
- define PRODUCTION_TUNNEL_OWNER as first_party_android_egress;
- optionally define PRODUCTION_SSH_USER; bose is the default.

After selecting a private trust boundary, register a dedicated Linux self-hosted runner with
labels `Linux`, `X64` and `mobile-proxy-production`. It must run as the local `bose`
user and have ADB, gcloud, Rust, Android NDK/SDK, Java and the local Secret Vault available.

On the production workstation the runner lives at
`/home/bose/.local/share/actions-runner/mobile-proxy-production`. Its GitHub registration token
is minted only inside `scripts/register-production-runner` under Secret Vault. Windows Task
Scheduler starts `scripts/run-production-runner` through WSL at logon and restarts it after a
failure. The launcher uses an explicit toolchain path and removes inherited proxy variables.
`scripts/adb-windows` delegates to the Windows SDK ADB server so the runner and the operator see
the same attached phone.

The current runner bootstrap is GitHub Actions Runner 2.336.0 for Linux x64, verified against
the SHA-256 digest published by the GitHub release API. When upgrading it, verify the new
official digest before replacing the installation; the runner's own automatic update remains
enabled for urgent compatibility updates.

## Normal change

1. Create a topic branch from current main.
2. Commit a bounded change with tests.
3. Push and open a pull request.
4. Merge only after Quality Gate succeeds.
5. Use the quality-summary-SHA artifact as the first diagnostic surface. It contains four results and links to the run; large successful logs do not need to be copied into agent context.

The compact repository snapshot is available at any revision:

    python3 scripts/repository_context.py

## Release

1. Change workspace.package.version in Cargo.toml in a reviewed pull request.
2. Merge with a green Quality Gate.
3. Create and push exactly one annotated tag matching that version:

       git tag -a v0.1.0 -m "mobile-proxy v0.1.0"
       git push origin v0.1.0

4. The tag receives the same Quality workflow. Only after it succeeds does Publish Release
   create immutable Linux artifacts, SHA-256 interoperability checksums, a release manifest
   and machine-readable provenance. GitHub-native attestations are additionally required when
   the repository owner and plan expose that API. Private repositories owned by personal
   accounts instead publish `provenance.json`, with every release asset covered by
   `SHA256SUMS`, because GitHub rejects native attestations for that repository class.
5. Do not reuse or move a release tag. Fix forward with a new patch version.

## Production deployment

Run Deploy Production from GitHub Actions using the published tag as both the workflow ref and
the `release_tag` input. For example, the CLI form is:

    gh workflow run deploy-production.yml --ref v0.1.0 -f release_tag=v0.1.0

Using `main` as the workflow ref is rejected because the production environment accepts only
protected `v*` tags. Validation resolves the annotated tag to one commit and requires an
existing GitHub Release. The production environment pauses for approval where the GitHub plan
enforces required reviewers, then the dedicated runner checks out that exact SHA.

The runner obtains operational values through scripts/with-production-secrets. GitHub does not receive the proxy password, control tokens, tunnel private key or WireGuard keys. VM deployment completes and verifies before device deployment starts. The device installer verifies the installed bytes, runtime owner, health and proxy smoke test.

An IP rotation is deliberately not part of deployment because it changes a customer-visible network identity. Run mobile-proxy-ip separately when rotation is required.

## Rollback

Rollback always names an already published tag or an already installed release ID. Never deploy an arbitrary branch as an emergency shortcut.

- Device: use operator-cli rollback-device with the previous git-SHA release ID, then verify-device.
- VM: rerun Deploy Production with the previous published tag.
- Record the failed tag, previous tag, observed symptom and bounded verification in an issue.

## Token and time economy

- AGENTS.md and repository_context.py replace repeated whole-repository discovery.
- The single Quality Gate replaces duplicate full test workflows and skips Rust, Android and
  supply-chain builds for Markdown-only diffs.
- Parallel policy, Rust, supply-chain and Android jobs shorten feedback.
- Success is summarized in a tiny JSON artifact; detailed logs remain server-side and are read only on failure.
- Release manifests and deployment SHAs remove repeated questions about what version is running.
- Dependabot batches Cargo, Gradle and GitHub Actions updates weekly instead of producing one stream per dependency.
- Historical plans live under docs/history and do not enter current agent context unless explicitly relevant.

## Further Git improvements

- Enable secret scanning, push protection, dependency graph and private vulnerability reporting.
- Require signed commits or vigilant mode after a signing identity is available.
- Add a four-eyes approval rule for changes under deploy, contracts and public control-plane routes.
- Use git bisect with focused regression tests for performance or reliability regressions.
- Use short-lived git worktrees for parallel experiments rather than leaving mixed changes in one checkout.
- Publish physical acceptance summaries as release or workflow artifacts, retaining raw soak logs outside Git.
- Back up the repository and release metadata to a second read-only remote; never mirror secrets.
