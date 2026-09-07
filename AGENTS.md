# Agent operating contract

Start every repository task with:

    python3 scripts/repository_context.py
    git status --short --branch

`repository_context.py` is a bounded **static repository map**. It never declares current stage, current Product Release, current production state or next action.

## Context recovery: one execution spine

After context loss read only:

1. this `AGENTS.md`;
2. `STAGE_WORKFLOW.md`;
3. the newest authoritative checkpoint in PRODUCT Issue #179;
4. the one current subordinate Stage Issue;
5. only the permanent standards/contracts/reference docs required by that stage.

PRODUCT #179 is the **only dynamic development/operations cursor**. A stage checkpoint authorizes the whole named stage through its exit criteria inside its mission, scope and hard boundaries. `NEXT ALLOWED ITEM` is a starting action, not a stop point.

Do not reconstruct current work from old Issue bodies, historical comments, chat memory, hand-maintained SHAs, static `CURRENT` labels, A-H gates, Item15-23/Item19-20 plans or GitHub Deployment projection.

### Context-budget rule

Do not load large historical Issues by default.

- **PRODUCT #179:** read Issue metadata/body and only the last comment; require it to be an owner-authored authoritative checkpoint. Walk backward minimally only if that invariant fails. Never fetch all #179 comments for normal recovery.
- **Current Stage Issue:** read its body and only the newest stage-relevant comments needed to resume. Do not replay completed history.
- **Controller #1:** command/intent/terminal ledger only. When runtime evidence is needed, read exact causal comment IDs referenced by the Stage Issue/Controller record; never fetch the full ledger for context.
- **Controller #97:** optional reusable rooted-phone observation/diagnostic reference. Open only when the current Stage Issue/probe requires it; it is not current phone state.
- `QUICK_REFERENCE.md` and `IMPLEMENTATION_PLAN.md` are optional human navigation, not additional mandatory agent steps. Do not read both merely to restate this contract.

## Authority model

One product, two authoritative planes. **Both repositories are public; confidentiality is not inferred from repository visibility.**

- `iamaman11/mobile-proxy` = **PRODUCT**: application/runtime source, shared product/domain architecture, Quality, product build/signing verification, annotated tags, immutable Product Releases and product documentation.
- `iamaman11/mobile-proxy-production` = **DEPLOYMENT CONTROLLER**: Issue #1 deployment ingress/ledger, deployment State Machine / Transaction Kernel, target admission/serialization/observation/adapters, durable mutation intent, exactly-once destructive dispatch, postconditions, recovery/quarantine and canonical runtime execution evidence.

Controller is not a second product source. PRODUCT is not deployment transaction authority. Neither plane may silently take over the other.

Secrets, target bindings, raw target identifiers, credentials, private keys, sensitive rendered config and unsafe raw runtime/ADB logs remain private.

Normative v2 authority contracts:

- `docs/operations/project-authority.md`
- `contracts/operations/project-authority-v2.json`
- `contracts/operations/github-control-plane-v2.json`
- `contracts/operations/production-topology-v2.json`
- `contracts/operations/product-release-authority-v2.json`

Older v1 authority/topology/control-plane and Item19/Item20 material is historical when it conflicts with v2.

## Control/document roles

- PRODUCT #179 — sole dynamic stage/operations cursor;
- PRODUCT #249 — stage-mapped planning/acceptance backlog only;
- PRODUCT #90 — Product Release/tag command surface only where the current Release contract requires it; historical architecture-tracker role superseded;
- Controller #1 — deployment command ingress/runtime ledger only;
- one subordinate Stage Issue — current stage mission/evidence/PR journal;
- `STAGE_WORKFLOW.md` — canonical working method;
- `docs/PRODUCTION_STAGE_ROADMAP.md` — static seven-stage sequence/scope;
- `docs/PRODUCTION_BASELINE_PLAN.md` — stable architecture/invariant baseline;
- `docs/architecture/ARCHITECTURE_STANDARD.md` — permanent architecture/complexity standard;
- `TEN_OUT_OF_TEN_VALIDATION_PLAN.md` — stage-mapped acceptance catalog, not action authority;
- `docs/FUTURE_PLATFORM_ARCHITECTURE_ROADMAP.md` — non-active future guidance;
- `docs/history` and superseded A-H / Item15-23 / Item19-20 plans — evidence/history only.

Architecture improvement is stage-mapped. Stage 5 owns phone-baseline simplification. Stage 6 is the first normal point for shared phone/VM target abstractions from demonstrated duplication.

## Deployment-controller invariants

Controller preserves:

```text
exact immutable Product Release
  -> semantic deployment request
  -> admission
  -> target-global serialization
  -> observation
  -> durable mutation intent before destructive dispatch
  -> at most one destructive dispatch for that intent
  -> independent postcondition observation
  -> canonical terminal classification
```

Ambiguous post-dispatch outcome:

```text
UNKNOWN -> read-only observation/reconciliation -> proven resulting state
```

No blind destructive retry. GitHub run/comment provenance does not redefine semantic request identity. Evidence-write retry never permits repeating a physical effect. Workflow success is not an independent target postcondition. GitHub Deployment is projection, not canonical runtime truth.

## Phone facts and local-agent evidence

Never infer phone state from chat, Issue prose, workflow color, elapsed time, timeout wording or expected architecture.

Prefer Controller observer/target-adapter evidence. If an exact fact cannot be obtained reliably, or validation inherently requires device UI/local-workstation/physical interaction, ask the local agent for the **narrow exact observation/interaction** and specify the evidence to return.

Classify every result exactly once as:

- `controller_capability_gap` — repeatable/decision-critical observation Controller should reasonably expose;
- `human_only_physical_observation` — inherently UI/physical/modem/operator interaction;
- `one_off_observation` — bounded evidence without demonstrated reusable Controller need.

A capability gap is not automatic framework work. Implement only the smallest current-stage observation capability when demonstrated, stage-relevant, materially reduces guessing/UNKNOWN/manual dependence and is simpler than repeated local assistance; otherwise defer it to the earliest stage it blocks.

Evidence routing:

- stage-level conclusion/classification -> current Stage Issue;
- reusable long-form rooted-phone probe/transport diagnostic -> optional Controller #97, with exact link from the Stage Issue;
- one-off stage evidence -> Stage Issue only; do not duplicate merely for completeness;
- machine command/intent/terminal -> Controller #1 only.

The local agent is never deployment mutation authority. It must not bypass immutable Release identity, durable intent, target serialization, exactly-once destructive dispatch or UNKNOWN reconciliation. Raw/manual destructive ADB remains forbidden as a Controller shortcut unless a newer owner checkpoint explicitly defines a different physical-test boundary.

## Architecture and change discipline

Build the smallest understandable industrial system that satisfies the real topology.

- functional outcome first; one owner per state/decision;
- add a layer only for an independent responsibility/lifecycle/failure mode;
- no code for code; no verification of verification;
- prefer explicit contracts, small pure functions, thin adapters and deletion/consolidation;
- generalize only after two real implementations need the same abstraction or another concrete current need exists;
- tests protect behavior/failure/security/authority boundaries, not other tests/checkers;
- no generic extension framework for hypothetical future targets.

Work on a topic branch. Finished meaningful code/docs + direct tests -> commit; significant non-code evidence -> current Stage Issue. Routine PR/CI repair, deterministic in-stage fixes, read-only observations, local-agent evidence, protected merge and post-merge checks are not stop points.

PRODUCT has no production target mutation authority. Production phone execution belongs to Controller. VM/provider work stays fail-closed until Stage 6 is explicitly opened. Manual SSH/raw ADB/workstation provider CLI are not standard production control paths. Deployment identity is exact immutable Product Release + exact admitted Controller revision; `latest` and mutable branches are forbidden.

## Verification and stage completion

For docs/policy-sized changes:

    scripts/quality-gate.sh fast

For code/release/tooling changes:

    scripts/quality-gate.sh

GitHub's required aggregate check is `Quality Gate`.

Follow `STAGE_WORKFLOW.md` and continue the current stage through its real exit criteria. New #179 checkpoints are only for stage exit/next stage, authority/stage-boundary change, genuine cross-stage blocker/decision, unresolved post-intent physical `UNKNOWN`, irreversible/external action outside current authority, or explicit owner plan change.