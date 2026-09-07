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

Prove the already accepted phone deployment remains correct under real operation, real phone failure domains and bounded load.

### Scope

Validate only phone-side failure domains required by the chosen topology:

- serving/data-path health available without opening VM/provider work;
- Android/rooted-runtime process and rendered-config health;
- runtime restart and full phone reboot recovery;
- deterministic degraded-state classification and causal re-observation;
- recovery/reconciliation without blind destructive retry;
- resource/concurrency/overload behavior actually exercised by the phone runtime;
- runtime/config tamper or mismatch detection;
- phone-side soak/leak/resource behavior.

When an exact phone fact cannot be obtained through Controller observation, use narrow local-agent assistance rather than guess and classify the result as `controller_capability_gap`, `human_only_physical_observation`, or `one_off_observation`.

### Minimality

Do not create a generic chaos framework or combinatorial State Machine matrix. Improve Controller observation only for demonstrated, stage-relevant capability gaps where the smallest automation is simpler and safer than recurring manual dependence.

### Exit

Phone-production is functionally healthy, resource-bounded and recoverable across the agreed phone matrix with no unresolved Stage-4 P0/P1.

---

## Stage 5 — Phone production baseline acceptance / simplification

### Goal

Leave one understandable long-term phone production path before adding the second real target.

### Scope

- resolve remaining demonstrated phone P0/P1 and evidence-trust gaps;
- converge active normative docs and ownership on the real phone/Controller path;
- classify and remove or isolate redundant v1/reconstruction/temporary recovery surfaces;
- verify PRODUCT <-> Controller ownership boundaries;
- reduce active code, workflow, authority and cognitive surface where possible.

### Minimality

Stage 5 should primarily simplify. New framework/infrastructure requires a concrete unresolved phone-baseline risk and must remove more complexity or uncertainty than it adds.

### Exit

One protected, documented, directly evidenced phone-production baseline remains.

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
