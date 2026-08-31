# Phone GitOps runtime checkpoint

This document records the verified production-phone execution boundary. It is a safe canonical
summary, not a source of credentials, device identifiers, workstation paths or raw device logs.
The public repository remains the sole source of project architecture and policy; the private
`iamaman11/mobile-proxy-production` repository is an execution satellite only.

## Verified on 2026-08-30

The production phone path is now:

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

Private Actions run `33314469889` passed the canonical read-only preflight for canonical source SHA
`95187bc6b22e991e1b8becac73e468e2020c35db`. The workflow proved all of the following without
recording a raw serial in its report:

- the exact required runner labels;
- required `adb`, `python`, `git` and `curl` tools;
- exactly one ADB-visible device and exact match to the private registered-device secret;
- successful `adb get-state` and a read-only shell probe;
- bounded evidence with `mutation_performed=false`.

No phone install, update, uninstall, restart, network modification, rollback or provider lifecycle
operation was performed for this checkpoint.

## Current fail-closed boundary

Read-only preflight is the only enabled phone production action. The old public deployment route is
blocked, and no raw workstation ADB command is an accepted delivery shortcut.

**This is a workflow-level phone-mutation gate, not only an APK-install gate.** Until the signing-continuity
conditions below are satisfied, the private production boundary must not enable install/update,
release activation, reboot/restart, network mutation, rollback or another mutable phone action merely
because that individual step does not replace the Android APK. This gate applies to the private phone
execution boundary only; it does not gate the public canonical provider-only Item 19 proof, which has
no phone credentials or phone mutation authority. Narrowing the phone gate still requires an explicit
architecture/security decision; it must not be inferred from a runbook.

The currently installed `com.example.mobileproxy` APK does not share the certificate of the local
debug build. The existing production signing identity has not been recovered into the private
GitHub execution boundary. Therefore a new APK must not be installed with `adb install -r`, and a
new key must not be generated as an implicit replacement: either action would break Android update
continuity or require an explicit destructive migration decision.

Existing public releases publish verified Linux runtime archives and provenance; they do not publish
Android APKs. They are not proof of Android application update capability.

## Required completion path

Before enabling **any mutable phone workflow**, all conditions below must hold:

1. Recover and independently verify the certificate identity of the installed Android application.
2. Place the corresponding keystore, alias and passwords only in private GitHub Actions secrets.
   The public repository records the secret names and signing contract, never values or derivatives.
3. Bind the requested mutable action to one exact immutable canonical source/release tuple and verify
   the applicable checksum/provenance and signing-continuity requirements before ADB mutation.
4. Allow mutation only after the read-only preflight passes in the same private run and the exact
   registered-device binding is re-proven.
5. For APK rollback, use a retained, verified, previously accepted **signed** APK for the selected
   immutable release tuple. Rebuilding an old revision during an incident is forbidden.
6. Serialize mutable commands per phone, verify the resulting installed/active state and health after
   each action, and write only bounded non-secret evidence.
7. Keep provider lifecycle completely outside the phone runner; the private runner must never receive
   Vultr credentials or become provider-state authority.

If any condition is missing, ambiguous or mismatched, the workflow must stop before mutation.

## Item 19 / item 20 handoff

Production Baseline item 19 proves the JIT Vultr **acceptance** lifecycle only from the public
canonical GitHub-hosted control plane. Its live proof is provider-only and ephemeral: create at most
one controlled VM, deploy and verify the exact candidate, then deterministically delete it and commit
the durable terminal state. Item 19 performs no phone mutation and does not consume #115.

The physical item-20 window opens only after the Item 19 provider proof is complete **and** this
mutable-phone gate is satisfied. Item 20 then opens a fresh one-at-a-time acceptance server session
through the protected typed lifecycle under a distinct Item 20 ownership intent; the terminal Item 19
proof intent is never reused. The fact that an item-20 stage may activate existing native files rather
than install `apps/android-app` does not bypass the phone gate above.

The private execution satellite consumes canonical immutable identity/evidence; it does not define
roadmap, architecture, release policy, provider desired state or acceptance policy.

### Protected Item 20 endpoint handoff design

`contracts/operations/item20-private-handoff-v1.json` defines the future public-provider to
private-phone transport handoff. The contract is **design-only and not enabled** while #115 is open.
The current private satellite therefore remains read-only and no endpoint secret or mutable Item 20
phone workflow is installed by this checkpoint.

When a later protected implementation is allowed, the transport endpoint may cross the repository
boundary only after the public typed lifecycle has resolved and verified the exact Item 20 provider
target. The endpoint is transport data, never provider identity or mutation authority.

The required future handoff is:

```text
verified Item 20 target
  -> derived transport endpoint
  -> encrypted private-repository Actions secret ITEM20_SESSION_ENVELOPE
  -> non-secret private workflow dispatch containing candidate_sha + control_plane_sha + fresh session_nonce
  -> exact tuple verification on the private execution boundary
  -> same-window registered-device preflight
  -> bounded private Item 20 execution
  -> private envelope deletion and absence confirmation
```

The envelope contains only `candidate_sha`, `control_plane_sha`, a fresh opaque session nonce and the
derived transport endpoint. It must not contain the provider UUID, Vultr credentials, phone
credentials or another authority selector. The dispatch payload must not contain the endpoint.

A future public handoff job may use the reserved `ITEM20_PHONE_HANDOFF_TOKEN` only as a narrowly
scoped credential for the private repository. Its required private-repository permissions are exactly
`Actions: write` and `Secrets: write`. The token must never be passed to the self-hosted phone runner.
The private `ITEM20_SESSION_ENVELOPE` must be encrypted with the private repository Actions public
key before upload and live only for one serialized Item 20 session.

Before replacing a stale envelope, the public control plane must prove that no prior private Item 20
session remains active. A stale envelope must fail exact candidate/control-plane/nonce matching.
After the private run reaches a terminal state, the envelope must be deleted and absence confirmed.
Provider cleanup remains mandatory even if handoff-secret cleanup or private execution fails; an
Item 20 acceptance result cannot be successful until both the private envelope is absent and the
exact provider target has reached deterministic terminal cleanup.

The endpoint, envelope, token and provider UUID must never be written to a public Issue, artifact,
workflow output, step summary or log merely to bridge the two control planes. Private evidence also
does not retain the endpoint after execution. Public terminal evidence may record only bounded
non-secret identities/results such as exact candidate/control-plane identity, private workflow run
identity/conclusion, private-secret absence and provider terminal-cleanup confirmation.

## Private signing-secret contract

The following names are required only after the signing identity is recovered. They belong in
private `iamaman11/mobile-proxy-production` repository Actions secrets, never public Git or issue
text:

- `ANDROID_RELEASE_KEYSTORE_B64`
- `ANDROID_RELEASE_KEYSTORE_PASSWORD`
- `ANDROID_RELEASE_KEY_ALIAS`
- `ANDROID_RELEASE_KEY_PASSWORD`

`ANDROID_PRODUCTION_SERIAL` remains a separate private repository secret for target binding. The
signing identity must not be replaced with a generated key unless an explicit, separate migration
authorizes uninstalling the installed app and establishing a new signing lineage.
