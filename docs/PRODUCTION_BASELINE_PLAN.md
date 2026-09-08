# Production Baseline Architecture and Invariants

Status: **active static architecture/invariant baseline; not an execution roadmap**  
PRODUCT repository: `iamaman11/mobile-proxy`  
Deployment Controller repository: `iamaman11/mobile-proxy-production`  
Dynamic stage/operations authority: newest authoritative checkpoint in PRODUCT Issue #179  
Canonical Stage 1-7 plan: `docs/PRODUCTION_STAGE_ROADMAP.md`  
Planning/acceptance backlog: PRODUCT Issue #249

This document defines durable production architecture and acceptance invariants. It intentionally contains no dynamic `CURRENT` stage, current SHA, current Product Release, next action or checkpoint cadence. It also does not duplicate the stage plan.

## 1. Goal

Reach a simple, understandable industrial Mobile Proxy baseline with:

- secure, behavior-tested PRODUCT code;
- deterministic Quality and immutable Product Release evidence;
- one Deployment Controller owning deployment execution;
- exactly-once destructive target semantics;
- independent target postcondition observation;
- deterministic recovery/quarantine after ambiguous execution;
- auditable dependency provenance;
- separately authorized target-local and full-topology operational evidence;
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

The old thin execution-satellite / PRODUCT-owned physical controller model is superseded.

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

A Product Release is an input to deployment. Physical target acceptance is not a prerequisite for Product Release creation. Runtime deployment identity combines the exact immutable Product Release and exact admitted Controller revision.

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

## 6. Evidence-domain separation

The production system has distinct evidence domains. They may share low-level adapters, but one result must not silently become another domain's truth.

### 6.1 Transport readiness

Runner/host/USB/ADB/root readiness proves only that the Controller can reach the registered target through the admitted transport. Transport degradation must not be reported as Release mismatch or PRODUCT runtime drift.

### 6.2 Exact Release state

Exact target-state observation proves only the immutable Product Release state required by the target contract: for the phone this includes the admitted APK/rooted-runtime/current truth. It is the shared concrete truth where deployment postcondition, normal Release observation and target-read-only reconciliation genuinely require the same facts.

### 6.3 Live operational state

Live runtime health is a separate concern from immutable Release state. Process presence, authenticated local health/readiness, serving prerequisites, cellular availability and bounded resource indicators may be `READY`, `DEGRADED` or `UNKNOWN` while exact Release state remains independently true.

Operational observation must not duplicate PRODUCT-owned health computation when a PRODUCT health contract already exists. It observes that contract and bounded target facts.

### 6.4 Lifecycle exercise state

A controlled process termination, runtime restart, phone reboot, VM restart or mismatch drill is an admitted perturbation with its own scenario identity, timeout, postcondition and recovery classification. It is not a free-form shell surface and is not ordinary observation.

### 6.5 Full-topology state

Phone-local or VM-local acceptance does not constitute full Mobile Proxy acceptance. Full production behavior exists only on the real path:

```text
external consumer
  -> VM / relay / serving edge
  -> authenticated reverse tunnel
  -> registered phone runtime
  -> mobile/cellular egress
  -> Internet
```

External proxy compatibility, real mobile-egress identity, production QUIC/reserve behavior, DNS/IPv6/leak policy, cross-target recovery, production-scale load and long soak are full-topology evidence and are accepted only at the stage that owns the complete real path.

## 7. Physical facts and observation capability

Git/GitHub is authoritative for reviewed source, contracts, Quality, release identity and durable transaction evidence. It is not a global clock for physical target state.

Physical facts must be observed under their declared target/domain/session/artifact dependencies. Do not infer them from chat history, workflow color, elapsed time or expected architecture.

Prefer Controller observer/target-adapter evidence. If a required phone fact cannot be obtained reliably, narrow local-agent assistance is allowed by `STAGE_WORKFLOW.md` and the current #179 checkpoint. Every returned fact is classified as:

- `controller_capability_gap`;
- `human_only_physical_observation`;
- `one_off_observation`.

A repeatable/decision-critical `controller_capability_gap` should be closed with the smallest Controller observation capability when it blocks the current stage and doing so is simpler/safer than recurring manual dependence. This is architecture feedback, not automatic framework permission.

## 8. Architecture complexity discipline

`docs/architecture/ARCHITECTURE_STANDARD.md` is the permanent quality floor.

- one owner per state/decision;
- one layer only for an independent responsibility/lifecycle/failure mode;
- prefer deletion, reuse and concrete implementations;
- generic abstractions require demonstrated present-day need;
- tests protect real behavior/failure/security/authority boundaries;
- no checker solely to prove another checker exists;
- no generic multi-target orchestration platform;
- physical operations expose observable boundaries rather than hiding unrelated effects behind one opaque success/timeout result.

Architecture work is stage-mapped, not a parallel roadmap. Stage 5 owns phone-baseline simplification/convergence. Stage 6 is the first normal point for extracting shared phone/VM target abstractions from two real implementations.

## 9. Historical evidence boundary

Historical Item19/Item20, Item15-23 and A-H execution plans remain audit evidence where useful. They do not restore old release ordering, same-repository controller ownership, old execution-satellite semantics or old current-stage authority.

Old failed workflow runs are never rerun merely to obtain a second physical effect. Re-entry follows current Controller durable state and read-only reconciliation rules.

## 10. PRODUCT acceptance

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

## 11. Deployment Controller acceptance

Controller acceptance requires exact Product Release admission, exact Controller-revision binding, semantic dedup independent of GitHub provenance, target-global serialization, observation before decision, durable intent before dispatch, exactly-once destructive dispatch per intent, independent postcondition observation, canonical terminal evidence, read-only UNKNOWN reconciliation and deterministic recovery/quarantine.

`vm-production` remains fail-closed until Stage 6 explicitly opens and proves its real target adapter/lifecycle end-to-end.

## 12. Full production acceptance

Full production acceptance requires all of:

1. PRODUCT acceptance complete for the exact immutable Release(s) in use.
2. Controller invariants proven for each real target.
3. Phone and VM each have direct target-local evidence appropriate to their stages.
4. The combined topology passes Stage 7 end-to-end functional, network, recovery, real-load and soak acceptance.
5. No unresolved P0/P1 contradicts final acceptance.

Do not collapse these evidence domains into one green workflow.

## 13. Change discipline

For docs/policy-sized changes use `scripts/quality-gate.sh fast`; for code/release/tooling changes use `scripts/quality-gate.sh`.

The active execution sequence is governed only by `STAGE_WORKFLOW.md` + newest PRODUCT #179 checkpoint + current Stage Issue. The complete static Stage 1-7 plan is owned only by `docs/PRODUCTION_STAGE_ROADMAP.md`.

Do not create a #179 checkpoint for ordinary commits, PR/CI repair, deterministic in-stage repair, read-only observations, local-agent evidence, protected merge or post-merge checks. At a genuine stage/authority/plan boundary, update the owning protected docs first, then publish one compact #179 checkpoint that points to them rather than restating them.
