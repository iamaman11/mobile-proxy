# Mobile Proxy Implementation Plan

This file is the concise entry point for project development.

Canonical documents:

- architecture / invariant baseline: `docs/PRODUCTION_BASELINE_PLAN.md`;
- current seven-stage execution roadmap: `docs/PRODUCTION_STAGE_ROADMAP.md`;
- universal working method: `STAGE_WORKFLOW.md`;
- final acceptance matrix: `TEN_OUT_OF_TEN_VALIDATION_PLAN.md`;
- planning / acceptance backlog: PRODUCT Issue #249;
- only authoritative stage / operations cursor: PRODUCT Issue #179.

If roadmap prose and the newest authoritative #179 checkpoint differ, #179 wins.

## Authority

```text
PRODUCT — iamaman11/mobile-proxy
  source / build / Quality / tags / immutable Product Release

DEPLOYMENT CONTROLLER — iamaman11/mobile-proxy-production
  /deploy ingress / admission / durable intent / target adapters
  exactly-once destructive dispatch / postcondition / recovery / evidence
```

Both repositories are public. Neither plane may silently take over the other's responsibility.

## Foundation invariants

- No code for code.
- No verification of verification.
- No new framework is justified merely to reconcile old PRODUCT/controller duplication.
- No old failed GitHub run is manually rerun to perform a deployment.

These are durable controller-v2 foundation constraints, not optional style guidance.

## Engineering doctrine

Build the smallest understandable industrial system that satisfies the real production topology.

- one owner per state/decision;
- add a layer only for an independent responsibility/lifecycle/failure mode;
- generalize only after two real implementations need the same abstraction, or another concrete present-day need exists;
- prefer explicit contracts, small pure functions and thin adapters;
- tests protect real behavior/failure/security/authority boundaries;
- prefer deletion/consolidation over speculative frameworks.

## Current seven-stage path

1. **Controller composite phone transaction — COMPLETE.**
2. **Immutable Product Release `v0.1.6` — CURRENT.**
3. **First real phone deployment.**
4. **Phone industrial operational validation.**
5. **Phone production baseline acceptance / simplification.**
6. **VM production transaction + first real deployment.**
7. **Combined PHONE + VM operational acceptance — final full-system 10/10.**

Stages 6–7 are planned but grant no current VM/provider authority. `vm-production` remains fail-closed until a newer #179 checkpoint explicitly opens Stage 6.

## VM architecture rule

Do not pre-generalize phone code for VM during Stages 2–5. Stage 6 is the first point where phone and VM are two real target implementations. Shared target abstractions may be extracted only from concrete duplication and only when the result is simpler than keeping two thin adapters.

Stage 6 uses the immutable Linux Product Release artifact and the existing Controller request/intent/serialization/exactly-once/recovery semantics. VM-specific materialization, activation and observation stay in the VM target adapter unless real duplication justifies extraction.

Stage 7 proves one combined production topology, not merely two independent green deployments.

## Durable progress

For each stage: one subordinate Stage Issue in the owning repository; implementation progress in the stage branch/PR; significant non-code findings in the Stage Issue; #179 only for authority/stage boundaries. PR-ready and routine CI fixes are not stop points.

## Full definition of done

Full production operation is complete only after Stage 7:

1. PRODUCT release/security/provenance properties are accepted.
2. Deployment Controller exactly-once/recovery invariants are accepted for both real targets.
3. Phone and VM each have independent local postcondition evidence.
4. The combined PHONE + VM topology passes functional, recovery, bounded-load and soak acceptance.
5. No unresolved P0/P1 contradicts the final production acceptance definition.
