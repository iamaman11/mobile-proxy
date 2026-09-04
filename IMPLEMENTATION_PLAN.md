# Mobile Proxy Implementation Plan

The sole active roadmap is:

- [Production Baseline Plan](docs/PRODUCTION_BASELINE_PLAN.md)

This file is only the concise execution entry point. It must not become a second backlog.

## Authority

Current authority is the accepted v2 split:

```text
PUBLIC PRODUCT
  iamaman11/mobile-proxy
  -> source / product architecture
  -> Quality
  -> product build + signing verification
  -> annotated product tag
  -> immutable Product Release

PRIVATE DEPLOYMENT CONTROLLER
  iamaman11/mobile-proxy-production
  -> /deploy ingress on private Issue #1
  -> deployment State Machine / Transaction Kernel
  -> target admission + serialization + observation
  -> durable mutation intent
  -> exactly-once destructive dispatch
  -> postcondition / recovery / quarantine
  -> canonical runtime evidence
```

Normative authority contracts:

- `docs/operations/project-authority.md`
- `contracts/operations/project-authority-v2.json`
- `contracts/operations/github-control-plane-v2.json`
- `contracts/operations/production-topology-v2.json`
- `contracts/operations/product-release-authority-v2.json`

Public Issue #179 is the authoritative migration/development checkpoint stream. Public Issue #228 is the 10/10 PRODUCT-hardening backlog only. Private Issue #1 is the runtime Deployment Controller command/ledger surface.

The newest #179 checkpoint always decides what may happen next. This file never grants `/deploy`, phone/ADB access, provider/VM mutation, signing authority, tag authority or release rewrite authority.

## Current 10/10 direction

The project is no longer trying to make the public repository own the physical deployment State Machine. The private Deployment Controller v2 owns deployment execution. The remaining work is to remove old dual ownership, finish PRODUCT hardening and then run separately authorized live acceptance.

The normal system must remain understandable as:

```text
state
  -> guard
  -> operation
  -> effect
  -> independent observation
  -> resulting state
```

No new framework is justified merely to reconcile old public/private duplication.

## Ordered stages

### Stage 1 — authority drift correction

Goal: make the active repository entry points describe exactly one authority model.

Required:

- `AGENTS.md`, README/navigation/roadmap/operations entry points use PRODUCT / DEPLOYMENT CONTROLLER v2 terminology;
- v1 “thin execution satellite” claims are removed from active guidance;
- public `control_state_machine.py` / `operation_state_machine.py` and similar files are not described as current runtime authority;
- existing public physical/deployment surfaces are classified as PRODUCT/shared-domain, deployment-only or historical;
- no source ownership deletion/porting yet unless a later #179 checkpoint permits it;
- no new documentation-consistency checker merely to prove prose changed.

### Stage 2 — physical source-ownership migration by simplification

After #179 explicitly permits it:

- prove what private v2 already owns;
- port only genuinely missing deployment-controller behavior;
- delete public deployment-only duplicate controller/runtime-mutation authority;
- keep genuine PRODUCT/shared-domain code public;
- mark or remove historical workflows/docs that can still mislead normal execution;
- do not create a third shared controller framework.

Exit condition: one developer can identify one owner for every active deployment decision and destructive boundary.

### Stage 3 — Android secret-state boundary

Close the PRODUCT security gap without introducing a new security framework:

- stop persisting WireGuard/private tunnel configuration as plaintext;
- use the existing AndroidKeyStore/AES-GCM model where appropriate;
- explicitly exclude secret-bearing state from backup/device transfer;
- preserve required direct-boot behavior;
- corrupt/missing ciphertext or key material fails closed;
- do not fall back to plaintext;
- prefer deterministic reprovisioning over complex migration of disposable bootstrap state unless continuity is a real production requirement.

### Stage 4 — minimal strong Android behavior coverage

Add a small number of tests that protect independent production contracts:

- secure persistent state and corruption refusal;
- boot restoration / desired-state behavior;
- tunnel lifecycle and backend failure;
- cellular-egress authentication/network refusal;
- local-control authentication and bounded retry semantics;
- one instrumentation/device-emulator smoke path only where Android framework/Keystore/service behavior is the actual invariant.

Do not increase test count as a proxy for confidence.

### Stage 5 — Product Release hardening

Keep one release prerequisite surface and close the remaining trust-boundary gaps:

- prerequisite proof must not load Android signing secret values merely to prove configuration;
- tag creation must require exact same-SHA successful Quality and Product Release prerequisite evidence;
- immutable `v0.1.4` is historical accepted Product Release input and must not be rewritten;
- future Product Releases remain public PRODUCT authority.

### Stage 6 — vendored WireGuard AAR provenance

Establish a direct auditable chain:

```text
official upstream
  -> exact version/release coordinates
  -> expected cryptographic digest
  -> checked-in AAR bytes
```

Prefer one small provenance metadata/note plus direct checksum assertion. If current bytes cannot be matched to authoritative upstream, replace them with reviewed upstream bytes rather than invent provenance.

### Stage 7 — stale normative tracker/doc cleanup

Once the active v2 model is stable:

- update/close open trackers whose old Item19/Item20 or thin-satellite wording can still steer work incorrectly;
- keep immutable historical evidence intact;
- move genuinely historical prose out of active navigation rather than maintaining parallel current-state summaries.

### Stage 8 — separately authorized live production acceptance

Live execution is not automatically unlocked by completing PRODUCT hardening.

When the newest #179 checkpoint explicitly permits it, deployment consumes:

```text
exact immutable Product Release
+ exact admitted private controller revision
```

The private controller then owns admission, target-global serialization, observation, durable pre-dispatch intent, at-most-once destructive dispatch, independent postcondition and terminal/recovery classification.

No old failed GitHub run is manually rerun to perform a deployment. Re-entry semantics come only from the canonical private ledger.

## Deployment-controller invariants that PRODUCT work must not break

- semantic request identity is independent of GitHub comment/run/attempt provenance;
- public GitHub Deployment is projection only;
- durable mutation intent precedes destructive dispatch;
- destructive dispatch is at most once for one durable intent;
- ambiguous post-dispatch state never causes blind destructive retry;
- UNKNOWN continuation is read-only observation/reconciliation;
- `RECOVERED != ACCEPTED`;
- target serialization is controller-owned;
- private controller canonical terminal evidence is runtime truth.

## Engineering discipline

1. No code for code.
2. No verification of verification.
3. Prefer deletion/consolidation over new abstraction layers.
4. One owner per state/decision.
5. Use the smallest test surface that proves independent behavior.
6. Do not preserve disposable bootstrap phone state through complex architecture unless continuity is explicitly required.
7. Product build/release/security/tests remain public PRODUCT responsibilities.
8. Deployment target access/mutation/recovery remain private Deployment Controller responsibilities.

## Quality

For docs/policy-only changes:

```bash
scripts/quality-gate.sh fast
```

For code/release changes:

```bash
scripts/quality-gate.sh
```

GitHub `Quality Gate` is the aggregate public PRODUCT check. A green public Quality result does not manufacture current target state or authorize runtime deployment.

## Definition of done

The project reaches full production 10/10 only when all three statements are true:

1. **PRODUCT** security, behavior, Quality, release-gate and provenance requirements are proven.
2. **DEPLOYMENT CONTROLLER** exactly-once mutation, target observation, recovery/quarantine and canonical terminal-evidence semantics are proven.
3. The separately authorized real target acceptance/recovery/soak sequence passes with no unresolved P0/P1 defect.

The latest #179 checkpoint remains the only authority for the exact next bounded step.
