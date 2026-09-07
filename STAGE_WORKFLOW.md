# Universal Stage Workflow

Canonical runtime authority is the newest authoritative checkpoint in PRODUCT Issue #179. If this file and #179 differ, #179 wins.

## Doctrine

**Analyze only enough to act. Save every meaningful result durably. One stage has one subordinate Stage Issue in its owning repository; implementation progress lives in the stage branch/PR, working decisions/evidence live in the Stage Issue, and #179 carries only authority/stage boundaries. A stage checkpoint authorizes the whole named stage within its scope and hard boundaries: continue until the real exit criteria are satisfied.**

## Context recovery: one execution spine

After losing chat or local context, recover current work in exactly this order:

1. repository `AGENTS.md`;
2. this `STAGE_WORKFLOW.md`;
3. the **newest authoritative checkpoint** in PRODUCT Issue #179;
4. the one current subordinate Stage Issue named by the stage;
5. only then the permanent standards/contracts/reference documents needed by that stage.

No other document or issue is a parallel execution roadmap. Static roadmaps, acceptance catalogs, architecture standards, backlogs and future recommendations never independently define the current stage, current Release, current SHA, next bounded action or checkpoint cadence.

Document roles:

- PRODUCT #179 — only dynamic stage/operations cursor;
- `docs/PRODUCTION_STAGE_ROADMAP.md` — static seven-stage sequence and scope;
- `docs/architecture/ARCHITECTURE_STANDARD.md` — permanent architecture/complexity/ownership standard applied inside every stage;
- `TEN_OUT_OF_TEN_VALIDATION_PLAN.md` — stage-mapped acceptance catalog, not action authority;
- PRODUCT #249 — planning/acceptance backlog only;
- `docs/FUTURE_PLATFORM_ARCHITECTURE_ROADMAP.md` — future/post-baseline guidance only;
- historical A-H, Item15-23 and Item19/20 plans — evidence/history only when superseded.

## One stage

For every development/acceptance stage:

1. Create exactly **one subordinate Stage Issue** in the repository that owns the stage. It contains mission, scope, hard boundaries, exit criteria and links to active PRs. It is never authority; #179 remains the only stage cursor.
2. After the first completed code/docs slice, create the stage branch and open the stage PR. Keep later slices and ordinary fixes in that PR. If the stage genuinely touches both repositories, use at most one active stage PR per touched repository, all linked to the same Stage Issue.
3. **Finished functional slice + direct tests -> commit now.** Do not wait for the whole stage and do not leave a completed meaningful slice only in chat/local state.
4. **Important decision/finding/blocker/evidence with no ready code -> comment in the Stage Issue.** The comment must contain enough information to resume without repeating the analysis.
5. **Routine implementation or CI fix -> code/test/policy commit, not an Issue comment.** Comment only when the result changes architecture, scope, authority, or records non-code evidence needed later.
6. PR creation, individual commits, red/green CI, deterministic known-state repair, read-only observation, ordinary evidence collection, bounded fixes, protected merge and post-merge checks are not stop points when they remain inside the current stage. Continue to the stage exit criteria.
7. At stage exit: write one final summary in the Stage Issue, close it as completed, then publish one #179 checkpoint opening the next stage.

## Stage-completion mandate

A #179 checkpoint that opens a stage is **continuous authority for that entire stage**, limited by the checkpoint's mission, scope, hard boundaries and exit criteria. It is not a one-step permission token.

`NEXT ALLOWED ITEM` identifies the next starting action. Completing that action does not require another checkpoint and is not a reason to stop. Continue autonomously through the remaining in-stage analysis, implementation, direct tests, PR work, CI repair, protected merge/post-merge acceptance, authorized operational validation and final evidence.

Do not manufacture intermediate #179 checkpoints merely to restate the next action or acknowledge routine progress. A concrete defect discovered inside the stage should be classified, repaired and verified inside the same stage when doing so does not cross an authority/stage boundary.

A genuine owner stop/new #179 checkpoint is required only for the exceptional conditions listed in the checkpoint rule below. If none applies, keep moving until exit.

## Phone facts and local-agent assistance

Physical phone state must be **observed, not guessed**. Do not infer a phone fact from chat history, workflow color, elapsed time, timeout wording or architectural expectation.

1. Prefer the Deployment Controller observer/target-adapter path for phone observation and mutation.
2. If the exact phone fact needed to continue cannot be obtained reliably through the available Controller observation, or the current validation inherently requires physical device UI/local-workstation interaction, explicitly ask the local agent for the **narrow exact observation or interaction needed** instead of guessing.
3. A local-agent request is operational assistance, not a new stage checkpoint and not a stage stop. After the evidence is returned, record significant physical evidence in the Stage Issue and continue the same stage.
4. Local-agent assistance may provide exact read-only diagnostics, device/UI observations and explicitly authorized physical interactions required by the current stage. State exactly what to observe/do and what evidence to return; never ask the agent to improvise or "try things".
5. The local agent is not deployment authority. It must not bypass immutable Release identity, durable mutation intent, target serialization, exactly-once destructive dispatch or UNKNOWN reconciliation. Raw/manual ADB or destructive local mutation is forbidden as a shortcut around the Controller. Any destructive action remains owned by the proper authorized Controller transaction path unless a newer owner checkpoint explicitly defines a different physical-test boundary.
6. If a phone-dependent conclusion cannot be proven with available evidence, classify it as unknown/unproven and request the missing local-agent observation. Do not substitute a hypothesis.

### Local-agent result -> Controller capability feedback

Every local-agent result is classified as exactly one:

- `controller_capability_gap` — repeatable or decision-critical observation needed for deployment, recovery or operational validation that should reasonably be available through Controller observation/target-adapter semantics;
- `human_only_physical_observation` — inherently device-UI, physical, modem or operator interaction that should remain outside normal Controller automation;
- `one_off_observation` — bounded evidence without a demonstrated reusable Controller requirement.

A `controller_capability_gap` is evidence of a missing capability, **not automatic permission to add framework code**. Apply the normal complexity/necessity gate:

- implement the smallest observation capability in the current stage when the gap is demonstrated, stage-relevant, reduces guessing/UNKNOWN/manual dependence, and is simpler than repeated local assistance;
- if it is real but does not block the current stage, record it and defer it to the earliest stage it actually blocks;
- if it is human-only or one-off, do not generalize it into Controller machinery.

When a Controller-owned authoritative decision, postcondition or recovery classification repeatedly depends on a local-agent fact that could be machine-observed safely, treat that dependence as a Controller design smell and resolve it before accepting the earliest stage whose exit depends on it.

## Architecture work is stage-mapped

Architecture improvement is not a parallel workstream. `ARCHITECTURE_STANDARD.md` supplies permanent rules; concrete architecture changes enter the earliest stage whose exit they block or whose demonstrated P0/P1 they close. Stage 5 explicitly owns phone-baseline simplification. Stage 6 is the first point where phone and VM are two real target implementations and therefore the first normal point for extracting shared target abstractions from demonstrated duplication.

Future architecture recommendations remain inactive until promoted through #179 into a stage.

## Durable-progress rule

No more than one completed meaningful work slice may exist only locally or in chat. Before switching context or ending a work session, either:

- commit finished code/docs to the stage branch; or
- record the significant non-code result in the Stage Issue.

## #179 checkpoint rule

Create a new authoritative #179 checkpoint only for:

- stage exit / next stage;
- authority or stage-boundary change;
- genuine cross-stage contract decision/blocker;
- unresolved post-intent physical `UNKNOWN` where further mutation is unsafe;
- an irreversible/external action outside current authority;
- explicit owner plan change.

Do not checkpoint ordinary commits, PR-ready state, CI failures/fixes, deterministic known-state repair, read-only observations, local-agent evidence requests/results, protected merge boundaries or post-merge checks already included in the current stage.
