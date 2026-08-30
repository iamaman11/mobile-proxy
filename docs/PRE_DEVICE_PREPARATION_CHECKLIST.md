# Pre-Device Preparation Checklist

> **STATUS: CURRENT GITOPS PREPARATION GATE**
>
> This checklist covers preparation before Production Baseline item 20 opens the mutable physical-phone window. It is candidate-relative: it must never hardcode an old SHA, artifact ID, provider instance or workstation path as current authority.
>
> It does not authorize phone mutation, provider mutation, final release publication or production promotion.

Canonical roadmap: `docs/PRODUCTION_BASELINE_PLAN.md`  
Item-19 tracker: #124  
Physical runbook: `docs/physical-phone-acceptance-runbook.md`  
Phone boundary: `docs/operations/phone-gitops-runtime.md`

## 1. Canonical status

Before preparing a physical run, confirm from current canonical repository state:

- [ ] items 15–18 are `COMPLETE`;
- [ ] item 19 is the active/first unfinished item until its live proof completes;
- [ ] item 20 has not been pulled forward;
- [ ] no final protected `v*` tag has been created before physical acceptance;
- [ ] `production-vultr` has not been used for acceptance;
- [ ] GCP/Google Cloud is not being used as an acceptance or production fallback.

If repository state conflicts with an old checklist, comment, artifact or remembered SHA, current protected repository state and the canonical roadmap win.

## 2. Exact current candidate

Do not copy a candidate identity from this document. Resolve the then-current immutable candidate from canonical GitHub evidence and record:

- [ ] exact full lowercase 40-character SHA;
- [ ] successful canonical `Quality` push run on protected `main` for that SHA;
- [ ] immutable `software-release-candidate-<sha>` artifact identity;
- [ ] artifact digest;
- [ ] evidence format and required physical-acceptance flag;
- [ ] `baseline_complete=false` before physical acceptance.

If source changes after these values are recorded, discard the preparation tuple and resolve a fresh candidate.

## 3. Item-19 Vultr readiness

No idle acceptance VM is created merely to complete this checklist.

Before the first item-19 provider mutation, verify for the exact same candidate SHA:

- [ ] fresh `/accept-candidate <sha>` immutable acceptance authority;
- [ ] fresh `/vultr-readonly-preflight <sha>` evidence;
- [ ] item-19 durable lifecycle state and typed Vultr client are protected on `main`;
- [ ] bounded item-19 lifecycle workflow is protected on `main`;
- [ ] the physical acceptance window is genuinely ready;
- [ ] the single repository-wide acceptance lifecycle concurrency boundary is active;
- [ ] only `LifecycleScope::Acceptance` can be used;
- [ ] `production-vultr` is unreachable from the item-19 path.

Provider target invariants:

- [ ] provider-assigned immutable UUID is the only resource identity authority;
- [ ] exact project/manager/scope/intent/generation ownership metadata is required;
- [ ] full bounded provider enumeration is used before lifecycle decisions;
- [ ] name, label, IP and provider list order are not selectors;
- [ ] create is durably fenced before provider POST;
- [ ] an ambiguous dispatched create is never blindly retried;
- [ ] delete is durably fenced for the exact verified binding;
- [ ] binding is cleared only after provider-confirmed deletion;
- [ ] terminal candidate intent cannot restart at generation 1.

## 4. Server artifact preparation

The acceptance VM server release must come from the exact candidate and the canonical GitHub-hosted item-19 execution path.

Prepare and verify:

- [ ] exact server artifact name and digest;
- [ ] deployment manifest/release metadata contains the exact candidate SHA;
- [ ] deployed bytes/manifest identity can be verified after deployment;
- [ ] required proxy listeners `1080`, `1081`, `3128` are configured as intended;
- [ ] QUIC primary endpoint and pinned TLS/TCP reserve endpoint are configured;
- [ ] controlled HTTP/HTTPS probes are available;
- [ ] a bounded, reversible mechanism exists to force only the QUIC failure used by item 20;
- [ ] WireGuard rollback server configuration is prepared but does not become provider ownership authority.

Do not use `gcloud`, a GCP VM manifest, a manually reserved GCP IP, Vultr CLI, or workstation SSH as the normal control plane.

## 5. Phone execution readiness

The physical phone is controlled only through private `iamaman11/mobile-proxy-production` execution on the `android-production` runner.

Prepare, without publishing the raw device identifier:

- [ ] exact phone manufacturer/model and Android build information;
- [ ] root/boot procedure for that exact device;
- [ ] SIM/operator and expected cellular conditions;
- [ ] USB/ADB transport is available to the dedicated runner;
- [ ] private `ANDROID_PRODUCTION_SERIAL` binding is configured;
- [ ] read-only private Actions preflight can prove exactly one matching registered device;
- [ ] runner has required `adb`, Python, Git and curl tooling;
- [ ] runner is not given Vultr credentials or unrelated broad PATs.

Raw workstation ADB may be used only for troubleshooting and is not accepted as the normal baseline execution/evidence path.

## 6. Mandatory signing-continuity gate

Current policy permits only read-only phone preflight until #115 / `docs/operations/phone-gitops-runtime.md` is satisfied.

Before any mutable phone workflow is enabled:

- [ ] recover the certificate identity of the installed Android application;
- [ ] independently verify signing continuity;
- [ ] store the corresponding keystore/alias/password values only in the private execution boundary;
- [ ] retain a verified signed rollback APK/release where APK lifecycle is part of the operation;
- [ ] ensure the same private run re-proves the exact registered-device binding before mutation;
- [ ] serialize mutable operations for the phone;
- [ ] verify installed/active state after each mutation.

The physical acceptance runbook not requiring an APK install in every stage does **not** bypass this mutable-phone gate. A newly generated replacement signing key is forbidden unless an explicit destructive signing-lineage migration is separately approved.

## 7. ABI and runtime compatibility

Before any phone release installation/activation step, query the selected phone through the private execution path and verify the candidate binaries support its ABI.

Required checks include the device equivalents of:

```text
getprop ro.product.cpu.abilist
getprop ro.product.cpu.abi
```

- [ ] candidate runtime binaries support the actual device ABI;
- [ ] if the device is 64-bit-only and the candidate lacks the required `aarch64-linux-android` payload, stop;
- [ ] any ABI fix produces a new immutable candidate and fresh item-19/20 evidence rather than mutating the frozen candidate.

## 8. Phone release variants

From the exact immutable candidate, prepare only the release material required by the approved GitOps workflows:

- [ ] primary `first_party_reverse_tunnel` state;
- [ ] stock `stock_wireguard_bridge` rollback state;
- [ ] exact reactivation path back to the same primary state;
- [ ] integrity metadata/digests for each retained artifact;
- [ ] no rebuild during the physical sequence.

Secrets must be references/Actions secrets, not literals in manifests or reports.

## 9. Secret separation

Required trust roles remain distinct. Exact values are never recorded here.

- [ ] provider credentials exist only in the scoped public GitHub-hosted Vultr execution environment;
- [ ] phone target/signing secrets exist only in the private phone execution boundary;
- [ ] provider credentials are absent from the private phone runner;
- [ ] raw phone binding/signing secrets are absent from public Vultr workflows;
- [ ] host/control-plane/device/proxy credentials are not reused across trust roles;
- [ ] credentials are not placed in command-line URLs or public evidence;
- [ ] reports contain only bounded non-secret summaries.

## 10. Controlled network/probe readiness

Prepare:

- [ ] canonical relay name/endpoint derived from the verified acceptance VM;
- [ ] certificate/pin material required by the exact candidate;
- [ ] deterministic controlled HTTP probe;
- [ ] deterministic controlled HTTPS probe;
- [ ] external test client/network for public proxy paths;
- [ ] documented expected behavior for mixed `1080`, SOCKS5 `1081`, HTTP/CONNECT `3128`;
- [ ] documented fault/recovery sequence for QUIC -> pinned TLS/TCP -> QUIC;
- [ ] documented WireGuard rollback and return-to-primary sequence.

The VM IP or DNS name is a transport endpoint after provider target verification, never provider lifecycle authority.

## 11. Evidence workspace

Prepare bounded evidence slots for:

- [ ] candidate identity and immutable artifact digest;
- [ ] current acceptance-authority evidence;
- [ ] current Vultr read-only preflight evidence;
- [ ] item-19 lifecycle/deployment evidence;
- [ ] exact server artifact/deployed identity;
- [ ] private phone preflight result;
- [ ] primary-online physical result;
- [ ] post-reboot result;
- [ ] forced TLS/TCP fallback result;
- [ ] QUIC recovery result;
- [ ] WireGuard rollback result;
- [ ] primary-reactivation result;
- [ ] final physical acceptance summary.

Do not predefine a mutable VM project/zone/instance tuple. The item-19 durable provider binding is the authority.

## 12. Dry validation before the live window

- [ ] permanent repository architecture/consistency checks pass;
- [ ] all item-19 typed lifecycle/state tests pass;
- [ ] incomplete or conflicting evidence is rejected;
- [ ] wrong/missing ownership metadata is rejected;
- [ ] duplicate provider ownership claims are rejected;
- [ ] stale generation and forked durable state are rejected;
- [ ] terminal intent reuse is rejected;
- [ ] wrong certificate/token/credentials fail without secret reflection;
- [ ] server rollback/fault helpers operate only on an already verified item-19 target;
- [ ] no GCP/current-workstation fallback remains in normative acceptance docs;
- [ ] no unresolved P0/P1 defect exists.

## 13. Ready-to-open decision

The physical acceptance window is ready only when all of these are simultaneously true:

1. exact current candidate/evidence are frozen and verified;
2. item-19 implementation is protected on `main`;
3. fresh exact-SHA acceptance authority and read-only Vultr preflight exist;
4. the exact phone is selected, private runner binding is ready, and ABI compatibility is proven;
5. #115 signing continuity no longer blocks mutable phone execution;
6. required server/phone release material and rollback states are prepared;
7. controlled probes and fault/recovery mechanisms are ready;
8. no source/artifact identity has changed;
9. no final release or production promotion has been pulled forward.

Only then may item 19 perform its JIT live acceptance-VM lifecycle proof and hand the exact verified VM to item 20. The acceptance VM must not be created early simply to keep work moving.
