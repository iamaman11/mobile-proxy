# Production Baseline Plan

Status: **active canonical implementation roadmap**  
PRODUCT repository: `iamaman11/mobile-proxy`  
Deployment Controller repository: `iamaman11/mobile-proxy-production`  
Acceptance backlog: public Issue #228  
Authoritative next-step checkpoint: public Issue #179

This file is the sole active development roadmap. It describes durable ordering and acceptance criteria; the newest authoritative #179 checkpoint decides the exact next bounded item that may execute.

## 1. Goal

Reach a simple, understandable industrial Mobile Proxy baseline with:

- secure and behavior-tested PRODUCT code;
- deterministic public Quality and immutable Product Release evidence;
- one private Deployment Controller owning deployment execution;
- exactly-once destructive target semantics;
- independent target postcondition observation;
- deterministic recovery/quarantine after ambiguous execution;
- auditable dependency provenance;
- separately authorized real-target acceptance and soak evidence;
- no unresolved P0/P1 defect.

The goal is not a larger orchestration framework. New machinery must remove a demonstrated uncertainty and remain simpler than the problem it solves.

## 2. Authority model

The accepted v2 split is normative:

| Plane | Repository | Authority |
| --- | --- | --- |
| PRODUCT | `iamaman11/mobile-proxy` | application/runtime source, shared product/domain architecture, public Quality, product build, Android signing verification, annotated product tags, immutable Product Releases and product documentation |
| DEPLOYMENT CONTROLLER | `iamaman11/mobile-proxy-production` | deployment ingress, deployment State Machine / Transaction Kernel, target admission/serialization/observation, target adapters, durable mutation intent, exactly-once destructive dispatch, postconditions, recovery/quarantine, private bindings/secrets and canonical runtime evidence |

Normative contracts:

- `docs/operations/project-authority.md`
- `contracts/operations/project-authority-v2.json`
- `contracts/operations/github-control-plane-v2.json`
- `contracts/operations/production-topology-v2.json`
- `contracts/operations/product-release-authority-v2.json`

The older “private thin execution satellite; public physical State Machine owner” model is superseded.

Public Issue #179 is the migration/development audit tracker, not the normal runtime deployment ledger. Public Issue #228 is backlog only. Private Issue #1 is the Deployment Controller command surface and canonical runtime execution ledger.

## 3. Retained PRODUCT invariants

The authority migration does not weaken previously audited PRODUCT behavior. The following remain current PRODUCT requirements unless a separately reviewed compatibility migration changes them.

### 3.1 Protected compatibility surface

- mixed SOCKS5/HTTP compatibility remains public on port `1080`;
- SOCKS5 remains public on port `1081`;
- HTTP including CONNECT remains public on port `3128`;
- QUIC remains the primary reverse-tunnel transport;
- certificate-pinned TLS/TCP reserve remains available and plaintext downgrade remains forbidden;
- WireGuard remains a controlled compatibility/rollback path until an explicit accepted deprecation;
- operator CLI/admin API compatibility is preserved unless a versioned migration explicitly changes it.

These are PRODUCT behavior contracts. The private Deployment Controller decides whether and how an exact immutable Product Release is applied to a target; it does not redefine the product compatibility surface.

### 3.2 Architecture and state ownership

Inside PRODUCT, dependency direction remains foundation/domain -> application -> infrastructure/adapters -> composition/delivery. Pure/domain modules do not take transport, persistence, Android, filesystem, process, environment or provider responsibilities. External inputs are converted into typed product/domain values at boundaries where the existing contracts require it.

Every currently registered PRODUCT/operational mutable-state group has one declared authoritative owner. Other contexts mutate durable product state only through the existing typed application/persistence boundaries. HTTP handlers do not own SQL transaction ordering or canonical business transitions.

The v2 cross-repository authority split is an additional boundary: deployment admission, target mutation, exactly-once dispatch and recovery are not PRODUCT mutable-state ownership and belong to the private Deployment Controller.

### 3.3 Durable PRODUCT state

The existing durable control-plane invariants remain unchanged:

- canonical mutable PRODUCT control-plane state is durable rather than memory-only;
- SQLite retains WAL, foreign keys, bounded busy timeout, single-writer/short-transaction discipline, integrity checks, backup and clean restore behavior;
- related device/command/replay/projection changes that form one product operation commit atomically as required by the existing persistence contract;
- legacy JSON migration remains bounded import/parity/diagnostic/rollback compatibility rather than an alternate canonical runtime store.

These PRODUCT persistence invariants are distinct from the private deployment mutation ledger.

### 3.4 Typed contracts, security and bounded operation

Existing typed identifier/status/error/protocol/tunnel/strategy contracts and typed BLAKE3 content/fingerprint policy remain in force. Secret values do not enter public Git/evidence. Public Actions remain least-privilege, fork-safe and free of production phone/ADB access.

Requests, mutation idempotency, queue/retry bounds, liveness/readiness separation, authentication and fail-closed proxy/session behavior remain governed by their existing PRODUCT contracts and tests. This Stage 1 authority correction does not waive those invariants.

### 3.5 Delivery integrity

Public PRODUCT delivery continues to require reviewed exact source, exact successful Quality where required, immutable product identity, deterministic build/signing verification, bounded checksums/SBOM/provenance and immutable Product Release evidence. Mutable `latest`, branch names or approximate artifact identity are forbidden as production deployment identity.

## 4. Product Release precedes deployment

The normal authority order is:

```text
protected public main + exact successful Quality
  -> Product Release prerequisite proof where required
  -> annotated product tag
  -> public signed PRODUCT build
  -> immutable Product Release v2
  -> private /deploy <target> <tag>
  -> private controller admission / observation / possible mutation / verification / recovery
```

Physical phone acceptance is not a prerequisite for creating the immutable Product Release under v2. Runtime identity combines the exact immutable Product Release and the exact admitted private controller revision.

`latest`, mutable branches, a public GitHub Deployment record, a historical acceptance candidate or Issue prose are not deployment identity.

## 5. Deployment execution invariants

The private Deployment Controller owns the runtime transaction model:

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

Required invariants:

1. durable mutation intent exists before destructive dispatch;
2. one durable intent admits at most one destructive target dispatch;
3. GitHub comment/run/attempt provenance does not redefine semantic request identity;
4. ambiguous post-dispatch outcome never causes blind destructive retry;
5. UNKNOWN continuation is read-only observation/reconciliation;
6. `RECOVERED != ACCEPTED`;
7. evidence-write retry never repeats the physical effect;
8. public GitHub Deployment is bounded projection only;
9. target-global serialization is private-controller authority;
10. a successful command/workflow is not an independent target postcondition.

Public PRODUCT work must not reintroduce a second runtime State Machine or mutation ledger.

## 6. Historical Item 19 / Item 20 evidence boundary

This section preserves immutable historical evidence required by existing audits; it is **not current runtime or release authority** under v2.

Historical Item 19 candidate `d151dbdd156279e32a5361d304c90f996bd2d565` remains historical provider-lifecycle proof only. Item 19 historical provider proof is COMPLETE. Its terminal proof intent, provider evidence and candidate identity are not reusable as a current deployment request, Product Release or private-controller terminal.

In the superseded Item19/Item20 roadmap, Item 20 is the first unfinished delivery item and Item 20 remains blocked by the signing-continuity gate recorded by that historical acceptance design. Any historical Item 20 JIT session required a distinct ownership intent rather than reuse Item 19's terminal proof intent.

Those statements are retained only so historical evidence remains auditable. Current work does **not** resume the old Item20 release ordering: Product Release v2 now precedes deployment, private Issue #1 is the runtime ingress/ledger, and the newest #179 checkpoint alone determines whether any future live acceptance action is permitted.

## 7. Ordered 10/10 development stages

Issue #228 carries the detailed backlog. The stages below are the canonical durable order; #179 chooses the exact current item.

### Stage 1 — remove active authority drift

Make all current entry points consistent with v2:

- remove active “thin satellite” claims;
- stop presenting public physical State Machine/controller files as runtime authority;
- point active guidance to v2 authority/topology/control-plane contracts;
- classify existing public physical/deployment surfaces as PRODUCT/shared-domain, deployment-only or historical;
- do not yet delete/port controller source unless a later #179 checkpoint explicitly allows it;
- do not create a new checker merely to prove documentation consistency.

### Stage 2 — source-ownership migration by simplification

When separately authorized:

- prove what private v2 already owns;
- port only genuinely missing deployment-controller behavior;
- delete public deployment-only duplicate runtime authority;
- keep genuine PRODUCT/shared-domain code public;
- retire or clearly mark historical public phone/Item19/Item20/deployment surfaces;
- never create a third shared controller framework.

Exit condition: every active deployment decision has one owner.

### Stage 3 — Android secret-state hardening

Close the demonstrated PRODUCT security boundary:

- no plaintext persistent WireGuard/private tunnel configuration;
- use the existing small AndroidKeyStore/AES-GCM model where appropriate;
- explicitly exclude secret-bearing state from backup/device transfer;
- preserve required direct-boot behavior;
- corrupt/missing ciphertext/key material fails closed;
- no plaintext fallback;
- prefer deterministic reprovisioning of disposable bootstrap state over complex compatibility migration unless continuity is explicitly required.

### Stage 4 — minimal strong Android behavior coverage

Protect independent production contracts with a small number of strong tests:

- secure persistent state and corruption refusal;
- boot restoration and desired-state behavior;
- tunnel lifecycle/backend failure;
- cellular-egress authentication and network refusal;
- local-control authentication and bounded retry/timeout behavior;
- instrumentation only where Android framework/Keystore/service behavior is the actual invariant.

Tests prove behavior, not test machinery.

### Stage 5 — Product Release gate hardening

Keep one prerequisite authority surface and ensure:

- prerequisite proof does not load signing secret values merely to prove secret configuration;
- product tag creation requires exact same-SHA successful Quality and prerequisite proof;
- immutable existing Product Releases are never rewritten;
- public PRODUCT remains the only build/sign/tag/release authority.

### Stage 6 — vendored Android dependency provenance

For the WireGuard AAR establish:

```text
official upstream
  -> exact version/release coordinates
  -> expected cryptographic digest
  -> checked-in bytes
```

Use the smallest direct provenance/checksum mechanism. If current bytes cannot be tied to authoritative upstream, replace them with reviewed upstream bytes.

### Stage 7 — stale normative tracker/doc cleanup

Remove stale active guidance without rewriting historical evidence:

- update/close open trackers whose old Item19/Item20 or thin-satellite wording can still steer execution;
- move genuinely historical material out of current navigation;
- keep Git history and immutable evidence as the archive.

### Stage 8 — live deployment and production acceptance

This stage requires a new explicit #179 authorization. PRODUCT-hardening completion alone does not authorize target mutation.

When authorized, the private Deployment Controller consumes the exact immutable Product Release, performs admission/serialization/observation, persists intent before any destructive dispatch, independently verifies the resulting target state and writes canonical terminal evidence.

Old failed GitHub workflow runs are not manually rerun as a deployment mechanism. Re-entry is derived from the canonical private ledger.

## 8. PRODUCT acceptance criteria

PRODUCT 10/10-ready requires, on reviewed exact source identities:

- coherent v2 authority documentation/contracts;
- no active duplicate deployment runtime owner in public after Stage 2;
- retained PRODUCT compatibility, architecture, persistence, security and bounded-operation invariants remain protected;
- Android secret persistence/backup boundaries fail closed;
- strong behavior coverage for the independent Android production contracts;
- exact Quality success;
- deterministic product build/signing verification;
- release prerequisite and tag gates bound to the exact source identity;
- immutable Product Release v2 evidence;
- complete provenance for vendored production binaries/dependencies;
- no unresolved P0/P1 PRODUCT defect.

Public Quality proves PRODUCT software/policy. It does not manufacture target state.

## 9. Deployment Controller acceptance criteria

The private controller is accepted only while it proves:

- exact immutable Product Release admission;
- exact controller-revision binding;
- semantic request dedup independent of GitHub provenance;
- target-global serialization;
- target observation before decision;
- durable mutation intent before dispatch;
- exactly-once destructive dispatch per intent;
- independent postcondition observation;
- canonical durable terminal evidence;
- read-only UNKNOWN recovery;
- deterministic quarantine/refusal;
- `RECOVERED != ACCEPTED`;
- no blind retry after an ambiguous destructive boundary.

VM production remains fail-closed until its controller-owned target adapter is proven end-to-end.

## 10. Full production 10/10

Full production 10/10 is reached only when all three are true:

1. PRODUCT acceptance criteria are complete.
2. Deployment Controller invariants remain independently proven.
3. The separately authorized live target acceptance/recovery/restart/soak sequence succeeds with no unresolved P0/P1 defect.

Do not collapse those three evidence domains into one green workflow.

## 11. Engineering doctrine

1. No code for code.
2. No verification of verification.
3. Prefer deletion and consolidation.
4. One owner per state/decision.
5. Add the smallest strong test surface.
6. Do not preserve disposable bootstrap state through complex machinery unless continuity is a real requirement.
7. Keep normal control flow understandable as `state -> guard -> operation -> effect -> independent observation -> resulting state`.
8. Public PRODUCT workflows never perform production phone/ADB mutation.
9. Private Deployment Controller never independently builds/signs/tags/releases the product.
10. Manual SSH, raw/manual ADB and workstation/provider CLI are not normal production control paths.

## 12. Quality and checkpoint discipline

For docs/policy-sized work:

```bash
scripts/quality-gate.sh fast
```

For code/release work:

```bash
scripts/quality-gate.sh
```

After every accepted merge or separately authorized production operation, record a bounded #179 checkpoint with exact relevant identities, mutation status and exactly one `NEXT ALLOWED ITEM`.

The newest #179 checkpoint supersedes stale execution wording elsewhere.
