# Agent operating contract

Start every repository task with:

    python3 scripts/repository_context.py
    git status --short --branch

The generated context is the bounded source for the current SHA, workspace layout, production data path, quality check and delivery workflows. Read deeper documents only when the task touches them.

## Sources of truth

- Product and operator behavior: README.md
- Runtime topology: RUNTIME_LAYOUT.md
- Git delivery and release policy: docs/GIT_DELIVERY.md
- Enforced architecture rules: contracts/governance/invariant-enforcement.json
- Current code and tests, not historical plans

Documents under docs/history describe completed investigations or superseded plans. They are evidence, not an active backlog.

## Change discipline

- Work on a topic branch; do not deploy an uncommitted tree.
- Keep Cargo.lock and the pinned Rust toolchain synchronized.
- Do not commit target directories, APK/build outputs, runtime binaries, credentials, generated GitHub credentials or raw acceptance logs.
- Use Secret Vault wrappers for operational secrets. Never print secret values.
- Keep production ports and client protocols compatible unless the user explicitly authorizes a breaking change.
- A production deployment is identified by an annotated semantic-version tag and its immutable commit SHA.

## Proportional verification

For docs and policy-only work:

    scripts/quality-gate.sh fast

For code or release changes:

    scripts/quality-gate.sh

GitHub has one aggregate required check named Quality Gate. Read its small quality-summary artifact before inspecting individual logs. Open detailed logs only for failed checks.

Live phone or VM mutation is allowed only when the task calls for deployment or live acceptance. Record the tag, SHA, release ID and bounded pass/fail evidence; do not commit credentials or large logs.
