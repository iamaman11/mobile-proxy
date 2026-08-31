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

The canonical GitOps migration/status tracker is Issue #90 in this repository. The active delivery status is owned by `docs/PRODUCTION_BASELINE_PLAN.md`, and the machine-readable execution topology is owned by `contracts/operations/production-topology-v1.json`; copied status summaries must not override either source.

`iamaman11/mobile-proxy-production` is a **private execution satellite only**. Its Issue #1 is a
reserved phone command/audit transport, not a roadmap or source of project truth.

## Current execution focus

The near-term objective is to produce, exercise and accept a functional Production Baseline candidate before doing more non-essential architecture/governance expansion.

The detailed sequencing decision lives **only** in the temporary `Current execution checkpoint` section of `IMPLEMENTATION_PLAN.md`. That section is subordinate to the Production Baseline Plan and current repository state, and must be deleted after software-complete release-candidate acceptance rather than retained as a permanent roadmap or copied into `docs/history/`.

Do not create a competing short-term plan here. In particular, bulk governance JSON -> Protocol Buffers migration, gRPC activation, generic plugin frameworks and broad theoretical-purity refactors are not current baseline work unless a demonstrated blocker requires them.

## Current GitHub control boundary

- canonical repository: public;
- protected `main`: PR + `Quality Gate`, no bypass, no deletion/non-fast-forward;
- protected `v*` tags: no bypass, no deletion/non-fast-forward;
- public repository self-hosted runners: forbidden;
- pre-release Vultr acceptance: GitHub-hosted only through the bounded `acceptance-vultr` workflow capability;
- final Vultr production: GitHub-hosted only through tag-only `production-vultr` after final release authority exists;
- phone execution: private `mobile-proxy-production` caller context -> `android-production` runner;
- legacy public deploy: intentionally fail-closed;
- release immutability: not enabled until publish ordering is fixed.

The machine-readable state is under `contracts/operations/`.

## Current production-migration status

Canonical delivery status: Production Baseline Items 15–19 are **COMPLETE** and Item 20 is the first unfinished item.

Already proven/protected:

- private read-only `android-production` runner/registered-device preflight;
- immutable pre-release acceptance authority;
- GitHub-hosted Vultr read-only account/key preflight;
- provider-neutral lifecycle plus typed Vultr UUID/ownership/generation-CAS adapter;
- bounded Item 19 provider proof for immutable candidate `d151dbdd156279e32a5361d304c90f996bd2d565`, including exact-candidate deployment/verification and deterministic proof-VM cleanup;
- protected non-live Item 20 foundation, including exact readiness-result consumption in the pure admission core and a bounded readiness-artifact verifier.

Still blocked/not complete:

- Item 20 session-workflow consumption/wiring beyond the current non-live foundation;
- mutable phone install/update/network/reboot/rollback while signing-continuity gate #115 is OPEN;
- final Android signing/release path and retained signed rollback artifacts;
- final annotated `v*` release authority and corrected immutable publication ordering;
- `production-vultr` promotion and deterministic end-to-end production rollback proof.

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

Both VM and phone targets must refer to the same canonical release tuple for final production:

- annotated `vMAJOR.MINOR.PATCH` tag;
- full Git SHA;
- artifact name;
- artifact digest/checksum;
- provenance/attestation identity;
- deployment ID `mobile-proxy-<tag>-<first12sha>`.

Pre-release acceptance deliberately uses an exact immutable candidate SHA plus its verified acceptance evidence instead of creating the final tag early. There is no production or acceptance meaning for `latest` or for a mutable branch.

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
