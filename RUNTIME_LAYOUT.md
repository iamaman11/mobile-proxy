# Runtime Layout

This document describes the canonical runtime topology and safe operational facts. Exact live provider identifiers, device serials, secret values and workstation paths are intentionally kept out of the public repository. Their schemas and invariants are versioned here; live values remain inside protected runtime boundaries.

For project/repository authority see `docs/operations/project-authority.md`. Current delivery status is owned by `docs/PRODUCTION_BASELINE_PLAN.md`; machine-readable topology policy is in `contracts/operations/production-topology-v1.json`.

## Phone

The production phone is a registered rooted Android target reached only through the private `iamaman11/mobile-proxy-production` execution satellite and its `android-production` self-hosted runner. The public repository must never target that runner directly.

Native runtime ownership:

- Magisk/root boot service starts the active versioned release;
- `runtime-supervisor` supervises `host-daemon` and `sing-box`;
- `host-daemon` owns control-plane synchronization, health and the native reverse tunnel;
- `sing-box` provides the phone-local proxy inbounds used by the reverse tunnel;
- active release path follows `/data/adb/mobile-proxy-node/releases/<release-id>` with an active pointer under `/data/adb/mobile-proxy-node/current`.

The normal path is `first_party_reverse_tunnel`. `first_party_android_egress` is the validated carrier-specific egress mode where Android `Network.bindSocket()` is required. Stock WireGuard remains an explicit rollback path. Unknown or contradictory ownership fails closed.

The Android app is not the primary reverse-tunnel owner. It is a managed production auxiliary component for topologies that use `first_party_android_egress` and for the app-owned WireGuard compatibility path. Native topologies that do not consume an app capability do not require APK installation; topologies that do consume it must include exact package/version/signer-match/install state and retained signed artifact provenance in candidate acceptance evidence.

Mutable phone deployment/update/verify/rollback remains gated by the canonical signing-continuity/migration policy. Manual/raw ADB is not an authorized production shortcut.

## Relay VM

The protected logical relay layout is:

- control plane service;
- reverse-tunnel server;
- relay readiness gate;
- public proxy edge;
- canonical SQLite control-plane state;
- public compatibility listeners `1080`, `1081` and `3128`;
- QUIC primary reverse transport with certificate-pinned TLS/TCP reserve.

Vultr lifecycle operations use GitHub-hosted Actions and the typed ownership adapter required by `contracts/governance/vm-ownership-v1.json`: immutable provider UUID binding, exact ownership tags, ownership intent/generation semantics and fail-closed behavior on ambiguity or mismatch. Pre-release acceptance uses bounded acceptance capability; final production uses tag-only `production-vultr` only after final release authority exists.

Historical Item 19 provider proof deployed and verified immutable candidate `d151dbdd156279e32a5361d304c90f996bd2d565` on one controlled acceptance VM and deterministically deleted that proof VM before terminal state. This is immutable historical evidence only. Its terminal Item 19 ownership intent is not reusable by Item 20, and its candidate-specific evidence does not define the active Item 20 final-release candidate.

The retired GCP/workstation path is historical implementation context only and is not the standard acceptance or production control plane.

## Public data path

```text
client
  -> public relay edge
  -> reverse-tunnel server
  -> authenticated fresh phone session
  -> phone-local proxy
  -> Android cellular egress
```

Compatibility surface:

- `1080`: mixed SOCKS5/HTTP compatibility;
- `1081`: SOCKS5;
- `3128`: HTTP including CONNECT;
- QUIC: primary reverse transport;
- pinned TLS/TCP: automatic reserve;
- stock WireGuard: explicit rollback;
- managed Android auxiliary egress/compatibility where selected by topology.

A reported connected state alone is insufficient. Serving authority requires the exact registered phone/session identity, freshness and successful bounded readiness/proxy checks.

## Control-plane trust zones

```text
PUBLIC canonical: iamaman11/mobile-proxy
  - source / docs / contracts / Quality / release policy
  - reusable implementation and workflow policy
  - GitHub-hosted Vultr orchestration
  - safe evidence index

PRIVATE execution satellite: iamaman11/mobile-proxy-production
  - thin caller/shim only
  - private secrets and android-production runner access
  - private physical execution/supporting evidence
```

The private repository is not a second policy engine. If private behavior conflicts with canonical public contracts or the exact pinned public SHA, execution fails closed and canonical state is reconciled first.

## Item 20 and final release identity

For the active 10/10 acceptance window, `candidate_sha` and `control_plane_sha` are explicit typed fields but their **values must be exactly equal** to the exact current protected public `main` SHA selected at admission.

```text
candidate_sha
  == control_plane_sha
  == exact protected main SHA
  == final_accepted_candidate_sha
  == final tag target SHA
  == source SHA of published artifacts
```

Protected-main advancement invalidates stale candidate evidence. Item 20 therefore obtains fresh Quality, software evidence, acceptance authority, preflight/provider proof, Android evidence where applicable, physical evidence, recovery evidence and soak for the newly selected SHA. The historical Item 19 SHA is never silently promoted into active Item 20 authority.

## Migration status semantics

Operational current state is machine-readable in contracts/trackers rather than maintained as a hardcoded moving SHA in this document. The stable gates are:

- public GitHub governance/control-plane split is contract-enforced;
- private repository is execution-only;
- provider lifecycle uses typed ownership and bounded evidence;
- Item 19 provider proof is historical-complete;
- Item 20 is the physical acceptance gate and requires a fresh same-SHA candidate window;
- mutable Android work remains subject to #115/#162 acceptance criteria;
- final annotated release publication and production promotion remain forbidden before Item 20 succeeds on the exact release SHA.

No statement here authorizes a VM or phone mutation outside the reviewed GitHub Actions path.
