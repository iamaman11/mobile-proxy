# Mobile Proxy

Rust-first mobile relay for exposing authenticated proxy services through a rooted Android device and its cellular connection.

## Project authority

Mobile Proxy has one product and two authoritative planes:

| Plane | Repository | Owns |
| --- | --- | --- |
| PRODUCT | `iamaman11/mobile-proxy` | application/runtime source, shared product/domain architecture, Quality, Linux/Android product build, Android signing verification, annotated product tags, immutable Product Releases and product documentation |
| DEPLOYMENT CONTROLLER | `iamaman11/mobile-proxy-production` | deployment ingress, deployment State Machine / Transaction Kernel, target admission/serialization/observation, target adapters, durable mutation intent, exactly-once destructive dispatch, postconditions, recovery/quarantine, private bindings/secrets and canonical runtime execution evidence |

The public repository is the canonical PRODUCT source. The private repository is the canonical deployment controller. It is not a second product source and must not independently build, sign, tag or publish Mobile Proxy.

The normative boundary is defined by:

- [Project authority](docs/operations/project-authority.md)
- [`project-authority-v2.json`](contracts/operations/project-authority-v2.json)
- [`github-control-plane-v2.json`](contracts/operations/github-control-plane-v2.json)
- [`production-topology-v2.json`](contracts/operations/production-topology-v2.json)
- [`product-release-authority-v2.json`](contracts/operations/product-release-authority-v2.json)

Older v1 authority/topology/control-plane wording is historical when it conflicts with these v2 contracts.

## Start here after context loss

Read in this order:

1. [Quick Reference](QUICK_REFERENCE.md) — current authority and navigation;
2. [Agent operating contract](AGENTS.md) — repository workflow and safety boundaries;
3. [Implementation Plan](IMPLEMENTATION_PLAN.md) — concise current development sequence;
4. [Production Baseline Plan](docs/PRODUCTION_BASELINE_PLAN.md) — the active 10/10 roadmap;
5. [Repository Map](REPOSITORY_MAP.md) and [Runtime Layout](RUNTIME_LAYOUT.md) — code placement and runtime topology;
6. [Git delivery](docs/GIT_DELIVERY.md) — product release and deployment-controller handoff.

Public Issue #179 is the authoritative migration/development checkpoint stream and authorizes one bounded next engineering item at a time. Public Issue #228 is the 10/10 PRODUCT-hardening backlog only. Private Issue #1 is the Deployment Controller command surface and canonical runtime ledger.

## Production architecture

The normal rooted runtime does **not** require Android `VpnService`.

```text
root/Magisk boot service
  -> runtime-supervisor
      -> host-daemon
      -> sing-box on loopback
          -> certificate-pinned QUIC reverse tunnel
          -> certificate-pinned TLS/TCP reserve
              -> relay VM public proxy ports
```

The default tunnel owner is `first_party_reverse_tunnel`. It uses no `tun0` and requires no active Android VPN. Unknown, missing or contradictory tunnel ownership fails closed.

On carriers that do not route root-owned sockets through the validated INTERNET data network, `first_party_android_egress` uses Android `Network.bindSocket()` for cellular egress while the authenticated reverse tunnel and server control plane remain authoritative. This mode does not create an Android VPN.

The Android project under `apps/android-app` is a managed product component for Android-owned capabilities, including cellular egress and the app-owned WireGuard compatibility path. Whether it must be installed is a deployment-controller decision derived from the exact Product Release and observed target state.

## Public compatibility surface

The relay preserves:

- mixed SOCKS5/HTTP proxy on `1080`;
- SOCKS5 proxy on `1081`;
- HTTP proxy including CONNECT on `3128`;
- QUIC as primary reverse transport;
- certificate-pinned TLS/TCP as automatic reserve;
- explicit stock WireGuard rollback;
- app-owned WireGuard compatibility path.

All public proxy paths require authentication. When no fresh authenticated device session is available, the relay fails closed rather than routing to an arbitrary device or silently downgrading to plaintext.

Use the dedicated `3128` endpoint for production HTTP/HTTPS clients. Port `1080` remains a mixed compatibility endpoint.

## Repository layout

- `crates/foundation` — bounded identifiers and typed internal BLAKE3 contracts;
- `crates/application` — transport-independent product/application ports;
- `crates/control-plane-sqlite` — product control-plane durable SQLite state and migrations;
- `crates/reverse-tunnel` — reverse-tunnel protocol, QUIC/TLS transport and proxy forwarding;
- `apps/operator-cli` — product/operator primitives; not a workstation production-deployment authority;
- `apps/android-app` — Android product component;
- `services/runtime-supervisor` — rooted phone process/recovery product component;
- `services/host-daemon` — phone-local health, rotation and runtime integration;
- `services/control-plane` — durable product control plane;
- `services/reverse-tunnel-server` — relay-side reverse-tunnel endpoint;
- `services/relay-gate` — relay readiness gate;
- `deploy` — product runtime templates/manifests and packaging inputs;
- `contracts` — product, governance and cross-plane authority contracts;
- `scripts` — product build/verification tooling plus legacy physical-control surfaces pending v2 ownership cleanup;
- `.github/workflows` — public PRODUCT CI/build/release workflows plus historical/development acceptance surfaces pending cleanup.

Existing public physical transaction/controller files are not runtime deployment authority merely because they still exist in the tree. Their final disposition is handled by the bounded source-ownership migration through Issue #179.

## Cryptographic policy

Project-owned internal content/fingerprint digests use typed BLAKE3-256:

```text
b3:<64 lowercase hexadecimal characters>
```

SHA-256 remains only where an external standard requires it, such as TLS/certificate fingerprints, Cargo registry checksums, GitHub artifact digests, OCI/SBOM/signature formats or other interoperability contracts.

Release roots contain a sorted integrity manifest covering packaged files with typed BLAKE3 and exact sizes. Product Release provenance is public PRODUCT evidence; deployment runtime truth remains private-controller evidence.

## Build and quality

```bash
cargo fmt --all -- --check
python3 scripts/check_architecture_boundaries.py
python3 -m unittest discover -s scripts/tests -p 'test_*.py'
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

For the repository gate:

```bash
scripts/quality-gate.sh       # full code and Android gate
scripts/quality-gate.sh fast  # docs/policy-sized changes
```

GitHub exposes one aggregate required check named `Quality Gate`. Agents should read the compact quality-summary artifact before loading detailed logs.

## Product Release and deployment

The authority order is:

```text
protected public main + exact successful Quality
  -> annotated semantic product tag
  -> public signed PRODUCT build
  -> immutable Product Release v2
  -> private /deploy <target> <tag>
  -> private controller admission / observation / possible mutation / verification / recovery
```

A Product Release is an immutable input to deployment. Physical acceptance is **not** a prerequisite for creating the Product Release under v2.

Runtime deployment identity combines:

```text
exact immutable Product Release
+ exact admitted private controller revision
```

`latest`, a mutable branch, a public GitHub Deployment record or Issue #179 narrative are never sufficient runtime identity.

The public PRODUCT repository has no production self-hosted runner and performs no production phone/ADB mutation. The private Deployment Controller owns target access and mutation. `vm-production` remains fail-closed until its private target adapter is proven end-to-end.

Manual SSH, raw/manual ADB, workstation deployment commands and provider CLI are not normal production control paths.

## Product and deployment safety

The Deployment Controller must preserve:

```text
state -> guard -> operation -> effect -> independent observation -> resulting state
```

Before destructive dispatch it persists durable mutation intent. A durable intent admits at most one destructive dispatch. Ambiguous post-dispatch outcome enters read-only recovery; there is no blind destructive retry and `RECOVERED != ACCEPTED`.

The public GitHub Deployment API is a bounded status/history projection only. Canonical runtime execution truth is the private controller ledger.

## 10/10 status terminology

- **PRODUCT 10/10-ready**: public source-controlled security, behavior, Quality, build, release-gate and provenance requirements are satisfied on exact reviewed source identities.
- **Deployment Controller accepted**: exactly-once mutation, target observation, canonical terminal evidence and recovery/quarantine invariants are independently proven in the private controller.
- **Full production 10/10 accepted**: PRODUCT and Deployment Controller evidence are both complete and the explicitly authorized live target acceptance/soak sequence has passed without unresolved P0/P1 defects.

The active ordered roadmap is [Production Baseline Plan](docs/PRODUCTION_BASELINE_PLAN.md). The latest authoritative #179 checkpoint always controls what may happen next.
