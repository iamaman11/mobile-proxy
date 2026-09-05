# Production phone GitOps runtime boundary

Status: **normative production-phone execution boundary**  
PRODUCT repository: `iamaman11/mobile-proxy`  
Deployment Controller repository: `iamaman11/mobile-proxy-production`  
Authority contract: `contracts/operations/project-authority-v2.json`  
Production topology: `contracts/operations/production-topology-v2.json`  
Product Release ordering: `docs/operations/final-release-authority-order.md`

Both repositories are public. Their roles are different, and repository visibility is not the confidentiality boundary. Secret values, target bindings, raw device identifiers, credentials, private keys, sensitive rendered configuration and unsafe raw ADB/runtime logs remain private.

Older Item 19/Item 20 and signing-generation material remains historical evidence where retained; it does not override this controller-v2 runtime model.

## Ownership

The PRODUCT repository owns application/runtime source, Quality, product build/signing verification, annotated tags and immutable Product Release v2.

The Deployment Controller owns deployment admission, target serialization, target observations/adapters, durable mutation intent, exactly-once destructive dispatch, postconditions, recovery/quarantine and canonical runtime execution classification.

The Deployment Controller is not a thin execution satellite and must not become a second PRODUCT source. It remains forbidden from copying application source or independently building/signing/tagging/publishing the product.

Public Issue #179 is the current migration/development execution cursor. Public Issue #228 is backlog only. Normal phone deployment ingress is Deployment Controller Issue #1:

```text
/deploy phone-production <vX.Y.Z>
```

## Runtime identity

Phone deployment identity is not a branch SHA and not a tracker cursor.

```text
runtime_identity
  = exact immutable Product Release v2
  + exact admitted Deployment Controller revision
```

The controller must resolve the exact semantic tag and immutable Release. `latest`, a mutable branch or a mutable GitHub Release is forbidden.

A Product Release must exist before deployment admission. Physical phone acceptance is not a prerequisite for creating the Product Release; it is deployment execution/verification after immutable product input exists.

## Product / phone separation

The PRODUCT `product-release` environment builds and verifies the signed Android APK. It contains product-signing secrets but has no phone/ADB/provider execution authority.

The controller consumes the immutable signed APK and owns any install/update/uninstall transaction required by target topology. Product-signing secrets do not need to be present on the phone runner for a normal deployment.

The production Android package is `com.example.mobileproxy`. The Android app is not the primary reverse-tunnel owner; it is a managed auxiliary component when topology uses Android `Network.bindSocket()` cellular egress or the app-owned WireGuard compatibility path.

A topology that does not require an app capability need not mutate the APK. A topology that does require it must bind the exact Product Release artifact, package/version and bounded signer-verification evidence before physical mutation.

## Registered-device boundary

`ANDROID_PRODUCTION_SERIAL` is a private target binding. It is used only to select the registered production phone and must never be emitted in public evidence.

Before destructive phone dispatch, the controller/adapter fails closed unless it can prove the intended registered target and required runner/tool state. First-attached-device discovery is forbidden.

Windows USB bridge / WSL runner wiring is transport infrastructure only. It may restore access to the expected physical USB device and runner listener, but never authorizes Android mutation by itself.

## State Machine / transaction rules

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
- one semantic intent admits at most one destructive adapter dispatch;
- duplicate semantic requests cannot cause a second physical mutation;
- no blind retry occurs after the destructive dispatch boundary;
- an ambiguous post-dispatch result becomes `UNKNOWN` and continues only with read-only recovery;
- recovery mode is reconciled from durable state after target-global serialization is acquired;
- `RECOVERED` never retroactively converts the original deployment into `ACCEPTED`;
- quarantine/terminal classification is durable controller evidence.

## Observation and freshness

Phone observations are facts, not implicit mutation authority. Reusable observed facts may be retained while their declared freshness and affected physical-domain generations remain valid.

A Git commit changing unrelated PRODUCT code must not mechanically make every phone fact stale. A physical-domain mutation invalidates facts causally dependent on that domain/generation. The controller must re-observe only required dependencies.

```text
changed X
  -> determine causal dependents of X
  -> invalidate only those facts
  -> re-observe only required dependencies
```

## Exactly-once boundary

Transport retries are allowed only before the destructive device invocation or for read-only observations whose contract is retry-safe.

After durable intent and possible device dispatch, the controller must never infer “workflow failed, therefore phone mutation did not happen.” It observes the phone and reconciles from durable state.

Target-global serialization prevents simultaneous destructive transactions, but locking alone is not idempotency. Semantic request identity, durable intent and post-lock recovery reconciliation are also required.

## Evidence and public projection

The controller durable ledger is canonical runtime execution truth. Because the repository is public, entries and issue projections must contain only bounded, non-sensitive classifications/digests/booleans. Secret values, target bindings, raw device identifiers and sensitive raw execution material remain private inputs/state outside public Git content/evidence.

Public GitHub Deployment is bounded status/history projection only. Projection failure or delay never causes another phone dispatch and never overrides the durable controller ledger.

Public evidence must not contain raw device identifiers, signer material/fingerprints, credentials, private endpoint secrets, workstation paths or unsafe raw phone logs.

## Failure semantics

The controller fails closed when:

- exact Product Release v2 cannot be resolved;
- GitHub Release is mutable or incomplete;
- controller revision cannot be bound exactly;
- registered-device or runner facts are missing/ambiguous/stale for the requested operation;
- target-global serialization cannot be obtained;
- durable mutation intent cannot be persisted/verified;
- recovery state is inconsistent after lock acquisition;
- postcondition observation cannot establish a safe terminal result.

Failure before the destructive boundary permits a future fresh admission attempt. Ambiguity after the destructive boundary permits only read-only recovery until the controller can classify physical state.

## VM extension

`vm-production` remains fail-closed until its target adapter is proven end-to-end. It reuses the same controller kernel and transaction semantics rather than reintroducing public PRODUCT production orchestration.

No phone, VM or provider mutation is authorized merely by this document.
