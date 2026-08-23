# Git delivery and production control

Git is the source of truth for code, dependency locks, release versions, quality evidence and the exact revision deployed to production. Secrets and mutable runtime state remain outside Git.

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

- require a pull request and one approval;
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

Register a dedicated Linux self-hosted runner with labels Linux, X64 and mobile-proxy-production. It must run as the local bose user and have ADB, gcloud, Rust, Android NDK/SDK, Java and the local Secret Vault available. Do not assign this runner to pull-request workflows. Use a private repository or restrict fork workflows because deployment jobs execute repository code with production access.

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

4. The tag receives the same Quality workflow. Only after it succeeds does Publish Release create immutable Linux artifacts, SHA-256 interoperability checksums, a release manifest and GitHub provenance attestations.
5. Do not reuse or move a release tag. Fix forward with a new patch version.

## Production deployment

Run Deploy Production from GitHub Actions and select the published tag. Validation resolves the annotated tag to one commit and requires an existing GitHub Release. The production environment pauses for approval, then the dedicated runner checks out that exact SHA.

The runner obtains operational values through scripts/with-production-secrets. GitHub does not receive the proxy password, control tokens, tunnel private key or WireGuard keys. VM deployment completes and verifies before device deployment starts. The device installer verifies the installed bytes, runtime owner, health and proxy smoke test.

An IP rotation is deliberately not part of deployment because it changes a customer-visible network identity. Run mobile-proxy-ip separately when rotation is required.

## Rollback

Rollback always names an already published tag or an already installed release ID. Never deploy an arbitrary branch as an emergency shortcut.

- Device: use operator-cli rollback-device with the previous git-SHA release ID, then verify-device.
- VM: rerun Deploy Production with the previous published tag.
- Record the failed tag, previous tag, observed symptom and bounded verification in an issue.

## Token and time economy

- AGENTS.md and repository_context.py replace repeated whole-repository discovery.
- The single Quality Gate replaces duplicate full test workflows.
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
