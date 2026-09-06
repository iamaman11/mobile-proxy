# Production Baseline Plan

Status: **active canonical implementation roadmap**  
PRODUCT repository: `iamaman11/mobile-proxy`  
Deployment Controller repository: `iamaman11/mobile-proxy-production`  
Acceptance backlog: public Issue #228  
Authoritative next-step cursor: newest authoritative checkpoint in public Issue #179

This file defines durable ordering and acceptance criteria. Issue #179 alone decides the exact current bounded action. Passing a roadmap stage never grants phone/ADB/provider/VM/tag/Release authority by itself.

## 1. Goal

Reach a simple, understandable industrial Mobile Proxy baseline with:

- secure, behavior-tested PRODUCT code;
- deterministic Quality and immutable Product Release evidence;
- one Deployment Controller owning deployment execution;
- exactly-once destructive target semantics;
- independent target postcondition observation;
- deterministic recovery/quarantine after ambiguous execution;
- auditable dependency provenance;
- separately authorized real-target acceptance and soak evidence;
- no unresolved P0/P1 defect.

No code for code. No verification of verification. Prefer deletion/consolidation over new framework layers.

## 2. Authority model

The accepted v2 split is normative:

| Plane | Repository | Authority |
| --- | --- | --- |
| PRODUCT | `iamaman11/mobile-proxy` | application/runtime source, shared product/domain architecture, Quality, product build, Android signing verification, annotated tags, immutable Product Releases |
| DEPLOYMENT CONTROLLER | `iamaman11/mobile-proxy-production` | deployment ingress, State Machine / Transaction Kernel, target admission/serialization/observation/adapters, durable mutation intent, exactly-once destructive dispatch, postconditions, recovery/quarantine, canonical runtime execution classification |

Both repositories are public. Secrets, private keys, target bindings, raw target identifiers, credentials, sensitive rendered configuration and unsafe raw production/ADB logs remain private. Repository visibility is never an authorization or confidentiality mechanism.

Normative contracts:

- `docs/operations/project-authority.md`
- `contracts/operations/project-authority-v2.json`
- `contracts/operations/github-control-plane-v2.json`
- `contracts/operations/production-topology-v2.json`
- `contracts/operations/product-release-authority-v2.json`

The old “thin execution satellite / public physical State Machine owner” model is superseded.

## 3. Retained PRODUCT invariants

Gate B changes deployment ownership, not product behavior.

### Compatibility

- mixed SOCKS5/HTTP compatibility remains on port `1080`;
- SOCKS5 remains on `1081`;
- HTTP including CONNECT remains on `3128`;
- QUIC remains primary reverse-tunnel transport;
- certificate-pinned TLS/TCP reserve remains available;
- plaintext downgrade is forbidden;
- WireGuard remains a controlled compatibility/rollback path until an explicit accepted deprecation;
- operator CLI/admin API compatibility changes only through reviewed versioned migration.

### Architecture and state ownership

Inside PRODUCT, dependency direction remains foundation/domain -> application -> infrastructure/adapters -> composition/delivery. Pure/domain modules do not own transport, persistence, Android, filesystem, process, environment or provider responsibilities.

Every registered PRODUCT mutable-state group has one authoritative owner. Deployment admission, target mutation, exactly-once dispatch and recovery are not PRODUCT mutable-state ownership; they belong to the Deployment Controller.

### Durable PRODUCT state

- canonical mutable PRODUCT control-plane state is durable rather than memory-only;
- SQLite retains WAL, foreign keys, bounded busy timeout, single-writer/short-transaction discipline, integrity checks, backup and clean restore behavior;
- related product-state transitions commit atomically where the persistence contract requires it;
- legacy JSON migration remains bounded compatibility, not an alternate canonical store.

### Security and bounded operation

Typed identifier/status/error/protocol/tunnel/strategy contracts and typed content/fingerprint digest policy remain in force. Secret values do not enter public Git/evidence. PRODUCT Actions remain least-privilege, fork-safe and free of production phone/ADB execution.

Requests, idempotency, queues/retries, liveness/readiness, authentication and fail-closed proxy/session behavior remain governed by their PRODUCT contracts/tests.

### Delivery integrity

PRODUCT delivery requires reviewed exact source, exact successful Quality where required, deterministic build/signing verification, typed digests/provenance and immutable Product Release evidence. `latest`, mutable branches or approximate artifact identity are forbidden production deployment identity.

## 4. Product Release precedes deployment

```text
protected PRODUCT main + exact successful Quality
  -> Product Release prerequisite proof
  -> annotated product tag
  -> signed PRODUCT build
  -> immutable Product Release v2
  -> /deploy <target> <tag>
  -> Deployment Controller admission / observation / possible mutation / verification / recovery
```

Physical phone acceptance is not a prerequisite for Product Release creation. Runtime identity combines the exact immutable Product Release and exact admitted controller revision.

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
5. UNKNOWN continuation is read-only observation/reconciliation;
6. `RECOVERED != ACCEPTED`;
7. evidence-write retry never repeats a physical effect;
8. public GitHub Deployment is bounded projection only;
9. target-global serialization is Deployment Controller authority;
10. workflow success is not an independent target postcondition.

PRODUCT work must not reintroduce a second runtime State Machine or mutation ledger.

## 6. Historical evidence boundary

Historical Item 19 candidate `d151dbdd156279e32a5361d304c90f996bd2d565` remains immutable provider-lifecycle evidence only. Historical Item 20/signing/reconstruction records remain audit history and do not restore old release ordering or runtime authority.

Old failed workflow runs are never rerun merely to obtain a second physical effect. Re-entry follows current controller durable state and read-only recovery rules.

## 7. Durable A-H implementation order

### Gate A — Deployment Controller health

Required current-controller policies execute on real hosted runners and finish terminal green.

### Gate B — source ownership / authority convergence

Remove duplicate active deployment-controller/physical-operation implementation from PRODUCT. Keep genuine PRODUCT/shared-domain/build/release code. Deployment Controller remains the single owner of ingress, target mutation State Machine, durable intent, exactly-once dispatch, recovery/quarantine and canonical runtime classification.

### Gate C — Android secret-state and backup/D2D hardening

- no plaintext persistent WireGuard/private tunnel configuration;
- reuse AndroidKeyStore/AES-GCM;
- explicit backup/device-transfer exclusions for secret-bearing state;
- preserve direct-boot requirements;
- missing/corrupt ciphertext/key material fails closed;
- no plaintext fallback.

### Gate D — Android behavior and framework tests

Protect secure state, boot restoration, tunnel lifecycle, cellular egress authentication/network refusal, local-control authentication/retry semantics and one Android framework/Keystore/service instrumentation smoke path.

### Gate E — supply-chain + Product Release prerequisite hardening

Bind vendored WireGuard AAR to official upstream identity/version/license/digest. Product tag creation requires exact same-SHA successful Quality plus Product Release prerequisite proof; prerequisite readiness must not unnecessarily load signing secret values.

### Gate F — new immutable Product Release

Create a new semantic Product Release from the hardened exact PRODUCT revision. Never rewrite historical `v0.1.4`. Require annotated tag -> exact source -> signed artifacts -> manifest/provenance/digests -> immutable Release.

### Gate G — exactly one admitted deployment

Only when #179 authorizes it, issue one semantic `/deploy <target> <new-release>` through Controller Issue #1. Bind exact immutable Product Release + exact controller revision, persist intent before destructive dispatch, execute at most once and independently verify postconditions.

### Gate H — real-world acceptance

On the final deployed release prove registered phone, reverse tunnel, relay/provider, external client, cellular egress/IP rotation, reboot/fallback/recovery and reliability/soak criteria from `TEN_OUT_OF_TEN_VALIDATION_PLAN.md`.

Historical phone experiments prove components only; they never substitute for Gate H on the final immutable release.

## 8. PRODUCT acceptance

PRODUCT 10/10-ready requires:

- coherent v2 authority docs/contracts and no active duplicate controller owner;
- retained compatibility/architecture/persistence/security invariants;
- Android secret persistence/backup boundary fail-closed;
- strong Android behavior coverage;
- exact Quality success;
- deterministic build/signing verification;
- release prerequisite/tag gates bound to exact source;
- immutable Product Release v2;
- complete provenance for vendored production binaries;
- no unresolved P0/P1 PRODUCT defect.

Quality proves PRODUCT software/policy; it does not manufacture target state.

## 9. Deployment Controller acceptance

Controller acceptance requires exact Product Release admission, exact controller-revision binding, semantic dedup independent of GitHub provenance, target-global serialization, observation before decision, durable intent before dispatch, exactly-once destructive dispatch per intent, independent postcondition observation, canonical terminal evidence, read-only UNKNOWN recovery, deterministic quarantine and `RECOVERED != ACCEPTED`.

`vm-production` remains fail-closed until its controller-owned adapter is proven end-to-end.

## 10. Full production 10/10

Full production 10/10 requires all three:

1. PRODUCT acceptance complete.
2. Deployment Controller invariants proven.
3. Separately authorized live target acceptance/recovery/restart/soak succeeds with no unresolved P0/P1 defect.

Do not collapse these evidence domains into one green workflow.

## 11. Change discipline

For docs/policy-sized changes use `scripts/quality-gate.sh fast`; for code/release changes use `scripts/quality-gate.sh`.

After each accepted merge or separately authorized production operation, record a bounded #179 checkpoint with exact identities, mutation status and exactly one `NEXT ALLOWED ITEM`. The newest #179 checkpoint supersedes stale wording elsewhere.
