# WSL workstation with a Windows-connected Android phone

Use Windows as the ADB server owner and invoke its `adb.exe` through WSL
interop. This keeps the phone USB connection on Windows while allowing the Rust
operator tools to run from the repository in WSL.

## One-time Windows setup

In a Windows PowerShell window, start the server and confirm that the device is
authorized:

```powershell
& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" start-server
& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" devices -l
```

The device must appear as `device`, not `unauthorized` or `offline`.

## WSL shell setup

From the repository, source the tracked setup file:

```bash
. scripts/wsl-android-env.sh
"$MOBILE_PROXY_ADB" devices -l
```

It selects the Windows SDK `adb.exe`, and the operator CLI honors
`MOBILE_PROXY_ADB` before all automatic discovery. This makes every command use
the same Windows-owned server and USB device.

If a workstation has already verified a Windows ADB server reachable from WSL
over TCP, it may explicitly use the Linux client instead:

```bash
export MOBILE_PROXY_ADB=/usr/bin/adb
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
```

When `ADB_SERVER_SOCKET` is set and `MOBILE_PROXY_ADB` is not, the operator CLI
prefers `/usr/bin/adb`; it never starts a second Linux ADB server.

## Android quality build

On WSL, run:

```bash
cargo run -p operator-cli -- install-android-app --skip-install
```

The command copies the Android project to `C:\Users\Bose\mobile-proxy-android-build`,
uses the Windows JDK when present, and runs unit tests, lint and debug APK
assembly through `gradlew.bat`. `scripts/quality-gate.sh` selects this path
automatically on WSL; GitHub Actions continues to use the Linux SDK path.

## Device gate

Before packaging or installing a release, verify the exact phone:

```bash
"$MOBILE_PROXY_ADB" -s <serial> shell getprop ro.product.cpu.abilist
"$MOBILE_PROXY_ADB" -s <serial> shell su 0 sh -c id
```

The current native runtime requires `armeabi-v7a` compatibility and root
access. Continue with [the physical acceptance runbook](physical-phone-acceptance-runbook.md)
only from a clean immutable candidate and its matching evidence artifact.
