# 10/10 Reproducibility and Reliability Validation Plan

Status: **normative acceptance matrix**  
Current implementation backlog: public Issue `#228`  
Current engineering/execution cursor: newest authoritative checkpoint in public Issue `#179`  
Authority boundary: `docs/operations/project-authority.md`  
Primary runtime: `first_party_reverse_tunnel`  
Rollback runtime: `stock_wireguard_bridge`

## 1. Meaning of 10/10

The project uses two distinct statuses:

1. **Software 10/10-ready** — every source-controlled, process-testable, dependency, Android-build and immutable-Product-Release gate passes on one exact protected PRODUCT revision.
2. **10/10 accepted / baseline complete** — that immutable Product Release, together with one exact admitted Deployment Controller revision, also passes the complete real-phone, real-provider/network, deployment, rollback, recovery and soak matrix.

Passing CI is necessary but cannot prove Android boot behavior, modem policy routing, carrier QUIC blocking, real cellular egress, signer/install state, real WireGuard handshake or long-running recovery. Software evidence therefore never claims physical acceptance or baseline completion.

Both repositories are public:

- `iamaman11/mobile-proxy` = PRODUCT authority;
- `iamaman11/mobile-proxy-production` = DEPLOYMENT CONTROLLER authority.

Repository visibility is not the confidentiality boundary. Secret values, target bindings, raw device identifiers, credentials, private keys, sensitive rendered config and unsafe raw production logs remain private.

## 2. Normative release and deployment identity

PRODUCT and controller identity are intentionally separate.

```text
product_release
  = exact annotated semantic tag
  + exact PRODUCT source SHA
  + exact immutable Product Release assets/provenance

runtime_deployment_identity
  = product_release
  + exact admitted deployment_controller_revision
```

A controller-only repair must not force a rebuild of unchanged product bytes. A new Product Release must not silently redefine which controller revision executed it.

For one acceptance campaign:

```text
accepted_product_source_sha
  == final annotated product tag target SHA
  == source SHA recorded by Product Release provenance

accepted_controller_revision
  == exact controller revision admitted for the deployment/acceptance campaign
```

The two SHAs are not required to be equal and normally belong to different repositories.

If protected PRODUCT `main` advances before Product Release creation, PRODUCT candidate evidence is stale and must be regenerated as required by its contracts. If the controller revision advances, controller admission/policy evidence must be re-established for the new controller revision without pretending the Product Release changed.

Historical Item 19/Item 20 candidates remain immutable historical evidence only. They do not define current Product Release or Deployment Controller identity.

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

A topology that consumes an Android app capability must treat exact package/version/signer/install state and retained signed artifact provenance as candidate-specific production acceptance evidence.

## 4. Durable A-H acceptance path

The project is completed in these gates. Issue #179 determines which gate/action is currently authorized; Issue #228 is backlog only.

### Gate A — Deployment Controller health

The current controller revision must execute its required hosted policy set on real runners and finish terminal green. Tree-equivalence is not a substitute for operational CI health.

### Gate B — source ownership / authority convergence

There must be exactly one active deployment controller implementation. PRODUCT retains application/runtime source, shared product/domain code, Quality/build/release logic. Deployment ingress, target mutation State Machine / Transaction Kernel, durable intent, exactly-once dispatch, target adapters, recovery/quarantine and canonical runtime execution evidence belong only to `mobile-proxy-production`.

### Gate C — Android security hardening

Eliminate plaintext persistent tunnel secret/config state, explicitly exclude secret-bearing state from backup/device transfer, retain deterministic direct-boot behavior and fail closed on missing/corrupt key material.

### Gate D — Android behavior tests

Prove secure state, boot restoration, tunnel lifecycle, cellular egress authentication/network refusal, local control behavior and at least one Android framework/Keystore/service instrumentation smoke path.

### Gate E — supply chain and Product Release prerequisites

Bind vendored Android binary dependencies to authoritative upstream provenance/digests. Product tag creation must require exact same-SHA successful Product Quality and Product Release prerequisite evidence without needlessly loading signing secret values into readiness jobs.

### Gate F — new immutable Product Release

Create a new semantic Product Release from the hardened exact PRODUCT revision. Do not rewrite historical `v0.1.4`. Require exact annotated tag -> exact source -> exact signed artifacts -> manifest/provenance/digests -> immutable GitHub Release.

### Gate G — exactly one admitted deployment

Through Deployment Controller Issue #1, submit exactly one semantic deployment request for the new immutable Product Release. Require exact Product Release + exact controller revision admission, target-global serialization, durable intent before destructive dispatch, exactly-once effect, independent postcondition and fail-closed UNKNOWN recovery.

### Gate H — real-world acceptance

On the deployed immutable release prove the real registered phone, reverse tunnel, relay/provider path, external client access, carrier egress/IP rotation, reboot/fallback/recovery and reliability/soak criteria below.

Historical real-phone experiments are valuable engineering evidence but never substitute for Gate H on the final immutable Product Release.

## 5. Immutable software gate

All PRODUCT checks pass on one clean, unchanged PRODUCT Git SHA before the Product Release is created.

### Architecture and policy

- application/domain dependency boundaries;
- native reverse-tunnel default enforcement;
- Android auxiliary role is explicit and cannot silently become the primary tunnel owner;
- unknown or contradictory tunnel ownership fails closed;
- bounded logs, errors, enums, queues and retries;
- source-controlled migration and rollback procedures;
- PRODUCT repository is the single product source/build/release authority;
- Deployment Controller is the single deployment transaction/target-mutation authority;
- no controller source is maintained in both repositories;
- repository visibility is not used as a substitute for secret/evidence containment.

### Cryptographic and release integrity

- internal release/config/binary digests use the admitted typed digest contracts;
- static domain separation and length framing are enforced where required;
- externally mandated algorithms remain unchanged;
- release roots contain sorted manifests and exact sizes;
- deployment identity is checked against immutable Product Release identity;
- evidence contains the exact full relevant Git revisions;
- final published artifact provenance records the exact final PRODUCT tag target SHA.

### Rust, supply chain and Android quality

- `cargo fmt --all -- --check`;
- `cargo clippy --workspace --all-targets -- -D warnings`;
- `cargo test --workspace`;
- RustSec/cargo-deny gates;
- vendored Android binary provenance/digest verification;
- Android unit/behavior/instrumentation tests;
- Android lint and assembly;
- sensitive backup/D2D policy is explicit;
- no production runtime reference may turn the app-owned VPN service into the default native tunnel owner;
- production release APK signing/package/version contracts remain machine-verified.

### Durable product state and operations

- canonical product mutable-state owners are explicit;
- migrations are deterministic and fail closed;
- acknowledged product state/replay/idempotency requirements survive restart where applicable;
- liveness is separate from serving readiness;
- readiness reports critical state without exposing secrets.

### Reverse-tunnel and proxy software acceptance

Controlled tests prove mixed `1080`, SOCKS5 `1081`, HTTP/CONNECT `3128`, forced QUIC failure, pinned TLS/TCP reserve, return to fresh QUIC, same device/session authority, no plaintext fallback and bounded deterministic capacity handling where these are product-testable.

Only after all software gates pass may evidence claim `software_10_of_10_ready=true`.

## 6. Provider and phone prerequisites

Historical provider/phone evidence remains historical evidence. Gate H must establish fresh release/controller-specific readiness as required by current v2 contracts.

Before any mutable phone/provider action:

- newest #179 checkpoint must explicitly authorize that bounded action;
- exact immutable Product Release identity must be resolved when deployment requires it;
- exact Deployment Controller revision/policies must be admitted;
- registered target binding must be proven without publishing raw identifiers;
- secrets/credentials must be supplied only through admitted private secret/environment inputs;
- UNKNOWN/QUARANTINED prior transactions must be reconciled according to controller policy before any new conflicting mutation.

No phone mutation is authorized merely by this document.

## 7. Fresh relay VM drill

Create or recreate a controlled test relay only through the admitted Deployment Controller/provider lifecycle for the active Product Release.

Acceptance includes declared topology, exact candidate artifacts, clean service startup, deterministic storage migration/restart, public proxy compatibility, QUIC and pinned TLS/TCP reachability, explicit rollback backend availability, idempotent provisioning and verified cleanup. Exact provider identity remains bounded according to trust-zone policy.

## 8. Fresh rooted-phone drill

Use the exact immutable Product Release and registered rooted phone through the admitted Deployment Controller revision.

Acceptance includes:

- registered-device/root proof before mutation;
- exact architecture-correct package/runtime identity;
- local manifest and byte-for-byte active-file verification where required;
- Magisk/service ownership by the exact active release;
- healthy/serving `runtime-supervisor`, `host-daemon` and `sing-box` where used by current topology;
- durable control-plane heartbeat;
- `tunnel_owner=first_party_reverse_tunnel` and no native-mode Android VPN owner;
- authenticated public proxy traffic exits through the phone carrier path;
- when Android auxiliary egress/compatibility is used: exact `com.example.mobileproxy` package, required versionName/versionCode, installed signer equals accepted candidate signer as a bounded classification, exact retained APK digest/provenance, and auxiliary service health.

“No APK installation required” is valid only for a topology that does not consume an Android app capability. It is not a global production-stack invariant.

## 9. Immutable physical stage sequence

Execute the current controller-owned physical acceptance operations corresponding to these stages. Historical public phone scripts are not active execution authority.

Required stages remain conceptually:

1. **online** — clean startup, fresh QUIC and all protected proxy protocol checks;
2. **post-reboot** — full phone reboot, service rehydration, durable inventory and fresh QUIC;
3. **fallback** — QUIC blocked while pinned TLS/TCP remains available and proxy paths pass;
4. **recovered** — QUIC restored and new connections return to fresh QUIC;
5. **wireguard** — explicit stock WireGuard rollback owns Android VPN, `tun0` exists, handshake is recent, reverse tunnel is inactive and protected proxy paths pass;
6. **post-wireguard-recovered** — the exact already-installed native release is reactivated without rebuilding, WireGuard stops, `tun0` disappears and fresh QUIC/proxy service returns.

The final summary proves one exact Product Release, one exact controller revision, one bounded target identity, exact deployment/recovery evidence, all accepted stages and absence of secrets/unbounded logs.

## 10. Repeated recovery matrix

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

## 11. Reliability thresholds

For each repeated category and combined set:

- automatic recovery success rate at least **99.5%**;
- median recovery under **20 seconds**;
- p95 recovery under **60 seconds**;
- no silent stuck state longer than **60 seconds**;
- no success while proxy traffic fails or tunnel freshness is stale;
- no unresolved degraded state without a bounded machine-readable reason;
- no cross-device/stale-session routing, plaintext downgrade or lost acknowledged operation.

With small fixed samples, one unexplained failure blocks acceptance. A PRODUCT software fix establishes a new Product Release candidate; a controller-only fix establishes a new controller revision. In either case, invalidate only evidence whose declared dependencies changed.

## 12. Rotation timing gate

For each supported phone/operator profile, evaluate candidate hold windows with at least 30 runs each and select the shortest window meeting the documented IP-change/recovery threshold. Materially different device/modem/operator profiles require their own current matrix.

## 13. Soak and resource gate

After recovery repetitions, run at least a 24-hour production-like soak using the same immutable Product Release and admitted controller/runtime identity. During soak, verify protected proxy paths at least once per minute, bounded tunnel/runtime/egress metrics, controlled rotations/restarts, no unbounded resource growth, no credential leakage and no unexplained outage longer than 60 seconds.

A monotonic leak or unbounded queue blocks acceptance regardless of remaining capacity.

## 14. Security and operational review

Before final closeout verify firewall exposure, credential separation, certificate pinning, wrong-credential failure behavior, release/backup permissions, rollback immutability, clean backup restore, dependency audit results and any explicit residual-risk record.

A full independent penetration test or fleet orchestration is outside current scope unless separately activated; absence is not misrepresented as completed assurance.

## 15. Final decision

Declare **10/10 accepted / baseline complete** only when:

- exact Product Release software evidence says `software_10_of_10_ready=true`;
- applicable Android signing and installed-state proof passes;
- Deployment Controller terminal evidence proves the admitted deployment transaction without blind retry;
- complete physical summary says `physical_phone_acceptance_complete=true` and `accepted=true`;
- repeated recovery thresholds pass;
- 24-hour soak passes;
- no unresolved P0/P1 defect remains;
- all evidence is bound to the exact Product Release and exact controller revision/dependencies it claims;
- final Product tag targets the accepted PRODUCT source SHA;
- published artifacts are derived from or immutably reused with provenance bound to that same PRODUCT source SHA;
- no sensitive target/secret material was made public as part of acceptance evidence.

Architecture/documentation reconciliation can complete before this global acceptance state. It must not claim that live physical 10/10 has already happened.
