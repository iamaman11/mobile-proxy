# Mobile Proxy Implementation Plan

This file is a **static index**, not a current execution plan. It deliberately carries no current stage, SHA, Product Release, target state, active PR or next action.

## Recover current work

Do **not** start here after context loss. Use:

`AGENTS.md -> STAGE_WORKFLOW.md -> newest authoritative PRODUCT #179 checkpoint -> current subordinate Stage Issue -> only stage-relevant permanent references`.

For context efficiency, read only the last #179 checkpoint comment, not its historical comment stream. Read Controller #1 only by exact causal ledger comment IDs when runtime evidence is needed.

## Static references

- `docs/PRODUCTION_STAGE_ROADMAP.md` — seven-stage sequence/scope;
- `docs/PRODUCTION_BASELINE_PLAN.md` — stable production architecture/invariants;
- `docs/architecture/ARCHITECTURE_STANDARD.md` — architecture/complexity/ownership standard;
- `TEN_OUT_OF_TEN_VALIDATION_PLAN.md` — stage-mapped acceptance catalog;
- PRODUCT #249 — planning/acceptance backlog only;
- `docs/FUTURE_PLATFORM_ARCHITECTURE_ROADMAP.md` — non-active future guidance.

Historical A-H, Item15-23 and Item19/Item20 execution sequences are audit history after supersession.

## Authority

```text
PRODUCT
  source / Quality / build / tags / immutable Product Release

DEPLOYMENT CONTROLLER
  deployment ingress / admission / target observation + serialization
  durable intent / exactly-once destructive dispatch
  independent postcondition / recovery / canonical runtime evidence
```

Both repositories are public. Secrets, private bindings/raw target identifiers and sensitive runtime evidence remain private.

## Permanent execution invariants

- one owner per state/decision;
- exact immutable Product Release + exact admitted Controller revision;
- durable mutation intent before destructive dispatch;
- at most one destructive dispatch per intent;
- independent postcondition;
- ambiguous post-dispatch result -> `UNKNOWN` -> read-only reconciliation;
- no blind destructive retry;
- physical phone facts are observed, never guessed;
- architecture changes are stage-mapped, not a parallel roadmap;
- generalize only from demonstrated current need/real implementations.

The project reaches full production acceptance only after Stage 7 exit. The current stage is intentionally resolved only from PRODUCT #179.