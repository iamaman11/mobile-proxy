# Agent operating contract

Start every repository task with:

    python3 scripts/repository_context.py
    git status --short --branch

The generated context is a bounded source for the current PRODUCT revision, workspace layout, Quality and release workflows. Read deeper documents only when the task touches them.

## Authority model

The project has one product and two authoritative planes. **Both repositories are public; authority and confidentiality are not inferred from repository visibility.**

- `iamaman11/mobile-proxy` = **PRODUCT authority**: application/runtime source, shared product/domain architecture, public Quality, product build/signing verification, annotated product tags, immutable Product Releases and product documentation.
- `iamaman11/mobile-proxy-production` = **DEPLOYMENT CONTROLLER authority**: Issue #1 deployment ingress, deployment State Machine / Transaction Kernel, target admission and serialization, target observation/adapters, durable mutation intent, exactly-once destructive dispatch, postconditions, recovery/quarantine and canonical runtime execution evidence.

Neither repository may silently take over the other's responsibility. The controller repository is not a second product source and must not independently build, sign, tag or publish the product. The PRODUCT repository must not own the runtime deployment transaction ledger, production target mutation authority or exactly-once destructive dispatch.

Controller source/policy may be public, but repository/environment secret values, target bindings, raw device identifiers, credentials, private keys, sensitive rendered config and unsafe raw runtime/ADB logs remain private and must never be committed or emitted unredacted.

Use these normative v2 contracts first:

- `docs/operations/project-authority.md`
- `contracts/operations/project-authority-v2.json`
- `contracts/operations/github-control-plane-v2.json`
- `contracts/operations/production-topology-v2.json`
- `contracts/operations/product-release-authority-v2.json`

Older v1 authority/topology/control-plane contracts and Item 19/Item 20 material are historical/development evidence when they conflict with v2.

## Current control surfaces

Keep product-development authority separate from runtime execution authority:

- public Issue #179 = the single current engineering/migration/execution cursor; always obey its newest authoritative checkpoint;
- public Issue #228 = 10/10 PRODUCT hardening backlog only; it never overrides #179 or grants runtime execution authority;
- public Issue #90 = product tag/release command surface where the accepted release contract requires it;
- `iamaman11/mobile-proxy-production` Issue #1 = Deployment Controller command surface and durable runtime ledger surface.

Always reread the newest authoritative #179 checkpoint before changing repository or production state. A stale Issue #179 body, #228 item or older comment does not override a newer checkpoint.

A `/deploy` command, phone/ADB action, provider/VM mutation, signing operation, tag or Product Release action is allowed only when the newest #179 checkpoint and the owning v2 authority plane explicitly permit it.

## Sources of truth

PRODUCT sources include:

- product/operator behavior: `README.md`;
- current development roadmap: `docs/PRODUCTION_BASELINE_PLAN.md` with `IMPLEMENTATION_PLAN.md` as the concise entry point;
- normative acceptance matrix: `TEN_OUT_OF_TEN_VALIDATION_PLAN.md`;
- runtime topology: `RUNTIME_LAYOUT.md`;
- architecture quality standard: `docs/architecture/ARCHITECTURE_STANDARD.md`;
- exact Rust workspace module graph: `contracts/governance/module-boundaries-v1.json`;
- authoritative product mutable-state ownership: `contracts/governance/state-ownership-v1.json`;
- Git delivery/product release policy: `docs/GIT_DELIVERY.md`;
- PRODUCT / Deployment Controller boundary: `docs/operations/project-authority.md` and the v2 contracts above;
- current code and tests, not superseded plans.

Deployment Controller runtime truth includes the exact controller revision, target bindings, durable mutation intent, terminal evidence and recovery/quarantine classification. Sensitive values supporting that truth remain private even though the repository itself is public.

Documents under `docs/history` and superseded v1 physical-control documents are evidence, not normal runtime authority.

## Deployment-controller invariants

The PRODUCT repository may document shared product/domain semantics, but active production target execution belongs to the Deployment Controller.

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

The old public physical controller implementation (`transaction_runner.py`, public physical state machines, operation executors, phone certification/acceptance scripts and their controller-specific tests) is historical Git evidence after the Gate B source-ownership migration. Do not recreate or maintain a second active public controller in the PRODUCT repository.

## PRODUCT hardening discipline

The target is a small, understandable industrial system, not a larger framework.

- Do not add code for code's sake. New machinery must close a concrete demonstrated defect, ambiguity or trust boundary.
- Do not verify verification. Tests protect behavior/invariants, not the existence or invocation of other tests/checkers.
- Prefer deletion, consolidation and reuse before adding a module, workflow, registry, abstraction or contract.
- One state/decision has one authoritative owner.
- Keep normal flow understandable as `state -> guard -> operation -> effect -> independent observation -> resulting state`.
- Do not build compatibility machinery merely to preserve disposable bootstrap phone state unless production policy actually requires continuity.
- Product security, behavior tests, release provenance and release gates belong to the PRODUCT plane.
- Deployment exactly-once, target observation/mutation and recovery belong to the Deployment Controller plane.

## Durable hardening path

The project progresses through these acceptance gates; Issue #179 determines which one is currently executable:

```text
A  Deployment Controller health
B  source ownership / authority convergence
C  Android secret-state and backup/D2D hardening
D  Android behavior and framework integration tests
E  supply-chain provenance + Product Release prerequisite hardening
F  new immutable Product Release
G  exactly one admitted deployment of that release
H  real-world phone + reverse-tunnel + provider + external-client acceptance
```

Historical phone experiments prove pieces of the path but never substitute for Gate H against the final immutable Product Release.

## Evidence validity

Git/GitHub is authority for reviewed PRODUCT source, product contracts, Quality, release identity and immutable Product Release evidence. It is not a global clock for physical targets.

Physical facts may be reused only according to the Deployment Controller's admitted observer/target/domain/session/artifact dependencies. A PRODUCT Git SHA is provenance unless the relevant controller contract explicitly makes it a validity dependency.

Do not infer physical current state from chat history, Issue prose, workflow success or public Deployment projection.

## Change discipline

- Work on a topic branch; do not deploy an uncommitted tree.
- Keep `Cargo.lock` and the pinned Rust toolchain synchronized.
- Every Rust workspace member and internal dependency edge must match `contracts/governance/module-boundaries-v1.json`.
- New PRODUCT authoritative/operational mutable product state must identify one owner and be registered in `contracts/governance/state-ownership-v1.json` when that registry applies.
- Architecture-significant changes must justify complexity, identify ownership and rollback/deletion path, and add/update an ADR only when they establish a long-lived decision.
- Do not create generic extension mechanisms for hypothetical future targets.
- Do not commit target directories, APK/build outputs, runtime binaries, credentials, generated GitHub credentials or raw acceptance logs.
- Secret values never belong in Git.
- The PRODUCT repository has no production self-hosted runner and must not perform deployment ADB/phone mutation.
- Phone execution belongs to the Deployment Controller on the registered `android-production` self-hosted runner with private target binding.
- VM/provider deployment remains fail-closed until its controller adapter is proven end-to-end.
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
