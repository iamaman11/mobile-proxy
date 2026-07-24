#!/usr/bin/env python3
"""Verify that the phone and VM contain the exact locally packaged candidate files."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import sys
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
    "nginx/mobile-public-proxy.conf": "/etc/nginx/stream-available/mobile-public-proxy.conf",
}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative_path(raw: Any) -> str:
    require(isinstance(raw, str) and 0 < len(raw) <= 256, "release path is invalid")
    path = PurePosixPath(raw)
    require(not path.is_absolute(), "release path must be relative")
    require(".." not in path.parts and "." not in path.parts, "release path escapes its root")
    require(all(part and part not in {"/", "\\"} for part in path.parts), "release path is invalid")
    return path.as_posix()


def load_release_inventory(root: Path) -> list[str]:
    manifest_path = root / _MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
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
        require(isinstance(digest, str) and 1 <= len(digest) <= 128, "release digest is invalid")
        require(isinstance(size, int) and 0 <= size <= 2**63 - 1, "release size is invalid")
        local = root / relative
        require(local.is_file(), "release inventory file is missing")
        require(local.stat().st_size == size, "release inventory size differs from the packaged file")
        paths.append(relative)
    return paths


def verify_device_release_metadata(root: Path, candidate_sha: str) -> None:
    metadata_path = root / "release-metadata.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AcceptanceFailure("device release metadata is unreadable") from error
    require(isinstance(metadata, dict), "device release metadata must be an object")
    require(metadata.get("format_version") == 1, "device release metadata version is unsupported")
    require(metadata.get("git_sha") == candidate_sha, "device package SHA differs from candidate")
    require(metadata.get("git_worktree_clean") is True, "device package was built from a dirty tree")


def release_tunnel_owner(root: Path) -> str:
    path = root / "config" / "host-daemon.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AcceptanceFailure("device host configuration is unreadable") from error
    require(isinstance(config, dict), "device host configuration is invalid")
    wireguard = config.get("wireguard")
    require(isinstance(wireguard, dict), "device WireGuard configuration is invalid")
    owner = wireguard.get("owner")
    require(owner in _SUPPORTED_DEVICE_OWNERS, "device release tunnel owner is unsupported")
    reverse = config.get("reverse_tunnel")
    require(isinstance(reverse, dict), "device reverse-tunnel configuration is invalid")
    if owner == "first_party_reverse_tunnel":
        require(wireguard.get("enabled") is False, "reverse release unexpectedly enables WireGuard")
        require(reverse.get("enabled") is True, "reverse release disables reverse tunnel")
    else:
        require(wireguard.get("enabled") is True, "WireGuard release disables WireGuard")
        require(reverse.get("enabled") is False, "WireGuard release leaves reverse tunnel enabled")
    return owner


def _run_bytes(command: list[str], failure: str) -> bytes:
    try:
        result = subprocess.run(command, check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise AcceptanceFailure(failure) from error
    return result.stdout


def _adb_prefix(serial: str | None) -> list[str]:
    prefix = ["adb"]
    if serial:
        prefix += ["-s", serial]
    return prefix


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
        local = root / relative
        require(len(remote_bytes) == local.stat().st_size, "deployed device file size differs")
        require(_sha256_bytes(remote_bytes) == _sha256_file(local), "deployed device file differs")


def _parse_sha256sum(output: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in output.splitlines():
        parts = line.strip().split(maxsplit=1)
        require(len(parts) == 2 and len(parts[0]) == 64, "VM digest output is invalid")
        digest, path = parts
        path = path.lstrip("*")
        require(all(character in "0123456789abcdef" for character in digest), "VM digest is invalid")
        require(path not in result, "VM digest output contains duplicate paths")
        result[path] = digest
    return result


def verify_vm_files(args: argparse.Namespace, root: Path, paths: list[str]) -> None:
    require(set(paths) == set(_VM_REMOTE_PATHS), "VM release inventory does not match the supported deployment map")
    remote_paths = [_VM_REMOTE_PATHS[path] for path in paths]
    remote_command = "sudo sha256sum -- " + " ".join(shlex.quote(path) for path in remote_paths)
    command = [
        "gcloud",
        "compute",
        "ssh",
        f"{args.vm_ssh_user}@{args.vm_instance}",
        "--project",
        args.vm_project,
        "--zone",
        args.vm_zone,
        "--ssh-key-file",
        args.vm_ssh_key,
        "--tunnel-through-iap",
        "--command",
        remote_command,
    ]
    output = _run_bytes(command, "failed to read deployed VM release digests").decode("utf-8", "strict")
    remote_hashes = _parse_sha256sum(output)
    require(set(remote_hashes) == set(remote_paths), "VM digest output is incomplete")
    for relative in paths:
        remote = _VM_REMOTE_PATHS[relative]
        require(remote_hashes[remote] == _sha256_file(root / relative), "deployed VM file differs")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--device-release-root", type=Path, required=True)
    parser.add_argument("--device-root", default="/data/adb/mobile-proxy-node")
    parser.add_argument("--device-serial")
    parser.add_argument(
        "--expected-tunnel-owner",
        choices=sorted(_SUPPORTED_DEVICE_OWNERS),
        help="Optional assertion; the authoritative owner is read from the packaged host config",
    )
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
        device_paths = load_release_inventory(args.device_release_root)
        verify_device_release_metadata(args.device_release_root, candidate_sha)
        expected_owner = release_tunnel_owner(args.device_release_root)
        if args.expected_tunnel_owner is not None:
            require(args.expected_tunnel_owner == expected_owner, "requested tunnel owner differs from package")
        vm_paths = load_release_inventory(args.vm_release_root)
        verify_device_files(
            args.device_release_root,
            device_paths,
            args.device_serial,
            args.device_root,
        )
        verify_android_vpn_owner(args.device_serial, expected_owner)
        verify_vm_files(args, args.vm_release_root, vm_paths)
        report = {
            "format_version": 1,
            "candidate_sha": candidate_sha,
            "expected_tunnel_owner": expected_owner,
            "device_release_entries": len(device_paths),
            "vm_release_entries": len(vm_paths),
            "device_release_metadata_match": True,
            "device_deployment_match": True,
            "android_vpn_owner_match": True,
            "vm_deployment_match": True,
            "accepted": True,
        }
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (AcceptanceFailure, UnicodeError) as error:
        print(f"physical deployment verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
