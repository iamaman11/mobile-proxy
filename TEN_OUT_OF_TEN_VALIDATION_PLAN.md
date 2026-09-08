# 10/10 Reproducibility and Reliability Validation Catalog

Status: **normative acceptance evidence catalog; not execution authority and not a roadmap**  
Dynamic engineering/operations cursor: newest authoritative checkpoint in PRODUCT Issue #179  
Canonical stage plan: `docs/PRODUCTION_STAGE_ROADMAP.md`  
Planning backlog: PRODUCT Issue #249  
Authority boundary: `docs/operations/project-authority.md`

This document defines **what evidence is required** for acceptance. It does not define which stage is current, does not authorize actions, and does not independently redefine stage scope/order.

Historical A-H/Item plans are superseded as execution sequencing. Useful requirements survive here only when they protect a current architecture, security, reliability or operational invariant.

## 1. Meaning of 10/10

The project distinguishes:

1. **PRODUCT software/Release accepted** — exact reviewed PRODUCT identity passes the required source-controlled security, behavior, dependency, build and immutable Product Release gates.
2. **Target accepted** — an exact immutable Product Release plus exact admitted Controller revision has direct target-local deployment/operational evidence appropriate to that target's owning stage.
3. **Full production 10/10 accepted** — PRODUCT, Controller and the complete real PHONE+VM topology pass Stage 7 functional/network/recovery/load/soak acceptance with no unresolved P0/P1.

CI is necessary but cannot manufacture Android boot behavior, modem/carrier behavior, physical process state, VM host state or long-running full-topology reliability evidence.

Secrets, target bindings, raw identifiers, credentials, private keys, sensitive rendered config and unsafe raw runtime logs remain private.

## 2. Release and runtime identity

```text
product_release
  = exact annotated semantic tag
  + exact PRODUCT source SHA
  + exact immutable Product Release assets/provenance

runtime_deployment_identity
  = product_release
  + exact admitted Deployment Controller revision
```

`latest`, mutable refs, approximate versions and GitHub Deployment projection are not runtime identity.

A Controller-only observation/recovery repair does not force a rebuild of unchanged product bytes. A new Product Release does not silently redefine the Controller revision that deployed it.

## 3. Runtime topology and roles

Primary phone runtime class:

```text
root/Magisk boot hook
  -> runtime-supervisor
      -> host-daemon
      -> sing-box on loopback
          -> certificate-pinned QUIC reverse tunnel
          -> certificate-pinned TLS/TCP reserve
```

The Android app is not the primary reverse-tunnel owner. It remains the PRODUCT owner of Android-specific capabilities consumed by the selected topology, including cellular `Network.bindSocket()` egress and the explicit WireGuard compatibility path where applicable.

Primary invariants include:

- `tunnel_owner=first_party_reverse_tunnel` for native primary mode;
- no plaintext downgrade;
- exact device/tunnel-session authority;
- no arbitrary available-device routing;
- exact APK package/version/signer/artifact identity when Android capability is consumed;
- WireGuard only as explicit compatibility/rollback where production policy permits it.

## 4. Evidence-domain rule

Acceptance evidence belongs to the **earliest stage whose exit genuinely depends on it**. A later-stage test is not pulled forward merely because it is useful eventually.

Distinct domains:

- **transport readiness** — can the admitted Controller path reach the registered target through runner/host/USB/ADB/root;
- **exact Release state** — are immutable target bytes/current state exact for the admitted Product Release;
- **live operational state** — is the accepted target locally running/ready/healthy with bounded resource state;
- **lifecycle exercise** — did one separately admitted perturbation recover to its exact postcondition;
- **full-topology state** — does the real external consumer -> VM -> reverse tunnel -> phone -> cellular path work correctly under failure/load/time.

One domain's success must not be projected as another domain's truth.

Stage mapping:

- Stage 1 — Controller phone transaction semantics;
- Stage 2 — immutable Product Release/software identity;
- Stage 3 — one exact real phone deployment/postcondition;
- Stage 4 — phone production-node operational acceptance;
- Stage 5 — phone baseline convergence/simplification;
- Stage 6 — VM foundation + VM-local target acceptance;
- Stage 7 — complete PHONE+VM end-to-end product/topology acceptance.

## 5. PRODUCT software and immutable Release evidence

As applicable to the active Product Release contract:

### Architecture / policy

- product/application/domain dependency boundaries;
- native reverse-tunnel default enforcement;
- Android auxiliary role cannot silently become tunnel owner;
- unknown/contradictory tunnel ownership fails closed;
- bounded errors, queues and retries;
- PRODUCT remains the sole product source/build/release authority;
- Controller remains the sole deployment transaction/target-mutation authority;
- no active duplicate Controller implementation in PRODUCT.

### Cryptographic / release integrity

- typed digest contracts are admitted;
- release roots/manifests contain required exact files/sizes/digests;
- exact relevant revisions are retained;
- immutable Release provenance records exact PRODUCT tag/source identity;
- published assets match Product Release authority contracts.

### Build / behavior

- Rust format/lint/tests and dependency/security gates required by PRODUCT policy;
- Android build/lint/unit/behavior/instrumentation coverage required by PRODUCT policy;
- secret persistence/backup/D2D remains fail-closed;
- compatibility ports/protocols remain protected;
- PRODUCT durable-state migrations/readiness remain deterministic.

PRODUCT evidence may claim software/Release acceptance. It cannot claim physical target state.

## 6. Stage 3 — exact phone deployment evidence

Required evidence:

- exact Product Release and Controller admission;
- target binding proof without publishing raw identifiers;
- durable mutation intent before destructive dispatch;
- at most one physical transaction effect for the semantic intent;
- exact installed APK where topology requires it;
- exact rooted-runtime inventory/materialization/current state;
- independent local postcondition observation;
- canonical terminal classification;
- ambiguous dispatch -> `UNKNOWN` -> read-only reconciliation before conflicting mutation.

A green workflow alone is not Stage-3 acceptance.

## 7. Stage 4 — phone production-node operational acceptance

Stage 4 is phone-only and must not claim complete proxy-product acceptance.

### 7.1 Controller exact-state convergence

- exact immutable Product Release admission precedes expected-state preparation;
- APK + rooted-runtime/current state uses one consistent Controller-owned concrete truth where normal Release observation, deployment postcondition and target-read-only reconciliation genuinely share the same facts;
- bounded exact/degraded/unknown evidence leaks no raw identifiers/config/secrets;
- workflow/job success is not target truth;
- Controller-only observation changes do not require a new Product Release when product bytes/semantics are unchanged;
- no speculative phone/VM framework before Stage 6.

### 7.2 Target-read-only projection reconciliation

Where current phone state is independently exact but an already-admitted public projection is stale:

- semantic identity is separate from `/deploy` and `/retry-deploy` mutation identity;
- exact target observation occurs first;
- no mutation intent is created;
- no APK/runtime/phone mutation occurs;
- historical Controller terminals are not rewritten;
- GitHub Deployment remains visibility projection only;
- missing/ambiguous projection fails closed;
- repeated identical reconcile is projection-layer no-op/idempotent when already correct.

### 7.3 Transport readiness / observation efficiency / evidence

- independent transport preflight proves runner assignment + registered-device ADB/root readiness without Release materialization;
- transport degradation is not classified as Product Release mismatch/runtime drift;
- Release observation records useful admission/materialization/phone-probe phase timings;
- cache entries are restricted to verified immutable/static intermediates with exact identity, atomic publication, per-use verification and bounded eviction;
- rendered secret-derived trees and mutable target observations are never retained as static cache truth;
- mandatory decision-grade evidence is durable; required evidence failure cannot produce acceptance success;
- recurring Broker/runner faults are represented only by bounded non-secret classification/counters needed for decisions.

### 7.4 Runner / host / USB recovery

The Stage-4 Issue binds the exact matrix from demonstrated failure domains, potentially including:

- existing runner-service session recovery without re-registration;
- WSL restart/cold-start;
- Windows restart + accepted owner-logon USB bridge path;
- USB detach/re-attach of only the registered/allowlisted phone path;
- transient Actions Broker/RunServer transport recovery.

Acceptance requires stable runner identity/labels, no unrelated device mutation and direct target observability before target claims resume.

### 7.5 Independent live operational observer

Operational health must be independently observable from immutable Release-state observation.

Where used by the selected phone topology, evidence includes:

- `runtime-supervisor`, `host-daemon`, `sing-box` process/service presence using bounded counters without publishing PID/cmdline;
- PRODUCT-owned authenticated local health/readiness contract rather than Controller reimplementation of PRODUCT health logic;
- serving/readiness/cellular prerequisites required by the phone node;
- bounded CPU/memory/FD/queue/log-growth indicators;
- result classification such as `READY`, `DEGRADED` or `UNKNOWN` without mutating the phone;
- operational failure does not rewrite an independently exact Release-state result.

### 7.6 Controlled phone-local lifecycle

Each perturbation must be a separately allowlisted fixed scenario with no arbitrary operator shell/argv surface and must have scenario identity, precondition, durable intent/evidence as appropriate, timeout, postcondition and recovery policy.

Required categories as bound by the Stage Issue:

- critical process termination -> automatic recovery;
- runtime restart -> exact operational + Release re-observation;
- full phone reboot -> exact accepted Release/runtime rehydration;
- phone-local network/degraded transition where meaningful without VM/provider mutation;
- runtime/config/current mismatch or tamper -> deterministic detection and fail-closed safe recovery/reconciliation.

Ambiguous destructive outcome never authorizes blind retry.

### 7.7 Bounded local resource sanity

Before Stage 4 exits, prove enough local resource behavior to establish the phone is a viable production node:

- bounded idle and bounded-exercise CPU/memory/process/FD/queue/log behavior;
- no immediate unbounded queue/log growth;
- no unexplained silent stuck state;
- no obvious monotonic local leak across the bounded phone-local exercise window;
- repetitions are chosen only for concrete phone failure modes, not inherited mechanically from historical counts.

Stage 4 does **not** need to manufacture production-scale throughput/concurrency or a long full-product soak before the VM exists.

### 7.8 Deferred full-topology evidence

The following belong to Stage 7 because they require the real VM/remote-consumer path:

- remote HTTP CONNECT/SOCKS5 acceptance;
- external mobile-egress IP proof;
- end-to-end DNS/IPv6/leak policy;
- production QUIC <-> pinned TLS/TCP failover through the real relay;
- production-scale external concurrency/throughput/latency;
- long production soak of the complete proxy path;
- cross-target degradation/recovery;
- full-topology release evolution/rollback.

### 7.9 Legitimate successor Product Release

Stage 4 may consume a real successor Product Release only when normal PRODUCT work independently creates one and the Stage-4 Issue needs deployment/rollback evidence. Never manufacture/repack a Release solely to satisfy a drill. The absence of such an artificial successor is not a Stage-4 exit blocker.

### 7.10 Local-agent / Controller feedback

If Controller cannot reliably observe a required phone fact, request the narrow local-agent fact and classify it exactly as:

- `controller_capability_gap`;
- `human_only_physical_observation`;
- `one_off_observation`.

Close a repeatable decision-critical Controller gap with the smallest safe observer/adapter capability only when it blocks acceptance and is simpler/safer than recurring manual dependence.

### 7.11 Stage-4 handoff

Before Stage 4 closes, retain:

- one exact evidence matrix for required categories;
- residual findings with owner/severity/disposition and no unresolved required P0/P1;
- active phone control-surface inventory: `retain`, `consolidate`, `isolate/deprecate`, `remove`;
- explicit Stage-4-only commands/workflows/version locks/recovery scaffolding;
- no guessed physical fact represented as accepted state.

## 8. Stage 5 — phone baseline convergence / simplification

Stage 5 consumes accepted Stage-4 evidence. It is not another broad physical test program.

Acceptance includes:

### One canonical phone Release-state path

- one concrete Controller-owned exact phone Release-state semantics remains where observe/postcondition/reconcile share the same truth;
- workflow/script duplicate desired-state/drift classification is removed;
- Actions/shell/ADB/GitHub Deployment remain adapters/projection, not state owners.

### Independent concerns remain independent

- transport diagnostics remain separate only when they own a real independent operational concern;
- live operational observation remains separate from immutable Release-state truth when the failure modes/lifecycle differ;
- route consolidation must not recreate the S4.3/S4.4 coupling by merging semantically independent evidence domains.

### One mutation/recovery model

- semantic request identity, target serialization, durable intent, exactly-once destructive dispatch, independent postcondition and `UNKNOWN` read-only recovery remain singular;
- projection reconcile remains separate from mutation identity/history;
- obsolete reconstruction/quarantine/migration/temporary recovery paths are removed or isolated after obligations end.

### Minimal operator/workflow surface

- every Issue #1 route/workflow has a current operator purpose;
- Stage-4-only variants are consolidated/removed where responsibilities are not independent;
- declarative registries equal the actually supported surface.

### Stable code/evidence ownership

- stable Release preparation/observation logic sits under the narrowest concrete Controller owner;
- immutable caches remain verified/bounded/disposable and contain no secret-derived rendered state;
- one developer can trace Release -> observation -> decision -> effect -> postcondition without contradictory status systems.

### Documentation / code deletion

- active normative docs converge on the real path;
- superseded historical material remains history, not execution guidance;
- redundant meta/wiring checks protecting no independent invariant are removed;
- PRODUCT/Controller authority boundaries remain intact.

Exit requires one singular protected phone baseline with no unresolved phone P0/P1/evidence-trust gap and no unjustified Stage-4 scaffolding.

## 9. Stage 6 — VM foundation and VM-local target acceptance

Only after #179 explicitly opens Stage 6 may VM/provider mutation occur.

Acceptance includes:

- one concrete real provider/VM lifecycle and target identity;
- required VM network/firewall/DNS/TLS/certificate/secrets ownership for the selected topology;
- exact immutable Product Release Linux/server artifact/provenance/digest;
- smallest VM-specific Controller adapter for any required provisioning hook, materialization, activation/service lifecycle and independent observation;
- durable intent/exactly-once mutation semantics reused from the Controller kernel;
- VM-local postcondition independent of workflow success;
- direct tests/evidence for concrete artifact/binding mismatch, partial materialization, activation/service failure, ambiguous dispatch and read-only reconciliation;
- provider credentials/mutation separated from the phone runner;
- required VM-local service/host restart/reboot recovery;
- one real canonical `ACCEPTED` VM deployment.

Stage 6 is the first normal point for extracting a shared phone/VM target abstraction from demonstrated duplication. No generic multi-target/provider platform.

## 10. Stage 7 — complete PHONE + VM operational acceptance

Bind the exact real topology when Stage 7 opens:

```text
external consumer
  <-> VM / relay / serving edge
  <-> authenticated reverse tunnel
  <-> registered phone runtime
  <-> selected mobile/cellular egress
  <-> Internet
```

Required combined evidence includes:

### Identity / compatibility

- exact accepted phone and VM identities;
- explicit permitted version/compatibility relation;
- no mutable/latest identity.

### Real external serving

- remote HTTP including CONNECT where supported;
- remote SOCKS5 where supported;
- authentication and wrong-credential behavior;
- actual external mobile-egress identity where claimed.

### Network / confidentiality

- production QUIC primary path;
- certificate-pinned TLS/TCP reserve/failover/recovery where production uses it;
- no plaintext downgrade/wrong-session routing;
- DNS/IPv6/leak behavior for the selected topology.

### Cross-target lifecycle / degradation

- phone critical-process/runtime restart and full phone reboot while topology is in use;
- VM service/host restart/reboot/reconnect;
- cellular loss/recovery;
- deterministic partial-target degradation;
- no blind destructive retry during cross-target ambiguity.

### Real load / overload

- external-client concurrency;
- production-relevant throughput/latency;
- bounded overload behavior;
- bounded CPU/memory/FD/queue/log state on relevant targets;
- no silent stuck state or unbounded growth.

### End-to-end soak / reliability

- production-like long-duration soak through the complete path;
- periodic functional/resource observations;
- exact duration/cadence/repetition matrix chosen from real measured behavior and the failures being protected, not mechanically inherited historical values.

### Release evolution / rollback

When production claims upgrade/rollback support:

- only legitimate immutable Product Releases and compatible signing/version relationships are used;
- durable intent precedes target effects;
- duplicate/retry cannot create a second destructive effect;
- local postconditions remain independent;
- ambiguous result -> `UNKNOWN` -> read-only reconciliation;
- the approved topology is restored and independently verified end-to-end.

No unresolved cross-target P0/P1 may remain at final acceptance.

## 11. Security and operational review

At the stage owning each surface, verify applicable:

- firewall/exposure boundaries;
- credential/provider separation;
- certificate pinning and wrong-credential failure behavior;
- release/backup permissions and rollback immutability;
- dependency/security audit results;
- explicit residual-risk records.

A full independent penetration test, fleet orchestration, generic chaos platform or hypothetical provider matrix is outside baseline acceptance unless separately promoted.

## 12. Final decision

Declare full production 10/10 accepted only when:

- exact PRODUCT software/Release evidence is accepted;
- Controller transaction/recovery invariants are accepted for the real targets;
- Stage-4 phone-node and Stage-5 baseline exits are satisfied;
- Stage-6 VM-local exit is satisfied;
- Stage-7 complete topology passes the agreed functional/network/recovery/load/soak matrix;
- no unresolved P0/P1 remains;
- all evidence is bound to the exact Product Release, Controller revision and causal target dependencies it claims;
- no sensitive target/secret material was made public.

Architecture/documentation convergence may complete earlier. It must never be represented as live physical acceptance.
