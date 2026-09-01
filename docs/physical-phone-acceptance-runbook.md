# Immutable-SHA Physical Phone Acceptance Runbook

Status: **normative execution contract for Production Baseline Item 20**. Item 19 provider proof is COMPLETE as historical evidence. Live Item 20 remains blocked until all current signing/private-execution/provider prerequisites pass.

Canonical roadmap: `docs/PRODUCTION_BASELINE_PLAN.md`  
Acceptance model: `TEN_OUT_OF_TEN_VALIDATION_PLAN.md`  
Item-20 tracker: #135  
Historical Item-19 tracker: #124  
Phone GitOps boundary: `docs/operations/phone-gitops-runtime.md`  
Production topology: `contracts/operations/production-topology-v1.json`  
Private endpoint handoff design: `contracts/operations/item20-private-handoff-v1.json`

## 1. Control-plane boundary

Physical acceptance uses two separated execution trust zones:

```text
public canonical repository
  -> exact protected main SHA selected as Item 20 candidate/control-plane SHA
  -> fresh candidate-specific software/provider evidence
  -> protected typed Item 20 acceptance lifecycle
  -> fresh distinct Item 20 ownership intent
  -> controlled acceptance VM

private execution satellite
  -> thin exact-SHA caller/shim
  -> android-production self-hosted runner
  -> exact registered physical phone
```

The boundaries are mandatory:

- `iamaman11/mobile-proxy` is the sole architecture, roadmap, release, acceptance-policy and provider-policy authority;
- `iamaman11/mobile-proxy-production` is an execution-only phone satellite;
- candidate SHA and control-plane SHA must be exactly equal to the protected public `main` SHA admitted for the acceptance window;
- the private phone runner receives no Vultr credentials;
- the public provider job receives no private phone serial, ADB credential or Android signing secret;
- GCP/Google Cloud, `gcloud`, workstation-managed VM lifecycle and manual provider SSH are not acceptance fallbacks;
- provider mutation is performed only through the protected typed Item 20 acceptance lifecycle and durable binding state under the distinct Item 20 ownership intent; the terminal Item 19 proof intent is never reused;
- phone mutation is performed only through the private `android-production` execution boundary.

Historical Item 19 candidate `d151dbdd156279e32a5361d304c90f996bd2d565` remains immutable historical provider-lifecycle proof only. It is not the active Item 20 candidate and its candidate-specific authority/evidence is not reused as final-release authority.

This runbook itself grants no live provider, endpoint-handoff or phone-mutation authority.

## 2. Required gates before opening the physical window

All applicable current gates must be true before the first mutable phone action:

1. #172 architecture/documentation reconciliation is merged to protected public `main` and exact post-merge `Quality` succeeds.
2. That exact protected `main` SHA is selected as both `candidate_sha` and `control_plane_sha` and source identity is frozen for the acceptance window.
3. The exact candidate has fresh immutable software candidate evidence and exact successful canonical `Quality` on protected `main`.
4. Fresh immutable `/accept-candidate <sha>` authority exists for that same SHA.
5. Fresh `/vultr-readonly-preflight <sha>` evidence exists for that same SHA.
6. Fresh exact-candidate provider lifecycle proof required by the Item 20 contract exists for that same SHA before the live window.
7. The private execution satellite is pinned to that exact public SHA and its `android-production` read-only preflight passes for exactly the registered device in the same execution window.
8. The applicable Android signed candidate has been built and retained with bounded digest/provenance; package/version/signer-match evidence is valid where the selected topology uses the managed Android component.
9. The signing-continuity / signing-generation migration gates in #115/#162 are completed sufficiently to authorize the required mutable phone workflow.
10. No unresolved P0/P1 defect exists.
11. The final protected `v*` release tag is still absent; Item 20 precedes final release publication.

If any gate is absent, stale, ambiguous, belongs to a different SHA, or protected `main` advances after admission, stop before phone mutation. A main advance establishes a new candidate and requires fresh candidate-specific evidence.

### Android role and signing gate

The Android app is not the primary reverse-tunnel owner. It is a managed production auxiliary component when topology uses first-party Android/cellular `Network.bindSocket()` egress or the app-owned WireGuard compatibility path.

A topology that does not consume an app capability need not install an APK. A topology that does consume it must prove exact package/version/signer-match/install state and retained signed artifact provenance. The workflow-level signing/mutation gate is not bypassed merely because one physical test step itself does not install an APK.

A locally generated replacement signing key outside the authorized migration path is forbidden.

## 3. Exact candidate and deployment identity

Item 20 consumes exact immutable evidence from canonical GitHub state. It must not select `latest`, a moving branch, an arbitrary artifact, a historical Item 19 candidate by default, or a manually entered provider resource.

Before traffic tests, bounded evidence must bind:

- exact candidate/control-plane SHA equality;
- exact protected-main identity and Quality run;
- immutable candidate artifact identity/digest;
- fresh candidate-specific acceptance authority and Vultr read-only preflight;
- fresh exact-candidate provider lifecycle proof required by Item 20;
- exact server artifact identity/digest;
- exact phone release/package identity where applicable;
- exact retained signed Android artifact digest/provenance where applicable;
- bounded installed package/version/signer-match state where applicable;
- private phone execution run identity;
- UTC timestamps required by the evidence schema.

Never record credentials, private keys, raw signer fingerprints, raw phone serials, private transport endpoints, unrestricted logs or secret-derived identifiers in public evidence.

## 4. Fresh Item 20 acceptance session

Item 20 does not adopt an arbitrary or pre-existing VM. The public canonical control plane opens exactly one fresh JIT acceptance VM through the protected typed lifecycle under a distinct Item 20 ownership intent. The terminal Item 19 proof intent is never reused.

The lifecycle must prove:

- `LifecycleScope::Acceptance`;
- exact ownership intent for the active Item 20 candidate;
- provider-assigned immutable UUID remains the internal lifecycle authority;
- exact project/manager/scope/intent/generation tags;
- complete provider enumeration before lifecycle decisions;
- deployed server bytes/manifest/SHA match the active candidate;
- required public listeners and controlled probes are healthy;
- serialized durable lifecycle ownership;
- deterministic cleanup after the physical session and provider absence before terminal CAS.

IP/DNS may cross into the private phone plane only as transport data derived from the already verified Item 20 target. It is never provider identity or mutation authority and is not published as public evidence.

Provider API calls are confined to the protected public lifecycle. The private Item 20 phone execution must not call Vultr APIs, GCP APIs, `gcloud`, a Vultr CLI or workstation provisioning scripts.

### 4.1 Private endpoint handoff boundary

`contracts/operations/item20-private-handoff-v1.json` remains fail-closed until its explicit live prerequisites are met. A public provider job must not mutate private repository secrets/content to move an endpoint across the trust boundary.

For an admitted live window the plaintext envelope contains only:

- exact `candidate_sha`;
- exact `control_plane_sha` with the same value;
- one fresh opaque session nonce;
- the derived transport endpoint.

Provider UUID, provider credentials, phone credentials and alternative mutation selectors are forbidden. The envelope is sealed to the dedicated private-execution recipient key. The matching private key remains private and never reaches a public runner.

The private dispatch may carry `candidate_sha`, `control_plane_sha`, `session_nonce` and sealed ciphertext; plaintext endpoint is forbidden from workflow inputs. The private workflow exact-matches candidate/control-plane/nonce before endpoint use. Stale or replayed ciphertext fails closed.

Public terminal evidence may record only bounded non-secret run/result/cleanup identities allowed by contract, not plaintext endpoint, provider UUID, nonce value, handoff token or decryption key.

## 5. Phone execution boundary

All phone-side mutation is invoked through the private execution repository on the dedicated runner labels:

```text
[self-hosted, Linux, X64, android-production]
```

Immediately before mutation the workflow re-proves, without publishing the raw serial:

- required runner labels/tools;
- exactly one ADB-visible registered target;
- exact private registered-device match;
- read-only ADB state/shell probes.

Mutable commands are serialized per production phone and fail closed on target ambiguity. Raw workstation ADB is troubleshooting-only and is not accepted baseline evidence or normal delivery control.

## 6. Android migration safety before Item 20

Where the active topology uses the managed Android component, #162 migration must have already followed the canonical safe sequence before Item 20 physical acceptance:

1. prove the registered device;
2. pull and retain the exact currently installed APK privately;
3. verify old package/version and prove the installed signer without publishing its fingerprint;
4. retain rollback evidence;
5. re-prove the registered device;
6. only then uninstall/install the exact verified new candidate;
7. verify package `com.example.mobileproxy`, required versionName/versionCode, bounded signer equality and local/runtime health;
8. execute defined rollback on post-capture failure where applicable.

The migration does not independently authorize provider mutation, final release, unrelated reboot or network mutation. #115/#162 close only after their real acceptance criteria are satisfied.

## 7. Baseline physical sequence

The sequence runs against one fresh Item 20 acceptance session and the same immutable candidate SHA throughout.

### Stage A — primary online

Required state:

- primary owner `first_party_reverse_tunnel`;
- no active Android VPN owner in native mode;
- no `tun0` requirement in native mode;
- fresh QUIC reverse-tunnel authority;
- durable heartbeat and serving/cellular/proxy readiness;
- managed Android auxiliary package/service state correct when the selected topology uses it.

Prove all protected proxy surfaces through the real phone path: SOCKS5/HTTP/CONNECT on mixed `1080`, SOCKS5 on `1081`, and HTTP/CONNECT on `3128`.

### Stage B — reboot/restart recovery

Perform only the approved bounded reboot/restart action through canonical/private GitOps. Do not clear canonical relay durable state. Prove exact registered phone, unchanged release identity, durable rehydration, fresh heartbeat/QUIC and all protected proxy paths.

### Stage C — forced TLS/TCP reserve

On the already verified Item 20 target, block QUIC while leaving certificate-pinned TLS/TCP reachable. Prove fresh `tls_tcp` reserve authority, no plaintext downgrade, unchanged device identity and all protected proxy paths.

### Stage D — return to QUIC

Remove the bounded QUIC fault through the approved server-side control, establish a new fresh QUIC session and prove all protected proxy paths again.

### Stage E — stock WireGuard rollback

Activate the already prepared rollback state through approved phone/server controls. Prove the expected app-owned WireGuard/VPN state, accepted rollback interface/handshake state, inactivity of the first-party reverse tunnel as required by rollback mode and protected proxy behavior.

### Stage F — return to exact primary

Reactivate the exact previously accepted primary release without rebuilding it. Prove WireGuard disabled, native ownership restored, fresh QUIC returned, protected proxy paths pass, and final phone/server identities still match the original active Item 20 candidate.

## 8. Repetition and soak

A single six-stage pass is insufficient for global 10/10. Execute the recovery/restart/crash repetition matrix and at least the required 24-hour production-like soak from `TEN_OUT_OF_TEN_VALIDATION_PLAN.md` on the same exact candidate. Any source change requires a new candidate and fresh candidate-specific evidence.

## 9. Evidence invariants

The final Item 20 summary must prove one coherent tuple:

```text
exact candidate SHA == exact control-plane/protected-main SHA
+ fresh immutable software candidate evidence
+ fresh acceptance authority/preflight/provider proof for that SHA
+ exact server artifact identity
+ exact private phone release identity
+ exact Android installed/signing evidence when applicable
+ one registered physical-device binding
+ required physical stages
+ required recovery/restart/crash matrix
+ required soak evidence
```

Evidence from different source SHAs, different server artifacts or rebuilt phone releases cannot be combined. Historical Item 19 evidence remains historical context rather than a substitute for fresh candidate-specific Item 20 proof.

## 10. Stop conditions

Reject/stop for any of the following:

- candidate/control-plane/protected-main SHA mismatch;
- protected `main` advances after admission;
- source SHA or immutable artifact identity changes during the run;
- fresh acceptance/preflight/provider evidence does not match the active candidate;
- server artifact identity cannot be verified;
- provider target would be selected by name, IP, list order or arbitrary external UUID input;
- ownership/generation is missing, conflicting or ambiguous;
- signing or private-phone binding gate is unsatisfied;
- phone target is ambiguous or mismatched;
- sealed endpoint handoff is stale, replayed, mismatched or publicly exposed;
- wrong tunnel/VPN owner;
- stale tunnel authority or plaintext downgrade;
- protected proxy failure;
- failed reboot/recovery/rollback/return-to-primary;
- Android package/version/signer/install mismatch where applicable;
- unresolved P0/P1 defect;
- evidence/report-set mismatch;
- requirement to use GCP, manual provider lifecycle, workstation SSH or public/raw ADB as a normal path.

## 11. Completion boundary

Successful Item 20 acceptance means all applicable physical, recovery and soak requirements passed for one exact candidate SHA. Only then may #135 close completed with exactly one `final_accepted_candidate_sha` marker.

That closeout does not itself create a release. Final release authority independently requires:

```text
final_accepted_candidate_sha
  == exact protected main SHA
  == final annotated tag target SHA
  == source SHA of published artifacts
```

Item 21 may create final immutable release evidence/tag only after these checks. Item 22 may promote production only from that accepted final release tuple.
