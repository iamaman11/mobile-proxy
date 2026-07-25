#!/usr/bin/env python3
"""Enforce the native reverse-tunnel production path and bounded rollback surface."""

from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

ANDROID_NS = "{http://schemas.android.com/apk/res/android}"
PRIMARY_OWNER = "first_party_reverse_tunnel"
ROLLBACK_OWNER = "stock_wireguard_bridge"
REMOVED_OWNER = "first_party_vpn_service"
BASELINE_MARKER = Path("docs/PRODUCTION_BASELINE_PLAN.md")


def _production_rust(path: Path) -> str:
    body = path.read_text(encoding="utf-8")
    return body.split("#[cfg(test)]", 1)[0]


def _require(path: Path, fragments: tuple[str, ...], errors: list[str], root: Path) -> str:
    if not path.is_file():
        errors.append(f"{path.relative_to(root)}: required native-runtime policy file is missing")
        return ""
    body = path.read_text(encoding="utf-8")
    for fragment in fragments:
        if fragment not in body:
            errors.append(f"{path.relative_to(root)}: missing native-runtime invariant {fragment!r}")
    return body


def check_repository(root: Path) -> list[str]:
    if not (root / BASELINE_MARKER).is_file():
        return []

    errors: list[str] = []
    cli = root / "apps/operator-cli/src/cli.rs"
    _require(
        cli,
        (
            f'pub const PRIMARY_TUNNEL_OWNER: &str = "{PRIMARY_OWNER}"',
            "default_value = PRIMARY_TUNNEL_OWNER",
        ),
        errors,
        root,
    )

    device_stack = root / "apps/operator-cli/src/device_stack.rs"
    stack_body = _require(
        device_stack,
        ("validate_tunnel_owner(&args.tunnel_owner)?", "install_device_release"),
        errors,
        root,
    )
    production_stack = stack_body.split("#[cfg(test)]", 1)[0]
    for forbidden in ["install_android_app", "InstallAndroidAppArgs", REMOVED_OWNER]:
        if forbidden in production_stack:
            errors.append(
                f"{device_stack.relative_to(root)}: production device stack must not reference {forbidden!r}"
            )

    support = root / "apps/operator-cli/src/device_support.rs"
    support_body = _production_rust(support) if support.is_file() else ""
    for required in [PRIMARY_OWNER, ROLLBACK_OWNER, "native reverse tunnel requires no active Android VPN"]:
        if required not in support_body:
            errors.append(f"{support.relative_to(root)}: missing native device invariant {required!r}")
    if REMOVED_OWNER in support_body:
        errors.append(f"{support.relative_to(root)}: removed Android VPN owner is still production-supported")

    provision = root / "apps/operator-cli/src/provision.rs"
    provision_body = _production_rust(provision) if provision.is_file() else ""
    for forbidden in [REMOVED_OWNER, "app-wireguard.conf", "wireguardPhonePrivateKeyEnv"]:
        if forbidden in provision_body:
            errors.append(f"{provision.relative_to(root)}: obsolete Android VPN packaging remains: {forbidden}")
    for required in ["validate_host_config", "render_json_template", "ensure_clean_worktree"]:
        if required not in provision_body:
            errors.append(f"{provision.relative_to(root)}: missing fail-closed packaging control {required!r}")

    supervisor_config = root / "services/runtime-supervisor/src/config.rs"
    config_body = _production_rust(supervisor_config) if supervisor_config.is_file() else ""
    for required in ["StockWireguardBridge", "FirstPartyReverseTunnel"]:
        if required not in config_body:
            errors.append(f"{supervisor_config.relative_to(root)}: missing owner {required}")
    for forbidden in ["FirstPartyVpnService", REMOVED_OWNER, "app_tunnel_config"]:
        if forbidden in config_body:
            errors.append(f"{supervisor_config.relative_to(root)}: Android VPN runtime owner remains: {forbidden}")

    supervisor_health = root / "services/runtime-supervisor/src/health.rs"
    health_body = _production_rust(supervisor_health) if supervisor_health.is_file() else ""
    if "kick_first_party_vpn_service" in health_body:
        errors.append(f"{supervisor_health.relative_to(root)}: Android VPN recovery remains active")
    if "kick_stock_wireguard_bridge" not in health_body:
        errors.append(f"{supervisor_health.relative_to(root)}: stock rollback recovery is missing")

    android_adapter = root / "services/runtime-supervisor/src/android.rs"
    android_body = _production_rust(android_adapter) if android_adapter.is_file() else ""
    for forbidden in ["com.example.mobileproxy", "SET_TUNNEL_CONFIG", "START_TUNNEL"]:
        if forbidden in android_body:
            errors.append(f"{android_adapter.relative_to(root)}: first-party Android VPN command remains: {forbidden}")
    for required in ["com.wireguard.android", "stop_compatibility_vpns"]:
        if required not in android_body:
            errors.append(f"{android_adapter.relative_to(root)}: rollback compatibility control is missing: {required}")

    manifest = root / "apps/android-app/src/main/AndroidManifest.xml"
    if not manifest.is_file():
        errors.append(f"{manifest.relative_to(root)}: optional Android scaffold manifest is missing")
    else:
        try:
            application = ET.parse(manifest).getroot().find("application")
        except ET.ParseError as error:
            errors.append(f"{manifest.relative_to(root)}: manifest XML is invalid: {error}")
            application = None
        if application is None:
            errors.append(f"{manifest.relative_to(root)}: application element is missing")
        else:
            if application.get(f"{ANDROID_NS}allowBackup") != "false":
                errors.append(f"{manifest.relative_to(root)}: optional app backup must be disabled")
            services = application.findall("service")
            vpn = next(
                (
                    service
                    for service in services
                    if service.get(f"{ANDROID_NS}name") == ".MobileProxyVpnService"
                ),
                None,
            )
            if vpn is None:
                errors.append(f"{manifest.relative_to(root)}: optional VPN scaffold service is missing")
            elif vpn.get(f"{ANDROID_NS}exported") != "false":
                errors.append(f"{manifest.relative_to(root)}: optional VPN scaffold must not be exported")

    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = check_repository(root)
    if errors:
        print("native runtime policy validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("native runtime policy validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
