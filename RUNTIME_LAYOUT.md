# Runtime Layout

This document describes the canonical runtime topology and safe operational facts. Exact live
provider identifiers, device serials, secret values and workstation paths are intentionally kept out
of the public repository. Their schemas and invariants are versioned here; their live values remain
inside the protected runtime boundary.

For project/repository authority see `docs/operations/project-authority.md`. Current delivery status
is owned by `docs/PRODUCTION_BASELINE_PLAN.md`; exact control-plane execution state is machine-readable
in `contracts/operations/production-topology-v1.json`.

## Phone

The production phone is a registered rooted Android target reached only through the private
`iamaman11/mobile-proxy-production` execution satellite and its `android-production` self-hosted
runner. The public repository must never target that runner directly.

Runtime ownership:

- Magisk/root boot service starts the active versioned release;
- `runtime-supervisor` supervises `host-daemon` and `sing-box`;
- `host-daemon` owns control-plane synchronization, health and the native reverse tunnel;
- `sing-box` provides the phone-local proxy inbounds used by the reverse tunnel;
- active release path follows `/data/adb/mobile-proxy-node/releases/<release-id>` with an active
  pointer under `/data/adb/mobile-proxy-node/current`.

The required normal path is `first_party_reverse_tunnel`; `first_party_android_egress` is the
validated carrier-specific egress owner where Android `Network.bindSocket()` is required. Stock
WireGuard remains an explicit rollback path. Unknown or contradictory ownership fails closed.

The private read-only GitHub Actions runner/device preflight is implemented and has passed against
the registered phone without publishing its raw identifier or mutating the device. Mutable phone
deployment/update/verify/rollback is **not yet enabled**: signing-continuity gate #115 remains OPEN,
and the complete mutable private-caller path must be protected before any phone mutation. Manual/raw
ADB is not an authorised production shortcut.

## Relay VM

The currently running relay is a legacy pre-Vultr deployment. Its exact provider account, host,
instance name, zone/address and SSH recovery details are external operational state and are not
canonical desired state for the next production path.

Logical runtime layout remains:

- control plane service;
- reverse-tunnel server;
- relay readiness gate;
- public proxy edge;
- canonical SQLite control-plane state;
- public compatibility listeners `1080`, `1081` and `3128`;
- QUIC primary reverse transport with certificate-pinned TLS/TCP reserve.

Vultr lifecycle operations use GitHub-hosted Actions and the typed ownership adapter required by
`contracts/governance/vm-ownership-v1.json`: immutable provider UUID binding, exact
`project=mobile-proxy` and `managed-by=mobile-proxy` tags, ownership intent/generation semantics and
fail-closed behavior on ambiguity or mismatch. Pre-release acceptance uses the bounded
`acceptance-vultr` capability; final production uses tag-only `production-vultr` only after final
release authority exists.

The typed lifecycle and its bounded Item 19 provider proof are complete. Item 19 deployed and
verified immutable candidate `d151dbdd156279e32a5361d304c90f996bd2d565` on one controlled
acceptance VM and deterministically deleted that proof VM before terminal state. Its terminal Item 19
ownership intent is not reusable by Item 20.

The legacy GCP/workstation provisioning path is retained only as historical implementation context;
it is not the standard acceptance or production control plane and the public deploy workflow
intentionally blocks it during migration.

## Public data path

The protected logical production path remains:

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
- stock WireGuard: explicit rollback.

A reported connected state alone is insufficient. Serving authority requires the exact registered
phone/session identity, freshness and successful bounded readiness/proxy checks.

## Control-plane trust zones

```text
PUBLIC canonical: iamaman11/mobile-proxy
  - source / docs / contracts / Quality / releases
  - GitHub-hosted Vultr orchestration
  - safe evidence index

PRIVATE execution satellite: iamaman11/mobile-proxy-production
  - thin caller/shim only
  - android-production runner access
  - private physical execution/supporting evidence
```

The immutable software candidate used for pre-release acceptance and the moving protected
control-plane revision are separate semantic identities. Final production correlates both targets by
the immutable release tuple and deployment ID defined in
`contracts/operations/project-authority-v1.json`.

## Current migration status

- public GitHub governance/control-plane split: documented and contract-enforced;
- legacy public production deployment: blocked fail-closed;
- private read-only phone runner/registered-device preflight: implemented and passed;
- immutable pre-release acceptance authority: implemented and proven;
- GitHub-hosted Vultr read-only preflight: implemented and proven;
- provider-neutral lifecycle plus typed Vultr ownership adapter: implemented;
- Item 19 bounded provider proof: complete, exact candidate verified and proof VM deleted;
- Item 20: first unfinished delivery item; protected non-live orchestration/readiness foundations
  exist, but live physical execution remains blocked by #115 and session workflow composition is not
  yet complete;
- mutable phone install/update/verify/rollback: blocked until #115 signing continuity and the
  protected mutable execution path are satisfied;
- final annotated release publication, release immutability and `production-vultr` promotion:
  pending and forbidden before Item 20 succeeds.

No item in this status authorizes a VM or phone mutation outside the reviewed GitHub Actions path.
