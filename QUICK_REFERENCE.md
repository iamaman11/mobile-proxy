# Quick Reference

## Authority in 30 seconds

Mobile Proxy has one product and two authoritative planes. **Both repositories are public.** Confidentiality lives in secrets, target bindings and bounded/redacted evidence, not repository visibility.

- **PRODUCT** — `iamaman11/mobile-proxy`: source, product/domain architecture, Quality, product build/signing verification, annotated tags, immutable Product Releases and product documentation.
- **DEPLOYMENT CONTROLLER** — `iamaman11/mobile-proxy-production`: Issue #1 deployment ingress, deployment State Machine / Transaction Kernel, target admission/serialization/observation, target adapters, durable mutation intent, exactly-once destructive dispatch, postconditions, recovery/quarantine and canonical runtime execution evidence.

The Controller is not a thin execution satellite and is not a second product source.

Normative v2 contracts:

1. `docs/operations/project-authority.md`
2. `contracts/operations/project-authority-v2.json`
3. `contracts/operations/github-control-plane-v2.json`
4. `contracts/operations/production-topology-v2.json`
5. `contracts/operations/product-release-authority-v2.json`

Older v1 authority/topology/control-plane wording is historical when it conflicts with v2.

## Start here after context loss

Use exactly this execution spine:

1. `AGENTS.md` — operating contract;
2. `STAGE_WORKFLOW.md` — canonical working method;
3. newest authoritative checkpoint in PRODUCT Issue **#179** — current stage, exact authority and boundaries;
4. the current subordinate Stage Issue — mission, evidence, active PR and blockers;
5. only then open stage-relevant standards/contracts/reference docs.

Do **not** reconstruct current execution from this file, `IMPLEMENTATION_PLAN.md`, a static roadmap, old issue body, chat memory, A-H gates, Item15-23/Item19-20 history or GitHub Deployment status.

## Control surfaces

- PRODUCT Issue **#179** — sole dynamic stage/operations cursor;
- PRODUCT Issue **#249** — stage-mapped planning/acceptance backlog only;
- PRODUCT Issue **#90** — Product Release/tag command surface where the current Product Release contract requires it; its historical architecture-tracker role is superseded;
- Controller Issue **#1** — deployment command ingress and durable runtime ledger surface.

A stage checkpoint authorizes the **whole stage to its exit criteria** inside its mission/scope/hard boundaries. `NEXT ALLOWED ITEM` names the next starting action, not a one-step permission or stop point.

Routine commits, PR/CI iterations, deterministic in-stage repairs, read-only observations, local-agent evidence, protected merge and post-merge checks are not checkpoint reasons.

## Document map

- `docs/PRODUCTION_STAGE_ROADMAP.md` — static seven-stage sequence/scope; contains no authoritative current stage.
- `docs/PRODUCTION_BASELINE_PLAN.md` — stable production architecture/invariants; not a parallel execution roadmap.
- `docs/architecture/ARCHITECTURE_STANDARD.md` — permanent architecture/complexity standard applied inside every stage.
- `TEN_OUT_OF_TEN_VALIDATION_PLAN.md` — acceptance catalog mapped to stages; does not authorize later-stage tests early.
- `docs/FUTURE_PLATFORM_ARCHITECTURE_ROADMAP.md` — future/post-baseline recommendations only.
- #249 — planning/backlog only.
- #179 — dynamic execution authority only.

Architecture work is stage-mapped. Stage 5 owns phone baseline simplification; Stage 6 is the first normal point for shared phone/VM target abstractions after two real implementations exist.

## Product/release boundary

PRODUCT flow:

```text
protected PRODUCT main + required Quality
  -> annotated product tag
  -> signed PRODUCT build
  -> immutable Product Release
```

Deployment flow:

```text
exact immutable Product Release
+ exact admitted Controller revision
  -> semantic deployment request
  -> admission / target serialization / observation
  -> durable intent before destructive dispatch
  -> at most one destructive dispatch for that intent
  -> independent postcondition
  -> canonical terminal evidence
```

GitHub Deployment status is projection only. It is never the canonical runtime ledger.

## Static seven-stage sequence

1. Controller composite phone transaction foundation.
2. Immutable Product Release.
3. First real phone deployment.
4. Phone industrial operational validation.
5. Phone production baseline acceptance / simplification.
6. VM production transaction + first real deployment.
7. Combined PHONE + VM operational acceptance.

The current stage, current Release and exact target identities are intentionally absent here; resolve them from #179.

## Phone facts and local-agent assistance

Never infer physical phone state from chat history, workflow color, elapsed time, timeout wording or expected architecture.

Prefer Controller observation. If an exact fact cannot be obtained reliably or the test inherently needs device UI/local-workstation/physical interaction, request the narrow exact observation/action from the local agent and state what evidence must be returned.

Classify every local-agent result as one of:

- `controller_capability_gap` — repeatable/decision-critical observation Controller should reasonably expose;
- `human_only_physical_observation` — inherently physical/UI/modem/operator interaction;
- `one_off_observation` — bounded fact with no demonstrated reusable Controller need.

A capability gap is not automatic framework work. Implement only the smallest stage-relevant observation improvement when it materially reduces guessing, UNKNOWN or recurring manual dependence. Local-agent assistance never becomes deployment mutation authority.

## Runtime safety invariants

Controller must preserve:

- target-global serialization;
- durable mutation intent before destructive dispatch;
- at most one destructive dispatch per durable intent;
- independent target postcondition observation;
- no blind retry after an ambiguous destructive boundary;
- read-only UNKNOWN reconciliation;
- semantic request identity independent of GitHub run/comment provenance;
- canonical terminal evidence.

## Development quality

```bash
scripts/quality-gate.sh fast  # docs/policy-sized changes
scripts/quality-gate.sh       # code/release/tooling changes
```

GitHub requires the aggregate `Quality Gate`. Read the compact quality summary before large logs.

## Hard boundaries

- PRODUCT workflows do not access the production phone or perform deployment mutation;
- Controller does not independently build/sign/tag/publish PRODUCT artifacts;
- raw/manual destructive ADB and manual SSH/provider CLI are not normal production control paths;
- secrets/raw target identifiers/sensitive runtime evidence do not enter public Git/evidence;
- `latest`, mutable branches and GitHub Deployment projection are never runtime identity;
- VM/provider mutation remains fail-closed until Stage 6 is explicitly opened by #179.
