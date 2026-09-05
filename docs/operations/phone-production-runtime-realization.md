# Rooted-phone runtime realization contract

Status: **normative PRODUCT materialization contract**  
Target: `phone-production`  
Component contract: `contracts/operations/phone-production-release-components-v1.json`  
Realization contract: `contracts/operations/phone-production-runtime-realization-v1.json`

## Purpose

The immutable rooted-phone Product Release must describe not only which PRODUCT bytes belong to `phone-production`, but also how those bytes relate to the runnable **release-relative** device layout. This contract closes that boundary without moving physical deployment authority into PRODUCT.

The Product Release remains an input to Deployment Controller. PRODUCT owns component identity and realization semantics. Deployment Controller owns the absolute device root, mutation intent, staging, atomic activation, process ordering, postcondition, recovery and terminal classification.

## Self-contained Release boundary

`phone-production-release-components-v1.json` includes `runtime-realization-contract` as a required component of the phone runtime tar:

```text
realization/phone-production-runtime-realization-v1.json
```

The normal Product Release component digest machinery binds the exact realization-contract bytes. Therefore changing a release path, disposition, render recipe/input contract or boundary changes the immutable rooted-phone Product Release identity. No second digest or identity mechanism exists.

Controller must consume the realization contract from the verified immutable runtime asset. It must not infer live paths from archive filenames and must not substitute a mutable Git checkout for the Release-bound contract.

## Component dispositions

Every required phone component has exactly one disposition:

- `live-copy` — the immutable component is copied to the exact declared release-relative `release_path`;
- `render-input` — the immutable component is an input to a declared deployment-time renderer and is not itself copied into the live release layout;
- `identity-only` — the component is Release-bound metadata and is not installed as a live runtime file.

The accepted live-copy mapping preserves the historical PRODUCT packager topology:

```text
runtime-supervisor     -> bin/runtime-supervisor
host-daemon            -> bin/host-daemon
sing-box               -> bin/sing-box
magisk-module-prop     -> module.prop
magisk-service         -> service.sh
```

Profiles and templates are explicitly render inputs. In particular, `module/service.sh` is **not** installed at `module/service.sh`; its accepted runnable path is `service.sh`.

## Deployment-derived sensitive runtime files

The runnable release also requires deployment-derived files whose values depend on the target manifest, deployment choice and secrets. Their values must never be published in Product Release evidence.

The realization contract declares the output path, renderer-contract id, normative PRODUCT implementation, immutable Product component inputs and runtime/deployment inputs for:

- required `config/host-daemon.json`;
- required `config/sing-box.json`;
- conditional `config/app-wireguard.conf` for the currently disabled `first_party_vpn_service` owner.

The renderer semantics remain PRODUCT-owned and are anchored to the accepted `operator-cli package-device-release` behavior in `apps/operator-cli/src/provision.rs`. Deployment Controller may implement/execute the declared renderer contract later, but it may not invent alternate input semantics or expose rendered secret values as public Product Release evidence.

Profile selection is explicit: `deviceManifest.operatorProfile`, default `default`, maps only to the three Product Release profile components declared by the realization contract.

## Required runnable postcondition scope

For current production topology, a materialized release is not complete unless these release-relative paths exist with the identity/derived semantics declared by the immutable realization contract:

```text
service.sh
module.prop
bin/runtime-supervisor
bin/host-daemon
bin/sing-box
config/host-daemon.json
config/sing-box.json
```

This is a PRODUCT layout contract only. It does not authorize staging or activation and does not define the absolute phone root.

## Legacy supplemental files

Historical `package-device-release` also creates:

- `bin/curl`;
- `release-metadata.json`;
- `integrity-manifest.json`.

They are explicitly classified as `runtime_required=false` for the current production runtime postcondition. They remain useful packaging/evidence helpers, but Controller must not silently promote them into Product Release runtime identity or use their absence to invent a new deployment failure class without a future PRODUCT contract change.

## Ownership and causal boundaries

The realization contract explicitly preserves these rules:

- Product Release contains no secret values;
- absolute device root belongs to Deployment Controller;
- atomic `current` switching and process stop/start ordering belong to Deployment Controller;
- paths are never inferred from filenames;
- VM/server components are forbidden from `phone-production` realization identity;
- the only pinned third-party runtime target for this bundle remains `sing-box` `android-arm`.

A VM-only artifact or pin change therefore remains causally independent of the rooted-phone realization identity.
