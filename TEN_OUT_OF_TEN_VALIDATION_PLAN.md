# 10/10 Reproducibility and Reliability Validation Catalog

Status: **normative acceptance catalog; not execution authority**  
Dynamic engineering/operations cursor: newest authoritative checkpoint in PRODUCT Issue #179  
Static stage sequence: `docs/PRODUCTION_STAGE_ROADMAP.md`  
Planning backlog: PRODUCT Issue #249  
Authority boundary: `docs/operations/project-authority.md`

This document defines evidence that final production acceptance may require. It does **not** authorize tests from later stages early. The newest #179 checkpoint selects the current stage; that stage's Issue binds the concrete matrix and identities.

Historical A-H ordering is superseded as execution sequencing. Its useful acceptance requirements are mapped below into the seven-stage model.

## 1. Meaning of 10/10

The project distinguishes:

1. **PRODUCT software/release accepted** — required source-controlled security, behavior, dependency, build and immutable Product Release gates pass on exact reviewed PRODUCT identity.
2. **Target accepted** — an exact immutable Product Release plus exact admitted Controller revision has direct target-local deployment/operational evidence for the stage that owns that target.
3. **Full production 10/10 accepted** — PRODUCT, Controller and the complete real PHONE+VM topology pass the Stage 7 functional/recovery/load/soak definition with no unresolved P0/P1.

CI is necessary but cannot manufacture Android boot behavior, modem routing, carrier behavior, physical process state, VM host state or long-running reliability evidence.

Both repositories are public:

- `iamaman11/mobile-proxy` = PRODUCT authority;
- `iamaman11/mobile-proxy-production` = DEPLOYMENT CONTROLLER authority.

Secrets, target bindings, raw target identifiers, credentials, private keys, sensitive rendered config and unsafe raw runtime logs remain private.

## 2. Release and deployment identity

```text
product_release
  = exact annotated semantic tag
  + exact PRODUCT source SHA
  + exact immutable Product Release assets/provenance

runtime_deployment_identity
  = product_release
  + exact admitted Deployment Controller revision
```

A Controller-only repair does not force a rebuild of unchanged product bytes. A new Product Release does not silently redefine which Controller revision deployed it.

`latest`, mutable refs, approximate versions or GitHub Deployment projection are not runtime identity.

## 3. Runtime and Android roles

The primary phone runtime is:

```text
root/Magisk boot hook
  -> runtime-supervisor
      -> host-daemon
      -> sing-box on loopback
          -> certificate-pinned QUIC reverse tunnel
          -> certificate-pinned TLS/TCP reserve
```

The Android app is **not the primary reverse-tunnel owner**. It is a managed PRODUCT component for Android-owned capabilities such as cellular `Network.bindSocket()` egress and the app-owned WireGuard compatibility path when the selected topology consumes them.

Primary invariants include:

- `tunnel_owner=first_party_reverse_tunnel` for native primary mode;
- no plaintext downgrade;
- exact device/tunnel-session authority;
- no arbitrary available-device routing;
- exact APK package/version/signer/artifact identity when the topology consumes Android app capability;
- stock WireGuard only as explicit compatibility/rollback where production policy permits it.

## 4. Stage mapping rule

Acceptance evidence belongs to the **earliest stage whose exit depends on it**. A later-stage test is not pulled forward merely because this catalog contains it.

- Stage 1 — Controller phone transaction semantics, no live phone acceptance requirement.
- Stage 2 — immutable Product Release/software identity.
- Stage 3 — one exact phone deployment and local postcondition.
- Stage 4 — phone-only industrial operational validation.
- Stage 5 — phone baseline simplification/evidence convergence.
- Stage 6 — VM-local transaction and first real VM deployment.
- Stage 7 — combined PHONE+VM end-to-end acceptance.

## 5. PRODUCT software and immutable Release evidence — Stages 1–2 prerequisites

As applicable to the current Product Release contract:

### Architecture and policy

- product/application/domain dependency boundaries;
- native reverse-tunnel default enforcement;
- Android auxiliary role cannot silently become primary tunnel owner;
- unknown/contradictory tunnel ownership fails closed;
- bounded errors, queues and retries;
- PRODUCT is the sole product source/build/release authority;
- Controller is the sole deployment transaction/target-mutation authority;
- no active duplicate Controller implementation in PRODUCT.

### Cryptographic and release integrity

- admitted typed digest contracts;
- release roots/manifests include exact files/sizes/digests as required;
- exact full relevant revisions are recorded;
- final published artifact provenance records exact PRODUCT tag/source identity;
- release artifacts match the Product Release authority contract.

### Build and behavior

- Rust formatting/lint/tests and dependency/security gates;
- Android build/lint/unit/behavior/instrumentation coverage required by PRODUCT policy;
- secret persistence/backup/D2D policy is fail-closed;
- product compatibility ports/protocols remain protected;
- PRODUCT durable-state migrations and readiness semantics remain deterministic.

Only PRODUCT evidence may claim software/release acceptance. It cannot claim physical target state.

## 6. Stage 3 — exact phone deployment evidence

Use the exact immutable Product Release and registered phone through the admitted Controller revision.

Required evidence includes:

- exact Release and Controller admission;
- target binding proof without publishing raw identifiers;
- durable mutation intent before destructive dispatch;
- exactly-once physical transaction semantics;
- exact installed APK when required by topology;
- exact rooted runtime inventory/materialization;
- exact active/current release;
- independent postcondition observation;
- canonical terminal classification;
- any ambiguous dispatch -> `UNKNOWN` -> read-only reconciliation before conflicting mutation.

A successful workflow alone is not Stage 3 acceptance.

## 7. Stage 4 — phone industrial operational validation

Stage 4 is **phone-only**. It does not authorize VM/provider creation, VM restart matrices or combined topology acceptance.

The current Stage 4 Issue binds the exact concrete matrix. Passing a control-plane subplan alone is insufficient: the full phone serving/recovery/resource/soak exit must be evidenced.

### Controller exact-state convergence

Stage 4 must prove that normal phone observation, deployment postcondition and target-read-only reconciliation do not carry independent definitions of desired phone state.

Required properties:

- exact immutable Product Release admission precedes Release-bound expected-state preparation;
- APK + rooted-runtime current state is observed through one consistent Controller-owned phone Release state semantics;
- bounded result distinguishes exact, degraded and unknown without leaking raw identifiers/config/secrets;
- workflow/job success is not a second target truth;
- a Controller-only change to observation/reconciliation semantics does not force a new Product Release when product bytes/behavior are unchanged;
- no generic phone/VM target framework is introduced merely to share one phone capability; cross-target abstraction waits for Stage 6 unless another present-day requirement proves it necessary.

### Target-read-only reconciliation

Where the durable mutation ledger contains historical terminal state but the current phone is independently proven exact, Stage 4 may require a separately admitted reconciliation operation.

Acceptance for that operation includes:

- semantic identity is separate from `/deploy` and `/retry-deploy` mutation identity;
- exact current target observation occurs before any projection write;
- no mutation intent is created;
- no APK/runtime dispatch or phone filesystem/package mutation occurs;
- the historical Controller terminal is not rewritten or retroactively converted;
- public GitHub Deployment remains visibility projection only;
- only one uniquely matching already-admitted projection may be repaired; missing or ambiguous projection fails closed rather than manufacturing history;
- a second identical reconcile is idempotent/no-op at the projection layer when no correction is required.

### Transport, observation efficiency and evidence

- independent phone transport preflight proves runner assignment, exact registered-device ADB state and required root capability without Release materialization;
- Release observation records separate admission/materialization/phone-probe timings rather than only one total;
- immutable/static cache entries are content-addressed, verified on every reuse, atomically published, bounded and disposable;
- cache hits never skip immutable Release admission or integrity verification;
- secret-derived rendered trees and mutable phone observations are never retained as static cache truth;
- mandatory decision-grade evidence is durable; required evidence upload failure cannot produce a green acceptance result;
- recurring Broker/runner errors are represented by bounded non-secret counters/classification without publishing raw listener logs or credentials.

### Runner / host / USB recovery

The exact Stage Issue selects the required host drills. Evidence should distinguish at least the recovery layers it exercises:

- existing runner-service session recovery without re-registration;
- WSL restart/cold-start recovery;
- Windows restart followed by the accepted owner-logon bridge path where that is the chosen USB ownership model;
- USB detach/re-attach recovery of only the registered/allowlisted phone path;
- transient GitHub Actions Broker/RunServer transport recovery.

Acceptance requires runner identity/labels remain unchanged, no unrelated USB/network target is modified, and the registered phone returns to an observable state before target claims resume.

### Serving and process health

- phone-local proxy/runtime is actually serving the selected phone-side path;
- `runtime-supervisor`, `host-daemon` and `sing-box` health/readiness is correct where used;
- rendered runtime configuration matches admitted topology without exposing secrets;
- no false success when service is not actually usable.

A failure in actual PRODUCT/runtime serving, lifecycle, resource or boot behavior is a PRODUCT defect. A failure in Controller admission/observation/target adapter/evidence/projection/runner control is a Controller defect. Fix the owning plane rather than moving responsibility across the PRODUCT/Controller boundary.

### Restart and reboot

- bounded runtime-supervisor termination/recovery;
- bounded host-daemon termination/recovery;
- bounded sing-box termination/recovery;
- full phone reboot followed by correct rehydration of exact accepted release/runtime;
- recovery evidence distinguishes process restart, boot/session change and deployment mutation.

### Network/degraded behavior

- phone-local loss/recovery of mobile-data path where required;
- QUIC failure/reserve behavior only where it can be tested without opening Stage 6 provider/VM mutation;
- deterministic classification of degraded/unavailable states;
- causal re-observation invalidates only facts whose dependencies changed;
- no plaintext or wrong-session fallback.

### Tamper/mismatch

- detect relevant runtime/config/current mismatch;
- classify the bounded mismatch sufficiently to select safe recovery without exposing secret-derived data;
- fail closed rather than report accepted/healthy state from stale evidence;
- recovery or reconciliation does not blindly repeat destructive mutation.

### Resource/load

- bounded CPU/memory/process/file-descriptor/queue behavior for the phone runtime under the load actually used by the selected phone topology;
- bounded concurrency and explicit overload behavior;
- no monotonic resource leak or unbounded queue/log growth.

### Phone-side repetitions and soak

The Stage 4 Issue may bind repetitions from the historical reliability model when they remain necessary and feasible. Historical targets included:

- up to 20 full phone reboots;
- up to 20 forced terminations for each critical phone runtime process;
- up to 20 mobile-data disconnect/reconnect events;
- bounded QUIC/reserve/return cycles where Stage-4 scope can exercise them safely;
- bounded rotation cycles when rotation is part of the selected phone topology;
- a production-like phone-side soak, historically 24 hours, with periodic serving/resource checks.

These numbers are acceptance targets/catalog values, **not automatic authorization for destructive operations**. The current Stage Issue must bind the exact agreed matrix, and #179 must authorize any mutation/physical-test boundary involved.

### Controlled successor deployment and rollback

Stage 4 may consume a legitimate successor Product Release created through normal PRODUCT authority when Stage 4 product/runtime fixes or normal release progression produce one. Do not create a fake/repacked Product Release solely to satisfy a drill.

When a successor deployment/rollback drill is part of the Stage Issue matrix, evidence must prove:

- one durable mutation intent before the first possible destructive effect;
- at most one destructive dispatch for the intent;
- atomic activation/materialization properties required by the phone target;
- exact independent postcondition;
- duplicate/retry handling cannot create a second mutation;
- rollback selects a retained immutable prior APK/runtime Release with compatible signing lineage;
- ambiguous rollback is `UNKNOWN` and fail-closed;
- the approved final target is restored and independently verified.

### Local-agent evidence and Controller feedback

If Controller cannot reliably observe a required phone fact, request the narrow local-agent observation instead of guessing. Classify it as:

- `controller_capability_gap`;
- `human_only_physical_observation`;
- `one_off_observation`.

A repeatable or decision-critical Controller capability gap that blocks Stage 4 should be closed with the smallest safe observer/adapter improvement when that is simpler than recurring manual dependence. Local-agent mutation never bypasses Controller transaction authority.

### Stage 4 reliability thresholds

For the concrete repeated categories selected by the Stage Issue, use bounded thresholds appropriate to the measured sample. The historical acceptance targets remain:

- automatic recovery success rate at least 99.5% where sample size can meaningfully support that claim;
- median recovery under 20 seconds;
- p95 recovery under 60 seconds;
- no silent stuck state longer than 60 seconds;
- no success classification while the required phone service/path is unusable;
- no unexplained degraded state.

With small fixed samples, one unexplained failure blocks acceptance rather than being hidden by percentages.

### Stage 4 handoff evidence

Before Stage 4 closes, retain one bounded handoff matrix mapping every accepted category above to exact evidence and classifying every active phone control surface as `retain`, `consolidate`, `isolate/deprecate`, or `remove` for Stage 5. Stage 5 must not begin by rediscovering which Stage 4 paths were temporary.

## 8. Stage 5 — phone baseline acceptance / simplification

Stage 5 is not another broad physical test program. It consumes the completed Stage 4 evidence/handoff and leaves one long-term phone path.

Acceptance includes:

### One canonical phone control path

- one concrete Controller-owned exact phone Release state semantics remains for normal observation, deployment postcondition and reconciliation where applicable;
- workflow/script-specific duplicate desired-state/drift classification is removed;
- Stage-4-only release/version bindings are removed from long-term operation unless a real compatibility contract requires them;
- GitHub Actions, shell, ADB and GitHub Deployment remain adapters/projection, not parallel state owners.

### One mutation/recovery model

- preserve semantic deployment identity, target serialization, durable mutation intent, exactly-once destructive dispatch, independent postcondition and `UNKNOWN` read-only recovery;
- projection reconciliation remains separate from deployment mutation identity and cannot rewrite private canonical terminal history;
- redundant v1/reconstruction/quarantine/migration/temporary-recovery paths are removed or isolated once their retained evidence/rollback obligations no longer require them.

### Minimal command/workflow surface

- every active Issue #1 route and production workflow has one current operator purpose;
- preflight/diagnostic routes remain separate only when they own an independent operational concern;
- routes/workflows that exist only because of Stage 4 implementation history are consolidated or removed;
- declarative command/target registries describe the actual supported production surface, with no dormant competing authority paths.

### Stable materialization/cache/evidence ownership

- stable phone Release preparation/observation logic sits under the narrowest real Controller owner rather than being imported from workflow-private helpers by multiple consumers;
- immutable cache optimizations remain bounded, verified, disposable and free of secret-derived rendered state;
- evidence schemas let one developer trace exact Release -> observed state -> decision -> possible effect -> postcondition without joining contradictory status systems;
- local-agent observations that revealed reusable Controller gaps are either implemented where required or explicitly dispositioned with stage mapping.

### Documentation, authority and code deletion

- converge normative phone/Controller docs and ownership on the real path;
- remove active stale A-H/Item15-23/Item19-20 execution language and stale backlog/cursor roles while retaining historical audit evidence as historical;
- reduce active workflows/policies/code/cognitive surface wherever an independent invariant does not require separation;
- remove redundant wiring/meta-verification checks that only prove other tests/checks exist;
- verify PRODUCT remains application/runtime/build/Release authority and Controller remains deployment/target execution authority.

### Generalization boundary

Stage 5 may make phone-specific ownership coherent, but it must not build a speculative generic phone/VM target framework. Stage 6 is the first normal point for shared target abstractions from two real implementations.

Exit requires one singular, protected, documented phone baseline with no unresolved phone P0/P1 or evidence-trust gap and no active Stage-4-only scaffolding lacking a long-term justification.

## 9. Stage 6 — VM-local transaction and first real VM deployment

Only after #179 explicitly opens Stage 6 may VM/provider mutation occur.

Acceptance includes:

- one concrete real VM lifecycle and target identity;
- exact immutable Product Release Linux artifact/provenance/digest;
- smallest VM-specific Controller adapter for materialization, activation/service lifecycle and independent observation;
- durable intent and exactly-once mutation semantics reused from the Controller kernel;
- VM-local postcondition independent of workflow success;
- direct tests for artifact mismatch, binding mismatch, partial materialization, activation/service failure, ambiguous dispatch and read-only reconciliation;
- provider credentials/mutation separated from phone runner;
- explicit provisioning/replacement ownership only if the chosen real lifecycle requires it;
- one real canonical `ACCEPTED` VM deployment.

VM-local restart/reboot checks required to prove that target may occur here. Combined PHONE+VM behavior remains Stage 7.

Stage 6 is the first normal point for extracting shared target abstractions from demonstrated phone/VM duplication. No generic multi-target platform.

## 10. Stage 7 — combined PHONE + VM operational acceptance

Bind the exact real topology when Stage 7 opens. Expected class:

```text
external client
  <-> VM / relay / serving edge
  <-> reverse tunnel
  <-> registered phone runtime
  <-> selected mobile/cellular egress
```

Required combined evidence includes:

- exact accepted identities of phone and VM and permitted compatibility/version relationship;
- authenticated end-to-end proxy path through both targets;
- required public compatibility endpoints;
- phone restart/reboot and VM service/host restart/reconnect interactions;
- deterministic partial-target unavailability;
- recovery on either target without blind destructive retry;
- QUIC primary and certificate-pinned TLS/TCP reserve behavior across the real path where production uses it;
- provider/relay lifecycle operations only when they are part of the selected real topology;
- bounded load/resources across the whole path;
- end-to-end soak/leak/reliability evidence;
- no unresolved cross-target P0/P1.

Historical relay-side targets may inform the Stage 7 matrix, including repeated service restarts, VM reboots, backup/restore and delete/recreate drills. They are not Stage 4 work and are executed only when Stage 7/#179 authority and the concrete VM lifecycle require them.

## 11. Security and operational review

At the stage that owns each surface, verify applicable firewall exposure, credential separation, certificate pinning, wrong-credential failure behavior, release/backup permissions, rollback immutability, dependency audit results and explicit residual-risk records.

A full independent penetration test, fleet orchestration, generic chaos platform or hypothetical provider matrix is outside the baseline unless separately promoted.

## 12. Final decision

Declare full production 10/10 accepted only when:

- exact PRODUCT software/Release evidence is accepted;
- Controller transaction/recovery invariants are accepted for real targets;
- phone Stage 4 and Stage 5 exits are satisfied;
- VM Stage 6 exit is satisfied;
- Stage 7 combined topology passes the agreed functional/recovery/load/soak matrix;
- no unresolved P0/P1 remains;
- all evidence is bound to the exact Product Release, Controller revision and causal target dependencies it claims;
- no sensitive target/secret material was made public.

Architecture/documentation convergence may complete earlier. It must never be misrepresented as live physical acceptance.
