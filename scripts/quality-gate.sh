#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
android_sdk="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Android/Sdk}}"
profile="${1:-full}"

cd "$repo_root"
python3 scripts/check_architecture_boundaries.py
python3 -m unittest discover -s scripts/tests -p 'test_*.py'
cargo fmt --all -- --check
git diff --check

if [[ "$profile" == "fast" ]]; then
    exit 0
fi
if [[ "$profile" != "full" ]]; then
    echo "usage: scripts/quality-gate.sh [fast]" >&2
    exit 64
fi

cargo metadata --format-version 1 --locked > /dev/null
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
cargo deny check advisories licenses bans sources

if grep -qi microsoft /proc/version 2>/dev/null \
    && [[ -x /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe ]]; then
    cargo run -p operator-cli -- install-android-app --skip-install
    exit 0
fi

if [[ ! -d "$android_sdk" ]]; then
    echo "Linux Android SDK directory is missing; set ANDROID_SDK_ROOT" >&2
    exit 1
fi

cd "$repo_root/apps/android-app"
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u NO_PROXY \
    -u http_proxy -u https_proxy -u all_proxy -u no_proxy \
    ANDROID_SDK_ROOT="$android_sdk" \
    ANDROID_HOME="$android_sdk" \
    ./gradlew --no-daemon testDebugUnitTest lintDebug assembleDebug
