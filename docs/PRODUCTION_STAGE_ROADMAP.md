# Production Stage Roadmap

Status: **canonical static Stage 1-7 plan**  
Dynamic authority: newest authoritative checkpoint in PRODUCT Issue #179  
Current-stage execution detail: the one subordinate Stage Issue  
Planning backlog: PRODUCT Issue #249  
Working method: `STAGE_WORKFLOW.md`

This file is the **single source of truth for the complete production stage sequence, each stage goal, scope, non-goals and exit boundary**.

It intentionally contains no dynamic `CURRENT` stage, current SHA, current Product Release, next action or mutation authority. Those belong only to PRODUCT Issue #179 and the current subordinate Stage Issue.

Related owners:

- `docs/PRODUCTION_BASELINE_PLAN.md` — durable architecture/topology/invariants, not sequencing;
- `docs/architecture/ARCHITECTURE_STANDARD.md` — permanent engineering/complexity quality floor;
- `TEN_OUT_OF_TEN_VALIDATION_PLAN.md` — acceptance evidence catalog mapped to these stages, not sequencing or action authority;
- PRODUCT Issue #249 — candidate backlog only, not a second roadmap.

## Stage model

A stage is accepted because one real functional/safety/authority outcome is proven. Stages are dependency boundaries, not arbitrary implementation batches.

Each stage has exactly one subordinate Stage Issue while it is current. The Stage Issue may refine implementation order and the concrete evidence matrix inside the stage, but it must not redefine this roadmap or open a later stage by itself.

Architecture work is not a parallel lane. A demonstrated architecture defect, evidence-trust gap or Controller capability gap enters the earliest stage whose exit it blocks. Future recommendations remain inactive until #179 promotes the owning stage.

The project deliberately separates three evidence domains:

1. **Release state** — exact immutable Product Release and exact target materialization/state.
2. **Target operational state** — whether one accepted target is locally healthy, observable and recoverable.
3. **Full-system state** — whether the real PHONE+VM topology serves remote consumers correctly under failure, load and time.

Passing an earlier domain never manufactures evidence for a later one.

---

## Stage 1 — Deployment Controller composite phone transaction foundation

### Goal

Establish one Controller-owned durable phone transaction for the complete phone Product Release: APK + rooted runtime.

### Required properties

- exact immutable Product Release admission/materialization;
- target-global serialization;
- observation before decision;
- durable mutation intent before destructive dispatch;
- at most one destructive dispatch per intent;
- complete APK + rooted-runtime local postcondition;
- ambiguous physical result -> `UNKNOWN` -> read-only reconciliation, never blind retry.

### Exit

The Controller phone transaction semantics are protected and directly tested without requiring a real production phone mutation merely to prove code structure.

---

## Stage 2 — Immutable Product Release

### Goal

Publish one exact immutable Product Release through the normal reproducible PRODUCT path and prove Controller admission of its complete identity.

### Scope

- exact protected PRODUCT source and required Quality/release prerequisites;
- annotated semantic tag;
- Linux, Android and rooted-phone runtime artifacts required by the active Product Release contract;
- manifest, provenance and artifact digests;
- immutable Release verification;
- exact Controller admission proof.

### Exit

The intended Product Release exists immutably with exact source/run/release evidence and Controller admission proof.

No production deployment, phone mutation or VM/provider mutation is implied by this stage.

---

## Stage 3 — First real phone deployment

### Goal

Prove the Controller on the registered production phone with one exact immutable Product Release.

### Scope

- fresh Release/Controller/target/binding revalidation;
- one semantic deployment request under #179 authority;
- one composite APK + rooted-runtime physical transaction;
- atomic activation and complete independent local postcondition;
- durable terminal evidence;
- deterministic known-state recovery and read-only reconciliation after ambiguity.

### Exit

The registered phone reaches canonical `ACCEPTED` for the exact Product Release with complete durable identity/postcondition evidence and no unresolved physical ambiguity.

---

## Stage 4 — Phone production-node operational acceptance

### Goal

Prove the already accepted `phone-production` target is a trustworthy **production node**: exact Release state remains independently observable, the live runtime is locally healthy, the node recovers deterministically across real phone/runner failure domains, and local resource behavior is bounded enough to hand a stable phone system to Stage 5.

Stage 4 is **phone-only**. It does not claim that the complete Mobile Proxy product is accepted, because the real external-client -> VM -> reverse-tunnel -> phone -> cellular path does not exist until later stages.

### Required separation of observation concerns

Stage 4 preserves independent evidence domains rather than extending one command until it owns everything:

```text
transport readiness
  != exact Release state
  != live operational health
  != lifecycle exercise result
```

Required properties:

- transport readiness may diagnose runner/host/USB/ADB/root without redefining phone Release truth;
- exact Release observation proves immutable APK + rooted-runtime/current state only;
- live operational observation is a separate read-only concern and may report `READY`, `DEGRADED` or `UNKNOWN` without rewriting an otherwise exact Release-state result;
- lifecycle perturbations are separately allowlisted operations with durable intent/evidence, fixed scenarios, bounded timeout and exact postconditions; they are not manual/free-form ADB shells.

### Workstreams

1. **Exact state / Controller trust**
   - keep one coherent Controller-owned exact phone Release state semantics for observation, deployment postcondition and target-read-only reconciliation where those consumers require the same APK + rooted-runtime truth;
   - keep transport preflight independent from Release materialization;
   - prove bounded exact/degraded/unknown evidence with no raw identifiers/secrets;
   - retain separately admitted target-read-only projection reconciliation for the demonstrated already-exact/historical-ledger case, with no mutation intent, target dispatch or historical-terminal rewrite.

2. **Observation efficiency / evidence resilience**
   - measure admission, immutable/static verification/materialization, secret-derived preparation and direct target probe phases separately;
   - cache only verified immutable/static intermediates with exact identity, atomic publication, re-verification and bounded eviction;
   - never persist secret-derived rendered trees or mutable phone truth as cache state;
   - required decision-grade evidence failure remains fail-closed;
   - recurring runner/Broker faults may justify only the smallest demonstrated diagnostic/recovery capability.

3. **Runner / host / USB resilience**
   - prove the registered runner recovers without re-registration or label/identity drift;
   - cover the selected Windows/WSL/USB ownership boundary and transient Actions transport recovery;
   - keep host transport recovery separate from deployment mutation authority.

4. **Phone-local runtime observation and lifecycle**
   - independently observe `runtime-supervisor`, `host-daemon`, `sing-box` and PRODUCT-owned authenticated local health/readiness where used;
   - observe serving/readiness/cellular prerequisites and bounded process/resource indicators without publishing PID/cmdline, credentials, raw responses or sensitive config;
   - prove bounded critical-process termination -> automatic recovery;
   - prove runtime restart -> exact re-observation;
   - prove full phone reboot -> exact Release/runtime rehydration;
   - prove deterministic local network/degraded classification required by the phone node;
   - prove runtime/config/current mismatch or tamper is detected and fails closed, followed only by safe admitted recovery/reconciliation.

5. **Bounded phone resource sanity**
   - establish idle/bounded-exercise CPU, memory, process, file-descriptor, queue and log-growth bounds;
   - prove no immediate unbounded queue, silent stuck state or obvious monotonic leak under the phone-local workload that can be meaningfully exercised without the VM;
   - use repetitions only where they directly protect a demonstrated phone failure mode.

### Explicit non-goals / deferred evidence

The following are **not required to close Stage 4** because their production meaning depends on the real VM/remote-consumer topology:

- full remote HTTP CONNECT/SOCKS5 acceptance;
- external mobile-egress IP proof;
- end-to-end DNS/IPv6/leak policy;
- production QUIC <-> pinned TLS/TCP failover through the real relay;
- production-scale concurrency/throughput/latency claims;
- long production soak of the complete proxy path;
- cross-target recovery or topology rollback.

A legitimate successor Product Release may be deployed/rolled back inside Stage 4 only when normal PRODUCT work independently creates one and the current Stage Issue explicitly needs that evidence. Absence of a manufactured successor Release is not a Stage-4 exit blocker.

### Product vs Controller defect routing

- actual PRODUCT/runtime serving, lifecycle, health semantics, resource or boot defects -> PRODUCT/runtime;
- admission/observation/target-adapter/evidence/projection/runner-control defects -> Controller;
- inherently physical/UI facts -> narrow local-agent evidence.

A Controller-only repair does not force a new Product Release. A PRODUCT/runtime repair follows protected PRODUCT delivery and immutable Product Release authority before any new physical deployment.

### Stage 4 -> Stage 5 handoff

Before Stage 4 closes, retain:

- one evidence matrix for every required Stage-4 category;
- every unresolved finding classified by owner/severity/disposition;
- a phone control-surface inventory classified `retain`, `consolidate`, `isolate/deprecate`, or `remove`;
- an explicit list of Stage-4-only commands/workflows/version locks/recovery scaffolding;
- no guessed physical fact represented as accepted state.

### Exit

`phone-production` is independently exact, locally operational, observable and recoverable across the agreed phone/runner matrix; bounded local resource sanity is accepted; no required phone P0/P1 remains; and the Stage-5 simplification handoff is complete.

---

## Stage 5 — Phone production baseline convergence / simplification

### Goal

Turn the proven Stage-4 phone node into one understandable, low-cognitive-cost long-term phone production baseline **before adding the second real target**.

Stage 5 is primarily deletion/convergence, not another broad physical-validation program.

### Required inputs

- accepted Stage-4 phone-node evidence matrix;
- zero unresolved Stage-4 P0/P1;
- explicit phone control-surface inventory;
- demonstrated retain/consolidate/isolate/remove candidates;
- exact owner classification for residual PRODUCT, Controller or human-only dependencies.

### Workstreams

1. **One phone Release-state path**
   - retain one concrete Controller-owned exact phone Release state semantics where observation/postcondition/reconcile share the same truth;
   - remove duplicate workflow/script-specific desired-state or drift classification;
   - keep GitHub Actions/shell/ADB as adapters, not alternate state owners.

2. **Independent operational observation**
   - retain a separate operational/diagnostic surface only where it owns a genuinely independent operator concern;
   - do not fold live health/process/resource semantics back into the immutable Release-state observer merely to reduce command count.

3. **One mutation/recovery kernel**
   - preserve semantic request identity, target serialization, durable intent, exactly-once destructive dispatch, independent postcondition and `UNKNOWN` read-only recovery;
   - keep projection reconciliation separate from mutation identity/history;
   - remove/isolate superseded reconstruction, quarantine, migration and temporary recovery paths once their obligations are satisfied.

4. **Minimal operator/workflow surface**
   - every active Issue #1 route/workflow has one current operator purpose;
   - consolidate/remove routes that differ only because of Stage-4 implementation history;
   - keep declarative registries equal to the actually supported production surface.

5. **Stable materialization/cache/evidence ownership**
   - retain only demonstrated bounded immutable-cache/transport optimizations;
   - keep secret-derived rendering ephemeral and physical target truth out of static caches;
   - converge evidence schemas so one developer can trace Release -> observation -> decision -> possible effect -> postcondition.

6. **Documentation/test convergence**
   - remove active stale execution-language/duplicate ownership while retaining audit history;
   - keep direct tests for real behavior/failure/security/authority boundaries;
   - delete redundant meta/wiring checks that protect no independent invariant.

### Generalization boundary

Do not build a speculative phone/VM framework in Stage 5. Stage 6 is the first normal point where two real target implementations may justify extracting a shared boundary.

### Exit

Exactly one protected, documented and directly evidenced phone-production baseline remains, with one mutation/recovery kernel, bounded independent observation surfaces, no unjustified Stage-4 scaffolding, no unresolved phone P0/P1/evidence-trust gap, and a clear seam for adding one real VM target.

---

## Stage 6 — VM foundation, transaction and first real VM acceptance

### Goal

Create the real VM/server side of the selected production topology and accept `vm-production` as the second real Controller target without weakening the proven phone baseline.

### Scope

- choose and bind one concrete provider/VM lifecycle and target identity; no hypothetical provider matrix;
- establish the required VM networking/firewall/DNS/TLS/certificate/secrets ownership for the selected topology;
- materialize the immutable Product Release Linux/server artifact with exact provenance/digest identity;
- keep phone-runtime-only identity/realization fields out of VM admission/materialization;
- add the smallest VM-specific Controller adapter for provisioning hooks where needed, materialization, activation/service lifecycle and independent local observation;
- reuse semantic request identity, durable intent, target serialization, exactly-once destructive boundary and read-only `UNKNOWN` recovery;
- keep provider credentials/provider mutation off the phone runner;
- prove concrete VM-local service restart/host restart/reboot/reconciliation failure modes required for target acceptance;
- perform one separately authorized first real `vm-production` deployment.

### Generalization boundary

This is the first normal point where phone and VM are two real target implementations. Extract a shared target abstraction only when concrete duplication exists, both sides express the same responsibility/lifecycle, and the extracted boundary is simpler than two thin adapters.

Do not build a generic provider platform, multi-target orchestrator, executor framework or service mesh.

### Exit

One real production VM is canonical `ACCEPTED` with exact immutable Product Release identity, exact Controller revision, durable intent and independent VM-local postcondition/lifecycle evidence. The phone baseline remains accepted and unaffected. The real topology prerequisites required for combined testing now exist.

---

## Stage 7 — Full PHONE + VM product/topology acceptance

### Goal

Prove the complete Mobile Proxy product as one operating production topology rather than two independently successful targets.

Bind the exact topology when Stage 7 opens. Intended class:

```text
external consumer
  <-> VM / relay / serving edge
  <-> authenticated reverse tunnel
  <-> registered phone runtime
  <-> selected mobile/cellular egress
  <-> Internet
```

### Required combined evidence

1. **Identity / compatibility**
   - exact accepted phone and VM identities plus permitted version/compatibility relationship;
   - no mutable/latest identity.

2. **Real external serving**
   - HTTP including CONNECT and SOCKS5 compatibility actually used by remote consumers;
   - authentication and wrong-credential failure behavior;
   - real external mobile-egress IP behavior where claimed by the product.

3. **Network correctness / confidentiality**
   - production QUIC primary path and certificate-pinned TLS/TCP reserve behavior;
   - no plaintext downgrade or wrong-session routing;
   - DNS/IPv6/leak behavior for the selected topology.

4. **Cross-target lifecycle / degradation**
   - phone process/runtime restart and full phone reboot while the topology is in use;
   - VM service/host restart/reboot/reconnect behavior;
   - cellular loss/recovery and deterministic partial-target degradation;
   - no blind destructive retry during cross-target ambiguity.

5. **Real load / concurrency / overload**
   - external-client concurrency, throughput/latency and bounded overload behavior across the complete path;
   - bounded CPU/memory/FD/queue/log behavior on the relevant targets;
   - no silent stuck state or unbounded growth.

6. **End-to-end soak / reliability**
   - production-like long-duration soak through the complete path with periodic functional/resource observations;
   - concrete duration/cadence/repetition matrix bound by the Stage-7 Issue from real measured behavior, not inherited automatically from historical numbers.

7. **Release evolution / rollback of the real topology**
   - when production lifecycle claims upgrade/rollback support, use only legitimate immutable Product Releases and compatible signing/version relationships;
   - preserve durable intent, exactly-once target effects and independent local postconditions;
   - ambiguous result -> `UNKNOWN` -> read-only reconciliation;
   - restore the approved topology and independently verify end-to-end service.

### Minimality

Every Stage-7 test must name the real production failure it protects against. Do not create a generic distributed orchestrator, service mesh or chaos platform merely to increase coverage.

### Exit

PHONE + VM production passes final full-system functional, network, recovery, real-load and soak acceptance with singular authority, direct target-local proofs, end-to-end evidence and no unresolved P0/P1.

---

## Promotion and fail-closed rules

- The newest #179 checkpoint alone selects the current stage and concrete Release/target identities.
- The current Stage Issue refines only the current stage's execution/evidence matrix; it is never stage authority.
- Future Stage Issues are created only when their stage opens.
- Work visible in a later stage is not pulled forward unless it already blocks the current stage or closes a demonstrated current P0/P1.
- `vm-production` and provider mutation remain fail-closed until #179 explicitly opens Stage 6.
- Full-system acceptance claims remain fail-closed until Stage 7.
- Future platform architecture remains non-active until explicitly promoted into a stage.
