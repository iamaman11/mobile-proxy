# Production Baseline Plan

Status: **active canonical implementation roadmap**  
PRODUCT repository: `iamaman11/mobile-proxy`  
Deployment Controller repository: `iamaman11/mobile-proxy-production`  
Planning / acceptance backlog: PRODUCT Issue #249  
Authoritative stage cursor: newest authoritative checkpoint in PRODUCT Issue #179  
Working method: `STAGE_WORKFLOW.md`

This file defines durable ordering and acceptance intent. It never grants `/deploy`, phone/ADB, provider/VM, tag or Product Release authority by itself; #179 does.

## 1. Goal

Reach one understandable industrial Mobile Proxy system with:

- deterministic PRODUCT build/Quality and immutable Product Release identity;
- one Deployment Controller owning all physical deployment authority;
- exactly-once destructive semantics per durable intent;
- independent postcondition observation and fail-closed recovery;
- one accepted phone-production target;
- one accepted vm-production target;
- one proven end-to-end PHONE + VM production topology;
- no unresolved P0/P1 defect.

No code for code. No verification of verification. Prefer deletion, explicit contracts, small pure functions and thin adapters over speculative framework layers.

## 2. Authority model

| Plane | Repository | Authority |
| --- | --- | --- |
| PRODUCT | `iamaman11/mobile-proxy` | application/runtime source, shared product/domain architecture, Quality, product build, signing verification, annotated tags, immutable Product Releases |
| DEPLOYMENT CONTROLLER | `iamaman11/mobile-proxy-production` | deployment ingress, admission, target serialization/observation/adapters, durable mutation intent, exactly-once destructive dispatch, postconditions, recovery/quarantine and canonical deployment evidence |

Both repositories are public. Secrets, private keys, target bindings, raw target identifiers, credentials, sensitive rendered configuration and unsafe raw production logs remain private.

One state/decision has one owner. PRODUCT never becomes deployment transaction authority; Controller never becomes canonical PRODUCT source/build/tag/Release authority.

## 3. Product Release and deployment identity

```text
protected PRODUCT main + exact successful Quality
  -> Product Release prerequisites
  -> annotated product tag
  -> immutable Product Release
  -> Controller admission
  -> /deploy <target> <tag>
  -> durable intent
  -> at most one destructive target dispatch
  -> independent postcondition
  -> terminal classification / read-only recovery
```

Production deployment identity is the exact immutable Product Release plus the exact admitted Controller revision. `latest`, mutable branches and approximate artifact identity are forbidden.

Ambiguous post-dispatch state is `UNKNOWN`; it never authorizes blind destructive retry.

## 4. Universal stage workflow

The canonical workflow is `STAGE_WORKFLOW.md`:

- one subordinate Stage Issue in the repository that owns the stage;
- one stage branch/PR per touched repository when implementation begins;
- finished functional/docs slice + direct tests -> commit;
- important non-code decision/finding/blocker/evidence -> Stage Issue comment;
- ordinary implementation/CI fixes -> commit in the same PR;
- #179 checkpoint only at stage exit, authority/stage-boundary change, genuine cross-stage blocker, physical UNKNOWN, or explicit owner plan change.

A PR becoming green is not a stage boundary by itself.

## 5. Seven-stage production roadmap

### Stage 1 — Deployment Controller v2 composite phone transaction — COMPLETE

One protected Controller transaction owns the whole phone Product Release: APK + rooted runtime. The accepted path has one durable mutation intent, one destructive authority, independent composite postcondition and read-only UNKNOWN recovery.

### Stage 2 — Immutable Product Release `v0.1.6` — CURRENT

Goal: publish the first immutable Release using the complete six-asset phone identity + realization model through the normal reproducible release path.

Work only on current blockers that materially affect `v0.1.6`: release-tag transport, exact Quality/prerequisites, demonstrated P0/P1 release safety/provenance defects, six-asset publication and exact Controller admission.

Exit: immutable `v0.1.6` exists with exact source/run/release evidence and Controller admission proof. No physical deployment belongs here.

### Stage 3 — First real phone deployment

Goal: execute exactly one admitted `/deploy phone-production v0.1.6` and prove the full local phone Product Release state.

Required: fresh release/controller/target/phone revalidation, real production renderer inputs, one durable composite APK+runtime transaction, atomic activation, complete local postcondition and durable terminal evidence. `UNKNOWN` continues read-only.

Exit: `v0.1.6` is physically ACCEPTED on the registered production phone.

### Stage 4 — Phone industrial operational validation

Goal: prove the accepted phone deployment remains correct under real operation, failures and bounded load.

Validate only real failure domains of the chosen phone topology: serving/data path, runtime processes, rendered config, restart/reboot, partial/degraded states, causal re-observation, resource/overload behavior, tamper/mismatch and soak.

Exit: phone-production is functionally healthy, resource-bounded and recoverable across the agreed matrix.

### Stage 5 — Phone production baseline acceptance / simplification

Goal: make the accepted phone architecture singular, understandable and maintainable before adding the second real target.

Work: converge active docs/entry points, resolve remaining demonstrated phone P0/P1 and evidence-trust gaps, remove or isolate redundant v1/reconstruction paths, and confirm PRODUCT <-> Controller ownership.

Stage 5 should primarily reduce active surface area. It closes the **phone-production baseline**, not final PHONE+VM system acceptance.

Exit: one protected, documented and directly evidenced phone production path remains, with no known P0/P1 contradicting the phone baseline.

### Stage 6 — VM production transaction + first real deployment

Goal: add `vm-production` as the second real Deployment Controller target and deploy one real production VM without weakening the proven phone path.

Required work:

- bind one concrete production VM lifecycle and target identity; do not design for hypothetical providers/VM types;
- consume the immutable Product Release Linux artifact and exact provenance/digest identity;
- keep phone-runtime-only identity fields out of VM admission/materialization;
- add the smallest VM-specific Controller adapter for materialization, activation/service lifecycle and independent observation;
- reuse the existing semantic request identity, durable intent, target serialization, exactly-once dispatch and read-only UNKNOWN recovery model;
- keep provider credentials/provider mutation off the phone runner;
- if VM creation/replacement is required, model that lifecycle explicitly in the Controller instead of hiding provider mutation inside deployment shell code;
- prove failure modes that actually exist: wrong artifact/digest, target binding mismatch, partial materialization, activation/service failure, ambiguous dispatch and recovery;
- perform one separately authorized real `vm-production` deployment.

**Generalization rule:** Stage 6 is the first point where phone + VM are two real implementations. Extract shared target abstractions only when concrete duplication exists and the resulting boundary is simpler than two thin adapters. Do not introduce a generic multi-target orchestration framework.

Exit: one real production VM is ACCEPTED with exact immutable Product Release identity, exact Controller revision, durable intent and independent local postcondition evidence; phone-production remains accepted and unaffected.

### Stage 7 — Combined PHONE + VM operational acceptance

Goal: prove the complete production topology as one system, not merely two independently successful target deployments.

The exact topology is bound from current production contracts when Stage 7 opens. Expected proof areas include the real chain such as:

```text
external client
  <-> VM / relay / serving edge
  <-> reverse-tunnel path
  <-> registered phone runtime
  <-> selected mobile/cellular egress
```

Required work:

- record exact accepted identities of both targets and their intended compatibility relationship;
- prove end-to-end serving/data path through PHONE + VM;
- test target restart/reboot and reconnect behavior;
- test partial target unavailability and deterministic degraded-state classification;
- prove recovery does not trigger blind destructive retry on either target;
- validate bounded load/resource behavior across the real path;
- validate only version-skew/rolling behavior that the actual production policy permits;
- run the agreed end-to-end soak/leak/reliability window;
- converge final operational docs/evidence and close any remaining demonstrated cross-target P0/P1.

Do not build a generic distributed orchestrator, service mesh abstraction or chaos framework merely for coverage. Every combined test must name the real failure it protects against.

Exit: PHONE + VM production topology passes final full-system 10/10 acceptance with singular authority, direct local target proofs, end-to-end functional/recovery evidence and no unresolved P0/P1.

## 6. Complexity gate

A new module/layer/framework/registry/check is justified only if at least one is concrete now:

- independent responsibility/lifecycle/failure mode;
- demonstrated defect or trust boundary;
- real duplication being removed;
- two real implementations requiring the shared abstraction;
- direct test of a real failure that otherwise escapes acceptance.

Future VM needs do not justify abstractions during Stages 2–5. Stage 6 permits only evidence-driven extraction from two real target implementations.

## 7. Acceptance evidence model

The historical A–H gates remain useful as evidence categories, not as the current execution-stage numbering:

- A/B: Controller health and PRODUCT/Controller authority convergence;
- C/D/E: PRODUCT security, behavior and supply-chain/release hardening;
- F: immutable Product Release;
- G: admitted physical deployment;
- H: real-world operational acceptance.

For the seven-stage roadmap, Gate H is complete only after Stage 7. Stage 5 closes the phone-only production baseline; Stage 6 proves the VM target; Stage 7 closes the combined system.

## 8. Target invariants

### phone-production

Uses the immutable APK + rooted-phone runtime identity and the accepted composite phone transaction. Phone-specific runtime realization/configuration remains phone-specific.

### vm-production

Remains fail-closed until Stage 6 explicitly opens and its Controller-owned adapter/lifecycle is proven end-to-end. VM deployment consumes the immutable Linux Release artifact and must not inherit phone runtime identity fields or phone-specific realization rules.

### cross-target

Phone and VM share only proven Controller semantics: immutable Release admission, semantic request identity, durable intent, target serialization, exactly-once destructive boundary, independent observation and read-only UNKNOWN recovery. Target-specific materialization/activation stays inside thin target adapters unless real duplication justifies extraction.

## 9. Full production definition of done

Full production operation is complete only after Stage 7 and requires all of the following:

1. PRODUCT acceptance: exact source/Quality/release/provenance and no unresolved PRODUCT P0/P1.
2. Controller acceptance: exactly-once mutation/recovery invariants proven for both real targets.
3. Direct local acceptance: phone-production and vm-production each have independent postcondition evidence.
4. Combined acceptance: real PHONE + VM data path, recovery, bounded load and soak pass under the agreed topology.
5. Architecture acceptance: one authority per state/decision, no active duplicate deployment path and no unnecessary generic framework.

## 10. Change discipline

For docs/policy-sized changes use `scripts/quality-gate.sh fast`; for code/release changes use `scripts/quality-gate.sh`.

The newest #179 checkpoint supersedes stale prose. Do not create #179 checkpoints for ordinary commits, PR-ready state, routine CI failures/fixes or merge boundaries already included in the current stage. Record one checkpoint at stage exit or the exceptional boundaries defined by `STAGE_WORKFLOW.md`.
