#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
android_sdk="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Android/Sdk}}"

cd "$repo_root"
python3 scripts/check_architecture_boundaries.py
python3 -m unittest discover -s scripts/tests -p 'test_*.py'
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
cargo audit
cargo deny check advisories licenses bans sources
git diff --check

if [[ ! -x "$android_sdk/build-tools/34.0.0/aapt" ]]; then
    echo "Linux Android SDK is missing build-tools; set ANDROID_SDK_ROOT" >&2
    exit 1
fi

cd "$repo_root/apps/android-app"
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
    -u http_proxy -u https_proxy -u all_proxy \
    ANDROID_SDK_ROOT="$android_sdk" ./gradlew --no-daemon \
    testDebugUnitTest lintDebug assembleDebug
