# Rust-Only Ultimate Plan 10/10

Date: 2026-06-03
Workspace: `/home/bose/projects/mobile-proxy`
Goal: make the system production-grade, Rust-first, reproducible, self-healing, and structurally clean across `VM relay + Android phone`.

## 1. Hard verdict on the current plan

The previous plan was directionally correct, but it was not sufficient for a true `10/10`.

What it was missing:
- explicit `from-zero` provisioning for both `VM relay` and `phone runtime`
- explicit recovery guarantees after `phone reboot`, `VM reboot`, `process crash`, `network flap`
- strict ownership split between `bootstrap`, `supervisor`, `domain policy`, `infra adapters`
- mandatory removal of runtime logic from `service.sh` and `*.ps1`
- measurable acceptance tests for programmatic `airplane on/off` timing windows: `1s`, `2s`, `3s`, `4s`, `5s`
- release gating, rollback rules, artifact versioning, and drift detection
- explicit codebase modularization and repository ownership rules

Verdict:
- as an architecture direction: `7/10`
- as an execution plan for a no-compromise system: `4/10`

## 2. Verified current gaps in the application

These are not theoretical concerns. They are visible in the current codebase.

1. `service.sh` no longer owns runtime and recovery behavior.
   Current state: [service.sh](/home/bose/projects/mobile-proxy/deploy/device-runtime/module/service.sh:34) validates the release and starts only `bin/runtime-supervisor`; route/WireGuard/process policy now belongs to Rust.

2. `host-daemon` is no longer a fixed IP-pool simulation.
   Current state: rotation execution is command-backed, health is probe-backed, startup is fail-closed, and public serving is not accepted without route/proxy/public-observer success.

3. VM-side `control-plane` is no longer memory-only.
   Current state: control-plane loads and persists registry/command state as JSON at `CONTROL_PLANE_STATE_PATH`, defaulting to `/var/lib/mobile-relaycontrolpoint/control-plane-state.json`.
   Current VM identity:
   - project: `project-56ecc519-f3ab-429a-b0a`
   - instance: `mobile-relaycontrolpoint-v2`
   - zone: `europe-central2-a`
   - IP: `34.118.88.54`
   Current blocker:
   - GCP describe access works
   - SSH shell access previously failed with `Permission denied (publickey)` even after OS Login key add
   - fixed on `2026-06-03` by snapshotting the boot disk and installing a local `bose` sudo SSH user through controlled recovery metadata
   - `operator-cli provision-vm` can now create and re-provision the VM runtime from repo artifacts and env secrets
   - `mobile-relaycontrolpoint-v2` is the current production relay, created from the application as a low-cost `e2-micro` instance with a 10 GB boot disk and static in-use IPv4 `34.118.88.54`

4. Device operations no longer depend on tracked PowerShell orchestration.
   Current state: persistent `*.ps1` operator scripts were removed from the active repo; install, verify, rollback, rotate, artifact prep, VM provision, and VM delete are Rust CLI commands.

5. The repo currently proves local compilation and packaging gates, not production reliability.
   Verified locally:
   - `cargo test` passes
   - `cargo clippy --all-targets --all-features -- -D warnings` passes
   - Android ARM binaries for `runtime-supervisor`, `host-daemon`, and `sing-box` are validated as ELF32 ARM for `/system/bin/linker`
   - Rust packaging rejects missing or wrong-architecture phone runtime binaries
   - full reboot/airplane/soak validation is still required before `10/10`

6. Executable crates were previously too monolithic; the modularization pass now covers runtime-supervisor, relay-gate, host-daemon, control-plane, operator-cli, and proxy-core.
   Evidence:
   - `services/runtime-supervisor` is split into `cli`, `config`, `process`, `android`, and `health`
   - `services/relay-gate` is split into `cli`, `probe`, and `report`
   - `services/runtime-supervisor` owns phone-side process lifecycle and recovery, but still needs live validation after cellular/SIM service is restored
   - `crates/runtime-domain` exists as first pure domain slice and needs broader replay/property coverage
   - `crates/proxy-core` is now module-split, but projection policy still lives there and should eventually be extracted if shared policy grows further

7. Live Android recovery after programmatic `airplane_bounce` was not production-grade on the old shell-owned runtime and must be revalidated on the new Rust-owned runtime.
   Verified on `SM_A022G` with `MTS BY` on `2026-06-02`:
   - rotate job succeeds
   - public IP changes
   - old runtime falls into `waiting_cellular`
   - `main` default route disappears while `rmnet4` table route remains
   - shell route guard fails to restore `healthy`
   Implication:
   - `cellular_route_ready` must not be coupled only to the `main` table
   - the new host-daemon health probe now accepts policy-table cellular defaults, but this fix still needs live phone verification

9. Live validation on `2026-06-04` found and fixed the `rotate/IP changed -> waiting_cellular` diagnosis bug.
   Current state:
   - when WireGuard is enabled and `tun0` is missing, health reports `waiting_wireguard` with `wireguard_path_not_ready`
   - `runtime-supervisor` defers `sing-box` startup until `tun0` exists
   - control-plane heartbeat/device records now expose `tun0_present` and `wg_handshake_recent`
   - phone release `checkall-phone-observability-20260604` and VM release `checkall-vm-observability-20260604` are live and healthy
   Remaining hard blocker:
   - stock WireGuard Android app cannot be controlled 100% programmatically by raw shell/root `am broadcast`; Android blocks the receiver path and shell cannot hold `CONTROL_TUNNELS`
   - target architecture must add a permissioned companion APK or replace the dependency with a Rust-owned/native WireGuard backend

10. Architecture decision on `2026-06-04`: choose the app-owned tunnel architecture, not a production companion for stock WireGuard.
   Decision:
   - final target is option 3 from [ANDROID_TUNNEL_ARCHITECTURE_DECISION.md](/home/bose/projects/mobile-proxy/ANDROID_TUNNEL_ARCHITECTURE_DECISION.md)
   - `apps/android-app` must become the first-party `VpnService` owner
   - `runtime-supervisor` remains the Rust policy owner
   - sing-box/libbox or a Rust tunnel engine may be used inside our APK boundary
   - stock WireGuard Android app is allowed only as a temporary bridge for live validation

8. Live Rust-owned runtime validation on `2026-06-03`.
   Current state:
   - installed release `hard-rust-supervisor-20260603-1733` on `SM_A022G`
   - process tree is `runtime-supervisor -> host-daemon + sing-box`
   - health returned `healthy`, `serving=true`, `cellular_route_ready=true`, `tun0_present=true`
   - single `4s` rotation changed IP and returned to `healthy`
   - full programmatic timing matrix completed; see [AIRPLANE_TIMING_STUDY_2026_06_03.md](/home/bose/projects/mobile-proxy/AIRPLANE_TIMING_STUDY_2026_06_03.md)
   - phone was migrated to the newly created VM endpoint `34.118.88.54`; control-plane reported `healthy`, `serving=true`, `publicly_serving=true`


## 3. Non-negotiable target

The target system must satisfy all of the following:

1. Provision a fresh `VM relay` from zero with one Rust command.
2. Provision a fresh rooted Android device from zero with one Rust command.
3. Recover automatically after:
   - phone reboot
   - VM reboot
   - `host-daemon` crash
   - `sing-box` crash
   - `control-plane` restart
   - temporary route loss after airplane mode
4. Support IP rotation through programmatic airplane bounce.
5. Validate whether the required airplane hold is really `4s`, or whether `1s`, `2s`, `3s`, or `5s` is the correct minimum for the target carrier/device combination, using programmatic toggles only.
6. Keep shell usage to minimal bootstrap only.
7. Be deterministic enough to replay failures and explain why recovery did or did not happen.
8. Keep the repository readable: every responsibility must have one obvious home, and `main.rs` files must stay composition roots rather than monoliths.

## 4. Target architecture

### A. Phone runtime

- `service.sh`
  - only starts one Rust binary: `runtime-supervisor`
  - no route repair
  - no WireGuard recovery policy
  - no process orchestration
  - no business rules

- `runtime-supervisor`
  - owns lifecycle of `host-daemon` and `sing-box`
  - owns reconciliation loop
  - owns failure detection
  - owns timers, retries, quarantine, and restart policy
  - target remaining gap: persist local event/state history across reboot

- `runtime-domain` (new Rust crate)
  - pure state machine
  - transitions from events to intents
  - no side effects

- `runtime-infra-android` (new Rust crate)
  - wraps Android/system calls
  - route inspection and repair
  - process management
  - WireGuard activation strategies
  - health probes
  - device-specific fallback strategy when direct route writes are denied by Android/network policy

### B. VM runtime

- `relay-gate`
  - public readiness gate
  - external probe executor
  - reports availability into control-plane

- `control-plane`
  - durable registry
  - durable command queue
  - desired-state storage
  - recovery intent tracking
  - idempotent command issuance

- `vm-supervisor` or systemd-managed services
  - boot-time start
  - crash restart
  - config version pinning

### C. Operations

- `operator-cli`
  - `provision-vm`
  - `provision-device`
  - `deploy-release`
  - `verify`
  - `rotate`
  - `recover`
  - `rollback`
  - `fleet-status`

No PowerShell or shell script may remain the source of truth for runtime policy.

## 5. Mandatory workstreams

Repository documentation rule:
- persistent documentation lives in root-level markdown files only
- architecture, runtime layout, quick reference, and the master plan must remain easy to find from the repository root

### Workstream 0. Baseline truth audit

Deliverables:
- map every responsibility currently living in `service.sh` and removed legacy operator scripts
- map every recovery path currently expected in production
- define exact boot sequence for phone and VM

Exit criteria:
- `feature -> current owner -> target Rust owner -> test owner` table exists

### Workstream 1. Repository and codebase modularization

Deliverables:
- split `services/host-daemon/src/main.rs` into focused modules such as:
  - `config.rs`
  - `state.rs`
  - `api.rs`
  - `rotation.rs`
  - `control_plane.rs`
  - `auth.rs`
- split `services/control-plane/src/main.rs` into focused modules such as:
  - `api.rs`
  - `store.rs`
  - `commands.rs`
  - `projection.rs`
- split `apps/operator-cli/src/main.rs` into focused modules such as:
  - `commands/status.rs`
  - `commands/rotate.rs`
  - `commands/airplane_study.rs`
  - `http.rs`
- keep each `main.rs` as composition root only
- extract pure policy from binaries into reusable crates where ownership becomes shared

Exit criteria:
- no executable crate keeps business logic concentrated in one oversized `main.rs`
- a new engineer can find config, state, API, orchestration, and infra code in under one minute
- module boundaries match the intended layered architecture

Current status:
- first pass completed in repo
- `proxy-core` is now module-split into `constants`, `runtime`, `commands`, `records`, and `endpoints`
- `operator-cli`, `control-plane`, `host-daemon`, and `proxy-core` are split into focused modules
- remaining work is durability, replay-grade domain coverage, and VM/phone live validation

### Workstream 2. Real phone supervisor

Deliverables:
- create `services/runtime-supervisor`
- move process management out of `service.sh`
- move route reconciliation out of shell
- move WireGuard kick/retry policy out of shell

Exit criteria:
- `service.sh` contains only bootstrap logic
- killing `host-daemon` or `sing-box` results in automatic supervised recovery

Current status:
- `services/runtime-supervisor` is in the workspace and owns `host-daemon`/`sing-box` process lifecycle
- `service.sh` is bootstrap-only
- supervisor performs WireGuard kick attempts, route repair attempts, and data-bounce fallback
- host-daemon health now treats Android policy-table cellular routes as route-ready
- live phone install and rotation testing passed on `SM_A022G`; reboot/crash/soak testing remains pending

### Workstream 3. Domain state machine

Deliverables:
- model states:
  - `booting`
  - `waiting_wireguard`
  - `waiting_cellular`
  - `starting_proxy`
  - `healthy`
  - `recovering`
  - `quarantined`
- model events:
  - boot
  - reboot
  - process_exit
  - probe_failed
  - route_missing
  - wg_missing
  - rotate_requested
  - rotate_completed
  - timeout
- model actions:
  - restart process
  - repair route
  - kick WireGuard
  - start rotate
  - mark quarantined

Exit criteria:
- property tests and transition tests exist
- replay of recorded event traces is deterministic
- recorded live trace for `rotate success + post-rotate route loss` is modeled and replayable

### Workstream 4. Durable VM control-plane

Deliverables:
- add persistence for device registry and commands
- add recovery of queued commands after restart
- add idempotent rotate command semantics
- add artifact and config fingerprint tracking

Exit criteria:
- restarting `control-plane` does not lose desired state or in-flight intent

### Workstream 5. Zero-to-one provisioning

Deliverables:
- `operator-cli provision-vm`
  - installs relay binaries/config
  - writes service manager units
  - validates boot persistence
- `operator-cli provision-device`
  - pushes release bundle
  - installs bootstrap module
  - validates root, config, runtime start, and first health

Exit criteria:
- new VM can be brought to ready state from a blank host
- new phone can be brought to ready state from a blank rooted device

Current status:
- Rust `package-device-release`, `install-device-release`, `verify-device`, and `rollback-device` commands now exist in `operator-cli`
- Rust `prepare-runtime-binaries` now rebuilds Android Rust binaries and downloads official `sing-box` artifacts
- Rust `provision-vm` now creates/configures a GCP relay VM from manifest/env and can re-provision the current VM
- current VM was re-provisioned from the application as release `vm-hard-check-20260603`
- fresh VM smoke passed on `2026-06-03`: `mobile-relaycontrolpoint-repro-test` was created from the application, provisioned, verified with active services/listening ports, then deleted with `operator-cli delete-vm`
- full migration proof completed on `2026-06-03`: phone manifest was switched to a newly created VM endpoint, device release `phone-v2-relay-20260603` was installed, public HTTP proxy on `34.118.88.54:3128` returned a mobile-carrier IP, and the old production VM was deleted through `operator-cli delete-vm`

### Workstream 6. Rotation engine

Deliverables:
- unify manual and API rotation into one Rust path
- add post-rotate convergence checks
- add failure reasons for:
  - IP unchanged
  - route missing
  - WireGuard not restored
  - proxy not serving
  - route repair blocked by Android permissions or policy routing behavior

Exit criteria:
- rotation succeeds or fails with a precise machine-readable reason
- rotate success is not accepted until the runtime returns to real serving health

### Workstream 7. Airplane timing study

This is mandatory. `4s` must not remain an assumption.

Test matrix:
- hold durations: `1s`, `2s`, `3s`, `4s`, `5s`
- mode: `API/programmatic toggle` only
- repetitions:
  - minimum `30` runs per hold duration

Metrics:
- IP actually changed
- time to cellular route recovery
- time to `tun0` recovery
- time to `healthy`
- recovery from rotate to `healthy` through Rust supervisor
- false-success rate
- failure mode distribution
- divergence between route heuristic and actual serving behavior

Decision rule:
- choose the shortest duration whose success rate is at least `99%` on the target device/carrier profile
- if no duration from `1s..5s` reaches target, keep `4s` or raise the window based on evidence

Current result on `SM_A022G` + `MTS BY`:
- `1s`: `24/30`, `80.00%`
- `2s`: `28/30`, `93.33%`
- `3s`: `29/30`, `96.67%`
- `4s`: `30/30`, `100.00%`
- `5s`: `30/30`, `100.00%`
- selected minimum: `4s`

### Workstream 8. Hardening and release discipline

Deliverables:
- artifact manifest with checksums
- binary fingerprint validation
- deployment guard against config/binary drift
- rollback command for VM and phone
- structured event timeline logs
- root-level runbook for known live recovery gaps

Exit criteria:
- every release is reproducible and reversible

## 6. Reliability acceptance gates

The architecture is not `10/10` until all gates are green.

Functional gates:
- `cargo test` green
- `cargo clippy --all-targets --all-features -D warnings` green
- supervisor restart tests green
- durable command recovery tests green

Phone resilience gates:
- `20` cold boots
- `20` host-daemon kills
- `20` sing-box kills
- `30` API airplane bounces for each tested hold duration from `1s` to `5s`

VM resilience gates:
- `20` control-plane restarts
- `20` relay-gate restarts
- `10` full VM reboots

Quality thresholds:
- automatic recovery success `>= 99.5%`
- median recovery `< 20s`
- p95 recovery `< 60s`
- false quarantine rate `< 0.5%`
- no silent stuck state lasting more than `60s`

## 7. Definition of done

The system is `10/10` only if all of the following are true:

1. Runtime logic is Rust-owned.
2. Shell is bootstrap-only.
3. VM and phone can both be provisioned from zero by Rust commands.
4. Recovery after reboot/crash/airplane is automatic and measured.
5. Airplane hold duration is evidence-based, not guessed.
6. The control-plane survives restarts without losing intended operations.
7. Every failure path emits a reason code and event trace.
8. Release artifacts are reproducible, versioned, and rollback-safe.

## 8. Practical execution order

1. Freeze current behavior and write the ownership map.
2. Split monolithic executables into navigable modules.
3. Build `runtime-supervisor`. Done for the first hard target.
4. Extract pure `runtime-domain`. First slice done; replay/property coverage remains.
5. Move Android adapters into Rust. Process lifecycle, health, rotation command execution, route repair, WireGuard kick, and data-bounce fallback are in Rust; dedicated adapter crates remain future cleanup.
6. Shrink `service.sh` to bootstrap-only. Done.
7. Re-evaluate health semantics so policy-routed serving is not marked false-degraded. First implementation done.
8. Close the live `post-rotate route loss` bug on the real phone.
9. Make `control-plane` durable.
10. Replace remaining VM operations with `operator-cli` and obtain working VM admin access.
11. Run the airplane timing study.
12. Run full reboot/crash/soak matrix.

## 9. Final conclusion

The old plan was a good architecture note. It was not enough as a no-failure execution plan.

The corrected standard is:
- `Rust owns runtime`
- `Rust owns provisioning`
- `Rust owns recovery`
- `programmatic tests decide the airplane timing`
- `reliability is proven by repeated failure drills, not by green unit tests`
