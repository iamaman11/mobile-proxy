# Android signing-generation migration and recovery

Status: **destructive retry blocked pending canonical fix, fresh private repin, fresh signed candidate, and fresh retention**  
Canonical tracker: `#162`  
Package: `com.example.mobileproxy`  
Migration target version: `0.1.4 / 1004`

This document is the bounded operational checkpoint for the one-time Android signing-generation reset. It records only non-secret facts. Signer fingerprints, signing material, raw device identifiers, provider credentials, and raw private phone logs remain outside the public repository.

## Authority model

The canonical public repository is the sole source of migration behavior and acceptance policy. The private production repository is an execution satellite only.

Private production-control workflows share the `issue_comment` event. One owner command therefore fans out to every subscribed workflow. Only the workflow whose command-prefix gate matches may execute its substantive job; unrelated sibling runs finish `skipped`.

A `skipped` sibling run is **not** a migration, recovery, diagnostic, or phone action. Phone state may be inferred only from the matching workflow, its phone job, and its retained evidence.

The control path is:

```text
owner command
  -> global issue_comment fan-out
  -> matching command gate
  -> immutable canonical public authority validation
  -> bounded off-phone/phone job
  -> retained evidence
  -> workflow_run audit/checkpoint
```

## Failed 2026-09-01 attempt

The attempt was authorized from canonical public SHA:

```text
6d8591b680e4b029cd04c0108b4f8e284bba2477
```

with private execution SHA:

```text
4f62d8faaf8b4e0414cbca23ccc4734b6a4355c3
```

The signed candidate build was private run `33516072922`. The destructive migration was private run `33516830166`.

The retained evidence establishes the following bounded sequence:

1. the old installed APK was retained before uninstall;
2. the old package was removed;
3. candidate `0.1.4 / 1004` was installed;
4. candidate version identity was verified;
5. the installed candidate APK matched the exact retained candidate digest;
6. the runtime supervisor restart path was invoked;
7. bounded local health did not become accepted;
8. rollback was attempted;
9. the legacy evidence exposed only aggregate `rollback_succeeded=false`.

The last fact is insufficient to prove whether reinstall of the retained old APK failed or whether a later runtime/bootstrap/health stage failed. Therefore a failed aggregate rollback boolean must not be interpreted as proof that the old APK is absent.

The workflow-run audit/checkpoint for this attempt also reported stale canonical SHA `20702dda4df3b539cac4402503f7a107a20ef38b`. The destructive command gate itself used `6d8591b680e4b029cd04c0108b4f8e284bba2477`; the stale value is an observability defect in the private checkpoint path, not a second authority source.

## Proven code-level recovery gap

The failed canonical migration restarted the existing runtime supervisor after package replacement. The runtime supervisor then reprovisions app-owned cellular egress configuration into device-protected app storage before starting `CellularEgressService`.

A destructive uninstall/install removes app data. The native provisioning path historically used root `create_dir_all()` for:

```text
/data/user_de/0/com.example.mobileproxy/files
```

while the watchdog launches the supervisor under `umask 077`. The provisioning code changed ownership only on the temporary JSON file, not on a newly created `files/` directory. If that directory had to be recreated after app-data destruction, it could remain root-owned and inaccessible to the Android app even though the JSON file itself was chowned to the package UID.

This is a concrete code-level failure mode consistent with the observed sequence: exact APK install and digest verification succeeded, the supervisor restart path ran, but the app-owned egress service/local health did not become accepted.

The exact post-failure phone state must still be established from the matching recovery/diagnostic workflow evidence. The code-level failure mode must not be substituted for missing phone evidence.

## Canonical correction requirements

A corrected migration must satisfy all of the following before another destructive attempt is authorized:

1. after each destructive install, derive the currently installed package UID without recording it;
2. immediately re-prove the registered device before private-storage mutation;
3. require the package device-protected root to exist;
4. create/repair only the package `files/` directory and bind its owner/mode to the current package UID;
5. invoke the canonical runtime bootstrap entrypoint in addition to terminating the exact old supervisor process, so an absent watchdog can also be recreated;
6. verify supervisor, `CellularEgressService`, app-egress port `18080`, and local proxy port `1080` independently;
7. on failure, rollback to the exact retained old APK and verify its version **and exact retained digest**;
8. prepare private storage and bootstrap runtime again after rollback reinstall;
9. retain stage-by-stage rollback booleans plus a bounded failure-stage enum;
10. never record the package UID, raw device identifier, signer fingerprint, credentials, or raw phone logs in public evidence.

The native runtime provisioning path must independently preserve app ownership when it has to create the egress `files/` directory. The migration-side repair remains necessary for this one-time reset because the runtime-supervisor binary already installed on the phone is not automatically replaced merely by changing canonical source.

## Migration evidence v2

The canonical migration report uses `format_version=2` and keeps the aggregate `rollback_succeeded` only as a derived terminal result. The stage evidence distinguishes at least:

```text
failure_stage
rollback_attempted
rollback_existing_package_removed
rollback_apk_reinstalled
rollback_apk_version_verified
rollback_apk_digest_verified
rollback_private_storage_prepared
rollback_runtime_bootstrap_invoked
rollback_runtime_supervisor_running
rollback_cellular_egress_service_running
rollback_local_app_egress_port_ready
rollback_local_proxy_port_ready
rollback_local_health_verified
rollback_failure_stage
rollback_succeeded
```

This makes `rollback_succeeded=false` actionable: operators can determine whether package restoration, exact artifact identity, runtime bootstrap, or local health was the failing stage without exposing sensitive phone data.

## Retry gate

The failed candidate/build chain is not reused after a canonical code change. Another `/android-release-migrate` is forbidden until this exact order has completed:

1. merge the canonical public fix through a topic PR;
2. obtain successful required `Quality Gate` for the exact new protected `main` SHA;
3. correct the stale private migration checkpoint/audit pin while repinning private execution to that same new canonical SHA;
4. ensure build, retention, and migration all execute from the same new private execution revision;
5. build a **new** signed `0.1.4 / 1004` candidate from the exact new canonical SHA;
6. retain the new candidate APK and provenance for at least 30 days before destructive mutation;
7. establish the current installed phone baseline through the matching read-only/recovery evidence and satisfy the expected-old-version gate;
8. only then issue a fresh destructive migration command;
9. retain migration evidence and the emergency old-generation APK;
10. require bounded local health before accepting the new signing generation.

A failed migration is never converted to success by rollback. A successful rollback merely restores a safe baseline from which a later, separately authorized attempt may begin.

## Final release ordering

The signing-generation migration is pre-Item-20 infrastructure. It does not create final release authority.

No final `v0.1.4` Git tag or GitHub Release may be created until physical Item 20 acceptance selects the exact final candidate SHA and all final-release authority gates agree on that same protected `main` SHA.
