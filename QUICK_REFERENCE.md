# Quick Reference

## Canonical project authority

The only canonical repository for project information is:

`https://github.com/iamaman11/mobile-proxy`

If context is missing, start with:

1. `AGENTS.md` — repository operating contract and source-of-truth rules;
2. `IMPLEMENTATION_PLAN.md` — temporary current execution checkpoint plus the pointer to the sole active roadmap;
3. `docs/PRODUCTION_BASELINE_PLAN.md` — active scope, delivery order, stop conditions and context-loss recovery protocol;
4. `REPOSITORY_MAP.md` — module and ownership map;
5. `RUNTIME_LAYOUT.md` — production runtime topology;
6. `docs/operations/project-authority.md` — canonical/private-satellite boundary;
7. `docs/GIT_DELIVERY.md` — protected Git/release/deployment flow.

`TEN_OUT_OF_TEN_VALIDATION_PLAN.md` is the normative **acceptance matrix**, not a competing implementation roadmap. `docs/future/` is non-active future direction. After reading the entry documents, inspect current `main`, open PRs and the latest permanent workflow results as required by the Production Baseline context-loss protocol.

The canonical GitOps migration/status tracker is Issue #90 in this repository.

`iamaman11/mobile-proxy-production` is a **private execution satellite only**. Its Issue #1 is a
reserved phone command/audit transport, not a roadmap or source of project truth.

## Current execution focus

The near-term objective is to produce, exercise and accept a functional Production Baseline candidate before doing more non-essential architecture/governance expansion.

The detailed sequencing decision lives **only** in the temporary `Current execution checkpoint` section of `IMPLEMENTATION_PLAN.md`. That section is subordinate to the Production Baseline Plan and current repository state, and must be deleted after software-complete release-candidate acceptance rather than retained as a permanent roadmap or copied into `docs/history/`.

Do not create a competing short-term plan here. In particular, bulk governance JSON -> Protocol Buffers migration, gRPC activation, generic plugin frameworks and broad theoretical-purity refactors are not current baseline work unless a demonstrated blocker requires them.

Known audit-snapshot drift after the merged state-ownership slice is tracked in Issue #100: the current repository already has the owner registry and permanent clean backup/restore process coverage even though two rows in the 2026-08-30 invariant audit still describe the earlier state. Repository state wins; #100 is a bounded semantic correction and does not authorize more architecture expansion.

## Current GitHub control boundary

- canonical repository: public;
- protected `main`: PR + `Quality Gate`, no bypass, no deletion/non-fast-forward;
- protected `v*` tags: no bypass, no deletion/non-fast-forward;
- public repository self-hosted runners: forbidden;
- Vultr execution: GitHub-hosted only through tag-only `production-vultr`;
- phone execution: private `mobile-proxy-production` caller context -> `android-production` runner;
- legacy public deploy: intentionally fail-closed;
- release immutability: not enabled until publish ordering is fixed.

The machine-readable state is under `contracts/operations/`.

## Current production-migration status

Not yet enabled:

- agent-invokable protected annotated-tag creation/release control;
- typed Vultr lifecycle adapter and live Vultr deployment;
- live read-only Vultr preflight proof;
- private phone preflight/deploy/verify/rollback workflow;
- live read-only phone runner/device proof;
- final Android signing/release path;
- deterministic end-to-end production rollback proof.

Do not use a workstation command, raw ADB, manual SSH, GCP/Vultr CLI or the legacy deployment
workflow as a shortcut around these gates.

## Development quality

```bash
scripts/quality-gate.sh fast  # docs/policy-sized changes
scripts/quality-gate.sh       # code/release changes
```

GitHub requires the aggregate `Quality Gate`. Read `quality-summary-<git-sha>` before opening large
job logs.

## Immutable release identity

Both VM and phone targets must refer to the same canonical release tuple:

- annotated `vMAJOR.MINOR.PATCH` tag;
- full Git SHA;
- artifact name;
- artifact digest/checksum;
- provenance/attestation identity;
- deployment ID `mobile-proxy-<tag>-<first12sha>`.

There is no production meaning for `latest` or for a mutable branch.

## Runtime/product compatibility

The protected public proxy surface remains:

- `1080`: mixed SOCKS5/HTTP compatibility;
- `1081`: SOCKS5;
- `3128`: HTTP including CONNECT;
- QUIC: primary reverse transport;
- certificate-pinned TLS/TCP: reserve;
- stock WireGuard: explicit rollback path.

Exact live provider identifiers, phone serials, secret values, local workstation paths and raw
acceptance logs are intentionally not part of this public quick reference. Their schema and safety
rules are canonical here; their live values remain in the appropriate protected runtime boundary.

## Historical operator commands

Older workstation/GCP/ADB command sequences are historical evidence, not the current production
control plane. Use Git history or `docs/history/` only when investigating legacy behavior; do not
restore those paths into normal production delivery.
