# Mobile Proxy

Rust-first mobile relay for exposing authenticated proxy services through a rooted Android device and its cellular connection.

## Project authority

Mobile Proxy has one product and two authoritative planes. **Both repositories are public.**

| Plane | Repository | Owns |
| --- | --- | --- |
| PRODUCT | `iamaman11/mobile-proxy` | application/runtime source, shared product/domain architecture, Quality, Linux/Android product build, Android signing verification, annotated product tags, immutable Product Releases and product documentation |
| DEPLOYMENT CONTROLLER | `iamaman11/mobile-proxy-production` | deployment ingress, deployment State Machine / Transaction Kernel, target admission/serialization/observation, target adapters, durable mutation intent, exactly-once destructive dispatch, postconditions, recovery/quarantine and canonical runtime execution evidence |

The PRODUCT repository is not deployment transaction authority. The Controller repository is not a second product source and must not independently build, sign, tag or publish Mobile Proxy. Secret values, target bindings, raw target identifiers and sensitive runtime evidence remain private even though Controller source/policy is public.

The normative boundary is defined by:

- [Project authority](docs/operations/project-authority.md)
- [`project-authority-v2.json`](contracts/operations/project-authority-v2.json)
- [`github-control-plane-v2.json`](contracts/operations/github-control-plane-v2.json)
- [`production-topology-v2.json`](contracts/operations/production-topology-v2.json)
- [`product-release-authority-v2.json`](contracts/operations/product-release-authority-v2.json)

Older v1 authority/topology/control-plane wording is historical when it conflicts with these v2 contracts.

## Start here after context loss

Use exactly this execution spine:

1. [Agent operating contract](AGENTS.md);
2. [Universal Stage Workflow](STAGE_WORKFLOW.md);
3. newest authoritative checkpoint in PRODUCT Issue **#179**;
4. the current subordinate Stage Issue;
5. only then open stage-relevant standards/contracts/reference docs.

Useful static references after the current stage is known:

- [Quick Reference](QUICK_REFERENCE.md);
- [Implementation Plan](IMPLEMENTATION_PLAN.md);
- [Production Stage Roadmap](docs/PRODUCTION_STAGE_ROADMAP.md);
- [Production Baseline Architecture and Invariants](docs/PRODUCTION_BASELINE_PLAN.md);
- [Architecture Standard](docs/architecture/ARCHITECTURE_STANDARD.md);
- [10/10 Validation Catalog](TEN_OUT_OF_TEN_VALIDATION_PLAN.md);
- [Repository Map](REPOSITORY_MAP.md) and [Runtime Layout](RUNTIME_LAYOUT.md);
- [Git delivery](docs/GIT_DELIVERY.md).

PRODUCT Issue #179 is the sole dynamic stage/operations cursor. PRODUCT Issue #249 is planning/acceptance backlog only. PRODUCT Issue #90 is the Product Release/tag command surface where the current Product Release contract requires it. Controller Issue #1 is the deployment command surface and canonical runtime ledger.

Static docs do not define the current stage, current Product Release, current SHA or next bounded action.

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

The Android project under `apps/android-app` is a managed product component for Android-owned capabilities, including cellular egress and the app-owned WireGuard compatibility path. Whether it must be installed is a Controller admission/deployment decision derived from the exact Product Release and observed target state.

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
- `scripts` — product build/verification tooling plus any bounded historical/control migration surfaces pending stage-mapped simplification;
- `.github/workflows` — PRODUCT CI/build/release plus bounded historical/development acceptance surfaces; no production target mutation authority.

Historical physical transaction/controller files in the PRODUCT tree do not become runtime authority merely because they exist. Their disposition is stage-mapped; Stage 5 is the primary phone-baseline simplification point.

## Cryptographic policy

Project-owned internal content/fingerprint digests use typed BLAKE3-256:

```text
b3:<64 lowercase hexadecimal characters>
```

SHA-256 remains only where an external standard requires it, such as TLS/certificate fingerprints, Cargo registry checksums, GitHub artifact digests, OCI/SBOM/signature formats or other interoperability contracts.

Release roots contain a sorted integrity manifest covering packaged files with typed BLAKE3 and exact sizes. Product Release provenance is PRODUCT evidence; deployment runtime truth is Controller evidence.

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
scripts/quality-gate.sh       # full code/release/tooling gate
scripts/quality-gate.sh fast  # docs/policy-sized changes
```

GitHub exposes one aggregate required check named `Quality Gate`. Read the compact quality summary before loading detailed logs.

## Product Release and deployment

The authority order is:

```text
protected PRODUCT source + required Quality
  -> annotated semantic product tag
  -> signed PRODUCT build
  -> immutable Product Release
  -> Controller /deploy <target> <tag>
  -> Controller admission / observation / possible mutation / verification / recovery
```

A Product Release is an immutable input to deployment. Physical acceptance is **not** a prerequisite for creating the Product Release under v2.

Runtime deployment identity combines:

```text
exact immutable Product Release
+ exact admitted Controller revision
```

`latest`, a mutable branch, GitHub Deployment projection or narrative Issue prose are never sufficient runtime identity.

PRODUCT has no production self-hosted runner and performs no production phone mutation. Controller owns target access and mutation. `vm-production` remains fail-closed until Stage 6 is explicitly opened and its target lifecycle is proven.

Manual SSH, raw/manual destructive ADB, workstation deployment commands and provider CLI are not normal production control paths.

## Product and deployment safety

Controller must preserve:

```text
state -> guard -> operation -> effect -> independent observation -> resulting state
```

Before destructive dispatch it persists durable mutation intent. One intent admits at most one destructive dispatch. Ambiguous post-dispatch outcome enters read-only reconciliation; there is no blind destructive retry.

GitHub Deployment API is a bounded status/history projection only. Canonical runtime execution truth is the Controller ledger.

## Phone facts and Controller improvement

Physical phone facts are observed, never guessed. Prefer Controller observation. If a required fact cannot be obtained reliably, request narrow local-agent evidence and classify it as:

- `controller_capability_gap`;
- `human_only_physical_observation`;
- `one_off_observation`.

A demonstrated repeatable/decision-critical capability gap may justify the smallest Controller observer/adapter improvement in the earliest stage it blocks. Human-only and one-off facts do not justify speculative automation. Local-agent assistance never becomes deployment mutation authority.

## Production acceptance terminology

- **PRODUCT accepted**: source-controlled security, behavior, Quality, build, release-gate and provenance requirements are satisfied for the exact Product Release.
- **Controller accepted for a target**: exactly-once mutation, target observation, postcondition and recovery/quarantine invariants are independently proven.
- **Full production accepted**: the seven-stage sequence reaches Stage 7 exit with PHONE+VM end-to-end functional/recovery/load/soak evidence and no unresolved P0/P1.

The static sequence is [Production Stage Roadmap](docs/PRODUCTION_STAGE_ROADMAP.md). The newest authoritative #179 checkpoint always controls what is current and what may happen next.
