# Universal Stage Workflow

Canonical runtime authority is the newest authoritative checkpoint in PRODUCT Issue #179. If this file and #179 differ, #179 wins.

## Doctrine

**Analyze only enough to act. Save every meaningful result durably. One stage has one subordinate Stage Issue in its owning repository; implementation progress lives in the stage branch/PR, working decisions/evidence live in the Stage Issue, and #179 carries only authority/stage boundaries. A stage checkpoint authorizes the whole named stage within its scope and hard boundaries: continue until the real exit criteria are satisfied.**

## Context recovery: one execution spine

After losing chat/local context, recover current work only in this order:

1. repository `AGENTS.md`;
2. this `STAGE_WORKFLOW.md`;
3. the newest authoritative checkpoint in PRODUCT Issue #179;
4. the one current subordinate Stage Issue;
5. only then permanent standards/contracts/reference docs required by that stage.

No other document/Issue is a parallel execution roadmap.

### Context-budget protocol

- #179 has historical depth: read Issue metadata/body + **last comment only**; require an owner-authored authoritative checkpoint. Walk backward minimally only if needed. Never fetch all #179 comments for normal recovery.
- Current Stage Issue: read the body + only newest stage-relevant comments needed to resume.
- Controller #1: never use the full ledger as context. Read exact command/intent/terminal comment IDs referenced by current stage/causal evidence.
- Controller #97: optional reusable rooted-phone diagnostic/probe reference only; read on demand, not during default recovery.
- Static roadmaps, acceptance catalogs, architecture standards, backlogs, `QUICK_REFERENCE.md` and `IMPLEMENTATION_PLAN.md` are on-demand references, not extra mandatory recovery hops.

After governance convergence, routine evidence must not be posted to #179. Future #179 comments are reserved for authority checkpoints and should be compact rather than restating permanent doctrine.

## Document roles

- PRODUCT #179 — only dynamic stage/operations cursor;
- `docs/PRODUCTION_STAGE_ROADMAP.md` — static seven-stage sequence/scope;
- `docs/architecture/ARCHITECTURE_STANDARD.md` — permanent architecture/complexity standard;
- `TEN_OUT_OF_TEN_VALIDATION_PLAN.md` — stage-mapped acceptance catalog, not action authority;
- PRODUCT #249 — planning/acceptance backlog only;
- `docs/FUTURE_PLATFORM_ARCHITECTURE_ROADMAP.md` — future/post-baseline guidance only;
- historical A-H, Item15-23 and Item19/20 plans — evidence/history only when superseded.

## One stage

For every stage:

1. Create exactly one subordinate Stage Issue in the owning repository with mission, scope, hard boundaries, exit criteria and PR links. It is never authority.
2. After the first completed code/docs slice, create the stage branch and stage PR. If both repos are genuinely touched, use at most one active stage PR per repo, linked to the same Stage Issue.
3. Finished functional slice + direct tests -> commit now.
4. Important decision/finding/blocker/evidence without ready code -> Stage Issue comment with enough detail to resume without repeating analysis.
5. Routine implementation/CI fix -> commit, not Issue commentary.
6. PR creation, commits, red/green CI, deterministic known-state repair, read-only observation, ordinary evidence collection, bounded fixes, protected merge/post-merge checks and local-agent requests/results are not stop points inside the stage.
7. At stage exit: final Stage Issue summary -> close completed -> one #179 checkpoint opening the next stage.

## Stage-completion mandate

A #179 checkpoint that opens a stage is continuous authority for that whole stage inside its mission/scope/hard boundaries/exit criteria. `NEXT ALLOWED ITEM` names the next starting action, not a one-step token.

Do not manufacture intermediate #179 checkpoints for routine progress. Repair demonstrated in-stage defects inside the same stage when no authority/stage boundary is crossed.

## Phone facts and local-agent assistance

Physical phone state must be **observed, not guessed**.

1. Prefer Deployment Controller observer/target-adapter paths.
2. If the exact fact cannot be obtained reliably, or validation inherently requires device UI/local-workstation/physical interaction, request the **narrow exact observation/interaction** and define evidence to return.
3. Local-agent help is operational assistance, not a checkpoint or mutation authority.
4. Never ask the local agent to improvise or “try things”.
5. Raw/manual destructive ADB may not bypass immutable Release identity, durable mutation intent, target serialization, exactly-once destructive dispatch or UNKNOWN reconciliation.
6. If the fact is unproven, keep it unknown and request the missing evidence.

Every local-agent result is classified as exactly one:

- `controller_capability_gap` — repeatable/decision-critical machine-observable fact Controller should reasonably expose;
- `human_only_physical_observation` — inherently device-UI/physical/modem/operator interaction;
- `one_off_observation` — bounded evidence without demonstrated reusable Controller need.

A capability gap is evidence of missing capability, not automatic framework permission. Implement only the smallest observation capability when demonstrated, stage-relevant, materially reduces guessing/UNKNOWN/manual dependence and is simpler than repeated local assistance; otherwise defer to the earliest stage it blocks.

### Evidence routing

- Current Stage Issue owns the **stage-level conclusion, classification, blocker and acceptance relevance**.
- Controller #97 may hold reusable long-form rooted-phone probe/transport diagnostics. Link the exact #97 evidence comment from the Stage Issue; do not duplicate full evidence in both places.
- One-off stage evidence stays only in the Stage Issue.
- Controller #1 contains machine command/intent/terminal ledger records only.
- #179 contains authority/stage boundaries only.

If a Controller-owned decision/postcondition/recovery repeatedly depends on a safely machine-observable local-agent fact, treat it as a Controller design smell and close the smallest necessary observation gap before the earliest dependent stage exits.

## Architecture work is stage-mapped

Architecture improvement is not a parallel workstream. `ARCHITECTURE_STANDARD.md` supplies permanent rules; concrete changes enter the earliest stage whose exit they block or whose demonstrated P0/P1 they close. Stage 5 owns phone-baseline simplification. Stage 6 is the first normal point for shared phone/VM target abstractions from demonstrated duplication.

## Durable-progress rule

No more than one completed meaningful slice may exist only locally/chat. Before switching context or ending a work session, commit finished code/docs or record significant non-code evidence in the Stage Issue.

## #179 checkpoint rule

Create a new authoritative #179 checkpoint only for:

- stage exit / next stage;
- authority or stage-boundary change;
- genuine cross-stage contract decision/blocker;
- unresolved post-intent physical `UNKNOWN` where further mutation is unsafe;
- irreversible/external action outside current authority;
- explicit owner plan change.

Do not checkpoint ordinary commits, PR/CI state, deterministic repair, read-only observations, local-agent evidence, protected merge or post-merge checks already inside current stage authority.