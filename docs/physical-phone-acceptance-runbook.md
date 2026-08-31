# Immutable-SHA Physical Phone Acceptance Runbook

Status: **normative execution contract for Production Baseline item 20. Item 19 provider proof is COMPLETE; live Item 20 execution remains blocked while #115 is unresolved and until the protected Item 20 admission/session capability is complete.**

Canonical roadmap: `docs/PRODUCTION_BASELINE_PLAN.md`  
Item-20 tracker: #135  
Completed Item-19 tracker: #124  
Phone GitOps boundary: `docs/operations/phone-gitops-runtime.md`  
Production topology: `contracts/operations/production-topology-v1.json`

## 1. Control-plane boundary

Physical acceptance is split across two deliberately separate execution planes:

```text
public canonical repository
  -> GitHub-hosted Item 20 acceptance-session lifecycle
  -> exact accepted candidate on one controlled acceptance VM

private execution satellite
  -> android-production self-hosted runner
  -> exact registered physical phone
```

The boundaries are mandatory:

- `iamaman11/mobile-proxy` is the sole architecture, roadmap, release and provider authority;
- `iamaman11/mobile-proxy-production` is an execution-only phone satellite;
- the private phone runner must never receive `VULTR_API_KEY` or `VULTR_SSH_PRIVATE_KEY`;
- the public Vultr job must never receive the private phone serial, ADB credentials or Android signing secrets;
- GCP/Google Cloud, `gcloud`, workstation-managed VM lifecycle and manual provider SSH are not acceptance fallbacks;
- provider mutation is performed only through the protected typed acceptance lifecycle and durable binding state under the distinct Item 20 ownership intent;
- phone mutation is performed only through the private `android-production` execution boundary.

This runbook describes Item 20. It does **not** authorize Item 20 provider or phone mutation while #115 is unresolved or before the exact-current Item 20 admission/session gates are protected and satisfied.

## 2. Required gates before opening the physical window

All of the following must be true before the first Item 20 provider mutation or mutable phone action:

1. Items 15, 16, 17, 18 and 19 are `COMPLETE`.
2. Item 19 is live-complete for the exact candidate used by this run:
   - one or zero controlled acceptance-VM semantics proven;
   - exact provider UUID/ownership/generation binding verified;
   - exact-candidate server artifact deployed and verified;
   - deterministic provider deletion and durable terminal state proven;
   - no production authority used.
3. The exact full lowercase 40-character candidate SHA has a successful canonical `Quality` push on protected `main` and immutable candidate evidence.
4. Fresh immutable `/accept-candidate <sha>` authority exists for that same SHA.
5. Fresh `/vultr-readonly-preflight <sha>` evidence exists for that same SHA.
6. The current protected Item 20 control-plane SHA has successful exact post-merge `Quality` evidence and is kept distinct from the immutable software candidate SHA.
7. The private `android-production` read-only preflight passes for exactly the registered device in the same execution window.
8. The signing-continuity gate in #115 / `docs/operations/phone-gitops-runtime.md` is resolved sufficiently to enable the mutable phone workflow.
9. No unresolved P0/P1 defect exists.
10. The final protected `v*` release tag is still absent; Item 20 precedes final release publication.

If any gate is absent, stale, ambiguous or belongs to a different candidate/control-plane identity, stop before provider or phone mutation.

### Signing gate is not APK-step-specific

The current canonical phone policy states that read-only preflight is the only enabled phone production action until signing continuity is recovered and verified. Therefore the physical window cannot be opened merely because a particular test step does not install `apps/android-app`.

Changing that policy would require an explicit architecture/security decision. It must not be inferred from this runbook.

## 3. Exact candidate and deployment identity

The Item 20 workflow must receive the exact accepted candidate SHA and immutable evidence identities from canonical GitHub evidence. It must independently bind the protected `control_plane_sha` that contains the Item 20 orchestration logic. It must not select `latest`, a moving branch, an arbitrary artifact or a manually entered provider resource.

Before traffic tests, verify and record bounded evidence for:

- exact immutable candidate SHA;
- exact protected Item 20 control-plane SHA;
- canonical Quality run identities for the candidate and current control plane as required by policy;
- immutable candidate artifact identity and digest;
- Item 19 acceptance-authority/preflight identities;
- Item 19 provider-proof lifecycle evidence identity;
- Item 20 fresh-session evidence identity;
- exact server artifact identity/digest;
- exact bound provider UUID represented only in the provider lifecycle evidence allowed by policy;
- exact phone release/package identity;
- private phone execution run identity;
- tester and UTC timestamps.

Never record credentials, private keys, raw phone serials, provider UUID/IP, full proxy URLs or unrestricted logs in public evidence.

## 4. Fresh Item 20 acceptance session from the protected typed lifecycle

Item 20 does not select or adopt an arbitrary or pre-existing VM. The public canonical control plane
opens exactly one fresh JIT acceptance VM through the protected typed lifecycle under a distinct
Item 20 ownership intent. The terminal Item 19 proof intent is never reused.

The lifecycle capability and provider-proof invariants are handed off from Item 19. The fresh Item 20 server session is
accepted only when the canonical provider lifecycle proves:

- `LifecycleScope::Acceptance`;
- exact immutable Item 20 ownership intent for the candidate;
- provider-assigned immutable UUID is the authority;
- exact project/manager/scope/intent/generation tags;
- complete provider enumeration was used before lifecycle decisions;
- deployed server bytes/manifest/SHA match the exact candidate;
- public listeners and controlled probes required for the physical test are healthy;
- the fresh session uses a distinct Item 20 ownership intent and does not reuse terminal Item 19 state;
- the immutable `candidate_sha` remains distinct from the protected `control_plane_sha`;
- the lifecycle remains under the single repository-wide serialized acceptance writer;
- deterministic cleanup runs after the physical session and confirms provider absence before terminal CAS.

IP address or DNS name may be supplied to the physical test only as a transport endpoint derived from that already verified target. They are never lifecycle selectors or ownership authority, and the raw endpoint must not be published in public evidence.

Item 20 must not call GCP APIs, `gcloud`, a Vultr CLI or a workstation VM-provisioning script. Vultr API access is confined to the canonical protected typed GitHub-hosted acceptance lifecycle.

## 5. Phone execution boundary

All phone-side mutation is invoked by the private execution repository on the dedicated runner labels:

```text
[self-hosted, Linux, X64, android-production]
```

The private run must first re-prove, without publishing the raw serial:

- required runner labels;
- required `adb`, Python, Git and curl tooling;
- exactly one ADB-visible device;
- exact match to the private registered-device binding;
- successful read-only ADB state/shell probes.

The mutable workflow must serialize commands for that phone and fail closed on any target ambiguity.

Raw workstation ADB commands are troubleshooting-only and are not acceptable baseline evidence or normal delivery control.

## 6. Phone release preparation

All phone release material must come from the exact immutable candidate and canonical/private GitOps path. Do not rebuild a different source revision during the physical sequence.

Required prepared states are:

- primary `first_party_reverse_tunnel` release;
- retained `stock_wireguard_bridge` rollback release/state;
- a verified path back to the exact primary release.

Where an Android APK is part of the selected release operation, certificate continuity and retained signed rollback artifacts must satisfy `docs/operations/phone-gitops-runtime.md`. A locally generated replacement key is forbidden.

Before activation, verify package metadata and integrity against the exact candidate evidence. After activation, verify the actual phone state against the expected immutable release identity.

## 7. Baseline physical sequence

The physical sequence is executed against the same fresh Item 20 acceptance VM and the same immutable candidate SHA throughout.

### Stage A — primary online

Required state:

- primary owner `first_party_reverse_tunnel`;
- no active Android VPN owner;
- no `tun0` requirement;
- fresh QUIC reverse-tunnel authority;
- durable heartbeat and serving/cellular/proxy readiness.

Prove all protected proxy surfaces through the real phone path:

- SOCKS5 on mixed `1080`;
- HTTP on mixed `1080`;
- HTTPS CONNECT on mixed `1080`;
- SOCKS5 on `1081`;
- HTTP on `3128`;
- HTTPS CONNECT on `3128`.

### Stage B — phone/service reboot recovery

Perform the approved bounded reboot/restart action through the private phone workflow. Do not clear canonical relay durable state.

After recovery prove:

- exact phone target remains the registered device;
- expected release identity is unchanged;
- durable state rehydrates;
- heartbeat becomes fresh;
- primary QUIC reconnects;
- all six protected proxy paths pass again.

### Stage C — forced TLS/TCP reserve

The public Item 20 server-side test helper, operating only on the already verified Item 20 acceptance target, must block the QUIC path while leaving certificate-pinned TLS/TCP reserve reachable.

This is a bounded test action against the verified acceptance target, not a new provider lifecycle selection.

Force a new connection and prove:

- fresh `tls_tcp` reserve authority;
- no plaintext downgrade;
- unchanged device identity;
- all six protected proxy paths pass.

### Stage D — return to QUIC

Remove the bounded QUIC fault, terminate/restart the reserve connection using the approved service control for the verified acceptance target, then prove new fresh QUIC authority and all protected proxy paths.

### Stage E — stock WireGuard rollback

Activate the already prepared rollback state through the private phone workflow and the approved server-side configuration action on the same verified acceptance target.

Prove:

- Android VPN owner is `com.wireguard.android`;
- expected WireGuard tunnel is active;
- `tun0`/equivalent rollback interface state matches the accepted contract;
- recent WireGuard handshake exists;
- first-party reverse tunnel is inactive as required by rollback mode;
- protected proxy behavior required by the rollback contract passes.

### Stage F — return to exact primary

Reactivate the exact previously accepted primary release/state without rebuilding it.

Prove:

- WireGuard is disabled;
- Android VPN owner is absent;
- rollback tunnel state is gone;
- exact primary phone release identity is restored;
- fresh QUIC authority returns;
- all six protected proxy paths pass;
- final server and phone identities still match the original immutable candidate.

## 8. Evidence and report-set invariants

The final physical acceptance summary must prove one coherent tuple:

```text
exact immutable candidate SHA
+ exact protected Item 20 control-plane SHA
+ immutable candidate evidence
+ Item 19 acceptance authority/preflight/provider-proof lifecycle evidence
+ fresh Item 20 acceptance-session evidence
+ exact server artifact identity
+ exact private phone release identity
+ one registered physical device binding
+ all required physical stages
```

Evidence from different candidate SHAs, different control-plane sessions, different server artifact digests or a rebuilt phone release cannot be combined.

Public evidence must be bounded and non-secret. Private phone evidence may contain only the minimum sensitive data required for execution/debugging and must not turn the private satellite into canonical project authority.

## 9. Stop conditions

Reject the candidate and stop advancement for any of the following:

- candidate SHA or immutable artifact identity changes during the run;
- protected Item 20 control-plane identity changes during the admitted session;
- Item 19 provider-proof evidence does not match the candidate;
- Item 20 session identity or ownership intent does not match the admitted candidate/control plane;
- server artifact identity cannot be verified;
- provider target would need to be selected by name, IP, list order or arbitrary UUID input;
- more than one resource claims the acceptance ownership intent;
- missing/wrong/conflicting ownership or generation;
- signing-continuity or private-phone binding gate is not satisfied;
- phone target is ambiguous or does not match the private registered binding;
- wrong tunnel or Android VPN owner;
- stale/mismatched tunnel authority;
- plaintext downgrade;
- failed protected proxy path;
- failed reboot/recovery;
- missing/stale WireGuard rollback proof;
- inability to return to the exact primary state;
- any requirement to fall back to GCP, manual provider lifecycle, workstation SSH or public ADB;
- unresolved P0/P1 defect;
- report-set mismatch.

Any software candidate change requires a new immutable candidate and fresh candidate evidence/authority. Any control-plane change after admission requires a fresh Item 20 admission bound to the new protected control-plane SHA.

## 10. Completion boundary

Successful Item 20 physical acceptance authorizes work on Item 21; it does not itself create the final release or grant production-Vultr authority.

Item 21 may create the final immutable release evidence and protected annotated `vMAJOR.MINOR.PATCH` tag only after this physical proof succeeds. Item 22 may perform production promotion only from that accepted final release tuple.
