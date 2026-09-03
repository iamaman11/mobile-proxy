# Agent operating contract

Start every repository task with:

    python3 scripts/repository_context.py
    git status --short --branch

The generated context is the bounded source for the current SHA, workspace layout, production data path, quality check and delivery workflows. Read deeper documents only when the task touches them.

## Canonical project authority

`iamaman11/mobile-proxy` is the only canonical repository for project information. The private
`iamaman11/mobile-proxy-production` repository is an execution satellite only; it is not a second
project and must not define independent architecture, roadmap, desired state, release policy,
acceptance policy or product behavior.

If chat history, local notes, provider state, a satellite repository or remembered intent conflicts
with this repository, fail closed and reconcile the canonical repository first through the normal
protected-`main` process. See `docs/operations/project-authority.md` and
`contracts/operations/project-authority-v1.json`.

## Sources of truth

All normative sources below live in the canonical repository:

- Product and operator behavior: README.md
- **Single current implementation roadmap:** IMPLEMENTATION_PLAN.md -> docs/PRODUCTION_BASELINE_PLAN.md
- Runtime topology: RUNTIME_LAYOUT.md
- Architecture quality standard: docs/architecture/ARCHITECTURE_STANDARD.md
- Physical-device transaction semantics: docs/operation-state-machine-v1.md
- Causal device-fact validity and Git authority: docs/architecture/ADR-003-causal-device-fact-validity-and-git-authority.md
- Exact Rust workspace module graph: contracts/governance/module-boundaries-v1.json
- Authoritative mutable-state ownership: contracts/governance/state-ownership-v1.json
- Git delivery and release policy: docs/GIT_DELIVERY.md
- Project authority and cross-repository boundary: docs/operations/project-authority.md
- GitHub bootstrap and control-plane split: docs/operations/github-bootstrap.md
- Project authority contract: contracts/operations/project-authority-v1.json
- GitHub desired-state contract: contracts/operations/github-control-plane-v1.json
- Production topology contract: contracts/operations/production-topology-v1.json
- Enforced architecture rules: contracts/governance/invariant-enforcement.json
- Current code and tests, not historical plans

Documents under docs/history describe completed investigations or superseded plans. They are evidence, not an active backlog.

There is no second development roadmap. Issue #179 is a live execution cursor inside the one canonical roadmap; it is not an alternative architecture plan.

## Current foundational gate

Before further application feature growth, VM generalization, orchestration expansion or new governance machinery, complete and accept the physical-device control State Machine defined by the canonical roadmap and `docs/operation-state-machine-v1.md`.

Until that gate is accepted, normal work is sequential:

1. formalize one deterministic device-control model, including causal fact validity and its invariants;
2. prove observation and operation-specific guards on the real registered phone;
3. prove bounded mutation plus independent postcondition verification;
4. prove explicit ambiguous-outcome handling after runner/controller loss;
5. prove recovery/quarantine at every destructive boundary;
6. prove controller restart and device reboot re-observation/rehydration;
7. prove reproducible clean project-owned device state from an allowed baseline;
8. only then resume feature growth and later generalize proven primitives to VM/provider targets.

A blocked foundational property is not permission to start another architecture lane. Make only the smallest change necessary to prove the next unproven property.

## Evidence validity and Git changes

Git/GitHub is the authority for source, reviewed contracts, Quality, artifacts and execution admission. It is **not** a global clock for the physical phone.

Keep three roles separate:

```text
Git/source authority
observed physical facts
one-operation transaction evidence
```

Rules:

- do not mark all phone facts stale merely because canonical `main` advanced;
- a Git SHA recorded on an observation is provenance unless `source/...` is explicitly one of that fact's validity dependencies;
- a physical fact is reusable only while every declared causal dependency still matches current context;
- use narrow dependencies such as target binding, semantic observer version, affected physical domain generation, boot/session identity, source identity, artifact identity or exact transaction identity;
- an unrelated docs/source change must not invalidate filesystem/package/runtime facts that do not depend on source identity;
- a source-bound guard or artifact-relative claim must still re-prove the exact current source/artifact authority required by its operation contract;
- when observer semantics change incompatibly or a defect invalidates old interpretations, change the observer contract identity and thereby stale only facts that depend on it;
- once a destructive command may have reached the target, advance the affected domain generation before any pre-mutation fact in that domain can be reused, even when the command result is lost;
- do not use one global `DeviceEpoch`; invalidate only affected domains/coupled scopes;
- ephemeral reachability/process/connectivity facts must use session/boot/transaction dependencies or another explicit freshness contract rather than being treated as indefinitely durable;
- every destructive transaction still requires the fresh same-transaction target/access boundary proof declared by its operation contract;
- never re-observe a phone fact *just because a Git SHA changed*; re-observe because a causal dependency is stale/unknown or the exact operation requires fresh boundary evidence.

`control_state_machine.py` owns admission/reuse of observed facts. `operation_state_machine.py` owns the strict ordered trace of one transaction. Workflows, Issue #179 and private CONTROL must not invent an alternate freshness rule.

See ADR-003 for the complete decision.

## Change discipline

- Work on a topic branch; do not deploy an uncommitted tree.
- Keep Cargo.lock and the pinned Rust toolchain synchronized.
- Every Rust workspace member and internal dependency edge must match `contracts/governance/module-boundaries-v1.json`; do not add a crate or dependency edge without classifying it in the same change.
- New authoritative or operational mutable state must identify one owning module and be registered in `contracts/governance/state-ownership-v1.json` in the same change; policy/type modules do not become implicit co-owners.
- Architecture-significant changes must justify complexity, identify ownership and rollback/deletion path, and add/update an ADR when they establish or materially change a long-lived architectural decision.
- Do not create abstractions, services, runtime components or generic extension mechanisms for hypothetical future use; prefer the smallest design that satisfies the current accepted requirement.
- **Do not add code for code.** New framework/orchestration/policy/test machinery must close a concrete currently demonstrated uncertainty and be simpler than the problem it solves.
- **Do not verify verification.** Do not add a checker merely to confirm another checker/test exists or ran, and do not add tests whose primary subject is the presence/invocation of other tests. A separate check is justified only for a separate invariant or trust boundary.
- Prefer deletion, simplification and reuse before adding a new module, abstraction, workflow or contract.
- Keep normal control flow understandable by one developer as `state -> guard -> operation -> effect -> independent observation -> resulting state`.
- Do not commit target directories, APK/build outputs, runtime binaries, credentials, generated GitHub credentials or raw acceptance logs.
- Secret values never belong in Git. `production-vultr` GitHub Environment secrets are the standard Vultr runtime source; local Secret Vault is bootstrap/recovery only and must not be reintroduced into the normal production path.
- The public repository has no self-hosted runner. Phone execution belongs only to the private
  `iamaman11/mobile-proxy-production` satellite; canonical phone workflow logic must remain here and
  be invoked from the private boundary through an immutable release/ref mechanism.
- Future Vultr lifecycle work belongs on a GitHub-hosted job in tag-only `production-vultr`.
- Production deployment is currently blocked fail-closed until the split workflows and typed
  Vultr adapter are implemented. Do not revive a workstation/ADB/GCP deployment shortcut.
- Manual SSH, raw ADB and provider CLI are not the standard production control plane.
- Keep production ports and client protocols compatible unless the user explicitly authorizes a breaking change.
- A production deployment is identified by an annotated semantic-version tag, immutable commit SHA, verified artifact/provenance and the deployment ID rule in the project-authority contract.

## Protect boundaries, not bootstrap state

During the physical-device-control foundation stage, the currently installed APK, runtime generation, project-owned files and project-owned configuration on the phone are disposable bootstrap state. They are not an asset that must be preserved at the cost of reproducibility.

Accordingly:

- do not build architecture around preserving the current installation in place;
- an authorized bounded wipe/reinstall/re-materialization of project-owned state is acceptable when followed by independent device verification;
- prefer revocable/test credentials for foundation experiments where practical;
- do not build complex secret-continuity or migration machinery solely to preserve incidental current phone state before reproducible control exists;
- no correctness assumption may depend on a credential, package or project-owned file surviving on the current phone.

This does not authorize secret leakage or uncontrolled mutation. Real credentials remain confidential; they must not be logged or committed. Provider/account actions remain separately authorized and bounded. Non-project-owned phone state is outside the mutation boundary.

## Proportional verification

For docs and policy-only work:

    scripts/quality-gate.sh fast

For code or release changes:

    scripts/quality-gate.sh

GitHub has one aggregate required check named Quality Gate. Markdown-only changes run the
policy gate; every other path runs policy, Rust, supply-chain and Android jobs. Read the small
quality-summary artifact before inspecting individual logs. Open detailed logs only for failed
checks.

Verification must be proportional and behavior-oriented. Prefer one strong transition/fault test per independent invariant over layers of tests that merely re-assert wiring or the existence of other checks.

Live phone or VM mutation is allowed only when the task calls for deployment or live acceptance and
the canonical GitOps path for that target is implemented. Record the tag, SHA, release/deployment
ID and bounded pass/fail evidence; do not commit credentials or large logs.
