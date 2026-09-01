# 10/10 Reproducibility and Reliability Validation Plan

Status: **normative acceptance matrix**  
Active implementation roadmap: `docs/PRODUCTION_BASELINE_PLAN.md`  
Primary runtime: `first_party_reverse_tunnel`  
Rollback runtime: `stock_wireguard_bridge`

## 1. Meaning of 10/10

The project uses two distinct statuses:

1. **Software 10/10-ready** — every source-controlled, process-testable, dependency, Android-build and immutable-SHA gate passes on one exact protected canonical commit.
2. **10/10 accepted / baseline complete** — that same immutable commit also passes the complete real-phone, real-provider/network, migration, rollback, recovery and soak matrix.

Passing CI is necessary but cannot prove Android boot behavior, modem policy routing, carrier QUIC blocking, real cellular egress, signer/install state, real WireGuard handshake or long-running recovery. Software evidence therefore never claims physical acceptance or baseline completion.

## 2. Normative one-SHA release identity

For the final Item 20 -> Item 21 acceptance chain there is one software identity:

```text
candidate_sha
  == control_plane_sha
  == exact protected public main SHA during the acceptance window
  == final_accepted_candidate_sha
  == final annotated tag target SHA
  == source SHA recorded for published artifacts
```

The active Item 20 candidate is selected from the exact current protected `main` after the architecture-reconciliation merge and must receive fresh candidate-specific Quality, software release evidence, acceptance authority, Vultr read-only preflight, provider proof, Android signing/migration evidence where applicable, physical acceptance, recovery evidence and soak evidence.

If protected `main` advances after admission, the acceptance window is stale. Candidate-specific evidence is regenerated and the affected sequence restarts for the new exact SHA. An ancestor SHA is not sufficient final release authority.

Historical Item 19 candidate `d151dbdd156279e32a5361d304c90f996bd2d565` remains immutable historical provider-lifecycle evidence only. Its historical proof is not rewritten and does not make that SHA the active Item 20/final-release candidate.

## 3. Runtime and Android roles

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
- no active Android VPN owner in native mode;
- no `tun0` requirement in native mode;
- QUIC is primary and TLS/TCP reserve is certificate-pinned;
- plaintext downgrade is forbidden;
- device and tunnel-session identity are exact;
- routing never selects an arbitrary available device.

`stock_wireguard_bridge` is an explicit emergency rollback. The Android app is **not the primary reverse-tunnel owner**, but it is a **managed production auxiliary component** for topologies that use first-party Android/cellular `Network.bindSocket()` egress or the app-owned WireGuard compatibility path.

A native topology that does not consume an app capability does not require APK installation. A topology that does consume an app capability must treat the exact package/version/signer/install state and retained signed artifact provenance as candidate-specific production acceptance evidence. Signing continuity and managed migration/update are production lifecycle requirements for those topologies.

## 4. Immutable software gate

All checks pass on one clean, unchanged Git SHA.

### Architecture and policy

- application/domain dependency boundaries;
- native reverse-tunnel default enforcement;
- Android auxiliary role is explicit and cannot silently become the primary tunnel owner;
- unknown or contradictory tunnel ownership fails closed;
- bounded logs, errors, enums, queues and retries;
- source-controlled migration and rollback procedures;
- public canonical repository is policy/source authority;
- private repository is execution-only and cannot become a parallel policy engine.

### Cryptographic and release integrity

- internal release/config/binary digests use typed BLAKE3-256;
- static domain separation and length framing are enforced;
- direct first-party SHA-256 and untyped BLAKE3 are rejected where project policy forbids them;
- externally mandated algorithms remain unchanged;
- release roots contain sorted manifests and exact sizes;
- phone and VM deployment identity is checked against immutable package identity;
- evidence contains the exact full Git SHA and clean-worktree assertion;
- final published artifact provenance records the exact final tag target SHA.

### Rust, supply chain and Android quality

- `cargo fmt --all -- --check`;
- `cargo clippy --workspace --all-targets -- -D warnings`;
- `cargo test --workspace`;
- RustSec/cargo-deny gates;
- Android unit tests, lint and assembly;
- backup disabled and sensitive components non-exported as required;
- no production runtime reference may turn the app-owned VPN service into the default native tunnel owner;
- production release APK signing/package/version contracts remain machine-verified.

### Durable state and operations

- SQLite is the sole canonical mutable control-plane store;
- migrations are deterministic and fail closed;
- acknowledged state, replay and idempotency survive restart;
- backup and clean-environment restore pass;
- liveness is separate from serving readiness;
- readiness reports critical state without exposing secrets.

### Reverse-tunnel and proxy acceptance

Controlled tests prove mixed `1080`, SOCKS5 `1081`, HTTP/CONNECT `3128`, forced QUIC failure, pinned TLS/TCP reserve, return to fresh QUIC, same device/session authority, no plaintext fallback and bounded deterministic capacity handling.

Only after all checks pass may evidence claim `software_10_of_10_ready=true`.

## 5. Provider and phone prerequisites

Item 19 historical provider proof remains historical evidence. Active Item 20 must establish fresh candidate-specific provider readiness/proof for the exact new candidate required by its contract; historical Item 19 ownership intent is not reused.

Before mutable Android migration or Item 20 phone work, all applicable #115/#162 gates must be satisfied. The private execution satellite must be pinned to the exact canonical public SHA and act as a thin transport/runner boundary. It must not duplicate release, issue-state, evidence-schema or acceptance policy that can live canonically in the public repository.

No phone mutation is authorized merely by this document.

## 6. Fresh relay VM drill

Create or recreate a controlled test relay only through the protected provider lifecycle for the active candidate.

Acceptance includes declared topology, exact candidate artifacts, clean service startup, deterministic storage migration/restart, public proxy compatibility, QUIC and pinned TLS/TCP reachability, explicit rollback backend availability, idempotent provisioning and verified cleanup. Exact provider identity remains bounded according to trust-zone policy.

## 7. Fresh rooted-phone drill

Use the exact immutable active candidate and the registered rooted phone.

Acceptance includes:

- root/registered-device proof before mutation;
- exact architecture-correct native package identity;
- local manifest and byte-for-byte active-file verification;
- Magisk/service ownership by the exact active release;
- healthy/serving `runtime-supervisor`, `host-daemon` and `sing-box`;
- durable control-plane heartbeat;
- `tunnel_owner=first_party_reverse_tunnel` and no native-mode Android VPN owner;
- authenticated public proxy traffic exits through the phone carrier path;
- when Android auxiliary egress/compatibility is used: exact `com.example.mobileproxy` package, required versionName/versionCode, installed signer equals accepted candidate signer as a bounded boolean, exact retained APK digest/provenance, and auxiliary service health.

“No APK installation required” is valid only for a topology that does not consume an Android app capability. It is not a global production-stack invariant.

## 8. Immutable physical stage sequence

Run `docs/physical-phone-acceptance-runbook.md` and validate bounded reports automatically.

Required stages remain:

1. **online** — clean startup, fresh QUIC and all protected proxy protocol checks;
2. **post-reboot** — full phone reboot, service rehydration, durable inventory and fresh QUIC;
3. **fallback** — QUIC blocked while pinned TLS/TCP remains available and proxy paths pass;
4. **recovered** — QUIC restored and new connections return to fresh QUIC;
5. **wireguard** — explicit stock WireGuard rollback owns Android VPN, `tun0` exists, handshake is recent, reverse tunnel is inactive and protected proxy paths pass;
6. **post-wireguard-recovered** — the exact already-installed native release is reactivated without rebuilding, WireGuard stops, `tun0` disappears and fresh QUIC/proxy service returns.

The final validator proves one exact candidate SHA, one bounded device identity, exact deployment reports/switches/reactivation, all accepted stages and absence of secrets/unbounded logs.

## 9. Repeated recovery matrix

A single successful physical run is not sufficient.

Phone-side repetitions:

- 20 full phone reboots;
- 20 `runtime-supervisor` forced terminations;
- 20 `host-daemon` forced terminations;
- 20 `sing-box` forced terminations;
- 20 mobile-data disconnect/reconnect events;
- 10 forced QUIC-block/TLS-reserve/QUIC-return cycles;
- 5 native-to-stock-WireGuard-to-native rollback cycles;
- 30 managed IP rotations at the selected hold window.

Relay-side repetitions:

- 20 control-plane restarts;
- 20 reverse-tunnel-server restarts;
- 20 relay-gate restarts;
- 20 Nginx reloads;
- 10 full VM reboots;
- one clean backup restore;
- one VM delete-and-recreate drill.

Every operation records bounded UTC/recovery/transport/result evidence without secrets.

## 10. Reliability thresholds

For each repeated category and combined set:

- automatic recovery success rate at least **99.5%**;
- median recovery under **20 seconds**;
- p95 recovery under **60 seconds**;
- no silent stuck state longer than **60 seconds**;
- no success while proxy traffic fails or tunnel freshness is stale;
- no unresolved degraded state without a bounded machine-readable reason;
- no cross-device/stale-session routing, plaintext downgrade or lost acknowledged operation.

With small fixed samples, one unexplained failure blocks acceptance. A software fix establishes a new SHA and invalidates candidate-specific evidence as required by the one-SHA rule.

## 11. Rotation timing gate

For each supported phone/operator profile, evaluate candidate hold windows with at least 30 runs each and select the shortest window meeting the documented IP-change/recovery threshold. Materially different device/modem/operator profiles require their own current matrix.

## 12. Soak and resource gate

After recovery repetitions, run at least a 24-hour production-like soak on the same exact candidate. During soak, verify protected proxy paths at least once per minute, bounded tunnel/runtime/egress metrics, controlled rotations/restarts, no unbounded resource growth, no credential leakage and no unexplained outage longer than 60 seconds.

A monotonic leak or unbounded queue blocks acceptance regardless of remaining capacity.

## 13. Security and operational review

Before final closeout verify firewall exposure, credential separation, certificate pinning, wrong-credential failure behavior, release/backup permissions, rollback immutability, clean backup restore, dependency audit results and any explicit residual-risk record.

A full independent penetration test, signed provenance beyond the activated baseline or fleet orchestration is outside current scope unless separately activated; absence is not misrepresented as completed assurance.

## 14. Final decision

Declare **10/10 accepted / baseline complete** only when:

- exact candidate software evidence says `software_10_of_10_ready=true`;
- applicable Android signing/migration and installed-state proof passes;
- complete physical summary says `physical_phone_acceptance_complete=true` and `accepted=true`;
- repeated recovery thresholds pass;
- 24-hour soak passes;
- no unresolved P0/P1 defect remains;
- all candidate-specific evidence belongs to the same immutable Git SHA;
- protected `main` still equals that accepted SHA at final tag creation;
- final tag targets that SHA;
- published artifacts are derived from or immutably reused with provenance bound to that same SHA.

Architecture/documentation reconciliation can complete before this global acceptance state. It must not claim that live physical 10/10 has already happened.
