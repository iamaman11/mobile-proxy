#!/usr/bin/env bash
# Source this file from WSL before using operator-cli with a phone connected to
# Windows: `. scripts/wsl-android-env.sh`.
# Do not change the caller's shell options: this file is designed to be sourced.

if ! grep -qi microsoft /proc/version 2>/dev/null; then
    echo "wsl-android-env.sh must be sourced from WSL" >&2
    return 1 2>/dev/null || exit 1
fi

if [[ -z "${MOBILE_PROXY_ADB:-}" ]]; then
    export MOBILE_PROXY_ADB=/mnt/c/Users/Bose/AppData/Local/Android/Sdk/platform-tools/adb.exe
fi

if [[ -z "${ANDROID_SDK_ROOT:-}" && -d /mnt/c/Users/Bose/AppData/Local/Android/Sdk ]]; then
    export ANDROID_SDK_ROOT=/mnt/c/Users/Bose/AppData/Local/Android/Sdk
    export ANDROID_HOME="$ANDROID_SDK_ROOT"
fi

echo "Using MOBILE_PROXY_ADB=$MOBILE_PROXY_ADB"
echo "Start Windows ADB first: adb.exe start-server"
echo "Then verify from WSL: $MOBILE_PROXY_ADB devices -l"
