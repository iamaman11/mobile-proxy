#!/usr/bin/env python3
"""Verify exact candidate deployment without creating new internal digest contracts."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from run_physical_phone_acceptance import (
    AcceptanceFailure,
    read_json,
    require,
    verify_candidate,
)

_MANIFEST_NAME = "integrity-manifest.json"
_EXPECTED_ALGORITHM = "blake3-256"
_EXPECTED_DOMAIN = "mobile-proxy/release-file/v1"
_MAX_ENTRIES = 128
_STOCK_WIREGUARD_PACKAGE = "com.wireguard.android"
_SUPPORTED_DEVICE_OWNERS = {"first_party_reverse_tunnel", "stock_wireguard_bridge"}
_DYNAMIC_VM_RELEASE_PATHS = {"nginx/mobile-public-proxy.conf"}
_VM_REMOTE_PATHS = {
    "bin/control-plane": "/opt/mobile-relaycontrolpoint/current/control-plane",
    "bin/relay-gate": "/opt/mobile-relaycontrolpoint/current/relay-gate",
    "bin/reverse-tunnel-server": "/opt/mobile-relaycontrolpoint/current/reverse-tunnel-server",
    "bin/sing-box": "/opt/mobile-public-proxy/sing-box",
    "config/control-plane.env": "/etc/mobile-relaycontrolpoint/control-plane.env",
    "config/relay-gate.env": "/etc/mobile-relaycontrolpoint/relay-gate.env",
    "config/reverse-tunnel-server.env": "/etc/mobile-relaycontrolpoint/reverse-tunnel-server.env",
    "config/wg0.conf": "/etc/wireguard/wg0.conf",
    "config/public-proxy.json": "/opt/mobile-public-proxy/config.json",
    "systemd/mobile-relaycontrolpoint.service": "/etc/systemd/system/mobile-relaycontrolpoint.service",
    "systemd/mobile-relay-gate.service": "/etc/systemd/system/mobile-relay-gate.service",
    "systemd/mobile-public-proxy.service": "/etc/systemd/system/mobile-public-proxy.service",
    "systemd/mobile-reverse-tunnel-server.service": "/etc/systemd/system/mobile-reverse-tunnel-server.service",
    "nginx/mobile-control-plane-tls": "/etc/nginx/sites-available/mobile-control-plane-tls",
}


def _safe_relative_path(raw: Any) -> str:
    require(isinstance(raw, str) and 0 < len(raw) <= 256, "release path is invalid")
    path = PurePosixPath(raw)
    require(not path.is_absolute(), "release path must be relative")
    require(".." not in path.parts and "." not in path.parts, "release path escapes its root")
    require(all(part and part not in {"/", "\\"} for part in path.parts), "release path is invalid")
    return path.as_posix()


def _run_bytes(command: list[str], failure: str) -> bytes:
    try:
        result = subprocess.run(command, check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise AcceptanceFailure(failure) from error
    return result.stdout


def verify_local_release_integrity(root: Path) -> None:
    _run_bytes(
        [
            "cargo",
            "run",
            "--quiet",
            "--release",
            "-p",
            "operator-cli",
            "--",
            "verify-release-integrity",
            "--root",
            str(root),
        ],
        "local release integrity verification failed",
    )


def load_release_inventory(root: Path) -> list[str]:
    try:
        manifest = json.loads((root / _MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AcceptanceFailure("release integrity manifest is unreadable") from error
    require(isinstance(manifest, dict), "release integrity manifest must be an object")
    require(manifest.get("format_version") == 1, "release manifest version is unsupported")
    require(manifest.get("algorithm") == _EXPECTED_ALGORITHM, "release digest algorithm is unsupported")
    require(manifest.get("domain") == _EXPECTED_DOMAIN, "release digest domain is unsupported")
    entries = manifest.get("entries")
    require(isinstance(entries, list) and 0 < len(entries) <= _MAX_ENTRIES, "release inventory is invalid")

    paths: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        require(isinstance(entry, dict), "release inventory entry is invalid")
        relative = _safe_relative_path(entry.get("path"))
        require(relative not in seen, "release inventory contains duplicate paths")
        seen.add(relative)
        digest = entry.get("digest")
        size = entry.get("size_bytes")
        require(
            isinstance(digest, str)
            and digest.startswith("b3:")
            and len(digest) == 67
            and all(character in "0123456789abcdef" for character in digest[3:]),
            "release digest is invalid",
        )
        require(isinstance(size, int) and 0 <= size <= 2**63 - 1, "release size is invalid")
        local = root / relative
        require(local.is_file(), "release inventory file is missing")
        require(local.stat().st_size == size, "release inventory size differs from the packaged file")
        paths.append(relative)
    require(paths == sorted(paths), "release inventory is not path-sorted")
    return paths


def verify_device_release_metadata(root: Path, candidate_sha: str) -> None:
    try:
        metadata = json.loads((root / "release-metadata.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AcceptanceFailure("device release metadata is unreadable") from error
    require(isinstance(metadata, dict), "device release metadata must be an object")
    require(metadata.get("format_version") == 1, "device release metadata version is unsupported")
    require(metadata.get("git_sha") == candidate_sha, "device package SHA differs from candidate")
    require(metadata.get("git_worktree_clean") is True, "device package was built from a dirty tree")


def release_tunnel_owner(root: Path) -> str:
    try:
        config = json.loads((root / "config/host-daemon.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AcceptanceFailure("device host configuration is unreadable") from error
    require(isinstance(config, dict), "device host configuration is invalid")
    wireguard = config.get("wireguard")
    reverse = config.get("reverse_tunnel")
    require(isinstance(wireguard, dict), "device WireGuard configuration is invalid")
    require(isinstance(reverse, dict), "device reverse-tunnel configuration is invalid")
    owner = wireguard.get("owner")
    require(owner in _SUPPORTED_DEVICE_OWNERS, "device release tunnel owner is unsupported")
    if owner == "first_party_reverse_tunnel":
        require(wireguard.get("enabled") is False, "reverse release unexpectedly enables WireGuard")
        require(reverse.get("enabled") is True, "reverse release disables reverse tunnel")
    else:
        require(wireguard.get("enabled") is True, "WireGuard release disables WireGuard")
        require(reverse.get("enabled") is False, "WireGuard release leaves reverse tunnel enabled")
    return owner


def _adb_prefix(serial: str | None) -> list[str]:
    return ["adb", *( ["-s", serial] if serial else [] )]


def _adb_text(serial: str | None, arguments: list[str], failure: str) -> str:
    return _run_bytes([*_adb_prefix(serial), *arguments], failure).decode("utf-8", "strict")


def parse_package_uid(output: str, package: str) -> int | None:
    for line in output.splitlines():
        if f"package:{package}" not in line:
            continue
        for part in line.split():
            if part.startswith("uid:") and part[4:].isdigit():
                return int(part[4:])
    return None


def parse_active_vpn_owner_uid(output: str) -> int | None:
    for line in output.splitlines():
        if "Transports:" not in line or "VPN" not in line or "OwnerUid:" not in line:
            continue
        suffix = line.split("OwnerUid:", 1)[1]
        digits = ""
        for character in suffix:
            if character.isdigit():
                digits += character
            elif digits:
                break
        if digits:
            return int(digits)
    return None


def verify_android_vpn_owner(serial: str | None, expected_owner: str) -> None:
    connectivity = _adb_text(
        serial,
        ["shell", "dumpsys", "connectivity"],
        "failed to inspect Android VPN owner",
    )
    active_uid = parse_active_vpn_owner_uid(connectivity)
    if expected_owner == "first_party_reverse_tunnel":
        require(active_uid is None, "Android VPN remained active during reverse-tunnel deployment")
        return
    packages = _adb_text(
        serial,
        ["shell", "cmd", "package", "list", "packages", "-U", _STOCK_WIREGUARD_PACKAGE],
        "failed to inspect stock WireGuard package",
    )
    expected_uid = parse_package_uid(packages, _STOCK_WIREGUARD_PACKAGE)
    require(expected_uid is not None, "stock WireGuard package UID is missing")
    require(active_uid == expected_uid, "active Android VPN owner is not stock WireGuard")


def verify_device_files(root: Path, paths: list[str], serial: str | None, device_root: str) -> None:
    prefix = _adb_prefix(serial)
    for relative in paths:
        remote = f"{device_root.rstrip('/')}/current/{relative}"
        remote_bytes = _run_bytes(
            [*prefix, "exec-out", "su", "0", "cat", remote],
            "failed to read deployed device release file",
        )
        require(remote_bytes == (root / relative).read_bytes(), "deployed device file differs")


def _write_verification_archive(root: Path, paths: list[str]) -> Path:
    handle = tempfile.NamedTemporaryFile(prefix="mobile-proxy-vm-verify-", suffix=".tar", delete=False)
    handle.close()
    archive = Path(handle.name)
    try:
        with tarfile.open(archive, "w") as bundle:
            for relative in paths:
                bundle.add(root / relative, arcname=relative, recursive=False)
    except Exception:
        archive.unlink(missing_ok=True)
        raise
    return archive


def verify_vm_files(args: argparse.Namespace, root: Path, paths: list[str], candidate_sha: str) -> None:
    expected_inventory = set(_VM_REMOTE_PATHS) | _DYNAMIC_VM_RELEASE_PATHS
    require(set(paths) == expected_inventory, "VM release inventory does not match the supported deployment map")
    static_paths = sorted(_VM_REMOTE_PATHS)
    archive = _write_verification_archive(root, static_paths)
    remote_base = f"/tmp/mobile-proxy-verify-{candidate_sha[:12]}-{os.getpid()}"
    remote_archive = f"{remote_base}.tar"
    target = f"{args.vm_ssh_user}@{args.vm_instance}"
    common = [
        "--project", args.vm_project,
        "--zone", args.vm_zone,
        "--ssh-key-file", args.vm_ssh_key,
        "--tunnel-through-iap",
    ]
    try:
        _run_bytes(
            ["gcloud", "compute", "scp", *common, str(archive), f"{target}:{remote_archive}"],
            "failed to upload exact VM verification payload",
        )
        comparisons = "\n".join(
            f"cmp -s -- {shlex.quote(remote_base + '/' + relative)} {shlex.quote(remote)}"
            for relative, remote in sorted(_VM_REMOTE_PATHS.items())
        )
        command = f"""set -eu
TMP={shlex.quote(remote_base)}
ARCHIVE={shlex.quote(remote_archive)}
cleanup() {{ sudo rm -rf \"$TMP\" \"$ARCHIVE\"; }}
trap cleanup EXIT
sudo rm -rf \"$TMP\"
sudo mkdir -p \"$TMP\"
sudo tar -xf \"$ARCHIVE\" -C \"$TMP\"
{comparisons}
printf 'exact-byte-match\\n'
"""
        output = _run_bytes(
            ["gcloud", "compute", "ssh", target, *common, "--command", command],
            "deployed VM file differs from the immutable package",
        ).decode("utf-8", "strict")
        require(output.strip().endswith("exact-byte-match"), "VM exact-byte comparison did not complete")
    finally:
        archive.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--device-release-root", type=Path, required=True)
    parser.add_argument("--device-root", default="/data/adb/mobile-proxy-node")
    parser.add_argument("--device-serial")
    parser.add_argument("--expected-tunnel-owner", choices=sorted(_SUPPORTED_DEVICE_OWNERS))
    parser.add_argument("--vm-release-root", type=Path, required=True)
    parser.add_argument("--vm-project", required=True)
    parser.add_argument("--vm-zone", required=True)
    parser.add_argument("--vm-instance", required=True)
    parser.add_argument("--vm-ssh-user", required=True)
    parser.add_argument("--vm-ssh-key", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        candidate_sha = verify_candidate(read_json(args.evidence))
        verify_local_release_integrity(args.device_release_root)
        verify_local_release_integrity(args.vm_release_root)
        device_paths = load_release_inventory(args.device_release_root)
        verify_device_release_metadata(args.device_release_root, candidate_sha)
        expected_owner = release_tunnel_owner(args.device_release_root)
        if args.expected_tunnel_owner is not None:
            require(args.expected_tunnel_owner == expected_owner, "requested tunnel owner differs from package")
        vm_paths = load_release_inventory(args.vm_release_root)
        verify_device_files(args.device_release_root, device_paths, args.device_serial, args.device_root)
        verify_android_vpn_owner(args.device_serial, expected_owner)
        verify_vm_files(args, args.vm_release_root, vm_paths, candidate_sha)
        report = {
            "format_version": 1,
            "candidate_sha": candidate_sha,
            "expected_tunnel_owner": expected_owner,
            "device_release_entries": len(device_paths),
            "vm_release_entries": len(vm_paths),
            "local_release_integrity_match": True,
            "device_release_metadata_match": True,
            "device_deployment_match": True,
            "android_vpn_owner_match": True,
            "vm_deployment_match": True,
            "comparison_contract": "exact-bytes",
            "accepted": True,
        }
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (AcceptanceFailure, UnicodeError, OSError, tarfile.TarError) as error:
        print(f"physical deployment verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
