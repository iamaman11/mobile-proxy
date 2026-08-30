# Immutable-SHA Physical Phone Acceptance Runbook

Status: **normative execution contract for Production Baseline item 20; not yet authorized for live execution while item 19 and the mutable-phone gate remain incomplete**.

Canonical roadmap: `docs/PRODUCTION_BASELINE_PLAN.md`  
Item-19 tracker: #124  
Phone GitOps boundary: `docs/operations/phone-gitops-runtime.md`  
Production topology: `contracts/operations/production-topology-v1.json`

## 1. Control-plane boundary

Physical acceptance is split across two deliberately separate execution planes:

```text
public canonical repository
  -> GitHub-hosted item-19 Vultr acceptance lifecycle
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
- provider mutation is performed only through the item-19 typed Vultr lifecycle and durable binding state;
- phone mutation is performed only through the private `android-production` execution boundary.

This runbook describes item 20. It does **not** authorize item-20 phone mutation while item 19 is ACTIVE or while the canonical signing-continuity gate is unresolved.

## 2. Required gates before opening the physical window

All of the following must be true before the first mutable phone action:

1. Items 15, 16, 17 and 18 are `COMPLETE`.
2. Item 19 is live-complete for the exact candidate used by this run:
   - one or zero controlled acceptance-VM semantics proven;
   - exact provider UUID/ownership/generation binding verified;
   - exact-candidate server artifact deployed and verified;
   - no production authority used.
3. The exact full lowercase 40-character candidate SHA has a successful canonical `Quality` push on protected `main` and immutable candidate evidence.
4. Fresh immutable `/accept-candidate <sha>` authority exists for that same SHA.
5. Fresh `/vultr-readonly-preflight <sha>` evidence exists for that same SHA.
6. The private `android-production` read-only preflight passes for exactly the registered device in the same execution window.
7. The signing-continuity gate in #115 / `docs/operations/phone-gitops-runtime.md` is resolved sufficiently to enable a mutable phone workflow.
8. No unresolved P0/P1 defect exists.
9. The final protected `v*` release tag is still absent; item 20 precedes final release publication.

If any gate is absent, stale, ambiguous or belongs to a different SHA, stop before phone mutation.

### Signing gate is not APK-step-specific

The current canonical phone policy states that read-only preflight is the only enabled phone production action until signing continuity is recovered and verified. Therefore the physical window cannot be opened merely because a particular test step does not install `apps/android-app`.

Changing that policy would require an explicit architecture/security decision. It must not be inferred from this runbook.

## 3. Exact candidate and deployment identity

The item-20 workflow must receive the exact accepted candidate SHA and immutable evidence identities from canonical GitHub evidence. It must not select `latest`, a moving branch, an arbitrary artifact or a manually entered provider resource.

Before traffic tests, verify and record bounded evidence for:

- exact candidate SHA;
- canonical Quality run identity;
- immutable candidate artifact identity and digest;
- item-19 acceptance-authority/preflight identities;
- item-19 acceptance lifecycle evidence identity;
- exact server artifact identity/digest;
- exact bound provider UUID represented only in the provider lifecycle evidence allowed by policy;
- exact phone release/package identity;
- private phone execution run identity;
- tester and UTC timestamps.

Never record credentials, private keys, raw phone serials, full proxy URLs or unrestricted logs in public evidence.

## 4. Acceptance VM handoff from item 19

Item 20 does not provision, select or adopt a VM itself.

The server side is handed off from item 19 and is accepted only when the canonical item-19 lifecycle proves:

- `LifecycleScope::Acceptance`;
- exact immutable ownership intent for the candidate;
- provider-assigned immutable UUID is the authority;
- exact project/manager/scope/intent/generation tags;
- complete provider enumeration was used before lifecycle decisions;
- deployed server bytes/manifest/SHA match the exact candidate;
- public listeners and controlled probes required for the physical test are healthy;
- the lifecycle remains under the single item-19 serialized writer.

IP address or DNS name may be supplied to the physical test only as a transport endpoint derived from that already verified target. They are never lifecycle selectors or ownership authority.

Item 20 must not call GCP APIs, Vultr APIs, `gcloud`, a Vultr CLI or a workstation VM-provisioning script.

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

The physical sequence is executed against the same item-19 acceptance VM and the same immutable candidate SHA throughout.

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

The public item-20 server-side test helper, operating only on the already verified item-19 acceptance target, must block the QUIC path while leaving certificate-pinned TLS/TCP reserve reachable.

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
exact candidate SHA
+ immutable candidate evidence
+ item-19 acceptance authority/preflight/lifecycle evidence
+ exact server artifact identity
+ exact private phone release identity
+ one registered physical device binding
+ all required physical stages
```

Evidence from different source SHAs, different server artifact digests or a rebuilt phone release cannot be combined.

Public evidence must be bounded and non-secret. Private phone evidence may contain only the minimum sensitive data required for execution/debugging and must not turn the private satellite into canonical project authority.

## 9. Stop conditions

Reject the candidate and stop advancement for any of the following:

- source SHA or immutable artifact identity changes during the run;
- item-19 lifecycle evidence does not match the candidate;
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

Any source change requires a new immutable candidate and fresh evidence/authority for the new SHA.

## 10. Completion boundary

Successful item-20 physical acceptance authorizes work on item 21; it does not itself create the final release or grant production-Vultr authority.

Item 21 may create the final immutable release evidence and protected annotated `vMAJOR.MINOR.PATCH` tag only after this physical proof succeeds. Item 22 may perform production promotion only from that accepted final release tuple.
