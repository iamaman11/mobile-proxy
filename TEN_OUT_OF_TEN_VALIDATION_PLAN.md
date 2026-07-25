# 10/10 Reproducibility and Reliability Validation Plan

Status: normative acceptance matrix  
Primary runtime: `first_party_reverse_tunnel`  
Rollback runtime: `stock_wireguard_bridge`

## 1. Meaning of 10/10

The project uses two distinct statuses:

1. **Software 10/10-ready** — every source-controlled, process-testable, dependency, Android-build and immutable-SHA gate passes on one exact commit.
2. **10/10 accepted / baseline complete** — the same immutable commit also passes the complete real-phone, real-network, rollback, recovery and soak matrix below.

Passing CI is necessary but cannot prove Android boot behavior, modem policy routing, carrier QUIC blocking, real cellular egress, real WireGuard handshake or long-running recovery. Therefore software evidence always sets `physical_phone_acceptance_required=true` and `baseline_complete=false`.

## 2. Normative architecture

The primary phone path is:

```text
root/Magisk boot hook
  -> runtime-supervisor
      -> host-daemon
      -> sing-box on 127.0.0.1
          -> certificate-pinned QUIC reverse tunnel
          -> certificate-pinned TLS/TCP reserve
```

Primary invariants:

- `tunnel_owner=first_party_reverse_tunnel`;
- `wireguard.enabled=false`;
- no active Android VPN owner;
- no `tun0` requirement;
- QUIC is primary;
- TLS/TCP reserve is certificate-pinned;
- plaintext downgrade is forbidden;
- device and tunnel-session identity are exact;
- routing never selects an arbitrary available device.

`stock_wireguard_bridge` is an explicit emergency rollback only. The optional Android app is not installed by the production stack and is not a supported production tunnel owner.

## 3. Immutable software gate

All checks must pass on one clean, unchanged Git SHA:

### Architecture and policy

- application/domain dependency boundaries;
- native reverse-tunnel default enforcement;
- no Android VPN dependency in production package/install/runtime/verify;
- unknown or contradictory tunnel ownership fails closed;
- bounded logs, errors, enums, queues and retries;
- source-controlled migration and rollback procedures.

### Cryptographic and release integrity

- internal release/config/binary digests use typed BLAKE3-256;
- static domain separation and length framing are enforced;
- direct first-party SHA-256 and untyped BLAKE3 are rejected in production Rust, Python, shell and Kotlin;
- externally mandated algorithms remain unchanged;
- release roots contain sorted BLAKE3 manifests and exact sizes;
- phone and VM deployment identity is checked byte-for-byte after BLAKE3 package verification;
- evidence contains the exact full Git SHA and a clean-worktree assertion.

### Rust quality and supply chain

- `cargo fmt --all -- --check`;
- `cargo clippy --workspace --all-targets -- -D warnings`;
- `cargo test --workspace`;
- RustSec advisory audit;
- cargo-deny advisories, licenses, bans and sources.

### Optional Android scaffold quality

The Android project is not a production tunnel dependency, but its checked-in source must remain buildable and safe:

- unit tests;
- lint with warnings as errors;
- debug assembly;
- backup disabled;
- VPN service non-exported;
- no production runtime reference to the app-owned VPN service.

### Durable state and operations

- SQLite is the sole canonical mutable control-plane store;
- migrations are deterministic and fail closed;
- acknowledged state survives restart;
- replay and idempotency survive restart;
- backup and clean-environment restore pass;
- process liveness is separate from serving readiness;
- readiness reports critical storage and worker state without exposing secrets.

### Reverse-tunnel and proxy acceptance

Controlled process tests must prove:

- mixed `1080` as SOCKS5, HTTP and HTTP CONNECT;
- SOCKS5 `1081`;
- HTTP and CONNECT `3128`;
- forced QUIC failure;
- certificate-pinned TLS/TCP reserve;
- same logical device/session authority;
- release of the QUIC block;
- return to fresh QUIC;
- no plaintext fallback;
- bounded pending registrations and deterministic capacity rejection.

Only after all checks pass may the workflow emit evidence with `software_10_of_10_ready=true`.

## 4. Fresh relay VM drill

Create or recreate a test relay exclusively from repository source, manifests and environment-provided secrets.

Acceptance:

- declared machine type, zone and reserved address are used;
- SSH administration works;
- control plane, relay gate, reverse-tunnel server and Nginx start cleanly;
- missing/corrupt/unsupported SQLite state fails closed;
- SQLite migration and restart preserve state;
- public `1080`, `1081` and `3128` route to reverse-tunnel loopback listeners in native mode;
- QUIC UDP and pinned TLS/TCP endpoints are reachable as designed;
- stock WireGuard backend is installed only for rollback testing;
- provisioning is idempotent;
- delete-and-recreate leaves no orphan test resources and restores the intended endpoint.

The deployed static VM files must exactly match the immutable local VM package. The intentionally switchable Nginx proxy transport configuration is verified separately by exact bytes after every switch.

## 5. Fresh rooted-phone drill

Use a clean detached checkout of the immutable candidate and a freshly prepared rooted phone.

Acceptance:

- root access is proven before installation;
- no production Android APK installation is required;
- architecture-correct native binaries are packaged;
- the package BLAKE3 manifest verifies locally;
- package metadata names the exact candidate SHA and clean tree;
- the install copies all package files exactly;
- active phone files compare byte-for-byte with the package;
- the Magisk/service.d hook starts only the active rooted release;
- `runtime-supervisor` owns `host-daemon` and `sing-box`;
- local health becomes healthy and serving;
- control plane receives a durable heartbeat;
- `tunnel_owner=first_party_reverse_tunnel`;
- `wireguard_enabled=false`;
- no Android VPN owner and no lingering `tun0`;
- public authenticated proxy traffic exits through the phone carrier IP.

## 6. Immutable physical stage sequence

Run `docs/physical-phone-acceptance-runbook.md` and validate the resulting bounded report set automatically.

Required stages:

1. **online** — clean startup, fresh QUIC and all six proxy protocol checks;
2. **post-reboot** — full phone reboot, service rehydration, durable inventory and fresh QUIC;
3. **fallback** — QUIC blocked while pinned TLS/TCP remains available, all proxy paths pass;
4. **recovered** — QUIC restored, new connections return to fresh QUIC;
5. **wireguard** — explicitly installed stock WireGuard release owns Android VPN, `tun0` exists, handshake is recent, reverse tunnel is inactive and all proxy paths pass;
6. **post-wireguard-recovered** — the exact already-installed native release is reactivated without rebuilding, WireGuard is stopped, `tun0` disappears and fresh QUIC plus all proxy paths return.

The final report validator must prove:

- one candidate SHA;
- one phone/device ID;
- three exact deployment reports;
- three exact VM transport switches;
- one exact native release reactivation;
- all six accepted stages;
- no tokens, keys, passwords, credential URLs or unrestricted logs in evidence.

## 7. Repeated recovery matrix

A single successful physical run is not enough for 10/10.

### Phone-side repetitions

- 20 full phone reboots;
- 20 `runtime-supervisor` forced terminations;
- 20 `host-daemon` forced terminations;
- 20 `sing-box` forced terminations;
- 20 mobile-data disconnect/reconnect events;
- 10 forced QUIC-block/TLS-reserve/QUIC-return cycles;
- 5 native-to-stock-WireGuard-to-native rollback cycles;
- 30 managed IP rotations at the selected hold window.

### Relay-side repetitions

- 20 control-plane restarts;
- 20 reverse-tunnel-server restarts;
- 20 relay-gate restarts;
- 20 Nginx reloads;
- 10 full VM reboots;
- one clean backup restore;
- one VM delete-and-recreate drill.

Every operation records UTC start, recovery completion, observed transport, device ID, resulting public IP where applicable and bounded reason codes. Secrets and unbounded logs are forbidden.

## 8. Reliability thresholds

For each repeated category and for the combined set:

- automatic recovery success rate: **at least 99.5%**;
- median recovery time: **under 20 seconds**;
- p95 recovery time: **under 60 seconds**;
- no silent stuck state longer than **60 seconds**;
- no success while proxy traffic fails;
- no success while tunnel freshness is stale;
- no unresolved degraded state without a bounded machine-readable reason;
- no cross-device or stale-session routing;
- no plaintext downgrade;
- no lost acknowledged durable operation.

With small fixed sample counts, a single unexplained failure blocks acceptance even where the nominal percentage calculation would round above the threshold. Failures must be fixed, software evidence regenerated on a new SHA and the affected matrix repeated from the beginning.

## 9. Rotation timing gate

For each supported phone/operator profile:

- evaluate candidate hold windows with at least 30 runs each;
- select the shortest window with at least 99% IP-change success and return to fresh serving state;
- reject false success when the IP does not change where change is required;
- reject success when phone-local health is good but public proxy traffic or reverse-tunnel freshness is not;
- preserve the selected value in the versioned operator profile.

Historical measurements are diagnostic only. Each materially different phone model, Android version, modem firmware or operator profile requires its own current matrix.

## 10. Soak and resource gate

Run at least a 24-hour production-like soak after the repeated recovery matrix.

During soak:

- authenticated checks of every proxy protocol path at least once per minute;
- tunnel owner, active transport, freshness, process health and public egress recorded as bounded metrics;
- periodic controlled rotations;
- at least one controlled relay process restart;
- no unbounded growth in memory, file descriptors, SQLite/WAL files, pending streams, logs or retry queues;
- no credential leakage in process arguments, logs, metrics, reports or error bodies;
- no unexplained outage longer than 60 seconds.

Resource limits are accepted from measured baselines, not arbitrary absolute numbers. A monotonic leak or unbounded queue blocks acceptance regardless of remaining machine capacity.

## 11. Security and operational review

Before final closeout:

- verify firewall exposure matches the documented ports only;
- verify admin/device/proxy credentials are distinct and environment-resolved;
- verify certificate pinning rejects the wrong certificate;
- verify wrong tokens and credentials fail without reflecting secrets;
- verify release and backup permissions;
- verify rollback does not rebuild or silently mutate the tested package;
- verify SQLite backup restoration on a clean path;
- review dependency audit results and exceptions;
- document any accepted residual risk with owner and expiry.

A full independent penetration test, signed provenance or fleet orchestration is outside the current production baseline unless separately activated. Their absence must not be disguised as completed assurance.

## 12. Final decision

Declare **10/10 accepted / baseline complete** only when:

- immutable software evidence says `software_10_of_10_ready=true`;
- the complete physical summary says `physical_phone_acceptance_complete=true` and `accepted=true`;
- repeated recovery thresholds pass;
- the 24-hour soak passes;
- there is no unresolved P0/P1 defect;
- all evidence belongs to the same immutable Git SHA;
- final documentation names the accepted SHA, workflow runs, evidence artifact and physical report set.

Any source or package-root change invalidates the candidate and requires the complete software and physical sequence on a new immutable SHA.
