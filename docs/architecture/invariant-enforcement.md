# Invariant enforcement audit

Status: normative governance companion  
Audit revision: `2026-08-30`  
Baseline `main`: `02067df89c5f7dc34198ef2d29d2405a21beb791`  
Machine-readable source: `contracts/governance/invariant-enforcement.json`

## Purpose

Architecture prose is not enforcement by itself. The matrix records which active requirements are protected by permanent repository controls, which are only partially protected, which remain planned work and which future concepts are not applicable yet.

The audit must never promote a requirement beyond the evidence named by its row. A source-controlled test can prove repository behavior; it cannot by itself prove mutable GitHub-hosted settings, a live phone, a provider account or other external state.

The source catalog is pinned by Git blob SHA. Editing a pinned normative source fails the permanent validator until the audit is deliberately repeated.

## Status semantics

- `enforced`: permanent repository evidence and a referenced CI step prove the complete row scope.
- `partially_enforced`: permanent CI proves a strict subset and the row names the bounded remaining slice.
- `review_only`: temporary human control with explicit owner, evidence, bounded follow-up and expiry within 180 days of the audit revision.
- `planned`: the requirement is active but adequate machine enforcement is not yet present.
- `not_applicable_yet`: the production concept is absent; the row names the exact activation condition. It is invalid once that condition becomes true.

There are no `review_only` rows in this revision.

## Baseline result

The audit contains 67 invariant IDs:

| Status | Count |
| --- | ---: |
| `enforced` | 31 |
| `partially_enforced` | 20 |
| `planned` | 10 |
| `not_applicable_yet` | 6 |
| `review_only` | 0 |

The validator has an independent required-ID set, so deleting an invariant from both a row list and a JSON catalog does not silently pass.

## 2026-08-30 semantic re-audit

This revision re-audits only controls whose implementation or external evidence materially changed. It does not bulk-promote unrelated rows.

### Full Rust workspace graph — `ARCH-001`

PR #96 introduced `contracts/governance/module-boundaries-v1.json` and `scripts/check_module_boundaries.py` into the required architecture policy gate. Every current Rust workspace member and every current internal dependency edge is classified exactly. The policy rejects an unclassified workspace member, package/path mismatch, undeclared or stale internal dependency, edge to an unknown module and dependency cycles.

Existing pure-crate dependency and vocabulary restrictions remain independent additional checks. `ARCH-001` is therefore `enforced` for the current workspace graph.

### Authoritative mutable-state ownership — `ARCH-003`

PR #99 introduced `contracts/governance/state-ownership-v1.json` and `scripts/check_state_ownership.py` into the required architecture policy gate. Current registered authoritative and operational mutable state has an explicit authority module; durable state also has a persistence owner. The policy rejects duplicate resource ownership, unknown owner modules, writers outside the declared authority and durable state with no persistence owner/writer.

The registry is intentionally an explicit inventory, not a semantic source-code oracle. A future source file could invent a new state concept without the checker understanding that it must be registered. Therefore `ARCH-003` is `partially_enforced`, not `enforced`, with the remaining slice limited to authoritative-state discovery rather than ownership validation for already registered state.

### Canonical SQLite state — `PERSIST-001`

The production control-plane daemon is SQLite-only. JSON is no longer a mutable runtime backend; it is limited to deterministic import, diagnostic export and previous-release rollback artifacts. Process acceptance proves state mutation, termination, restart, replay and conflict behavior against SQLite. `PERSIST-001` is `enforced`.

### SQLite operating discipline — `PERSIST-002`

The SQLite store permanently establishes WAL mode, foreign-key enforcement, a five-second busy timeout, `synchronous=FULL`, immediate bounded write transactions and fail-closed schema/version validation.

Backup/restore evidence is also permanent: `control-plane-state-backup` validates and materializes backups, verifies canonical parity, restores only into a new target and publishes atomically; `state_backup_cli.rs` exercises backup, verification, clean restore and successful startup of a control-plane process from the restored database.

The remaining gap is narrower: there is no explicit complete SQLite integrity/corruption check such as `PRAGMA integrity_check` (or an equivalent demonstrated complete check) in startup/verification. `PERSIST-002` therefore remains `partially_enforced` under `sqlite-integrity-startup-acceptance`.

### Atomic state mutation — `PERSIST-003`

The state layer builds one candidate projection, the SQLite adapter compare-and-swaps the complete relational state in one immediate transaction, verifies post-write parity, commits, and only then publishes the candidate in memory. Stale expected state fails closed. Process tests prove restart/replay behavior. `PERSIST-003` is `enforced`.

### JSON-to-SQLite migration lifecycle — `PERSIST-004`

The migration utility validates legacy JSON before writes, imports it through the isolated adapter, rehydrates canonical SQLite for parity/diagnostic output, and provides `rollback-export` for the previous accepted release. The current daemon has retired JSON runtime selection. Process acceptance round-trips the latest post-mutation rollback artifact back through the accepted importer. `PERSIST-004` is `enforced`.

### Database upgrade discipline — `UPGRADE-002`

This row can no longer be `not_applicable_yet`: canonical SQLite migrations now exist. The initial v1 migration is transactional and previous-release state compatibility is exercised, but no schema-version evolution has yet demonstrated an expand-migrate-contract sequence and rollback after expansion. The active rule is therefore `planned`, not prematurely enforced.

## External controls and freshness

Repository-hosted CI and mutable platform configuration are different evidence classes.

`GITHUB-001` records the actual `Protect main` ruleset. On `2026-08-30`, ruleset `21243704` was verified to require a pull request, resolved review threads, an up-to-date branch and the required `Quality Gate`; branch deletion and non-fast-forward updates are rejected and no bypass actor exists.

The desired state is versioned in `contracts/operations/github-control-plane-v1.json`, and repository policy checks validate that desired contract and workflow shape. However, the required PR Quality job does not continuously query live GitHub ruleset state. Therefore `GITHUB-001` is `partially_enforced`, not `enforced`.

Every external snapshot control carries a `verification` object with `kind=external_snapshot`, the exact verification date, external subject identity, `freshness_policy=reverify_on_every_audit_revision` and whether continuous CI verification exists. The validator requires an external snapshot's `verified_at` date to equal the current `audit_revision`. An externally mutable control cannot claim `enforced` unless continuous CI verification is explicitly true.

## Material open gaps

The matrix, not this prose summary, is authoritative for exact ownership and follow-up names. The highest-impact remaining gaps include:

- semantic discovery of newly invented authoritative state that bypasses the explicit registry (`ARCH-003` residual only);
- review-backed SQL/business-transition isolation where generic AST tooling would not be justified (`ARCH-006`);
- architecture change-scope and ADR supersession enforcement (`ARCH-007`, `ARCH-008`);
- explicit SQLite startup/integrity-corruption checking (`PERSIST-002` residual only; clean backup/restore process recovery is already covered);
- first real schema evolution proving expand-migrate-contract rollback (`UPGRADE-002`);
- broader typed taxonomies and raw-string boundary enforcement;
- repository-wide secret-log, metric-cardinality and bounded-concurrency controls;
- health/readiness/store/tunnel/phone surface separation;
- physical reserve-tunnel and release acceptance on one immutable SHA.

## Permanent validation

`scripts/check_invariant_enforcement.py` fails closed when a pinned normative source changes without re-audit, the required invariant catalog drifts or duplicates IDs, a row has an unsupported or under-evidenced status, an enforcement path or referenced CI step disappears, a `review_only` exception is unbounded or expired, an external control lacks explicit ownership/evidence state, an external snapshot is not reverified on the audit revision, or an external snapshot claims full `enforced` status without continuous CI verification.

The validator is invoked from the permanent architecture/policy job and has regression tests under `scripts/tests`.
