# Mobile Proxy

Rust-first mobile relay for exposing authenticated proxy services through a rooted Android device and its cellular connection.

## Production architecture

The normal device runtime does **not** use Android `VpnService`.

```text
root/Magisk boot service
  -> runtime-supervisor
      -> host-daemon
      -> sing-box on loopback
          -> certificate-pinned QUIC reverse tunnel
          -> certificate-pinned TLS/TCP reserve
              -> relay VM public proxy ports
```

The default tunnel owner is `first_party_reverse_tunnel`. It uses no `tun0` and requires no active Android VPN. The rooted runtime also supports explicit carrier and rollback owners. Unknown, missing or contradictory tunnel ownership fails closed.

On carriers that do not route root-owned sockets through the validated INTERNET data network, use `first_party_android_egress`. The authenticated reverse tunnel and server control plane remain authoritative, while both proxy upstream sockets and the pinned TLS reserve are created through the app's `Network.bindSocket()` cellular egress. This mode does not create an Android VPN.

The Android project under `apps/android-app` remains optional for the primary rooted runtime, but it is now the supported owner for the app-owned WireGuard compatibility path. Normal native reverse-tunnel packaging, installation and verification still do not require an active Android VPN.

## Public compatibility surface

The relay preserves:

- mixed SOCKS5/HTTP proxy on `1080`;
- SOCKS5 proxy on `1081`;
- HTTP proxy including CONNECT on `3128`;
- QUIC as primary reverse transport;
- certificate-pinned TLS/TCP as automatic reserve;
- explicit stock WireGuard rollback;
- app-owned WireGuard compatibility path.

All public proxy paths require authentication. The reverse-tunnel control frame carries the selected proxy protocol, so SOCKS5 streams terminate at the phone's dedicated `1081` inbound and HTTP/CONNECT streams at `3128`; the mixed public port is detected before forwarding. When no fresh authenticated device session is available, the relay fails closed rather than routing to an arbitrary device or silently downgrading to plaintext.

Use the dedicated `3128` endpoint for production HTTP/HTTPS clients. Port `1080` remains a mixed SOCKS5/HTTP compatibility endpoint and should not be selected when the consumer can choose a dedicated protocol port.

## Repository layout

- `crates/foundation` — bounded identifiers and the typed internal BLAKE3 contract;
- `crates/application` — transport-independent application ports;
- `crates/control-plane-sqlite` — canonical durable SQLite state and migrations;
- `crates/reverse-tunnel` — QUIC/TLS transport and proxy forwarding;
- `apps/operator-cli` — packaging, deployment, verification, rotation and rollback;
- `services/runtime-supervisor` — rooted phone process and recovery owner;
- `services/host-daemon` — phone-local health, rotation and control-plane synchronization;
- `services/control-plane` — durable device/command control plane;
- `services/reverse-tunnel-server` — relay-side reverse-tunnel endpoint;
- `services/relay-gate` — relay readiness gate;
- `deploy` — reproducible runtime templates and manifests;
- `scripts` — permanent architecture, digest and acceptance gates.

## Cryptographic policy

Project-owned internal content and fingerprint digests use typed BLAKE3-256:

```text
b3:<64 lowercase hexadecimal characters>
```

They are derived through `mobile-proxy-foundation::ContentDigest` with a versioned static domain and length framing for every input part. Direct untyped BLAKE3 and new first-party SHA-256 contracts are rejected across production Rust, Python, shell and Kotlin source.

SHA-256 remains only where an external standard requires it, such as TLS/certificate fingerprints, Cargo registry checksums, GitHub artifact digests, OCI/SBOM/signature formats or other interoperability contracts. Passwords are not content-hashed; protocol KDF/MAC/signature/encryption algorithms are not replaced with BLAKE3.

Release roots contain a sorted `integrity-manifest.json` covering every packaged file with typed BLAKE3 and exact sizes. Deployment acceptance first verifies that manifest, then compares active phone and VM files byte-for-byte with the immutable local package.

## Prerequisites

For the primary device runtime:

- rooted Android device;
- ADB access with `adb shell su 0 sh -c id` returning `uid=0`;
- architecture-correct `runtime-supervisor`, `host-daemon` and `sing-box` binaries prepared under `deploy/device-runtime/bin`;
- device and relay manifests;
- required secrets provided only through environment variables;
- generated reverse-tunnel certificate identity and phone certificate pin.

The Android APK and stock WireGuard are not primary-runtime prerequisites. Stock WireGuard is needed only to exercise the documented rollback gate.

## Build and quality

```bash
cargo fmt --all -- --check
python3 scripts/check_architecture_boundaries.py
python3 -m unittest discover -s scripts/tests -p 'test_*.py'
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

For the exact local gate, use:

```bash
scripts/quality-gate.sh       # full code and Android gate
scripts/quality-gate.sh fast  # architecture, Python tests, formatting and diff hygiene
```

GitHub runs one aggregate required check named `Quality Gate`. It executes policy, Rust,
supply-chain and Android checks in parallel and publishes a compact
`quality-summary-<git-sha>` artifact. Agents should read that summary before loading large
job logs. The pinned toolchain is defined in `rust-toolchain.toml`.

The mandatory GitHub quality workflows additionally run:

- RustSec advisories, dependency licenses, bans and sources through pinned cargo-deny;
- Android scaffold unit tests;
- Android lint with warnings as errors;
- Android debug assembly;
- process-level liveness/readiness tests;
- SQLite migration, backup and clean restore drills;
- forced QUIC failure, pinned TLS/TCP reserve and QUIC recovery;
- mixed `1080`, SOCKS5 `1081`, HTTP and CONNECT proxy coverage.

## Git delivery

Code reaches production only through an annotated semantic-version tag that passed
`Quality Gate` and produced a published GitHub Release. `Deploy Production` resolves that
tag to one immutable SHA, waits for approval in the `production` environment, then uses the
dedicated runner to deploy and verify the VM followed by the Android device.

Operational secrets stay in the local Secret Vault on the trusted runner and are injected only
into child deployment processes. See [Git delivery and production control](docs/GIT_DELIVERY.md)
for repository settings, release commands, rollback and runner setup.

## Prepare runtime binaries

```bash
cargo run -p operator-cli -- prepare-runtime-binaries
```

Generated runtime binaries are intentionally not committed. The packaging command verifies the expected Android ARM ELF architecture before creating a release.

The sing-box version, upstream GitHub asset SHA-256 provenance and typed BLAKE3 content
digests are pinned in `deploy/sing-box-artifacts.lock.json`. Preparation fails closed when
the requested version, archive size, content digest, executable version or rendered
production configuration does not match. A successfully validated candidate is installed
atomically and the previous local binary is retained as `sing-box.rollback` in the ignored
binary directory.

## Generate reverse-tunnel identity

```bash
cargo run -p operator-cli -- generate-reverse-tunnel-identity \
  --output-env-file .secrets/reverse-tunnel.env
```

`.secrets/` is ignored by Git. Secret files are local-only and permission-restricted.

## Package and install the primary device runtime

`first_party_reverse_tunnel` is the default; passing it explicitly is optional but useful in runbooks:

```bash
cargo run --release -p operator-cli -- package-device-release \
  --manifest-path deploy/manifests/devices/example-device.json \
  --release-id candidate-native \
  --tunnel-owner first_party_reverse_tunnel

cargo run --release -p operator-cli -- install-device-stack \
  --manifest-path deploy/manifests/devices/example-device.json \
  --release-id candidate-native \
  --device-serial <adb-serial> \
  --tunnel-owner first_party_reverse_tunnel
```

Packaging requires a clean Git worktree, validates and JSON-escapes all template values, rejects unresolved placeholders, writes exact Git SHA metadata and verifies the finished BLAKE3 manifest. Installation validates root-shell inputs, copies the release, restarts the rooted runtime and compares deployed files byte-for-byte.

## Verify the primary runtime

```bash
cargo run --release -p operator-cli -- verify-device \
  --manifest-path deploy/manifests/devices/example-device.json \
  --device-serial <adb-serial> \
  --required-tunnel-owner first_party_reverse_tunnel
```

Verification requires healthy serving state, the exact native owner, no active Android VPN and a successful authenticated public proxy smoke test unless explicitly skipped for a bounded diagnostic reason.

## Provision the relay VM

```bash
cargo run --release -p operator-cli -- provision-vm \
  --manifest-path deploy/manifests/vms/example-gcp-relay.json \
  --release-id candidate-vm \
  --ssh-user <vm-user> \
  --ssh-key <absolute-key-path>
```

The VM hosts the control plane, reverse-tunnel server, readiness gate, authenticated public proxy and the optional WireGuard compatibility backend used by both the stock rollback path and the app-owned VPN path.

The production `optimized-hybrid` route keeps public `1080`, `1081` and `3128` on the proven phone
mixed-proxy path through the pinned TLS reverse tunnel to Android cellular egress. The port numbers
and client protocols remain unchanged. VM sing-box termination remains an explicit comparison and
rollback mode, but is not in the production data path.
The TLS fallback maintains eight authenticated idle data streams per phone session, so a burst
of five consumers reuses established cellular connections instead of starting five simultaneous
TCP and TLS handshakes. Capacity remains bounded and the legacy on-demand stream remains a
compatible overflow path. Activated streams are replenished immediately instead of waiting for the
proxied request to finish.

## Rotate cellular identity

For agents and remote operators, install `scripts/mobile-proxy-ip` on `PATH` and provision the
mode-`600` client config shown in `deploy/client/mobile-proxy-ip.env.example` once. Rotation is then
one command, uses no ADB, and does not expose admin or UI credentials:

```bash
mobile-proxy-ip
```

On the operator host, the wrapper automatically consumes the existing `mobile-proxy.rotation-token`
and certificate records from Secret Vault, so no plaintext client config is created.

For programs, select JSON output. Exit code zero means the IP changed and the public proxy plus
fresh reverse tunnel recovered. The result contains `old_ip`, `new_ip`, elapsed time, readiness and
both local and public serving state:

```bash
mobile-proxy-ip --format json
```

The client talks only to `/api/v1/rotation/devices/{id}` with a dedicated rotation token. It
generates an idempotency key, safely retries transient command submission, waits for the server and
requires a different IP, healthy readiness, public serving and a fresh reverse tunnel before
reporting success. The legacy `rotate-server` CLI name remains available for compatibility.

The older `rotate` command below targets the phone-local operator API and is intended for device
maintenance and diagnostics:

```bash
cargo run --release -p operator-cli -- rotate \
  --strategy airplane_bounce \
  --require-public-ip-change true
```

A rotation is successful only when the public IP changes as required and the native reverse tunnel returns fresh and serving. A healthy phone-local process alone is insufficient.

## Rollback

Release rollback performs a full runtime restart rather than only changing a symlink:

```bash
cargo run --release -p operator-cli -- rollback-device \
  --manifest-path deploy/manifests/devices/example-device.json \
  --device-serial <adb-serial> \
  --release-id <installed-release-id>
```

Stock WireGuard rollback is exercised only through the immutable physical acceptance runbook. After that stage, the same already-installed native release must be reactivated without rebuilding, `tun0` must disappear and fresh QUIC service must return.

## Release status terminology

- **Software 10/10-ready** means every source-controlled, process-testable, dependency, Android build and immutable-SHA acceptance gate has passed on one exact commit.
- **Baseline complete / 10/10 accepted** additionally requires the real-phone sequence, repeated recovery drills and soak thresholds in `TEN_OUT_OF_TEN_VALIDATION_PLAN.md`.

Software evidence must never claim the baseline is complete. A source change invalidates the candidate and requires all software evidence to be regenerated before physical testing.

The canonical implementation scope is `docs/PRODUCTION_BASELINE_PLAN.md`. The executable device procedure is `docs/physical-phone-acceptance-runbook.md`.
