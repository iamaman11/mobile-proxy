# Quick Reference

Optional **human cheat-sheet**. It is not part of the mandatory agent recovery path and never carries dynamic current-stage/current-SHA/current-Release state.

## One execution spine

After context loss use only:

`AGENTS.md -> STAGE_WORKFLOW.md -> newest authoritative PRODUCT #179 checkpoint -> current subordinate Stage Issue -> stage-relevant permanent references`.

Context budget:

- #179: Issue metadata/body + **last owner-authored authoritative checkpoint comment only**; never full comment history for normal recovery;
- current Stage Issue: body + only newest comments needed to resume;
- Controller #1: exact causal command/intent/terminal comment IDs only when runtime ledger evidence is needed;
- Controller #97: optional reusable rooted-phone diagnostic/probe reference, on demand only.

## Authority in 30 seconds

Both repositories are public.

- **PRODUCT** — `iamaman11/mobile-proxy`: source, product/domain architecture, Quality, build/signing verification, annotated product tags, immutable Product Releases and product documentation.
- **DEPLOYMENT CONTROLLER** — `iamaman11/mobile-proxy-production`: deployment ingress/ledger, State Machine / Transaction Kernel, target admission/serialization/observation/adapters, durable mutation intent, exactly-once destructive dispatch, postconditions, recovery/quarantine and canonical runtime execution evidence.

Controller is not a second product source. PRODUCT is not deployment transaction authority. Secrets, private bindings/raw target identifiers and sensitive runtime evidence remain private.

Normative cross-plane details live in `docs/operations/project-authority.md` and the v2 authority/topology/release contracts.

## Control/document roles

- PRODUCT #179 — only dynamic stage/operations cursor;
- current subordinate Stage Issue — current stage mission/evidence/PR journal;
- PRODUCT #249 — stage-mapped backlog only;
- PRODUCT #90 — Product Release/tag command surface only where required;
- Controller #1 — command/runtime ledger only;
- `docs/PRODUCTION_STAGE_ROADMAP.md` — static seven-stage sequence/scope;
- `docs/PRODUCTION_BASELINE_PLAN.md` — stable architecture/invariants;
- `docs/architecture/ARCHITECTURE_STANDARD.md` — permanent complexity/ownership standard;
- `TEN_OUT_OF_TEN_VALIDATION_PLAN.md` — stage-mapped acceptance catalog;
- `IMPLEMENTATION_PLAN.md` — static index only;
- future/historical plans — never current execution authority unless explicitly promoted by a newer #179 checkpoint.

## Controller safety kernel

```text
exact immutable Product Release
+ exact admitted Controller revision
  -> semantic request
  -> admission + target lock
  -> observe
  -> durable intent if mutation is required
  -> at most one destructive dispatch
  -> independent observe/postcondition
  -> canonical terminal
```

Ambiguous post-dispatch outcome is `UNKNOWN`; only read-only reconciliation is allowed. No blind destructive retry. GitHub Deployment status is projection, not canonical runtime truth.

## Phone/local-agent rule

Physical phone facts are observed, never guessed. Prefer Controller observation. If a required fact cannot be obtained reliably, request the narrow exact local-agent observation/interaction and classify the result as:

- `controller_capability_gap`;
- `human_only_physical_observation`;
- `one_off_observation`.

Stage-level conclusion/classification belongs in the current Stage Issue. Reusable long-form rooted-phone probe/transport diagnostics may live in Controller #97 and be linked from the Stage Issue. One-off evidence is not duplicated. Local-agent assistance never becomes deployment mutation authority.

## Static seven-stage sequence

1. Controller composite phone transaction foundation.
2. Immutable Product Release.
3. First real phone deployment.
4. Phone industrial operational validation.
5. Phone production baseline acceptance / simplification.
6. VM production transaction + first real deployment.
7. Combined PHONE + VM operational acceptance.

Current stage is intentionally absent here; resolve it only from PRODUCT #179.