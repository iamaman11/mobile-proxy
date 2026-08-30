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

The currently installed `com.example.mobileproxy` APK does not share the certificate of the local
debug build. The existing production signing identity has not been recovered into the private
GitHub execution boundary. Therefore a new APK must not be installed with `adb install -r`, and a
new key must not be generated as an implicit replacement: either action would break Android update
continuity or require an explicit destructive migration decision.

Existing public releases publish verified Linux runtime archives and provenance; they do not publish
Android APKs. They are not proof of Android application update capability.

## Required completion path

Before enabling a mutable phone workflow, all conditions below must hold:

1. Recover and independently verify the certificate identity of the installed Android application.
2. Place the corresponding keystore, alias and passwords only in private GitHub Actions secrets.
   The public repository records the secret names and signing contract, never values or derivatives.
3. Build from an annotated immutable canonical tag or verified canonical artifact, then verify the
   release tuple, checksum/provenance and certificate continuity before ADB mutation.
4. Allow a requested `install`, `update` or `rollback` only after the read-only preflight passes in
   the same private run and the exact registered-device binding is re-proven.
5. For rollback, use a retained, verified, previously accepted **signed** APK for the selected
   immutable release tuple. Rebuilding an old revision during an incident is forbidden.
6. Serialize mutable commands per phone, verify the installed version and health after each action,
   and write only bounded non-secret evidence.

If any condition is missing, ambiguous or mismatched, the workflow must stop before mutation.

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
