# Android Tunnel Architecture Decision

Date: 2026-06-04

## Decision

Choose option 3 for the production `10/10` architecture:

- build a first-party Android runtime component in `apps/android-app`
- make that component own Android `VpnService`
- remove the production dependency on the stock WireGuard Android app
- keep Rust runtime policy as the control owner
- use sing-box/libbox or a Rust tunnel engine inside our application boundary

This rejects a production dependency on a separate WireGuard companion app. A companion APK is acceptable only as a temporary migration bridge, not as the final architecture.

## Why

The current live blocker is not the WireGuard protocol. The blocker is ownership.

The stock WireGuard Android app can create `tun0` through its UI, and the current VM + phone path becomes healthy after that. Raw shell/root `am broadcast` did not create `tun0`; Android logged background execution blocking, and `com.android.shell` cannot be granted `com.wireguard.android.permission.CONTROL_TUNNELS` because it does not request that permission.

For a no-compromise system, tunnel lifecycle must be owned by our deployable artifact, not by another app's UI, app settings, receiver policy, or permission model.

## Can We Use Only sing-box?

Not as the current CLI-only deployment.

The phone sits behind mobile NAT/CGNAT. A proxy listener on the phone is not reachable from the VM unless the phone first creates an outbound overlay or reverse tunnel to the VM.

The current working reachability layer is:

```text
VM public proxy -> VM wg0 10.66.66.1 -> phone tun0 10.66.66.2 -> phone sing-box -> mobile carrier IP
```

`sing-box` can remain the proxy/tunnel engine, but the Android application must own the VPN/TUN lifecycle. Running the existing `sing-box` CLI on the phone without an app-owned `VpnService` does not solve VM-to-phone reachability.

## Target Shape

Phone:

- `apps/android-app`
  - `MobileProxyVpnService`
  - foreground service lifecycle
  - boot receiver
  - one-time Android VPN consent flow
  - local authenticated control endpoint or binder bridge for `runtime-supervisor`
- Rust runtime
  - `runtime-supervisor`
  - `host-daemon`
  - health, rotation, state machine, recovery policy
- tunnel engine
  - preferred first implementation: sing-box/libbox or equivalent embedded engine under our APK
  - acceptable protocol: WireGuard or another measured overlay, but not the stock WireGuard app as the owner

VM:

- keep the current Rust-provisioned control-plane, relay-gate, public proxy, and durable state
- adapt relay config to the selected phone-side overlay endpoint

## Acceptance Criteria

- `operator-cli` installs the Android APK and Rust runtime from repo artifacts.
- After one VPN consent on a fresh phone, reboot recovery requires no manual UI action.
- `runtime-supervisor` can request tunnel up/down through our app-owned control path.
- `tun0` or equivalent overlay path is observable from host-daemon health.
- VM control-plane reports `healthy`, `serving=true`, `publicly_serving=true`.
- process kill, phone reboot, VM reboot, and airplane rotation drills pass without stock WireGuard UI.

## Tested Facts

- Current Android project builds via Windows Gradle wrapper from a Windows-path copy of `apps/android-app`.
- Building through the WSL UNC path produced stale APK output and must not be treated as a valid release build path.
- WSL Linux Gradle cannot currently build the Android app against the Windows SDK because the SDK contains Windows build-tools binaries.
- The first app-owned tunnel scaffold is implemented:
  - `MobileProxyVpnService`
  - `TunnelCommandReceiver`
  - `BootReceiver`
  - persistent desired-state flag
  - UI VPN consent entry point
- The APK was built from a Windows-path copy of `apps/android-app` and installed on `SM_A022G`.
- `operator-cli install-android-app --device-serial R58T10QKGBE` now performs that copy/build/install path from Rust.
- Android package manager sees `com.example.mobileproxy/.MobileProxyVpnService` under `android.net.VpnService`.
- Android package manager sees explicit start/stop tunnel command receivers.
- Current phone can run stock WireGuard UI and produce `tun0=10.66.66.2/32`.
- Current phone does not accept raw shell/root broadcast tunnel-up as a reliable programmatic control path.
- Safe `START_TUNNEL` broadcast without VPN consent was tested and did not disrupt the live stock-WireGuard path.

## Remaining Implementation Gap

The first-party app now owns the Android VPN lifecycle surface, but it does not yet contain the real tunnel engine. The next implementation step is to embed or bind a real engine under `MobileProxyVpnService`:

- preferred: sing-box/libbox with the phone-side overlay/reverse-tunnel config under our APK boundary
- acceptable: Rust-owned tunnel engine with JNI or local control from `runtime-supervisor`

The current scaffold intentionally does not replace the live stock-WireGuard tunnel until that engine exists and passes reboot/process/rotation drills.

## Source References

- Android `VpnService`: https://developer.android.com/reference/android/net/VpnService
- Android always-on VPN guide: https://developer.android.com/develop/connectivity/vpn
- sing-box configuration docs: https://sing-box.sagernet.org/configuration/
- WireGuard Android source: https://github.com/WireGuard/wireguard-android
