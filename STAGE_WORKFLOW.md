# Universal Stage Workflow

Canonical runtime authority is the newest authoritative checkpoint in PRODUCT Issue #179. If this file and #179 differ, #179 wins.

## Doctrine

**Analyze only enough to act. Save every meaningful result durably. One stage has one subordinate Stage Issue in its owning repository; implementation progress lives in the stage branch/PR, working decisions/evidence live in the Stage Issue, and #179 carries only authority/stage boundaries. Continue the stage until its real exit criteria are satisfied.**

## One stage

For every development/acceptance stage:

1. Create exactly **one subordinate Stage Issue** in the repository that owns the stage. It contains mission, scope, hard boundaries, exit criteria and links to active PRs. It is never authority; #179 remains the only stage cursor.
2. After the first completed code/docs slice, create the stage branch and open the stage PR. Keep later slices and ordinary fixes in that PR. If the stage genuinely touches both repositories, use at most one active stage PR per touched repository, all linked to the same Stage Issue.
3. **Finished functional slice + direct tests -> commit now.** Do not wait for the whole stage and do not leave a completed meaningful slice only in chat/local state.
4. **Important decision/finding/blocker/evidence with no ready code -> comment in the Stage Issue.** The comment must contain enough information to resume without repeating the analysis.
5. **Routine implementation or CI fix -> code/test/policy commit, not an Issue comment.** Comment only when the result changes architecture, scope, authority, or records non-code evidence needed later.
6. PR creation, red/green CI, individual commits and ordinary bounded fixes are not stop points. Continue to the stage exit criteria, including protected merge/post-merge checks when the stage includes them.
7. At stage exit: write one final summary in the Stage Issue, close it as completed, then publish one #179 checkpoint opening the next stage.

## Durable-progress rule

No more than one completed meaningful work slice may exist only locally or in chat. Before switching context or ending a work session, either:

- commit finished code/docs to the stage branch; or
- record the significant non-code result in the Stage Issue.

## #179 checkpoint rule

Create a new authoritative #179 checkpoint only for:

- stage exit / next stage;
- authority or stage-boundary change;
- genuine cross-stage contract blocker;
- ambiguous physical `UNKNOWN`;
- explicit owner plan change.

Do not checkpoint ordinary commits, PR-ready state, CI failures/fixes or merge boundaries already included in the current stage.