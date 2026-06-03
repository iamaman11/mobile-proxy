# Device Runtime Bundle

This directory defines the reproducible runtime layout for rooted Android phones.

## Layout

- `templates/host-daemon.base.json` - base daemon config template
- `templates/sing-box.base.json` - base sing-box config template
- `profiles/*.json` - operator profile overlays
- `module/service.sh` - bootstrap-only Magisk start script; it starts `bin/runtime-supervisor`
- `bin/` - required binaries (`runtime-supervisor`, `host-daemon`, `sing-box`)

## Build/Install Contract

1. `scripts/device/install-device.ps1` renders config templates with secrets from environment variables and a per-device manifest.
2. The script pushes a versioned release to `/data/adb/mobile-proxy-node/releases/<release-id>`.
3. `current` is switched atomically to the new release.
4. `service.sh` starts `runtime-supervisor` from `current`.
5. `runtime-supervisor` owns `host-daemon`, `sing-box`, WireGuard kick attempts, route repair attempts, and data-bounce fallback.

## Required Secrets

Set these values in your shell before install/verify:

- `MOBILE_PROXY_ADMIN_TOKEN`
- `MOBILE_PROXY_DEVICE_TOKEN`
- `MOBILE_PROXY_RELAY_USER`
- `MOBILE_PROXY_RELAY_PASSWORD`

## Binary Requirement

`deploy/device-runtime/bin/runtime-supervisor`, `deploy/device-runtime/bin/host-daemon`, and `deploy/device-runtime/bin/sing-box` are required Android ARM binaries and intentionally not committed.
