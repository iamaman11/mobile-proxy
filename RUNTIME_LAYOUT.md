# Runtime Layout

This document describes the canonical runtime topology and safe operational facts. Exact live
provider identifiers, device serials, secret values and workstation paths are intentionally kept out
of the public repository. Their schemas and invariants are versioned here; their live values remain
inside the protected runtime boundary.

For project/repository authority see `docs/operations/project-authority.md`.

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

Phone deployment/verification is currently **not GitOps-enabled** in the new split control plane.
Until the canonical private-caller workflow is implemented and proven, manual/raw ADB is not an
authorised production shortcut.

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

The target VM control plane is Vultr through a GitHub-hosted Actions job in `production-vultr`.
Before any provider lifecycle operation is enabled, the typed adapter must satisfy
`contracts/governance/vm-ownership-v1.json`: immutable provider UUID binding, exact
`project=mobile-proxy` and `managed-by=mobile-proxy` tags, generation/CAS semantics and fail-closed
behavior on ambiguity or mismatch.

The legacy GCP/workstation provisioning path is retained only as historical implementation context;
it is not the standard production control plane and the public deploy workflow intentionally blocks
it during migration.

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

Both targets are correlated by one immutable canonical release tuple and deployment ID defined in
`contracts/operations/project-authority-v1.json`.

## Current migration status

- public GitHub governance/control-plane split: documented and contract-enforced;
- legacy public production deployment: blocked fail-closed;
- private phone execution satellite: initialized, no production command workflow enabled;
- live Vultr preflight: pending;
- typed Vultr lifecycle: pending;
- live phone runner/device preflight: pending;
- phone deploy/verify/rollback: pending;
- release-control command channel and corrected immutable release publication flow: pending.

No item in this status authorizes a VM or phone mutation outside the reviewed GitHub Actions path.
