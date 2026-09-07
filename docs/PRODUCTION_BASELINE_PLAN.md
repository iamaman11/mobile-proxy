# Production Baseline Architecture and Invariants

Status: **active static architecture/invariant baseline; not an execution roadmap**  
PRODUCT repository: `iamaman11/mobile-proxy`  
Deployment Controller repository: `iamaman11/mobile-proxy-production`  
Dynamic stage/operations authority: newest authoritative checkpoint in PRODUCT Issue #179  
Static stage sequence: `docs/PRODUCTION_STAGE_ROADMAP.md`  
Planning/acceptance backlog: PRODUCT Issue #249

This document defines durable production architecture and acceptance invariants. It intentionally contains no dynamic `CURRENT` stage, current SHA, current Product Release, next action or checkpoint cadence. Historical A-H implementation ordering is superseded by the seven-stage roadmap and is not an alternate execution plan.

## 1. Goal

Reach a simple, understandable industrial Mobile Proxy baseline with:

- secure, behavior-tested PRODUCT code;
- deterministic Quality and immutable Product Release evidence;
- one Deployment Controller owning deployment execution;
- exactly-once destructive target semantics;
- independent target postcondition observation;
- deterministic recovery/quarantine after ambiguous execution;
- auditable dependency provenance;
- separately authorized real-target operational evidence;
- no unresolved P0/P1 defect contradicting acceptance.

No code for code. No verification of verification. Prefer deletion/consolidation over new framework layers.

## 2. Authority model

| Plane | Repository | Authority |
| --- | --- | --- |
| PRODUCT | `iamaman11/mobile-proxy` | application/runtime source, shared product/domain architecture, Quality, product build, Android signing verification, annotated tags, immutable Product Releases |
| DEPLOYMENT CONTROLLER | `iamaman11/mobile-proxy-production` | deployment ingress, State Machine / Transaction Kernel, target admission/serialization/observation/adapters, durable mutation intent, exactly-once destructive dispatch, postconditions, recovery/quarantine, canonical runtime execution classification |

Both repositories are public. Secrets, private keys, target bindings, raw target identifiers, credentials, sensitive rendered configuration and unsafe raw production logs remain private. Repository visibility is never an authority or confidentiality mechanism.

Normative cross-plane contracts:

- `docs/operations/project-authority.md`
- `contracts/operations/project-authority-v2.json`
- `contracts/operations/github-control-plane-v2.json`
- `contracts/operations/production-topology-v2.json`
- `contracts/operations/product-release-authority-v2.json`

The old “thin execution satellite / PRODUCT-owned physical controller” model is superseded.

## 3. Product invariants

### Compatibility

- mixed SOCKS5/HTTP compatibility remains on port `1080`;
- SOCKS5 remains on `1081`;
- HTTP including CONNECT remains on `3128`;
- QUIC remains primary reverse-tunnel transport;
- certificate-pinned TLS/TCP reserve remains available;
- plaintext downgrade is forbidden;
- WireGuard remains an explicit compatibility/rollback path until an accepted deprecation;
- operator/admin compatibility changes only through reviewed versioned migration.

### Architecture and state ownership

Inside PRODUCT, dependency direction remains foundation/domain -> application -> infrastructure/adapters -> composition/delivery. Pure/domain modules do not own transport, persistence, Android, filesystem, process, environment or provider responsibilities.

Every authoritative mutable state/decision has one owner. Deployment admission, target mutation, durable mutation intent, exactly-once dispatch and recovery are Controller responsibilities, not PRODUCT mutable-state ownership.

### Durable PRODUCT state

Where PRODUCT state is durable, persistence remains deterministic and fail-closed. SQLite retains WAL, foreign keys, bounded busy timeout, single-writer/short-transaction discipline, integrity checks, backup and clean restore behavior. Legacy stores are bounded migration/compatibility surfaces, not alternate authority.

### Security and bounded operation

Typed identifiers/status/error/protocol/tunnel/strategy contracts and typed content/fingerprint digest policy remain in force. Secret values do not enter public Git/evidence. PRODUCT Actions remain least-privilege and free of production target mutation.

Requests, idempotency, queues/retries, liveness/readiness, authentication and fail-closed proxy/session behavior remain governed by their PRODUCT contracts/tests.

## 4. Product Release precedes deployment

```text
protected PRODUCT source + required Quality
  -> Product Release prerequisite proof
  -> annotated product tag
  -> signed PRODUCT build
  -> immutable Product Release
  -> /deploy <target> <tag>
  -> Controller admission / observation / possible mutation / verification / recovery
```

A Product Release is an input to deployment. Physical phone acceptance is not a prerequisite for Product Release creation. Runtime deployment identity combines the exact immutable Product Release and exact admitted Controller revision.

`latest`, mutable branches, approximate versions and public GitHub Deployment projection are forbidden deployment identity.

## 5. Deployment execution invariants

```text
semantic request
  -> admission
  -> target-global serialization
  -> target observation
  -> durable mutation intent
  -> at most one destructive dispatch for that intent
  -> independent postcondition observation
  -> canonical terminal classification
```

Required:

1. durable mutation intent exists before destructive dispatch;
2. one intent admits at most one destructive target dispatch;
3. GitHub comment/run/attempt provenance does not redefine semantic request identity;
4. ambiguous post-dispatch outcome never causes blind destructive retry;
5. `UNKNOWN` continuation is read-only observation/reconciliation;
6. evidence-write retry never repeats a physical effect;
7. public GitHub Deployment is bounded projection only;
8. target-global serialization is Controller authority;
9. workflow success is not an independent target postcondition;
10. a Controller-only repair does not force a new Product Release when product bytes/semantics are unchanged.

PRODUCT must not reintroduce a second deployment State Machine or mutation ledger.

### 5.1 One exact phone Release state semantics

For the production phone, operations that need the same Release-bound target truth must not independently reimplement desired-state interpretation.

The stable conceptual path is:

```text
exact immutable Product Release
  -> prepare/verify expected phone Release state
  -> observe exact APK + rooted runtime state
  -> bounded exact / degraded / unknown classification
  -> operation-specific decision
```

Normal observation, deployment pre/postcondition and target-read-only reconciliation may have different orchestration and evidence envelopes, but the underlying exact phone Release state semantics have one Controller owner. Workflow-specific scripts must not become independent state machines by defining conflicting drift/current/desired truth.

This is a concrete phone boundary. Do not generalize it into a speculative multi-target framework before a second real target demonstrates the shared responsibility.

### 5.2 Target-read-only reconciliation versus mutation identity

A target-read-only reconciliation operation is not a second deployment attempt.

When current target state is independently proven exact, reconciliation may update an already-admitted visibility projection under a separate semantic identity, subject to all of the following:

- no durable mutation intent is created;
- no APK/runtime/package/filesystem destructive dispatch occurs;
- historical Controller terminals remain immutable historical transaction truth;
- reconciliation never retroactively converts an earlier `REFUSED`, `UNKNOWN`, `RECOVERED` or other terminal into a different canonical terminal;
- GitHub Deployment projection remains visibility only and cannot authorize a target effect;
- missing or ambiguous projection identity fails closed rather than creating deployment history from observation alone;
- repeating the same reconciliation when projection is already correct is a no-op at the projection layer.

A projection write is a Controller control-plane side effect, not a phone mutation. Its permission/serialization/evidence contract must reflect that distinction rather than incorrectly treating projection truth as target truth.

## 6. Physical facts and observation capability

Git/GitHub is authoritative for reviewed source, contracts, Quality, release identity and durable transaction evidence. It is not a global clock for physical target state.

Physical facts must be observed under their declared target/domain/session/artifact dependencies. Do not infer them from chat history, workflow color, elapsed time or expected architecture.

Prefer Controller observer/target-adapter evidence. If a required phone fact cannot be obtained reliably, narrow local-agent assistance is allowed by `STAGE_WORKFLOW.md` and the current #179 checkpoint. Every returned fact is classified as:

- `controller_capability_gap`;
- `human_only_physical_observation`;
- `one_off_observation`.

A repeatable/decision-critical `controller_capability_gap` should be closed with the smallest Controller observation capability when it blocks the current stage and doing so is simpler/safer than recurring manual dependence. This is architecture feedback, not automatic permission to add framework machinery.

## 7. Architecture complexity discipline

`docs/architecture/ARCHITECTURE_STANDARD.md` is the permanent quality floor.

- one owner per state/decision;
- one layer only for an independent responsibility/lifecycle/failure mode;
- prefer deletion, reuse and concrete implementations;
- generic abstractions require demonstrated present-day need;
- tests protect real behavior/failure/security/authority boundaries;
- no checker solely to prove another checker exists;
- no generic multi-target orchestration platform;
- physical operations must expose observable boundaries rather than hide unrelated effects behind one opaque success/timeout result.

Architecture work is stage-mapped, not a parallel roadmap. Stage 4 may introduce only the smallest concrete phone capability required to remove a demonstrated validation/reconciliation ambiguity. Stage 5 is the dedicated phone simplification/convergence stage and should primarily consolidate/delete the temporary surfaces exposed by Stage 4. Stage 6 is the first normal point for extracting shared phone/VM target abstractions from two real implementations.

## 8. Historical evidence boundary

Historical Item19/Item20, Item15-23 and A-H execution plans remain immutable audit evidence where useful. They do not restore old release ordering, same-repository controller ownership, old execution-satellite semantics or old current-stage authority.

Old failed workflow runs are never rerun merely to obtain a second physical effect. Re-entry follows current Controller durable state and read-only reconciliation rules.

## 9. PRODUCT acceptance

PRODUCT acceptance requires, as applicable to the current Product Release contract:

- coherent v2 authority docs/contracts and no active duplicate deployment owner;
- retained compatibility/architecture/persistence/security invariants;
- required Android security/behavior coverage;
- exact required Quality success;
- deterministic build/signing verification;
- release prerequisite/tag gates bound to exact source;
- immutable Product Release with complete provenance/digests;
- no unresolved PRODUCT P0/P1.

Quality proves PRODUCT software/policy; it does not manufacture target state.

## 10. Deployment Controller acceptance

Controller acceptance requires exact Product Release admission, exact Controller-revision binding, semantic dedup independent of GitHub provenance, target-global serialization, one authoritative target-state interpretation per concrete target, observation before decision, durable intent before dispatch, exactly-once destructive dispatch per intent, independent postcondition observation, canonical terminal evidence, target-read-only reconciliation that cannot mutate or rewrite historical transaction truth, and deterministic recovery/quarantine.

`vm-production` remains fail-closed until Stage 6 explicitly opens and proves its real target adapter/lifecycle end-to-end.

## 11. Full production acceptance

Full production acceptance requires all of:

1. PRODUCT acceptance complete for the exact immutable Release(s) in use.
2. Controller invariants proven for each real target.
3. Phone and VM each have direct local evidence appropriate to their stages.
4. The combined topology passes Stage 7 end-to-end functional, recovery, bounded-load and soak acceptance.
5. No unresolved P0/P1 contradicts final acceptance.

Do not collapse these evidence domains into one green workflow.

## 12. Change discipline

For docs/policy-sized changes use `scripts/quality-gate.sh fast`; for code/release/tooling changes use `scripts/quality-gate.sh`.

The active execution sequence is governed only by `STAGE_WORKFLOW.md` + newest PRODUCT #179 checkpoint + current Stage Issue. Do not create a #179 checkpoint for ordinary commits, PR/CI repair, deterministic in-stage repair, read-only observations, local-agent evidence, protected merge or post-merge checks. At stage exit, close the Stage Issue and publish one #179 checkpoint opening the next stage.
