#!/usr/bin/env bash
set -euo pipefail

# Install the narrow GitHub Actions runner transport override. Run as root in the runner's Ubuntu
# distribution. This script neither calls ADB nor changes Android, Windows, or global IPv6 state.

unit='mobile-proxy-phone-runner.service'
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source_file="$source_dir/mobile-proxy-phone-runner-ipv4-only.conf"
target_dir="/etc/systemd/system/${unit}.d"
target_file="$target_dir/10-ipv4-only.conf"

if [[ "${EUID}" -ne 0 ]]; then
  echo 'run as root' >&2
  exit 64
fi
if [[ ! -f "$source_file" ]]; then
  echo 'canonical override is missing' >&2
  exit 1
fi
if [[ "$(systemctl show "$unit" -p User --value)" != 'mobileproxyphone' ]]; then
  echo 'unexpected runner service identity' >&2
  exit 1
fi

install -d -m 0755 "$target_dir"
install -m 0644 "$source_file" "$target_file"
systemctl daemon-reload
systemctl restart "$unit"
systemctl is-active --quiet "$unit"
systemctl show "$unit" -p Environment --value | grep -Fq 'DOTNET_SYSTEM_NET_DISABLEIPV6=1'
systemctl show "$unit" -p Environment --value | grep -Fq 'DOTNET_SYSTEM_NET_SECURITY_DISABLETLSRESUME=1'
echo 'mobile_proxy_phone_runner_ipv4_override=installed'
