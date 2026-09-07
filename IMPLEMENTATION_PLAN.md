# Mobile Proxy Implementation Plan

This file is a concise **static context and sequencing entrypoint**. It does not carry dynamic current-stage, current-SHA, current-Release or next-action state.

## Recover current work

Use the single execution spine:

1. `AGENTS.md`;
2. `STAGE_WORKFLOW.md`;
3. newest authoritative checkpoint in PRODUCT Issue #179;
4. the current subordinate Stage Issue;
5. only the permanent documents required by that stage.

If any static prose and the newest authoritative #179 checkpoint differ, #179 wins.

## Document roles

- static seven-stage sequence: `docs/PRODUCTION_STAGE_ROADMAP.md`;
- stable architecture/invariant baseline: `docs/PRODUCTION_BASELINE_PLAN.md`;
- canonical working method: `STAGE_WORKFLOW.md`;
- permanent architecture standard: `docs/architecture/ARCHITECTURE_STANDARD.md`;
- stage-mapped acceptance catalog: `TEN_OUT_OF_TEN_VALIDATION_PLAN.md`;
- planning/acceptance backlog only: PRODUCT Issue #249;
- future/post-baseline guidance only: `docs/FUTURE_PLATFORM_ARCHITECTURE_ROADMAP.md`;
- only dynamic development/operations cursor: PRODUCT Issue #179.

Historical A-H and Item15-23/Item19-20 execution sequences are evidence/history after supersession. They do not compete with the seven-stage path.

## Authority

```text
PRODUCT — iamaman11/mobile-proxy
  source / build / Quality / tags / immutable Product Release

DEPLOYMENT CONTROLLER — iamaman11/mobile-proxy-production
  /deploy ingress / admission / durable intent / target adapters
  exactly-once destructive dispatch / postcondition / recovery / evidence
```

Both repositories are public. Confidentiality is carried by secrets, private bindings and redacted evidence, not repository visibility. Neither plane may silently take over the other's responsibility.

## Foundation invariants

- No code for code.
- No verification of verification.
- No new framework merely to reconcile historical duplication.
- No blind destructive retry after an ambiguous mutation boundary.
- No old failed GitHub run is manually rerun to obtain a second physical effect.
- One owner per state/decision.
- Add a layer only for an independent responsibility/lifecycle/failure mode.
- Prefer explicit contracts, small pure functions and thin adapters.
- Prefer deletion/consolidation over speculative frameworks.
- Generalize only after two real implementations need the same abstraction, or another concrete present-day need exists.

## Static seven-stage sequence

1. **Deployment Controller composite phone transaction foundation** — prove one durable phone transaction owns APK + rooted runtime with exact Release identity and read-only UNKNOWN recovery.
2. **Immutable Product Release** — publish and admit one exact immutable Release with required artifacts/provenance.
3. **First real phone deployment** — achieve one canonical `ACCEPTED` phone deployment with independent local proof.
4. **Phone industrial operational validation** — prove the accepted phone under real operation, phone faults and bounded load.
5. **Phone production baseline acceptance / simplification** — leave one understandable, protected, documented phone path and remove/isolate redundant active surfaces.
6. **VM production transaction + first real deployment** — add one concrete `vm-production` adapter/lifecycle and accept one real VM without weakening phone invariants.
7. **Combined PHONE + VM operational acceptance** — prove the real end-to-end topology, recovery, bounded load and soak as one system.

This list intentionally contains no `CURRENT`, concrete Release version or current SHA. Resolve those only from the newest #179 checkpoint.

## Architecture improvement belongs inside stages

`ARCHITECTURE_STANDARD.md` is a permanent constraint, not a second roadmap. A concrete architecture improvement enters the earliest stage whose exit it blocks or whose demonstrated P0/P1 it closes.

- Stage 4 may improve Controller phone observation when a demonstrated capability gap blocks reliable phone validation.
- Stage 5 is the primary phone simplification/convergence stage.
- Stage 6 is the first normal point for shared phone/VM target abstractions because two real implementations finally exist.
- Future platform work remains inactive until promoted through #179 into a stage.

## Local-agent feedback rule

When Controller cannot obtain an exact phone fact, request the narrow fact/interaction from the local agent rather than guess. Classify the result as `controller_capability_gap`, `human_only_physical_observation`, or `one_off_observation`.

A `controller_capability_gap` is implemented only when it is demonstrated, stage-relevant, reduces UNKNOWN/manual dependence, and the smallest Controller observation capability is simpler than repeated local assistance. Local-agent help never becomes deployment mutation authority.

## Durable progress

For each stage: one subordinate Stage Issue in the owning repository; implementation progress in the stage branch/PR; significant non-code findings/evidence in the Stage Issue; #179 only for authority/stage boundaries. Routine PR/CI repair, read-only observation, local-agent evidence and protected merge/post-merge gates are not stop points.

## Full definition of done

The project reaches full production acceptance only after Stage 7 proves all of:

1. PRODUCT release/security/provenance properties are accepted.
2. Deployment Controller exactly-once/recovery invariants are accepted for both real targets.
3. Phone and VM each have independent local postcondition evidence.
4. The combined PHONE + VM topology passes functional, recovery, bounded-load and soak acceptance.
5. No unresolved P0/P1 contradicts final production acceptance.
