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
- `docs/quick-reference.md` - current proxy parameters and rotate command
- `docs/runtime-layout.md` - current observed production layout on VM and phone

## Reality Check

- this repo is a clean reconstruction, not a recovered copy of the original source tree
- live phone and VM runtimes are the current production reference
- Rust services here are intentionally simpler than the live stack, but they track the same roles and interfaces

## Build

Rust workspace:

```powershell
cd C:\Users\Bose\temp\mobile
cargo build
cargo test
```

Android shell:

```powershell
$env:JAVA_HOME='C:\Program Files\Eclipse Adoptium\jdk-17.0.18.8-hotspot'
$env:Path="$env:JAVA_HOME\bin;C:\Users\Bose\tools\gradle-8.10.2\bin;$env:Path"
cd C:\Users\Bose\temp\mobile\apps\android-app
gradle.bat assembleDebug
```

## Local Stack

Start the reconstructed local stack:

```powershell
cd C:\Users\Bose\temp\mobile
.\scripts\start-local-stack.ps1 -Token replace_me
```

Smoke-test it:

```powershell
.\scripts\test-local-stack.ps1 -Token replace_me
```

## Notes

- the control and operations path is Rust-first through `apps/operator-cli`
- the Android project stays intentionally thin until a Rust-backed mobile UI is chosen
- docs use placeholders for secrets; do not store live credentials in repo-tracked files
