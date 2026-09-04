# Production phone GitOps runtime boundary

Status: **normative production-phone execution boundary**  
Public PRODUCT repository: `iamaman11/mobile-proxy`  
Private Deployment Controller: `iamaman11/mobile-proxy-production`  
Authority contract: `contracts/operations/project-authority-v2.json`  
Production topology: `contracts/operations/production-topology-v2.json`  
Product Release ordering: `docs/operations/final-release-authority-order.md`

This document defines the current controller-v2 phone boundary. Older Item 19/Item 20 and signing-generation material remains historical evidence where retained, but it does not override this runtime model.

## Ownership

The public repository owns PRODUCT source, Quality, product build/signing verification, annotated tags and immutable Product Release v2.

The private repository owns DEPLOYMENT CONTROL: deployment admission, target serialization, target observations/adapters, durable mutation intent, exactly-once destructive dispatch, postconditions, recovery/quarantine and canonical runtime evidence.

The private repository is therefore **not** merely a thin execution satellite. It remains forbidden from copying application source or independently building/signing/publishing the product, but its Deployment Controller is authoritative for physical execution.

Public Issue #179 is a migration/development audit tracker. Normal phone deployment ingress is private Issue #1:

```text
/deploy phone-production <vX.Y.Z>
```

## Runtime identity

Phone deployment identity is not a public branch SHA and not a tracker cursor.

```text
runtime_identity
  = exact immutable Product Release v2
  + exact private controller revision
```

The controller must resolve the exact semantic tag and immutable Release. `latest`, a mutable branch, or a mutable GitHub Release is forbidden.

A Product Release must exist before deployment admission. Physical phone acceptance is not a prerequisite for creating the Product Release; it is part of deployment execution/verification after immutable product input exists.

## Product / phone separation

The public `product-release` environment builds and verifies the signed Android APK. It contains product-signing secrets but has no phone/ADB/provider execution authority.

The private controller consumes the immutable signed APK and owns any install/update/uninstall transaction required by the target topology. Product-signing secrets do not need to be present on the phone runner for a normal deployment.

The production Android package is `com.example.mobileproxy`. The Android app is not the primary reverse-tunnel owner; it is a managed auxiliary component when topology uses Android `Network.bindSocket()` cellular egress or the app-owned WireGuard compatibility path.

A topology that does not require an app capability need not mutate the APK. A topology that does require it must bind the exact Product Release artifact, package/version and bounded signer-verification evidence before physical mutation.

## Historical Item 19 / Item 20 provider-isolation boundary

The controller-v2 migration supersedes the old **release ordering**, but it does not erase historical provider-isolation safety facts. The following constraints remain intentionally preserved for audit and fail-closed compatibility with historical Item 19/Item 20 evidence:

- The private runner has no Vultr credentials.
- Before enabling any mutable phone workflow: the responsible execution authority must prove its own target, identity, admission and recovery preconditions; historical provider proof never authorizes a phone mutation by itself.
- Item 19 provider proof is COMPLETE.
- The historical Item 19 proof SHA remains historical evidence; that SHA is not active Item 20 release authority.
- Under the historical Item 20 handoff, private Item 20 phone execution must not call Vultr APIs.

These statements preserve the old provider-isolation boundary only. They do **not** restore Item 20, signing-generation #115 or `final_accepted_candidate_sha` as prerequisites for an annotated Product tag or immutable Product Release v2. Current product/deployment ordering is defined by the v2 authority contracts at the top of this document.

## Registered-device boundary

`ANDROID_PRODUCTION_SERIAL` is a private target binding. It is used only to select the registered production phone and must never be emitted in public evidence.

Before any destructive phone dispatch, the private controller/adapter must fail closed unless it can prove the intended registered target and required runner/tool state. First-attached-device discovery is forbidden.

The existing Windows USB bridge and WSL runner wiring remain transport/runtime infrastructure only. They can restore access to the expected physical USB device and runner listener, but they never authorize an Android mutation by themselves.

## State Machine / transaction rules

The active controller rules are:

```text
resolve exact Product Release + exact controller revision
  -> acquire target-global serialization
  -> re-read durable controller ledger
  -> reconcile recovery mode after lock
  -> observe target facts
  -> classify admission
  -> if mutation is required:
       persist durable mutation intent
       -> exactly one destructive adapter dispatch
       -> independent postcondition observation
  -> terminal classification
```

Mandatory invariants:

- mutation intent exists durably before destructive dispatch;
- the Android adapter exposes one destructive install path for the active transaction;
- duplicate semantic requests cannot cause a second physical mutation;
- no blind retry occurs after the destructive dispatch boundary;
- an ambiguous post-dispatch result becomes `UNKNOWN` and continues only with read-only recovery;
- recovery mode is reconciled again from durable state after the target-global lock is acquired;
- `RECOVERED` never retroactively converts the original deployment into `ACCEPTED`;
- quarantine/terminal classification is durable private controller evidence.

## Observation and freshness

Phone observations are facts, not implicit mutation authority. Reusable observed facts may be retained when their declared freshness and affected physical-domain generations remain valid.

A Git commit changing unrelated code must not mechanically make every phone fact stale. A physical-domain mutation invalidates the facts causally dependent on that domain/generation. The controller should re-observe only what the operation contract says is stale or causally affected.

This enables the intended industrial model:

```text
changed X
  -> determine causal dependents of X
  -> invalidate only those facts
  -> re-observe only required dependencies
```

rather than `commit -> all phone state stale -> probe everything again`.

## Exactly-once boundary

Transport retries are allowed only before the destructive device invocation or for read-only observations whose contract is retry-safe.

After durable intent and possible device dispatch, the controller must never infer “the workflow failed, therefore the phone mutation did not happen.” It must observe the phone and reconcile from durable state.

The controller's target-global lock prevents simultaneous destructive phone transactions, but locking alone is not the idempotency contract. Durable semantic request identity, mutation intent and post-lock recovery reconciliation are also required.

## Evidence and public projection

Canonical runtime execution evidence remains private because it may bind target state and recovery details unavailable to the public PRODUCT plane.

Public GitHub Deployment is a bounded status/history projection only. Projection failure or delay never causes another phone dispatch and never overrides the private durable controller ledger.

Public evidence must not contain raw device identifiers, signer fingerprints/material, credentials, private endpoint secrets, workstation paths or raw sensitive phone logs.

## Failure semantics

The phone controller fails closed when:

- exact Product Release v2 cannot be resolved;
- GitHub Release is mutable or its required asset contract is incomplete;
- controller revision cannot be bound exactly;
- registered-device or runner facts are missing/ambiguous/stale for the requested operation;
- target-global serialization cannot be obtained;
- durable mutation intent cannot be persisted/verified;
- recovery state is inconsistent after lock acquisition;
- postcondition observation cannot establish a safe terminal result.

A failure before the destructive boundary permits a future fresh admission attempt. An ambiguity after the destructive boundary permits only read-only recovery until the controller can classify the physical state.

## VM extension

`vm-production` is intentionally fail-closed until its target adapter is proven end-to-end. It will reuse the same controller kernel and transaction semantics rather than reintroducing a separate public production orchestration authority.

No phone, VM or provider mutation is authorized merely by this document.
