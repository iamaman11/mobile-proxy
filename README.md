# Mobile Proxy

Reconstructed source tree for the live mobile relay, rebuilt as a Rust-first workspace instead of trying to recreate the lost monorepo byte-for-byte.

## Purpose

- keep a local source-of-truth that matches the current production architecture closely enough to rebuild and evolve it
- prioritize reliability and operability over historical fidelity
- keep the Android app as a thin shell and move control logic into Rust

## Layout

- `crates/proxy-core` - shared Rust models, runtime defaults, and proxy metadata
- `apps/operator-cli` - Rust CLI for status, proxy data, and rotation
- `services/host-daemon` - local device API baseline
- `services/control-plane` - registry and readiness service baseline
- `services/relay-gate` - VM-side readiness gate baseline
- `apps/android-app` - minimal Android shell source
- `config/*.example.env` - local example environment files
- `scripts/start-local-stack.ps1` - local dev stack launcher
- `scripts/test-local-stack.ps1` - local dev stack smoke test
- `scripts/device/*.ps1` - device install, verify, and rollback automation
- `scripts/ops/check-fleet.ps1` - fleet readiness and staleness report
- `deploy/device-runtime` - reproducible phone runtime bundle templates
- `deploy/manifests/devices/*.json` - per-device manifest declarations
- `docs/quick-reference.md` - current proxy parameters and rotate command
- `docs/runtime-layout.md` - current observed production layout on VM and phone

## Reality Check

- this repo is a clean reconstruction, not a recovered copy of the original source tree
- live phone and VM runtimes are the current production reference
- Rust services here are intentionally simpler than the live stack, but they track the same roles and interfaces

## Build

Rust workspace:

```powershell
cd \\wsl.localhost\Ubuntu\home\bose\projects\mobile-proxy
cargo build
cargo test
```

Android shell:

```powershell
$env:JAVA_HOME='C:\Program Files\Eclipse Adoptium\jdk-17.0.18.8-hotspot'
$env:Path="$env:JAVA_HOME\bin;C:\Users\Bose\tools\gradle-8.10.2\bin;$env:Path"
cd \\wsl.localhost\Ubuntu\home\bose\projects\mobile-proxy\apps\android-app
gradle.bat assembleDebug
```

## Local Stack

Start the reconstructed local stack:

```powershell
cd \\wsl.localhost\Ubuntu\home\bose\projects\mobile-proxy
.\scripts\start-local-stack.ps1 -Token replace_me
```

Smoke-test it:

```powershell
.\scripts\test-local-stack.ps1 -Token replace_me
```

## Device Runtime Rollout

1. Set required secrets in the shell:

```powershell
$env:MOBILE_PROXY_ADMIN_TOKEN='replace_admin_token'
$env:MOBILE_PROXY_DEVICE_TOKEN='replace_device_token'
$env:MOBILE_PROXY_RELAY_USER='replace_relay_user'
$env:MOBILE_PROXY_RELAY_PASSWORD='replace_relay_password'
```

2. Install a release to a phone:

```powershell
.\scripts\device\install-device.ps1 `
  -ManifestPath .\deploy\manifests\devices\example-device.json `
  -ReleaseId 2026.06.01
```

3. Verify health and public proxy:

```powershell
.\scripts\device\verify-device.ps1 -ManifestPath .\deploy\manifests\devices\example-device.json
```

4. Roll back if needed:

```powershell
.\scripts\device\rollback-device.ps1 -ManifestPath .\deploy\manifests\devices\example-device.json
```

5. Check fleet status:

```powershell
.\scripts\ops\check-fleet.ps1 -ControlPlaneUrl http://34.118.26.142:8080
```

## Notes

- the control and operations path is Rust-first through `apps/operator-cli`
- the Android project stays intentionally thin until a Rust-backed mobile UI is chosen
- docs and manifests use placeholders for secrets; do not store live credentials in repo-tracked files
