# Mobile Proxy Implementation Plan

The sole active repository roadmap is [Production Baseline Plan](docs/PRODUCTION_BASELINE_PLAN.md).

The normative acceptance matrix is `TEN_OUT_OF_TEN_VALIDATION_PLAN.md`. PRODUCT Issue #249 is the stage-mapped planning backlog. PRODUCT Issue #179 is the only authoritative stage/operations cursor and overrides stale roadmap prose.

The canonical working method is `STAGE_WORKFLOW.md`.

## Authority

```text
PRODUCT — iamaman11/mobile-proxy
  source / build / Quality / tags / immutable Product Release

DEPLOYMENT CONTROLLER — iamaman11/mobile-proxy-production
  /deploy ingress / admission / durable intent / target adapters
  exactly-once destructive dispatch / postcondition / recovery / evidence
```

Neither plane may take over the other's responsibility. Secrets, target bindings, credentials, private keys, sensitive rendered configuration and unsafe raw runtime logs never belong in public evidence.

## Engineering doctrine

Build the smallest understandable industrial system that satisfies the real production topology.

- no code for code;
- no verification of verification;
- one owner per state/decision;
- add a layer only for an independent responsibility/lifecycle/failure mode;
- generalize only after two real implementations need the same abstraction, or another concrete present-day need exists;
- prefer explicit contracts, small pure functions and thin adapters;
- tests protect real behavior/failure/authority boundaries;
- prefer deletion/consolidation over speculative frameworks.

## Seven-stage roadmap

Stage numbering is execution planning, not authority. The newest #179 checkpoint decides what is currently allowed.

1. **Deployment Controller v2 composite phone transaction — COMPLETE.** One durable phone transaction owns APK + rooted runtime, with one destructive authority and read-only UNKNOWN recovery.
2. **Immutable Product Release `v0.1.6` — CURRENT.** Close only live release blockers, restore the normal release-tag happy path, publish the six-asset immutable Release and prove Controller admission.
3. **First real phone deployment.** Execute exactly one admitted `/deploy phone-production v0.1.6`, prove APK + rooted-runtime local postcondition and durable terminal evidence.
4. **Phone industrial operational validation.** Prove real data path, resource bounds, reboot/restart, degraded states, recovery, causal re-observation, tamper detection and soak for the accepted phone topology.
5. **Phone production baseline acceptance / simplification.** Close the phone baseline, remove/isolate redundant legacy surfaces, converge docs and ownership, and leave one understandable phone production path. This is not yet full PHONE+VM project acceptance.
6. **VM production transaction + first real deployment.** Add `vm-production` as the second real Controller target using the immutable Linux Release asset, a concrete VM lifecycle/binding and exactly-once deployment semantics; deploy one real production VM and prove its local postcondition.
7. **Combined PHONE + VM operational acceptance.** Prove the complete production topology end-to-end with exact identities on both targets, cross-target data path, restart/recovery/failure behavior, bounded load and soak. Stage 7 is the final full-system 10/10 acceptance.

## VM design boundary

VM work is intentionally deferred until Stage 6. Do not pre-generalize phone code for a hypothetical VM during Stages 2–5.

When Stage 6 starts:

- reuse the existing Controller State Machine, durable intent, request identity, serialization and recovery semantics;
- add only the VM-specific target binding/adapter/materialization/observation needed by the chosen real VM topology;
- use the immutable Linux Product Release artifact; phone runtime identity fields must not leak into VM admission;
- keep provider credentials and provider mutation out of the phone runner;
- if VM provisioning/replacement is required, make that lifecycle explicit and Controller-owned rather than hiding it inside deployment shell code;
- extract shared phone/VM abstractions only after real duplication is visible and materially simpler than two thin adapters.

Stage 6 exits only when one real `vm-production` deployment is ACCEPTED with immutable Release identity, exact Controller revision, durable intent and independent local postcondition evidence.

## Combined-system acceptance boundary

Stage 7 validates the product as one operating system, not two independent successful deployments. It must cover the real intended path, for example:

```text
external client
  <-> VM / relay / serving edge
  <-> reverse-tunnel path
  <-> registered phone runtime
  <-> selected mobile/cellular egress
```

The exact topology is bound from current production contracts when Stage 7 opens; this roadmap does not invent provider details in advance.

Stage 7 must prove only concrete operational failure domains that exist in that topology: target restart/reboot, link loss/reconnect, partial target unavailability, allowed version skew if any, resource exhaustion/overload, recovery without blind destructive retry, and end-to-end soak. Do not build a generic multi-target orchestration or chaos framework merely for coverage.

## Durable progress

For each stage: one subordinate Stage Issue in the owning repository; implementation progress in the stage branch/PR; significant non-code findings in the Stage Issue; #179 only for authority/stage boundaries. PR-ready and routine CI fixes are not stop points.

## Definition of done

Full production operation is complete only after Stage 7:

1. PRODUCT release/security/provenance properties are accepted.
2. Deployment Controller exactly-once/recovery invariants are accepted for both real targets.
3. Phone and VM each have direct local postcondition evidence.
4. The combined production topology passes agreed functional, recovery, bounded-load and soak acceptance.
5. No unresolved P0/P1 contradicts the production acceptance definition.

Until Stage 6 explicitly opens, `vm-production` remains fail-closed and no provider/VM mutation is implied by this plan.
