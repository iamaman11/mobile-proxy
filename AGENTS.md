# Agent operating contract

Start every repository task with:

    python3 scripts/repository_context.py
    git status --short --branch

`repository_context.py` is a bounded **static repository map**. It does not declare the current stage, current Product Release, current production state or next action. Resolve dynamic work only through the execution spine below.

## Context recovery and execution spine

After any context loss, read in this order and stop looking for competing current-state prose:

1. this `AGENTS.md`;
2. `STAGE_WORKFLOW.md`;
3. the newest authoritative checkpoint in PRODUCT Issue #179;
4. the one current subordinate Stage Issue;
5. only the permanent standards/contracts/reference documents needed for that stage.

PRODUCT Issue #179 is the **only dynamic development/operations stage cursor**. A stage checkpoint authorizes the whole named stage through its exit criteria within its stated mission, scope and hard boundaries. `NEXT ALLOWED ITEM` is a starting action, not a stop point.

Do not reconstruct current work from old issue bodies, historical comments, chat memory, hand-maintained SHAs, `CURRENT` labels in static documents, A-H gates, Item15-23/Item19-20 plans or public GitHub Deployment status.

## Authority model

The project has one product and two authoritative planes. **Both repositories are public; authority and confidentiality are not inferred from repository visibility.**

- `iamaman11/mobile-proxy` = **PRODUCT authority**: application/runtime source, shared product/domain architecture, Quality, product build/signing verification, annotated product tags, immutable Product Releases and product documentation.
- `iamaman11/mobile-proxy-production` = **DEPLOYMENT CONTROLLER authority**: Issue #1 deployment ingress, deployment State Machine / Transaction Kernel, target admission and serialization, target observation/adapters, durable mutation intent, exactly-once destructive dispatch, postconditions, recovery/quarantine and canonical runtime execution evidence.

Neither repository may silently take over the other's responsibility. Controller is not a second product source and must not independently build, sign, tag or publish the product. PRODUCT must not own the deployment transaction ledger, production target mutation authority or exactly-once destructive dispatch.

Repository/environment secret values, target bindings, raw target identifiers, credentials, private keys, sensitive rendered config and unsafe raw runtime/ADB logs remain private even though Controller source/policy is public.

Normative v2 authority contracts:

- `docs/operations/project-authority.md`
- `contracts/operations/project-authority-v2.json`
- `contracts/operations/github-control-plane-v2.json`
- `contracts/operations/production-topology-v2.json`
- `contracts/operations/product-release-authority-v2.json`

Older v1 authority/topology/control-plane contracts and Item19/Item20 material are historical evidence when they conflict with v2.

## Control surfaces

- PRODUCT Issue #179 = sole dynamic stage/operations cursor;
- PRODUCT Issue #249 = stage-mapped planning/acceptance backlog only;
- PRODUCT Issue #90 = Product Release/tag command surface where the current Product Release contract requires it; its historical GitOps architecture tracker role is superseded;
- `iamaman11/mobile-proxy-production` Issue #1 = Deployment Controller command ingress and durable runtime ledger surface.

Before any repository or production-state write, reread the newest #179 checkpoint and revalidate relevant PRODUCT/Controller mains, protected checks and immutable Release identity. A stale issue body or older comment never overrides a newer checkpoint.

A `/deploy`, phone mutation, provider/VM mutation, signing operation, tag or Product Release action is permitted only when the newest #179 checkpoint and the owning v2 authority plane permit it.

## Document roles

There is one execution roadmap, not several parallel plans:

- `STAGE_WORKFLOW.md` — canonical working method;
- `docs/PRODUCTION_STAGE_ROADMAP.md` — static seven-stage sequence/scope only; no dynamic current state;
- `docs/PRODUCTION_BASELINE_PLAN.md` — stable production architecture/invariants baseline, not a competing execution sequence;
- `docs/architecture/ARCHITECTURE_STANDARD.md` — permanent architecture, ownership and complexity standard applied inside every stage;
- `TEN_OUT_OF_TEN_VALIDATION_PLAN.md` — acceptance catalog mapped to stages; it never authorizes later-stage work early;
- `IMPLEMENTATION_PLAN.md` and `QUICK_REFERENCE.md` — concise navigation/context-recovery entrypoints;
- PRODUCT Issue #249 — planning/backlog only;
- `docs/FUTURE_PLATFORM_ARCHITECTURE_ROADMAP.md` — non-active future/post-baseline recommendations;
- `docs/history` and superseded A-H / Item15-23 / Item19-20 plans — history/evidence only.

Architecture improvement is **stage-mapped**. A concrete architecture defect enters the earliest stage whose exit it blocks or whose demonstrated P0/P1 it closes. Stage 5 owns phone-baseline simplification. Stage 6 is the first normal point for extracting shared phone/VM target abstractions from demonstrated duplication. Do not run an architecture roadmap in parallel with the stages.

## Deployment-controller invariants

Controller must preserve:

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

If a destructive dispatch may have occurred but its result is ambiguous:

```text
UNKNOWN
  -> read-only observation/reconciliation
  -> proven resulting state
```

Rules:

- no blind destructive retry after the dispatch boundary;
- `RECOVERED != ACCEPTED`;
- GitHub Deployment is projection, never canonical runtime ledger;
- GitHub run/comment/attempt provenance does not redefine semantic request identity;
- evidence-write retry is not permission to repeat a physical effect;
- target serialization is Controller-owned;
- workflow success is not an independent target postcondition.

## Phone facts, local agent and Controller feedback

Never infer physical phone state from chat history, Issue prose, workflow color, elapsed time, timeout wording or architectural expectation.

Prefer Controller observer/target-adapter evidence. If an exact phone fact cannot be obtained reliably through Controller observation, or validation inherently requires device UI/local-workstation/physical interaction, ask the local agent for the **narrow exact observation or interaction** and specify the evidence to return. This request/result is not a stage checkpoint or stage stop.

Every local-agent result must be classified as exactly one:

- `controller_capability_gap` — repeatable or decision-critical observation that should reasonably be available through Controller observation semantics;
- `human_only_physical_observation` — inherently UI/physical/modem/operator interaction;
- `one_off_observation` — bounded evidence without a demonstrated reusable Controller requirement.

A `controller_capability_gap` is not automatic permission for new framework code. Apply the architecture complexity/necessity gate. Implement the smallest observation capability when the gap is demonstrated, current-stage relevant, reduces guessing/UNKNOWN/manual dependence and is simpler than repeated local assistance; otherwise record it for the earliest stage it blocks. Human-only and one-off facts must not be generalized without evidence.

The local agent is never deployment mutation authority. It must not bypass immutable Release identity, durable intent, target serialization, exactly-once destructive dispatch or UNKNOWN reconciliation. Raw/manual destructive ADB remains forbidden as a Controller shortcut unless a newer owner checkpoint explicitly defines a different physical-test boundary.

## Product architecture and complexity discipline

Build the smallest understandable industrial system that satisfies the real topology.

- functional outcome first;
- one owner per state/decision;
- add a layer only for an independent responsibility/lifecycle/failure mode;
- no code for code and no verification of verification;
- prefer explicit contracts, small pure functions and thin adapters;
- prefer deletion/consolidation/reuse before new modules, workflows, registries or abstractions;
- generalize only when two real implementations need the same abstraction or another concrete present-day requirement exists;
- tests protect behavior/failure/security/authority boundaries, not other tests/checkers;
- do not build generic extension mechanisms for hypothetical future targets.

Inside PRODUCT, exact workspace dependency rules remain in `contracts/governance/module-boundaries-v1.json`; PRODUCT mutable-state ownership remains in `contracts/governance/state-ownership-v1.json` where applicable.

## Change discipline

- Work on a topic branch; do not deploy an uncommitted tree.
- Finished meaningful code/docs + direct tests -> commit; significant non-code evidence -> current Stage Issue.
- Routine PR/CI failures/fixes, deterministic in-stage repairs, read-only observations, local-agent evidence, protected merge and post-merge checks are not stop points.
- Do not commit target directories, build outputs, runtime binaries, credentials or raw sensitive acceptance logs.
- PRODUCT has no production self-hosted runner and performs no production phone mutation.
- Production phone execution belongs to Controller on the registered target runner with private binding.
- VM/provider work remains fail-closed until Stage 6 is explicitly opened.
- Manual SSH/raw ADB/workstation provider CLI are not the standard production control plane.
- Deployment identity is exact immutable Product Release + exact admitted Controller revision; `latest` and mutable branches are forbidden.

## Proportional verification

For docs/policy-sized changes:

    scripts/quality-gate.sh fast

For code/release/tooling changes:

    scripts/quality-gate.sh

GitHub's required aggregate check is `Quality Gate`. Verification must be behavior-oriented and proportional.

## Stage completion

Follow `STAGE_WORKFLOW.md`. Continue the current stage autonomously through analysis, implementation, tests, PR work, CI repair, protected merge/post-merge acceptance, authorized operational validation and final evidence until its real exit criteria are satisfied.

Create a new #179 checkpoint only for the exceptional boundaries defined there: stage exit/next stage, authority or stage-boundary change, genuine cross-stage contract decision/blocker, unresolved post-intent physical `UNKNOWN` where further mutation is unsafe, irreversible/external action outside current authority, or explicit owner plan change.
