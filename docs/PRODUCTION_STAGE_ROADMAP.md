# Production Stage Roadmap

Status: **static seven-stage sequencing and scope model**  
Dynamic authority: newest authoritative checkpoint in PRODUCT Issue #179  
Planning backlog: PRODUCT Issue #249  
Working method: `STAGE_WORKFLOW.md`

This document does not declare a current stage, current Release, current SHA, next action or mutation authority. Resolve all dynamic execution state from #179 and the current subordinate Stage Issue.

The stable architecture/invariant baseline is `docs/PRODUCTION_BASELINE_PLAN.md`. The permanent architecture quality floor is `docs/architecture/ARCHITECTURE_STANDARD.md`. The acceptance catalog is `TEN_OUT_OF_TEN_VALIDATION_PLAN.md`.

## Stage model

A stage is accepted because a real functional/safety/authority outcome is proven, not because files, classes, workflows or checks exist.

Each stage has one subordinate Stage Issue in its owning repository. Implementation progress lives in the stage branch/PR; significant non-code findings/evidence live in the Stage Issue; #179 is used only for dynamic stage/authority boundaries.

Architecture improvement is not a parallel lane. A demonstrated architecture defect, evidence-trust gap or Controller capability gap enters the earliest stage whose exit it blocks. Future recommendations remain inactive until #179 promotes them.

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

The Controller transaction semantics are protected and directly tested without requiring a real production phone mutation merely to prove code structure.

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

## Stage 4 — Phone industrial operational validation

### Goal

Prove the already accepted phone deployment remains correct under real operation, real phone failure domains and bounded load, while converging any newly demonstrated Controller observation/reconciliation gaps into the smallest coherent phone execution path required for trustworthy validation.

### Integrated Controller truth path

Stage 4 validation must not grow separate workflow-specific definitions of phone truth. When observation, deployment postcondition and target-read-only reconciliation need the same exact Release-bound phone state, they must consume one consistent Controller-owned phone Release state semantics:

```text
exact immutable Product Release
  -> prepare/verify expected phone Release state
  -> observe exact current phone state
  -> one bounded classification: exact / degraded / unknown
  -> operation-specific decision
```

This is a concrete phone capability boundary, not a generic multi-target framework. Stage 6 remains the first normal point for extracting shared phone/VM target abstractions from two real implementations.

A target-read-only reconcile operation, when required by demonstrated Stage 4 evidence, has a semantic domain separate from deployment mutation identity. It may repair an already-admitted public visibility projection only after exact current target proof. It must not create mutation intent, dispatch APK/runtime work, rewrite historical Controller terminals, infer target truth from the projection, or manufacture a new deployment record merely because the target is exact.

### Validation workstreams

Validate only phone-side failure domains required by the chosen topology, in an order that preserves causal evidence:

1. **Exact observation/control-plane trust**
   - independent transport preflight for runner/ADB/root readiness;
   - Release-bound exact APK + rooted-runtime observation with bounded evidence;
   - one shared exact phone Release state semantics for observe/deploy/reconcile consumers;
   - target-read-only projection reconciliation for the demonstrated already-exact/ledger-history case;
   - no success classification without durable decision-grade evidence.

2. **Observation efficiency and evidence resilience**
   - measure admission/materialization/observation sub-phases rather than optimize an opaque total;
   - retain only verified immutable public/static intermediates whose cache identity is exact and revalidated on use;
   - never persist secret-derived rendered trees or mutable phone-state truth in the cache;
   - record bounded assignment/probe/transport evidence and fail closed when required evidence cannot be retained;
   - recurring runner/Broker faults may justify only the smallest demonstrated diagnostic/recovery capability.

3. **Runner / host / USB recovery**
   - prove the registered runner recovers without re-registration or label/identity drift;
   - prove the versioned Windows/WSL/USB boundary across the exact recovery drills bound by the Stage Issue;
   - keep host/runner recovery separate from phone deployment mutation authority.

4. **Phone runtime and serving lifecycle**
   - serving/data-path health available without opening VM/provider work;
   - Android/rooted-runtime process and rendered-config health;
   - bounded critical-process termination/recovery;
   - runtime restart and full phone reboot recovery;
   - deterministic degraded-state classification and causal re-observation;
   - phone-local network/degraded behavior required by the selected topology;
   - runtime/config/current tamper or mismatch detection and fail-closed recovery/reconciliation.

5. **Resource, concurrency and soak**
   - resource/concurrency/overload behavior actually exercised by the phone runtime;
   - bounded CPU/memory/process/file-descriptor/queue/log behavior;
   - no silent stuck state or monotonic leak;
   - production-like phone-side soak with a concrete Stage-Issue-bound duration/check cadence.

6. **Deployment/reconcile/rollback lifecycle**
   - prove the already-exact path through target-read-only reconciliation without reusing a historical mutation semantic identity;
   - prove one real successor deployment only through normal immutable Product Release authority when a legitimate successor Release exists; never create a fake Product Release solely to satisfy a drill;
   - preserve one durable mutation intent before any destructive effect, exactly-once dispatch, independent postcondition and duplicate/retry safety;
   - prove Controller rollback only when two retained immutable APK/runtime Releases with compatible signing lineage exist, then restore the approved target and verify it independently.

Historical repetition counts and soak durations are acceptance references, not automatic authorization. The current Stage Issue binds the exact physical/repetition matrix and records accepted evidence.

### Product vs Controller defect routing

Stage 4 findings are repaired by the owner of the failing responsibility:

- PRODUCT/runtime defects include actual serving behavior, runtime lifecycle, product health semantics, resource bounds and boot/restart behavior;
- Controller defects include admission/observation semantics, target adapters, mutation/recovery semantics, evidence, projection and runner/host control-plane reliability;
- human-only physical/UI facts remain narrow local-agent interactions and never become hidden deployment authority.

A Controller-only repair does not force a new Product Release. A PRODUCT/runtime repair follows normal protected PRODUCT delivery and immutable Product Release authority before any new physical deployment.

### Minimality

Do not create a generic chaos framework, combinatorial State Machine matrix, generic target manager or second state platform. Improve Controller observation/reconciliation only for demonstrated, stage-relevant gaps where the smallest concrete capability is simpler and safer than recurring manual dependence or duplicated state truth.

### Stage 4 -> Stage 5 handoff

Before Stage 4 closes, the Stage Issue must leave a bounded handoff containing:

- one evidence matrix covering every Stage 4 exit category and exact accepted references;
- all unresolved findings classified by owner and severity;
- a phone control-surface inventory classified `retain`, `consolidate`, `isolate/deprecate`, or `remove` for Stage 5;
- explicit identification of any Stage-4-only command/workflow/version binding or recovery scaffolding;
- no unproven physical fact represented as accepted state.

### Exit

Phone-production is functionally healthy, resource-bounded and recoverable across the agreed phone matrix; required deployment/reconcile/rollback properties have direct retained evidence; no required physical fact is guessed; and no unresolved Stage-4 P0/P1 remains.

---

## Stage 5 — Phone production baseline acceptance / simplification

### Goal

Turn the proven Stage 4 phone system into one understandable, low-cognitive-cost long-term phone production baseline before adding the second real target.

Stage 5 is primarily a **convergence and deletion stage**. It consumes Stage 4 evidence; it is not a second broad phone chaos/load program and it must not preserve temporary validation machinery merely because that machinery once produced useful evidence.

### Required inputs

Stage 5 starts from the completed Stage 4 handoff:

- accepted phone operational evidence matrix;
- zero unresolved Stage-4 P0/P1;
- explicit current phone control-surface inventory;
- demonstrated keep/consolidate/isolate/remove candidates;
- exact owner classification for any residual PRODUCT, Controller or human-only operational dependency.

Do not create the Stage 5 subordinate Issue until #179 explicitly opens Stage 5.

### Convergence workstreams

1. **One phone state truth path**
   - retain one concrete Controller-owned exact phone Release state semantics used by normal observation, deployment postcondition and reconciliation where applicable;
   - remove duplicated workflow/script-specific desired-state or drift classification;
   - remove Stage-4-only version locks from the long-term path unless a real compatibility contract requires them;
   - keep GitHub Actions/shell as delivery/adapters, not alternate state owners.

2. **One mutation/recovery kernel**
   - preserve semantic request identity, target serialization, durable intent, exactly-once destructive dispatch, independent postcondition and `UNKNOWN` read-only recovery;
   - ensure projection reconciliation is separate from mutation identity and cannot rewrite private canonical history;
   - remove/isolate superseded reconstruction, quarantine, migration or temporary recovery paths once their retained evidence/rollback obligations are satisfied.

3. **Command/workflow surface reduction**
   - inventory every active Issue #1 route and production workflow by real operator need;
   - retain a separate diagnostic/preflight route only when it has an independent operational purpose;
   - consolidate routes that differ only because of Stage 4 implementation history;
   - disable/remove stale commands and workflows instead of leaving dormant competing authority surfaces;
   - keep the declarative registry aligned with the actual minimal supported surface.

4. **Materialization/cache/evidence ownership**
   - retain immutable cache/transport optimizations only where they have demonstrated value and a bounded deletion/recovery path;
   - centralize stable phone Release preparation/observation logic under the narrowest concrete owner rather than importing workflow-private helpers across multiple scripts;
   - keep secret-derived rendering ephemeral and keep physical target truth out of static caches;
   - converge evidence schemas so one developer can reconstruct state -> decision -> effect -> postcondition without joining unrelated artifacts.

5. **PRODUCT <-> Controller and documentation convergence**
   - verify PRODUCT remains source/build/release authority and Controller remains deployment/target execution authority;
   - remove active references to superseded A-H/Item15-23/Item19-20 execution semantics and stale backlog/cursor roles;
   - make `AGENTS.md`, `STAGE_WORKFLOW.md`, Stage Roadmap, baseline, authority docs, acceptance catalog and Controller overlay describe the same long-term phone path;
   - keep historical evidence historical rather than deleting audit history.

6. **Test and policy simplification**
   - retain direct tests for state transitions, identity, security, recovery, bounded evidence and real failure modes;
   - delete redundant wiring/meta-verification checks that do not protect an independent invariant;
   - reduce CI/workflow count where one existing fitness function already owns the invariant.

### Generalization boundary

Do not extract a generic phone/VM target framework in Stage 5. Phone-specific code may be made internally coherent, but shared target abstractions wait until Stage 6 demonstrates duplication with a real VM implementation.

### Minimality

Every Stage 5 addition must either remove more active complexity than it adds or close a concrete unresolved phone-baseline risk. New background services, state stores, schedulers, abstraction layers or provider models are exceptional and require current evidence.

### Exit

Exactly one protected, documented and directly evidenced phone-production baseline remains:

- one understandable source -> Release -> Controller -> phone -> observation path;
- one mutation/recovery kernel;
- one bounded projection/evidence model;
- no active Stage-4-only authority/scaffolding without a documented long-term need;
- redundant/superseded phone control surfaces removed or explicitly isolated;
- no unresolved phone P0/P1 or evidence-trust gap;
- Stage 6 can add a real VM without first reverse-engineering which phone path is canonical.

---

## Stage 6 — VM production transaction + first real deployment

### Goal

Add `vm-production` as the second real Controller target and accept one real production VM without weakening the proven phone path.

### Scope

- bind one concrete production VM lifecycle and target identity; no hypothetical provider matrix;
- consume the immutable Product Release Linux artifact with exact provenance/digest identity;
- keep phone-runtime-only identity/realization fields out of VM admission/materialization;
- add the smallest VM-specific target adapter for materialization, activation/service lifecycle and independent observation;
- reuse semantic request identity, durable intent, target serialization, exactly-once destructive boundary and read-only UNKNOWN recovery;
- keep provider credentials/provider mutation off the phone runner;
- model real VM provisioning/replacement explicitly only if the chosen lifecycle requires it;
- directly test concrete VM failure modes;
- perform one separately authorized first real `vm-production` deployment.

### Generalization boundary

This is the **first normal point where phone and VM are two real target implementations**. Extract shared target abstractions only when concrete duplication exists, the responsibility has one real lifecycle/failure model, and the extracted boundary is simpler than two thin adapters.

Do not build a generic multi-target orchestrator, executor framework or provider abstraction platform.

### Exit

One real production VM is canonical `ACCEPTED` with exact immutable Product Release identity, exact Controller revision, durable intent and independent local postcondition evidence. Phone-production remains accepted and unaffected.

---

## Stage 7 — Combined PHONE + VM operational acceptance

### Goal

Prove the complete production topology as one operating system, not merely two independently successful deployments.

Bind the exact topology when Stage 7 opens. The intended class is:

```text
external client
  <-> VM / relay / serving edge
  <-> reverse-tunnel path
  <-> registered phone runtime
  <-> selected mobile/cellular egress
```

### Scope

- exact accepted identities of phone and VM and permitted compatibility relationship;
- real end-to-end serving/data path through both targets;
- phone restart/reboot and VM service/host restart/reconnect behavior;
- deterministic partial-target degradation;
- no blind destructive retry during cross-target recovery;
- bounded load/resources across the real path;
- only production-permitted version skew/rolling behavior;
- end-to-end soak/leak/reliability acceptance;
- close demonstrated cross-target P0/P1;
- converge final operational evidence/docs.

### Minimality

Do not create a generic distributed orchestrator, service mesh or chaos platform merely for coverage. Every combined test must name the actual production failure it protects against.

### Exit

PHONE + VM production passes the final full-system acceptance with singular authority, direct local target proofs, end-to-end functional/recovery evidence, bounded-load/soak evidence and no unresolved P0/P1.

## Promotion and fail-closed rules

- The newest #179 checkpoint alone selects the current stage and concrete Release/target identities.
- Future Stage Issues are created only when their stage opens.
- Work visible in a later stage is not pulled forward unless it already blocks the current stage or closes a demonstrated current P0/P1.
- `vm-production` and provider mutation remain fail-closed until #179 explicitly opens Stage 6.
- Future platform architecture remains non-active until explicitly promoted into a stage.
