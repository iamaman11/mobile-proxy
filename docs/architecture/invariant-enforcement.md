# Invariant enforcement audit

Status: normative governance companion  
Baseline `main`: `e154f8cbd7bfef4040c1b92743eefb89b5edcb82`  
Machine-readable source: `contracts/governance/invariant-enforcement.json`

## Purpose

Architecture documents define required behavior, but prose alone is not enforcement. This audit records which requirements are protected by permanent CI, which are only partially protected, and which remain explicit implementation work. It must not be used to claim production guarantees that the referenced gate or test does not actually prove.

The matrix covers the normative requirements extracted from:

- `docs/ULTIMATE_IMPLEMENTATION_PLAN.md`;
- `docs/architecture/ADR-001-bounded-contexts-and-clean-dependencies.md`;
- `docs/architecture/ADR-002-cryptographic-hashing-and-kdf-policy.md`;
- `docs/architecture/foundation-primitives.md`;
- `docs/architecture/digest-inventory-and-migration.md`;
- `contracts/compatibility/proxy-surface-v1.json`.

Each source is pinned by its Git blob SHA. Any edit to one of those files makes the permanent validator fail until the audit is deliberately repeated and both the source catalog and invariant catalog are updated.

## Status semantics

- `enforced`: the active rule has repository evidence and a referenced permanent CI workflow step. A document-only statement or an optional local test is insufficient.
- `partially_enforced`: permanent CI proves only the stated subset. The row must also name the bounded follow-up slice that closes the remaining scope.
- `review_only`: a temporary human control. It is allowed only with an owner, evidence note, planned slice and expiry no more than 180 days after the audit revision. There are currently no `review_only` rows.
- `planned`: the rule is active but has no adequate machine enforcement yet. The matrix must name the planned bounded slice.
- `not_applicable_yet`: the target production concept is not present yet. The row must state the activation condition and the planned slice; the status is not a waiver after that condition becomes true.

## Baseline result

The audit contains 67 grouped invariant IDs:

| Status | Count |
| --- | ---: |
| `enforced` | 23 |
| `partially_enforced` | 18 |
| `planned` | 18 |
| `not_applicable_yet` | 8 |
| `review_only` | 0 |

Grouping is deliberate: one ID may cover a coherent normative rule repeated in several sections, but its source anchor and scope must remain specific enough to review. The validator carries an independent required-ID set, so deleting a row and deleting it from the JSON catalog does not silently pass.

## What is currently machine-enforced

The current permanent `Rust Quality` workflow proves only the controls referenced by matrix rows, including:

- protected mixed `1080`, SOCKS5 `1081` and HTTP/CONNECT `3128` compatibility;
- QUIC-first behavior, certificate-pinned TLS/TCP reserve and WireGuard compatibility inventory;
- current pure-crate dependency and vocabulary restrictions;
- typed foundation validation, request lineage, deadline and command-boundary behavior;
- typed BLAKE3 digest formatting, static domain separation and length framing;
- rejection of new first-party SHA-256 producers and legacy release checksum contracts;
- fail-closed device and VM release integrity manifests;
- bounded and expiring reverse-tunnel pending streams, device/session binding and heartbeat freshness;
- the currently implemented formatting, strict Clippy and workspace test suite.

This list is not a claim that every rule in ADR-001 or the Ultimate Plan is enforced.

## Material open gaps

The highest-impact active gaps remain explicit in the matrix:

- single owner per aggregate and typed application-port mutation boundaries;
- thin transport handlers and prohibition of SQL or business transitions in HTTP routes;
- durable SQLite canonical state, transactional audit/outbox semantics and JSON migration;
- repository-wide typed status/error taxonomies;
- application-specific canonical-field detection;
- repository-wide bounded queue/map/task enforcement;
- secret-bearing `Debug` and log detection;
- generated protobuf isolation and future `buf` gates;
- migration/rollback guarantees and production-slice evidence contracts;
- physical reserve-tunnel acceptance on one immutable SHA.

## Fingerprint migration finding

`config_fingerprint` and `binary_fingerprint` are not yet compliant typed digest contracts:

- `HeartbeatRequest` and `DeviceRecord` serialize both fields as `Option<String>`;
- the host daemon sends no `config_fingerprint` producer value;
- `binary_fingerprint` is read from `HOST_DAEMON_BINARY_FINGERPRINT` with a fallback value of `reconstructed`;
- the control plane persists the raw JSON scalar values in the current JSON state file;
- no algorithm/domain/version reader, legacy migration adapter, restart-safe backfill, index migration or rollback process exists.

Accordingly the audit marks the migration as `planned` or `partially_enforced`; it does not treat the presence of `ContentDigest` elsewhere as proof that these fields are migrated.

The next bounded migration must inventory exact canonical source bytes and preserve the existing JSON scalar representation unless a separate versioned API migration is approved. It must never compute `BLAKE3(SHA256(data))`.

## External GitHub control

`GITHUB-001` records the requirement that `main` cannot be changed without the required `Rust Quality` check. The available GitHub connector can inspect repository state, PRs, reviews, inline threads and workflow runs, but it does not expose branch protection or repository rulesets. Therefore branch protection is **not verified** and is not claimed as enforced.

The control remains owned by `repository-admin` under planned slice `configure-and-export-main-ruleset`. Closure requires evidence from GitHub branch protection or a ruleset export showing that the permanent `Rust Quality` check is required for `main`.

## Permanent validation

`scripts/check_invariant_enforcement.py` fails closed when:

- a pinned normative source changes without re-audit;
- a required invariant ID is missing, duplicated or added only on one side of the catalog;
- a row has an unsupported status or missing owner/source/scope;
- `enforced` lacks evidence paths or permanent CI references;
- `partially_enforced` lacks evidence, CI or a follow-up slice;
- `planned` lacks a bounded planned slice;
- `not_applicable_yet` lacks an activation condition;
- a referenced workflow, step, test, script or evidence path does not exist;
- a `review_only` exception is ownerless, evidence-free, unplanned, expired or longer than 180 days;
- the external GitHub control disappears or is represented without explicit ownership and evidence state.

The validator is invoked by the permanent architecture step and has regression tests under `scripts/tests`.
