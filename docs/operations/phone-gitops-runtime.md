# Phone GitOps runtime checkpoint

Status: **normative production-phone execution boundary**  
Canonical repository: `iamaman11/mobile-proxy`  
Private execution satellite: `iamaman11/mobile-proxy-production`

This document records safe canonical policy and bounded execution facts. It does not contain credentials, signer fingerprints, device identifiers, workstation paths, provider identifiers or raw device logs. The public repository remains the sole source of project architecture, workflow policy, release identity and acceptance policy; the private repository is execution-only.

Final release authority ordering is defined by `docs/operations/final-release-authority-order.md` and `contracts/operations/final-release-authority-v1.json`.

## Verified production execution boundary

```text
exact immutable canonical public SHA
  -> thin private execution caller
  -> [self-hosted, Linux, X64, android-production] runner
  -> registered physical phone
  -> bounded private evidence
  -> safe canonical result
```

The public repository has no self-hosted runner or public ADB workflow. The private runner has no Vultr credentials or unrelated GitHub token authority. A registered-device proof is required immediately before every mutable phone operation; first-attached-device discovery is forbidden.

The canonical read-only preflight proves the required runner labels/tools, exactly one ADB-visible registered target, `adb get-state`, a read-only shell probe and `mutation_performed=false` without recording the raw device identifier.

## Windows USB bridge boundary

Windows owns the physical USB controller while the private runner operates in the owner's Ubuntu
WSL distribution. A cable connection alone therefore does not restore WSL ADB after a Windows
restart. `scripts/device/mobile-proxy-usb-bridge.ps1` is the canonical long-running USB bridge;
`scripts/device/install-mobile-proxy-usb-bridge.ps1` installs its owner-logon Scheduled Task.

The installer accepts exactly one matching device, records one physical USB bus for the task, and
the bridge subsequently attaches only that bus with the expected hardware ID. It never calls ADB
shell commands or mutates the phone. If WSL's delayed USB event has standard permissions, its
local recovery loop reapplies permissions only for that expected VID:PID and resets only the local
runner ADB server. A missing, replaced or ambiguous device fails closed, after which the existing
private exact-device ADB preflight blocks all phone work. Other USB buses are not attached or
modified.

The task deliberately runs only after the WSL owner's logon: a Windows `LocalSystem` service cannot
access a per-user WSL distribution. Fully unattended recovery while no user has logged in requires
a separately provisioned headless Windows/Android host; it is outside this workstation runner's
trust boundary.

## GitHub runner IPv4 transport override

The private Linux runner is a .NET process. If the WSL network advertises IPv6 but cannot complete
TLS to GitHub Actions endpoints over IPv6, the runner can remain locally active while GitHub marks
it offline. `mobile-proxy-phone-runner-ipv4-only.conf` scopes
`DOTNET_SYSTEM_NET_DISABLEIPV6=1`, `DOTNET_SYSTEM_NET_SECURITY_DISABLETLSRESUME=1` and
`DOTNET_SYSTEM_NET_HTTP_SOCKETSHTTPHANDLER_HTTP2SUPPORT=0` to that one systemd unit. The latter two
avoid a TLS-terminating network path aborting a resumed .NET `SslStream` session or an HTTP/2 Actions
broker channel; HTTPS over HTTP/1.1 remains available. Neither setting disables IPv6 globally or
changes any phone network setting. The matching installer verifies the expected unprivileged runner
identity, installs the drop-in and restarts only the runner listener.

The override is appropriate only after confirming the failure mode: GitHub Actions TLS works over
IPv4 and fails over IPv6 for the same runner identity. Its rollback is removal of the exact systemd
drop-in followed by a listener restart. A GitHub `online` runner status and the existing exact-device
ADB preflight remain required before phone work.

## Android production role

The Android app is **not the primary reverse-tunnel owner**. The normal `first_party_reverse_tunnel` mode is rooted/native and does not require an active Android VPN or APK-owned tunnel.

The app is nevertheless a **managed production auxiliary component** for topologies that use `first_party_android_egress` / cellular `Network.bindSocket()` egress and for the app-owned WireGuard compatibility path. Therefore the statement “the production stack never installs the APK” is not valid globally.

For a native topology that does not use an app function, APK installation is not a prerequisite. For a production topology that does use the Android auxiliary path, acceptance evidence must bind the exact canonical source SHA to the installed package, versionName/versionCode, signer-match boolean, retained signed artifact digest/provenance and resulting bounded runtime health. Signing continuity and managed update/migration are production lifecycle requirements for that topology.

## Android signing generation reset

The production package identity is `com.example.mobileproxy`. The historical installed application was built under an unrecoverable signing identity, so #162 defines the only authorized destructive signing-generation migration path. It retains the exact installed APK, proves the installed signer without publishing the fingerprint, installs a candidate signed by the private production identity, verifies the new generation, and retains rollback evidence. This narrow migration does not authorize unrelated phone/network/provider mutation.

Signing secrets live only in the private repository Actions secret boundary. Public or canonical evidence records no keystore material, password, alias, signer fingerprint or secret-derived identifier.

### Version identity versus final release authority

For release `X.Y.Z`:

- final Git tag, when later authorized: `vX.Y.Z`;
- workspace package version: `X.Y.Z`;
- Android `versionName`: `X.Y.Z`;
- Android `versionCode`: `X * 1_000_000 + Y * 1_000 + Z`.

The first candidate of the new signing generation is `versionName=0.1.4`, `versionCode=1004`. Version metadata may exist on the protected pre-release candidate so the exact signed migration candidate can be built and verified. Version metadata is not release authority.

No final `v0.1.4` tag or GitHub Release is an input to the signing-generation migration. The migration is bound to an exact canonical SHA plus retained signed-candidate evidence from that same SHA. The final tag remains forbidden until Item 20 accepts that same exact SHA and #135 records `final_accepted_candidate_sha`.

### Exact-app build proof

The signed APK must be built off the phone runner from the exact immutable canonical SHA. Before any phone mutation it must prove:

1. exact clean canonical source;
2. canonical package/version contract;
3. private signing identity usability without exposing secret values;
4. signed release APK creation and signature validity;
5. candidate signer equals the configured private signer as a bounded boolean;
6. package `com.example.mobileproxy`, `versionName=0.1.4`, `versionCode=1004`;
7. exact typed artifact digest/provenance and retained candidate identity.

The phone mutation job receives the exact verified APK and bounded evidence, never signing secrets.

### Destructive migration and emergency rollback

Before uninstalling the old package, the canonical migration must:

1. prove the registered device;
2. pull and retain the exact installed `base.apk` privately;
3. verify old package/version and prove its installed signer without publishing the fingerprint;
4. re-run registered-device proof;
5. only then uninstall/install the exact verified candidate;
6. verify package/version/signer match and bounded local/runtime health;
7. roll back automatically to the retained old APK on post-capture failure where the defined rollback path applies.

The migration does not reboot the phone, bounce mobile data or perform unrelated network mutation merely to establish the new signing generation. A rollback result never converts a failed migration into success.

After the new signing generation is accepted, routine update/rollback stays inside that generation using retained previously accepted signed artifacts. Re-entering the old signing generation is another destructive lineage transition and requires separate authority.

## Mutable phone gate

Before enabling any mutable phone workflow:

1. bind the action to one exact immutable canonical SHA/release tuple appropriate to that stage;
2. verify the exact signed APK digest/package/version/signing evidence before ADB mutation when the topology uses the APK;
3. run the registered-device preflight immediately before each mutable operation;
4. serialize mutable commands per production phone;
5. retain the exact rollback artifact instead of rebuilding an old revision;
6. verify resulting installed/runtime state before acceptance;
7. write only bounded non-secret evidence;
8. keep provider lifecycle completely outside the phone runner.

For #162 specifically, authority is the exact canonical SHA plus retained signed-candidate evidence; a final `v*` tag is absent and must not be required. For normal post-release update/rollback, authority is the accepted tagged release tuple.

If any condition is missing, ambiguous or mismatched, the workflow stops before mutation.

## Item 19 / Item 20 handoff

Item 19 provider proof is COMPLETE. It is historical provider-only evidence for candidate `d151dbdd156279e32a5361d304c90f996bd2d565`; that SHA is not active Item 20 release authority. The proof VM was deterministically cleaned up and its terminal ownership intent is never reused.

The physical item-20 window opens only after the Item 19 provider proof is complete and the mutable-phone gate is satisfied. Item 20 then selects the exact current protected public `main` SHA as both `candidate_sha` and `control_plane_sha`, obtains fresh candidate-specific software/authority/preflight/provider evidence, freezes source identity, and opens the protected typed Item 20 acceptance lifecycle under a distinct Item 20 ownership intent.

A protected-main advance after admission invalidates the acceptance window. Item 20 does not inherit candidate-specific authority from historical Item 19 merely because the historical proof is valid.

Fresh immutable `/accept-candidate <sha>` authority and Fresh `/vultr-readonly-preflight <sha>` evidence are required for the exact Item 20 candidate. private Item 20 phone execution must not call Vultr APIs.

After successful physical acceptance, recovery repetitions and soak, #135 records exactly one `final_accepted_candidate_sha` and closes `completed`. Final release authority then requires:

```text
final_accepted_candidate_sha == exact protected main SHA == final tag target SHA == published artifact source SHA
```

Only then may the owner issue `/release-tag vX.Y.Z <sha>` on #90. The tag workflow independently rechecks #115, #135, the marker, exact protected-main equality and exact main Quality.

The private execution satellite consumes canonical immutable identity/evidence; it does not define roadmap, architecture, release policy, provider desired state or acceptance policy.

## Protected Item 20 endpoint handoff design

`contracts/operations/item20-private-handoff-v1.json` defines the future provider-to-phone transport handoff. `candidate_sha` and `control_plane_sha` remain explicit envelope fields for boundary verification, but their values must be exactly equal for the 10/10 window.

The plaintext transport endpoint may cross the trust boundary only after the public typed lifecycle resolves and verifies the exact provider target. It is transport data, never provider identity or mutation authority.

The sealed envelope contains only the same exact candidate/control-plane SHA, a fresh opaque session nonce and the derived endpoint. Provider UUID, provider credentials, phone credentials and other authority selectors are forbidden. The plaintext endpoint is never a workflow input or public evidence.

The public handoff credential is narrowly scoped to dispatch into the private repository; private secret write and content write are forbidden. The private handoff decryption key remains private and is never available to the public job. Public terminal evidence is bounded to non-secret run/result identities and verified cleanup state.

## Private target-binding contract

`ANDROID_PRODUCTION_SERIAL` is a private execution binding used only to select the registered production phone. It must never be replaced by first-device discovery and must not be written to logs, artifacts or Issues.
