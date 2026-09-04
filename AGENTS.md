# Agent operating contract

Start every repository task with:

    python3 scripts/repository_context.py
    git status --short --branch

The generated context is a bounded source for the current public PRODUCT revision, workspace layout, Quality and release workflows. Read deeper documents only when the task touches them.

## Authority model

The project has one product and two authoritative planes:

- `iamaman11/mobile-proxy` = **PRODUCT authority**: application/runtime source, shared product/domain architecture, public Quality, product build/signing verification, annotated product tags, immutable Product Releases and product documentation.
- `iamaman11/mobile-proxy-production` = **DEPLOYMENT CONTROLLER authority**: private Issue #1 deployment ingress, deployment State Machine / Transaction Kernel, target admission and serialization, target observation/adapters, durable mutation intent, exactly-once destructive dispatch, postconditions, recovery/quarantine, private bindings/secrets and canonical runtime execution evidence.

Neither repository may silently take over the other's responsibility. The private repository is not a second product source and must not independently build, sign, tag or publish the product. The public repository must not own the runtime deployment transaction ledger, production target mutation authority or exactly-once destructive dispatch.

Use these normative v2 contracts first:

- `docs/operations/project-authority.md`
- `contracts/operations/project-authority-v2.json`
- `contracts/operations/github-control-plane-v2.json`
- `contracts/operations/production-topology-v2.json`
- `contracts/operations/product-release-authority-v2.json`

Older v1 authority/topology/control-plane contracts and Item 19/Item 20 material are historical/development evidence when they conflict with v2.

## Current control surfaces

Keep product-development authority separate from runtime execution authority:

- public Issue #179 = migration/development audit tracker and the authority for the next bounded engineering item;
- public Issue #228 = 10/10 PRODUCT hardening backlog only; it never grants runtime execution authority;
- public Issue #90 = product tag/release command surface where the accepted release contract requires it;
- private Issue #1 = Deployment Controller command surface and canonical private runtime ledger.

Always reread the newest authoritative #179 checkpoint before changing repository or production state. A stale Issue #179 body or older comment does not override a newer checkpoint.

A `/deploy` command, phone/ADB action, provider/VM mutation, signing operation or release rewrite is allowed only when the newest #179 checkpoint and the owning v2 authority plane explicitly permit it.

## Sources of truth

Public PRODUCT sources include:

- product/operator behavior: `README.md`;
- current development roadmap: `docs/PRODUCTION_BASELINE_PLAN.md` with `IMPLEMENTATION_PLAN.md` as the concise entry point;
- runtime topology: `RUNTIME_LAYOUT.md`;
- architecture quality standard: `docs/architecture/ARCHITECTURE_STANDARD.md`;
- exact Rust workspace module graph: `contracts/governance/module-boundaries-v1.json`;
- authoritative product mutable-state ownership: `contracts/governance/state-ownership-v1.json`;
- Git delivery/product release policy: `docs/GIT_DELIVERY.md`;
- PRODUCT / Deployment Controller boundary: `docs/operations/project-authority.md` and the v2 contracts above;
- current code and tests, not superseded plans.

Private Deployment Controller runtime truth is intentionally private and includes its exact controller revision, target bindings, durable mutation intent, terminal evidence and recovery/quarantine classification.

Documents under `docs/history` and superseded v1 physical-control documents are evidence, not normal runtime authority.

## Deployment-controller invariants

The public repository may document shared product/domain semantics, but active production target execution belongs to the private Deployment Controller.

The controller must preserve this shape:

```text
exact immutable Product Release
  -> semantic deployment request
  -> admission
  -> target-global serialization
  -> observation
  -> durable mutation intent (before destructive dispatch)
  -> at most one destructive dispatch for that intent
  -> independent postcondition observation
  -> canonical terminal classification
```

If a destructive dispatch may have occurred but the result is ambiguous:

```text
UNKNOWN
  -> read-only observation/reconciliation
  -> RECOVERED | QUARANTINED | separately proven terminal
```

Rules:

- no blind destructive retry after the dispatch boundary;
- `RECOVERED != ACCEPTED`;
- public GitHub Deployment is a bounded projection, never the canonical runtime ledger;
- GitHub run/comment/attempt provenance must not redefine semantic request identity;
- evidence-write retry is not permission to repeat a physical effect;
- exact target serialization is controller-owned;
- a successful command or workflow is not an independent postcondition.

Existing public files such as `scripts/control_state_machine.py`, `scripts/operation_state_machine.py`, `scripts/transaction_runner.py`, `scripts/atomic_physical_contracts.py`, `scripts/physical_operation_plan.py`, `scripts/operations/*` and legacy phone/Item19/Item20 deployment workflows are **not** current production deployment authority merely because they remain in the tree. Their final PRODUCT/shared-domain vs deployment-only vs historical disposition is handled by the bounded source-ownership migration authorized through #179.

## PRODUCT hardening discipline

The target is a small, understandable industrial system, not a larger framework.

- Do not add code for code's sake. New machinery must close a concrete demonstrated defect, ambiguity or trust boundary.
- Do not verify verification. Tests protect behavior/invariants, not the existence or invocation of other tests/checkers.
- Prefer deletion, consolidation and reuse before adding a module, workflow, registry, abstraction or contract.
- One state/decision has one authoritative owner.
- Keep normal flow understandable as `state -> guard -> operation -> effect -> independent observation -> resulting state`.
- Do not build compatibility machinery merely to preserve disposable bootstrap phone state unless production policy actually requires continuity.
- Product security, behavior tests, release provenance and release gates belong to the public PRODUCT plane.
- Deployment exactly-once, target observation/mutation and recovery belong to the private Deployment Controller plane.

## Evidence validity

Git/GitHub is authority for reviewed public source, product contracts, Quality, release identity and immutable Product Release evidence. It is not a global clock for physical targets.

Physical facts may be reused only according to the private controller's admitted observer/target/domain/session/artifact dependencies. A public Git SHA is provenance unless the relevant controller contract explicitly makes it a validity dependency.

Do not infer physical current state from chat history, Issue prose, workflow success or public Deployment projection.

## Change discipline

- Work on a topic branch; do not deploy an uncommitted tree.
- Keep `Cargo.lock` and the pinned Rust toolchain synchronized.
- Every Rust workspace member and internal dependency edge must match `contracts/governance/module-boundaries-v1.json`.
- New public authoritative/operational mutable product state must identify one owner and be registered in `contracts/governance/state-ownership-v1.json` when that registry applies.
- Architecture-significant changes must justify complexity, identify ownership and rollback/deletion path, and add/update an ADR only when they establish a long-lived decision.
- Do not create generic extension mechanisms for hypothetical future targets.
- Do not commit target directories, APK/build outputs, runtime binaries, credentials, generated GitHub credentials or raw acceptance logs.
- Secret values never belong in Git.
- The public repository has no production self-hosted runner and must not perform deployment ADB/phone mutation.
- Phone execution belongs to the private Deployment Controller on the registered private `android-production` runner.
- VM/provider deployment remains fail-closed until its private controller adapter is proven end-to-end.
- Manual SSH, raw/manual ADB and workstation/provider CLI are not the standard production control plane.
- Production deployment consumes an exact immutable Product Release plus an exact admitted controller revision; `latest` and mutable branches are forbidden deployment identity.

## Protect boundaries, not bootstrap state

Project-owned bootstrap phone state is disposable unless a current production requirement explicitly makes continuity necessary. Do not build architecture around preserving an incidental installation.

This never weakens confidentiality or containment: credentials remain secret, non-project-owned phone state is outside the mutation boundary and provider/account actions remain separately authorized.

## Proportional verification

For docs and policy-only work:

    scripts/quality-gate.sh fast

For code or release changes:

    scripts/quality-gate.sh

GitHub has one aggregate required check named `Quality Gate`. Read the compact quality summary before opening large logs.

Verification must be behavior-oriented and proportional. Prefer a few strong transition/fault tests for independent invariants over layers of meta-checks.
