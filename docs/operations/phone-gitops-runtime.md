# Phone GitOps runtime checkpoint

This document records the verified production-phone execution boundary. It is a safe canonical
summary, not a source of credentials, device identifiers, workstation paths or raw device logs.
The public repository remains the sole source of project architecture and policy; the private
`iamaman11/mobile-proxy-production` repository is an execution satellite only.

Final release authority ordering is defined normatively in
`docs/operations/final-release-authority-order.md` and
`contracts/operations/final-release-authority-v1.json`.

## Verified production execution boundary

The production phone path is:

```text
immutable canonical source SHA
  -> private mobile-proxy-production caller
  -> [self-hosted, Linux, X64, android-production] runner
  -> dedicated unprivileged service identity
  -> ADB transport to the registered physical phone
  -> bounded private evidence
  -> safe canonical result
```

The public repository has no self-hosted runner or ADB workflow. The runner belongs only to the
private execution repository and has no Vultr credentials, unrelated GitHub PAT or normal-job
administrative privilege. Its ADB access is bounded to the registered phone; it is not a discovery
or "first attached device" mechanism.

The canonical read-only preflight proves all of the following without recording a raw serial:

- the exact required runner labels;
- required `adb`, `python`, `git` and `curl` tools;
- exactly one ADB-visible device and exact match to the private registered-device secret;
- successful `adb get-state` and a read-only shell probe;
- bounded evidence with `mutation_performed=false`.

The registered-device proof is not a one-time bootstrap assertion. A mutable workflow must run it
again immediately before each mutable phone operation.

## Android signing generation reset

The original Android application uses package identity `com.example.mobileproxy`. The Android Git
subtree at public tag `v0.1.3` and the subtree immediately before this migration work are identical,
so `v0.1.3` is the immutable functional-source baseline for the signing-generation reset.

The historical installed application was built under an unrecoverable signing identity. Repository
owner approval therefore explicitly authorizes a destructive signing-lineage reset: retain the exact
installed signed APK, uninstall the old package, install a verified APK signed by the new private
production identity, reprovision the new app UID, and establish a new durable signing generation.
This authorization is narrow: it does not authorize unrelated phone, network, provider or runtime
mutation.

The new signing identity is stored only in private repository Actions secrets under these names:

- `ANDROID_RELEASE_KEYSTORE_B64`
- `ANDROID_RELEASE_KEYSTORE_PASSWORD`
- `ANDROID_RELEASE_KEY_ALIAS`
- `ANDROID_RELEASE_KEY_PASSWORD`

A private offline proof has already demonstrated that the keystore opens, the alias is present, the
private-key password is valid, and a temporary signature can be created and verified. Secret values,
certificate fingerprints and secret-derived values are not canonical evidence.

### Version identity versus final release authority

Repository release metadata and Android application metadata use one stable semantic version. For
release `X.Y.Z`:

- final Git tag, when later authorized: `vX.Y.Z`;
- workspace package version: `X.Y.Z`;
- Android `versionName`: `X.Y.Z`;
- Android `versionCode`: `X * 1_000_000 + Y * 1_000 + Z`.

The first candidate of the new signing generation uses Android identity `versionName=0.1.4` and
`versionCode=1004`; the historical `versionName=1.1.0` / `versionCode=2` numbering is not reused.
The workspace/Android `0.1.4` metadata may exist on a protected pre-release SHA so an exact signed
migration candidate can be built and verified. That metadata does **not** itself create final release
authority.

No final `v0.1.4` tag or GitHub Release is an input to the signing-generation migration. The migration
is bound instead to an exact canonical SHA plus retained signed-candidate evidence from that same SHA.
The protected annotated `v0.1.4` tag is an Item 21 output and remains forbidden until Item 20 physical
acceptance has completed and the exact final release control-plane SHA is recorded in #135.

### Exact-app build proof

The signing migration must not silently replace the application with different functional code.
For the `0.1.4` migration candidate, canonical automation compares `apps/android-app` against
`v0.1.3` and allows exactly one Android source-tree difference:
`apps/android-app/app/build.gradle.kts`. That file may differ only because the release identity and
production signing contract are being established. A Kotlin, manifest, resource, embedded library or
other Android functional-source change causes the migration build to fail before phone mutation.

The signed APK must be built from the exact immutable canonical SHA off the phone runner. The build
must verify:

1. exact clean Git source and the `v0.1.3` Android functional baseline;
2. canonical package/version contract;
3. private signing identity usability;
4. signed release APK creation;
5. APK signature validity and signer equality to the configured private key;
6. APK package `com.example.mobileproxy`, `versionName=0.1.4`, `versionCode=1004`;
7. exact typed BLAKE3 APK digest and bounded release evidence.

Signing secrets belong only to this off-phone build/sign job. The self-hosted phone mutation job
must receive the exact signed APK plus bounded typed-digest evidence, but no signing secrets.

### Destructive migration and emergency rollback

Before uninstalling the old package, the phone job must pull and retain the exact currently installed
`base.apk`, record only its typed digest/version metadata, and verify the expected old package
identity. This retained signed APK is the emergency migration rollback artifact. No old source is
rebuilt.

Every uninstall, install and runtime-supervisor restart is separately preceded by the same-run
registered-device proof. The mutation sequence is serialized per production phone:

```text
verified 0.1.4 signed APK from exact canonical SHA
  -> same-run registered-device proof
  -> retain exact installed old signed APK
  -> registered-device proof
  -> uninstall old com.example.mobileproxy
  -> registered-device proof
  -> install exact verified 0.1.4 APK
  -> verify package/version
  -> registered-device proof
  -> terminate only the exact current runtime-supervisor process
  -> existing watchdog restarts runtime-supervisor
  -> runtime-supervisor reprovisions the new Android UID
  -> verify CellularEgressService + local egress/proxy ports
  -> retain accepted 0.1.4 signed APK for future rollback
```

`deploy/device-runtime/module/service.sh` already owns runtime-supervisor through a watchdog. The
migration therefore does not reboot the phone, bounce mobile data, alter routes or restart the whole
runtime module. It terminates only the exact current `runtime-supervisor`; the watchdog restarts it,
which resets its in-memory provisioning state and causes credentials to be provisioned for the new
Android UID.

If the new package cannot be installed or cannot reach the bounded local-health gate, the migration
must attempt a fail-closed destructive rollback: remove any newly installed package, reinstall the
exact retained old signed APK, restart only runtime-supervisor through the same watchdog mechanism,
and verify the restored local egress path. A rollback result never converts a failed migration into a
successful migration result.

After the 0.1.4 candidate is accepted as the new signing generation, normal update/rollback lifecycle
is inside the new signing generation. Future routine rollback uses a retained previously accepted APK
signed by the new production key. The old signing generation is not an update-compatible rollback
target; using its retained APK again would require another explicit destructive uninstall/install
action and separate authority.

## Mutable phone gate

This is a workflow-level phone-mutation gate, not only an APK-install gate. The explicit signing-lineage
reset narrows the old signer-continuity blocker only for the exact canonical #162 migration workflow;
it does not gate the public canonical provider-only Item 19 proof or grant unrelated mutable-phone
authority.

Before enabling **any mutable phone workflow**, the workflow must satisfy all of these conditions:

1. Bind the action to one exact immutable canonical source/release tuple appropriate to that stage.
2. Verify the exact signed APK typed digest, package/version metadata and signing evidence before ADB
   mutation.
3. Run the registered-device preflight immediately before every mutable operation.
4. Serialize mutable commands per production phone.
5. Retain the exact previously accepted signed rollback APK; never rebuild an old revision during an
   incident.
6. Verify resulting installed state and bounded health before acceptance.
7. Write only bounded non-secret evidence.
8. Keep provider lifecycle completely outside the phone runner; the private runner must never receive
   Vultr credentials or become provider-state authority.

For the one-time #162 signing-generation migration specifically, the immutable authority is the exact
canonical SHA plus retained signed-candidate evidence; a final `v*` tag is explicitly absent and must
not be required. For later normal post-release update/rollback, the immutable authority is the final
accepted tagged release tuple defined by the normal lifecycle.

If any condition is missing, ambiguous or mismatched, the workflow must stop before mutation.

## Item 19 / item 20 handoff

Production Baseline item 19 proves the JIT Vultr **acceptance** lifecycle only from the public
canonical GitHub-hosted control plane. Its live proof is provider-only and ephemeral: create at most
one controlled VM, deploy and verify the exact candidate, then deterministically delete it and commit
the durable terminal state. Item 19 performs no phone mutation and does not consume #115.

The narrow #162 signing-generation migration is a pre-Item20 prerequisite that may execute only under
its explicit owner-approved destructive authorization and exact migration gates. Successful migration
establishes the new Android signing generation; it does not create Item 20 acceptance or final release
authority. #115 is closed `completed` only when its actual acceptance criteria are satisfied.

The physical item-20 window opens only after the Item 19 provider proof is complete **and** #115 is
closed `completed`. Item 20 then opens a fresh one-at-a-time acceptance server session through the
protected typed lifecycle under a distinct Item 20 ownership intent; the terminal Item 19 proof intent
is never reused. The fact that an item-20 stage may activate existing native files rather than install
`apps/android-app` does not bypass the phone gate above.

After successful Item 20 physical acceptance, #135 records the exact
`final_release_control_plane_sha` and closes `completed`. Only then may the owner issue the final
`/release-tag vX.Y.Z <sha>` command on canonical tracker #90. The tag workflow independently rechecks
#115, #135, the exact marker and exact main Quality before creating an annotated tag.

The private execution satellite consumes canonical immutable identity/evidence; it does not define
roadmap, architecture, release policy, provider desired state or acceptance policy.

### Protected Item 20 endpoint handoff design

`contracts/operations/item20-private-handoff-v1.json` defines the future public-provider to
private-phone transport handoff. The plaintext transport endpoint may cross the repository boundary
only after the public typed lifecycle has resolved and verified the exact Item 20 provider target.
The endpoint is transport data, never provider identity or mutation authority.

The required handoff is:

```text
verified Item 20 target
  -> derived transport endpoint
  -> seal candidate_sha + control_plane_sha + fresh session_nonce + endpoint
     to a dedicated private-execution recipient public key
  -> private workflow_dispatch carrying candidate_sha + control_plane_sha + session_nonce + ciphertext
  -> private runner decrypts with ITEM20_HANDOFF_PRIVATE_KEY_B64
  -> exact tuple verification on the private execution boundary
  -> same-window registered-device preflight
  -> bounded private Item 20 execution
```

The plaintext envelope before sealing contains only `candidate_sha`, `control_plane_sha`, a fresh
opaque session nonce and the derived transport endpoint. It must not contain provider UUID, Vultr
credentials, phone credentials or another authority selector. The plaintext endpoint must never be a
workflow input. Only sealed ciphertext may accompany the non-secret tuple in the private dispatch.

A public handoff job may use the reserved `ITEM20_PHONE_HANDOFF_TOKEN` only as a narrowly scoped
credential for `iamaman11/mobile-proxy-production`. Its required private-repository permission is
exactly `Actions: write`. **`Secrets: write` and `Contents: write` are forbidden.** This prevents the
public provider job from replacing private device/signing secrets or private repository content. The
token must never be passed to the self-hosted phone runner.

The private handoff decryption key is a distinct private repository Actions secret named
`ITEM20_HANDOFF_PRIVATE_KEY_B64`. The public job never receives that private key and never writes,
updates or deletes any private repository secret. The implementation uses fail-closed tuple and nonce
matching and deterministic provider cleanup even when private execution fails.

The plaintext endpoint, token, private decryption key and provider UUID must never be written to a
public Issue, artifact, workflow output, step summary or log merely to bridge the two control planes.
Private evidence also does not retain the plaintext endpoint after execution. Public terminal evidence
may record only bounded non-secret identities/results such as exact candidate/control-plane identity,
private workflow run identity/conclusion and provider terminal-cleanup confirmation.

## Private target-binding contract

`ANDROID_PRODUCTION_SERIAL` is a separate private repository secret used only to bind ADB execution
to the registered production phone. It must never be replaced by first-device discovery and must not
be written to logs, artifacts or Issues.
