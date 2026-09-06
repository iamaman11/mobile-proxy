# Production Stage Roadmap

Status: **active stage sequencing plan**  
Authority: newest authoritative checkpoint in PRODUCT Issue #179  
Planning backlog: PRODUCT Issue #249  
Working method: `STAGE_WORKFLOW.md`

This file describes the intended development sequence. It never grants code, merge, tag/Release, `/deploy`, phone/ADB or provider/VM authority by itself.

The stable architecture/invariant baseline remains `docs/PRODUCTION_BASELINE_PLAN.md`.

## Stage model

A stage is accepted because a real functional/safety/authority outcome is proven, not because files, classes, workflows or checks exist.

Each stage has one subordinate Stage Issue in its owning repository. Implementation progress is committed to the stage branch/PR; significant non-code findings are recorded in the Stage Issue; #179 is used only for stage/authority boundaries.

## Stage 1 — Deployment Controller v2 composite phone transaction — COMPLETE

One protected Controller transaction owns the complete phone Product Release: APK + rooted runtime.

Accepted properties:

- Release-bound runtime verification/materialization;
- one durable mutation intent;
- one destructive transaction authority;
- atomic rooted-runtime activation;
- composite APK + runtime postcondition;
- ambiguous physical result -> read-only UNKNOWN recovery, never blind retry.

No phone mutation was part of Stage 1 acceptance.

---

## Stage 2 — Immutable Product Release `v0.1.6` — CURRENT

### Goal

Publish the first immutable Product Release using the complete six-asset rooted-phone identity + realization model through the normal reproducible PRODUCT release path.

### Scope

- revalidate only current live PRODUCT blockers for `v0.1.6`;
- close the release-tag transport happy path if still required;
- exact protected PRODUCT main + Quality + Product Release prerequisites;
- fix only demonstrated P0/P1 release blockers relevant to `v0.1.6`;
- publish Linux bundle + APK + rooted-phone runtime bundle + release manifest + provenance + artifact digests;
- prove Deployment Controller admission accepts the exact published six-asset Release identity.

### Minimality

Do not turn Stage 2 into historical backlog cleanup. No new framework or generic abstraction without a current failure mode or acceptance need.

### Exit

Immutable `v0.1.6` exists with exact source/run/release evidence and Controller admission proof.

No production `/deploy`, phone/ADB/self-hosted target mutation or provider/VM mutation belongs to Stage 2.

---

## Stage 3 — First real phone deployment

### Goal

Prove Deployment Controller v2 on the registered production phone.

### Scope

- fresh Release/Controller/target/phone revalidation;
- bind the real production runtime manifest / renderer inputs;
- exactly one semantic `/deploy phone-production v0.1.6` when #179 explicitly opens mutation authority;
- one composite APK + rooted-runtime transaction;
- atomic activation and complete local postcondition;
- durable terminal evidence;
- UNKNOWN -> read-only reconciliation, never a second destructive dispatch.

### Exit

`v0.1.6` is physically ACCEPTED on the registered phone with complete local Product Release proof.

---

## Stage 4 — Phone industrial operational validation

### Goal

Prove the accepted phone deployment remains healthy under real operation, faults and bounded load.

### Scope

Validate only real failure domains of the chosen phone topology:

- serving/data path;
- Android/runtime process health;
- rendered configuration;
- restart/reboot;
- partial/degraded state classification;
- rollback/recovery/reconciliation;
- causal invalidation and targeted re-observation;
- resource/concurrency/overload behavior where actually used;
- tamper/mismatch detection;
- soak/leak/resource behavior.

### Minimality

Do not generate a combinatorial State Machine matrix or generic chaos framework. Every test must name the real operational failure it protects against.

### Exit

Phone-production is functionally healthy, resource-bounded and recoverable across the agreed matrix.

---

## Stage 5 — Phone production baseline acceptance / simplification

### Goal

Leave one understandable long-term phone production path before adding the second real target.

### Scope

- resolve remaining demonstrated phone P0/P1 and evidence-trust gaps;
- converge active normative docs/entry points on the real v2 phone path;
- classify and remove or isolate redundant v1/reconstruction surfaces;
- verify PRODUCT <-> Controller ownership boundaries;
- reduce active code/authority/cognitive surface where possible.

### Minimality

Stage 5 should primarily simplify. New framework/infrastructure requires a concrete unresolved phone acceptance risk.

### Exit

Phone-production baseline is singular, protected, documented and directly evidenced.

**Stage 5 is final phone baseline acceptance, not final PHONE+VM project acceptance.**

---

## Stage 6 — VM production transaction + first real deployment

### Goal

Add `vm-production` as the second real Deployment Controller target and deploy one real production VM without weakening the proven phone path.

### Scope

- bind one concrete real production VM lifecycle and target identity; do not design a provider/VM-type matrix in advance;
- consume the immutable Product Release **Linux artifact** and exact provenance/digest identity;
- ensure phone-runtime-only identity and realization fields do not leak into VM admission/materialization;
- add the smallest VM-specific Controller target adapter for materialization, activation/service lifecycle and independent observation;
- reuse the existing semantic request identity, durable mutation intent, target serialization, exactly-once destructive boundary and read-only UNKNOWN recovery model;
- keep provider credentials and provider mutation off the phone runner;
- if VM creation/replacement is required by the chosen real lifecycle, model that lifecycle explicitly in Controller ownership rather than hiding provider mutation inside ad-hoc deployment shell code;
- test only concrete VM failure modes: artifact/digest mismatch, target binding mismatch, partial materialization, activation/service failure, ambiguous dispatch and recovery;
- perform exactly one separately authorized first real `vm-production` deployment.

### Generalization boundary

Stage 6 is the **first point where phone and VM are two real target implementations**.

Only now may shared target abstractions be extracted, and only when:

- concrete duplication exists in both real adapters;
- the shared responsibility genuinely has one lifecycle/failure model;
- the extracted boundary is simpler than keeping two thin adapters.

Do **not** build a generic multi-target orchestrator, executor framework or provider abstraction platform.

### Exit

One real production VM is ACCEPTED with exact immutable Product Release identity, exact Controller revision, durable intent and independent local postcondition evidence. Phone-production remains accepted and unaffected.

---

## Stage 7 — Combined PHONE + VM operational acceptance — FINAL FULL-SYSTEM 10/10

### Goal

Prove the complete production topology as one operating system, not merely two independently successful deployments.

The exact topology is bound from current production contracts when Stage 7 opens. The intended class is:

```text
external client
  <-> VM / relay / serving edge
  <-> reverse-tunnel path
  <-> registered phone runtime
  <-> selected mobile/cellular egress
```

### Scope

- record exact accepted identities of phone and VM and their permitted compatibility relationship;
- prove the real end-to-end serving/data path through both targets;
- prove phone reboot/runtime restart and VM service/host restart/reconnect behavior;
- classify partial target unavailability deterministically;
- prove recovery on either target never causes blind destructive retry;
- validate bounded load/resources across the real path;
- validate only version-skew/rolling behavior actually permitted by production policy;
- run the agreed end-to-end soak/leak/reliability window;
- close remaining demonstrated cross-target P0/P1;
- converge final operational docs/evidence.

### Minimality

Do not create a generic distributed orchestrator, service-mesh abstraction or chaos framework merely for coverage. Every combined test must name the actual failure it protects against.

### Exit

PHONE + VM production topology passes final full-system 10/10 with:

- singular authority;
- direct local target proofs for phone and VM;
- end-to-end functional/recovery evidence;
- bounded-load and soak evidence;
- no unresolved P0/P1.

## VM fail-closed rule

Until Stage 6 is explicitly opened by a newer #179 checkpoint:

- `vm-production` remains fail-closed;
- provider/VM mutation is not authorized;
- Stage 2–5 work must not add speculative VM/general-target abstraction merely for future extensibility;
- future Stage 6/7 subordinate Issues are not created in advance.

## Full production definition

Full project operation is complete only after Stage 7. Stage 5 closes the phone-production baseline; Stage 6 proves the second real target; Stage 7 closes the combined system.
