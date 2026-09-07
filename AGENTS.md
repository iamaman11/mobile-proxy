# Agent operating contract

This repository owns PRODUCT concerns. Cross-project working method and dynamic stage authority are intentionally centralized elsewhere; do not duplicate them here.

## Start after context loss

Run:

    python3 scripts/repository_context.py
    git status --short --branch

Then recover current work through exactly:

`PRODUCT AGENTS.md -> PRODUCT STAGE_WORKFLOW.md -> newest authoritative PRODUCT #179 checkpoint -> current subordinate Stage Issue -> only stage-relevant permanent references`.

Context budget:

- PRODUCT #179: Issue metadata/body + last owner-authored authoritative checkpoint comment only; never load the full history for normal recovery.
- current Stage Issue: body + only newest stage-relevant comments required to resume.
- Controller #1: exact causal command/intent/terminal comment IDs only when runtime evidence is needed.
- Controller #97: optional reusable rooted-phone diagnostic/probe reference, on demand only.
- `QUICK_REFERENCE.md` and `IMPLEMENTATION_PLAN.md` are optional human references, not mandatory agent hops.

## One source of truth per concern

- **dynamic stage/operations authority:** PRODUCT Issue #179;
- **cross-project working method/checkpoint/local-agent rules:** `STAGE_WORKFLOW.md`;
- **cross-plane ownership and release/deployment boundary:** `docs/operations/project-authority.md` plus v2 authority/topology/Product Release contracts;
- **static stage sequence/scope:** `docs/PRODUCTION_STAGE_ROADMAP.md`;
- **architecture/complexity standard:** `docs/architecture/ARCHITECTURE_STANDARD.md`;
- **stage acceptance catalog:** `TEN_OUT_OF_TEN_VALIDATION_PLAN.md`;
- **current stage evidence/decisions:** the one subordinate Stage Issue;
- **Controller runtime transaction truth:** exact records in Controller Issue #1;
- **reusable local phone diagnostic mechanics:** optional Controller Issue #97.

No second document or repository may independently redefine one of these concerns. Controller `AGENTS.md` is a repo-local overlay, not a copy of global governance.

## PRODUCT boundary

PRODUCT (`iamaman11/mobile-proxy`) owns:

- application/runtime source and shared product/domain architecture;
- Quality and product build/signing verification;
- annotated product tags and immutable Product Releases;
- PRODUCT documentation and cross-project normative authority contracts.

Deployment Controller (`iamaman11/mobile-proxy-production`) owns deployment ingress, target serialization/observation/adapters, durable mutation intent, exactly-once destructive dispatch, postconditions, recovery/quarantine and canonical runtime execution evidence.

PRODUCT must not perform production phone/VM mutation or become the deployment transaction ledger. Controller must not independently build/sign/tag/publish the product.

Both repositories are public. Secrets, target bindings, raw target identifiers, credentials, private keys, sensitive rendered config and unsafe raw runtime/ADB output remain private.

Normative cross-plane contracts:

- `docs/operations/project-authority.md`
- `contracts/operations/project-authority-v2.json`
- `contracts/operations/github-control-plane-v2.json`
- `contracts/operations/production-topology-v2.json`
- `contracts/operations/product-release-authority-v2.json`

Older v1 cross-repository authority/topology/control-plane material is historical when it conflicts with v2.

## PRODUCT-local engineering discipline

- Work on a topic/stage branch; do not deploy an uncommitted tree.
- Finished meaningful code/docs + direct tests -> commit; significant non-code stage evidence -> current Stage Issue.
- PRODUCT workflows do not access production targets.
- Product Release identity is immutable and exact; source workspace version, `latest`, mutable branches and GitHub Deployment projection are not runtime deployment identity.
- Architecture improvement is stage-mapped; no parallel architecture roadmap.
- Prefer deletion/consolidation, small explicit contracts/functions and demonstrated need over speculative framework code.
- VM/provider mutation remains fail-closed until Stage 6 is opened by #179.

## Verification

For docs/policy-sized changes:

    scripts/quality-gate.sh fast

For code/release/tooling changes:

    scripts/quality-gate.sh

GitHub's required aggregate check is `Quality Gate`.

For stage completion, checkpoint cadence, phone/local-agent behavior, capability-gap classification and evidence routing, follow `STAGE_WORKFLOW.md` rather than duplicating those rules here.
