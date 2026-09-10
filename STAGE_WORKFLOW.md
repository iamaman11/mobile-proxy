# Universal Stage Workflow

Canonical runtime authority is the newest authoritative owner checkpoint in PRODUCT Issue #179. If any static document, Stage Issue, chat context or workflow projection conflicts with that checkpoint, #179 wins for **current stage/authority only**.

## 1. One source of truth per concern

| Concern | Sole owner |
| --- | --- |
| Current stage, current operational authority/boundaries | PRODUCT Issue #179 newest authoritative checkpoint |
| Full static Stage 1-7 plan: goal/scope/non-goals/exit | `docs/PRODUCTION_STAGE_ROADMAP.md` |
| Durable architecture/topology/invariants | `docs/PRODUCTION_BASELINE_PLAN.md` + normative v2 contracts |
| Architecture/complexity quality floor | `docs/architecture/ARCHITECTURE_STANDARD.md` |
| Acceptance evidence requirements | `TEN_OUT_OF_TEN_VALIDATION_PLAN.md` |
| Candidate/not-yet-promoted work | PRODUCT Issue #249 |
| Current-stage execution plan, findings, evidence, PR links | one subordinate Stage Issue |
| Deployment command/intent/terminal runtime ledger | Controller Issue #1 |
| Reusable rooted-phone diagnostic mechanics | optional Controller Issue #97 |

No second file/Issue independently restates or redefines another owner's concern.

## 2. Context recovery — minimum sufficient path

After context loss, read only:

1. repository `AGENTS.md` — repo-local rules only;
2. this `STAGE_WORKFLOW.md`;
3. PRODUCT #179 metadata/body + **last owner-authored authoritative checkpoint only**;
4. current Stage Issue body + only the newest stage-relevant comments needed to resume;
5. only then the specific permanent reference that the current decision actually requires.

Do **not** load the full roadmap, acceptance catalog, backlog, #179 history, Controller #1 ledger or #97 by default.

Load `PRODUCTION_STAGE_ROADMAP.md` only for a stage-boundary/scope/dependency decision. Load `TEN_OUT_OF_TEN_VALIDATION_PLAN.md` only when deciding whether evidence is sufficient. Load #249 only when triaging/promoting future work.

### Context-budget invariant

A normal resume should answer four questions without historical replay:

- What stage is current?
- What is currently allowed/forbidden?
- What is the current Stage Issue?
- What is the latest accepted finding / next unresolved stage item?

If those answers require reading dozens of historical comments, the documentation/evidence routing is defective and should be repaired rather than normalized.

### Current-state-over-history rule

Current physical/runtime state is never reconstructed from a dense historical narrative merely because that narrative contains exact SHAs, run IDs or prior bounded evidence. Historical evidence explains what happened in that transaction; it does not establish what is true now.

When a current decision depends on target state, first identify the owning observation surface and obtain current bounded evidence. Source inspection and historical artifacts may narrow hypotheses only after the relevant current-state prerequisite is known or explicitly unavailable.

## 3. Stage execution model

Each stage has exactly one subordinate Stage Issue in its owning repository.

The Stage Issue stores:

- current-stage mission and concrete execution order;
- scope/hard boundaries inherited from the canonical roadmap + #179;
- significant findings/decisions/blockers;
- accepted evidence references;
- PR links and exit matrix.

It is never authority by itself and must not redefine future stages.

Keep the Stage Issue body **compact and current**. Do not turn it into an append-only historical replay. Superseded execution plans, old SHAs and one-off evidence remain in comments/Git history; the body should contain only durable stage scope, current decision structure, current blockers/accepted slices and exit criteria. If the body contradicts a newer stage comment, repair the body instead of expecting future agents to mentally reconcile both.

A #179 checkpoint that opens a stage authorizes the **whole named stage** inside the roadmap scope and checkpoint hard boundaries. `NEXT ALLOWED ITEM` is the next starting point, not a one-step token.

Routine branch/PR creation, commits, CI failure/fix, deterministic known-state repair, read-only observation, local-agent evidence, protected merge and post-merge checks are continuous in-stage work, not checkpoint boundaries.

## 4. Durable progress

- Work on a topic/stage branch; use protected PR flow.
- Finished meaningful code/docs + direct tests -> commit promptly.
- Significant non-code finding/decision/evidence -> current Stage Issue comment.
- Do not leave more than one meaningful completed slice only in chat/local state.
- At stage exit: final evidence/handoff summary -> close Stage Issue completed -> one #179 checkpoint opening the next stage.

## 5. Physical facts, diagnostic ordering and local-agent assistance

Physical target state is observed, never guessed.

### Observation-before-hypothesis gate

For any current physical/runtime failure or ambiguous result, use this order:

1. **Classify the evidence domain first**: runner/host transport, phone transport/root, exact Release identity, live operational runtime, lifecycle/recovery, resource behavior, or another already-owned domain.
2. **Use the existing owning read-only observer/target adapter before inventing a deeper causal theory.** A specialized exercise must not substitute for a missing prerequisite observation.
3. **Separate current evidence from historical evidence.** A historical failure remains exactly what its artifact proved; later observations may explain it but do not rewrite it.
4. **Use source inspection only to interpret observed behavior or define the next discriminating observation.** Source semantics are not evidence that a process, listener, route or target is currently healthy.
5. If the owning observer cannot obtain the required fact reliably, classify the missing fact as a capability gap or bounded local-only observation and request the narrowest exact evidence.
6. Choose a repair, retry, recovery or mutation only after the failure domain is decision-grade. Never add pacing/backoff/retry merely to obtain green when the failed prerequisite is unknown.

This is a sequencing invariant, not a new orchestration framework. Existing domain owners and command surfaces remain independent.

### Local-agent assistance

1. Prefer the Controller observer/target adapter that owns the fact.
2. If the fact cannot be obtained reliably, or inherently needs physical/UI/local-workstation interaction, request the narrow exact observation/interaction and exact evidence to return.
3. Never ask a local agent to improvise, explore or perform broad repair.
4. Local-agent assistance is not deployment mutation authority.
5. Raw/manual destructive ADB never bypasses immutable Release identity, target serialization, durable intent, exactly-once dispatch, independent postcondition or `UNKNOWN` reconciliation.

Classify every local-agent result exactly as:

- `controller_capability_gap` — repeatable/decision-critical safely machine-observable fact the Controller should reasonably expose;
- `human_only_physical_observation` — inherently physical/UI/modem/operator fact;
- `one_off_observation` — bounded evidence without demonstrated reusable Controller need.

A capability gap is not framework permission. Implement only the smallest stage-relevant observation capability when it materially reduces guessing/`UNKNOWN`/manual dependence and is simpler/safer than recurring local assistance.

### Chat local-agent handoff protocol

When the project uses the chat bridge to invoke a local agent, the local-agent instruction must be emitted as a **standalone assistant message** containing the bounded task itself. Do not bury it inside a progress update, explanation, writing block or final summary. One local-agent request owns one bounded observation/interaction scope. Wait for and consume its returned evidence before issuing a replacement request unless the owner explicitly changes the task.

This UI/protocol rule exists so the operator can unambiguously distinguish project discussion from an executable local-agent handoff.

### Evidence routing

- Stage-specific conclusion/classification/blocker/acceptance relevance -> current Stage Issue.
- Reusable long-form rooted-phone diagnostic mechanics -> Controller #97, linked from the Stage Issue.
- Machine command/ACK/intent/terminal/recovery ledger -> Controller #1.
- Current authority/stage boundary -> #179 only.

Do not duplicate the same evidence across these surfaces.

## 6. Architecture work is stage-mapped

Architecture improvement is not a parallel roadmap.

A change enters the earliest stage whose exit it actually blocks or whose demonstrated P0/P1 it closes. Add a layer only for an independent responsibility/lifecycle/failure mode. Prefer explicit contracts, small pure functions, thin adapters and deletion/consolidation.

Stage 5 owns phone-baseline simplification. Stage 6 is the first normal point where two real target implementations may justify shared phone/VM abstractions.

## 7. #179 checkpoint rule

Create a new authoritative #179 checkpoint only for:

- stage exit / next stage;
- authority or stage-boundary change;
- explicit owner plan change affecting stage scope/dependencies;
- genuine cross-stage contract decision/blocker;
- unresolved post-intent physical `UNKNOWN` where further mutation is unsafe;
- irreversible/external action outside current authority.

A checkpoint should be compact and contain only:

- decision;
- current stage;
- current Stage Issue;
- exact current authority/hard boundaries;
- concrete current identities only when operationally necessary;
- pointers to the protected roadmap/contracts rather than copied plan text.

Do not post routine progress/evidence to #179.
