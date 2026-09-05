#!/usr/bin/env python3
"""Prepare only the immutable rooted-phone runtime bytes for Product Release."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Mapping

ANDROID_TARGET = "armv7-linux-androideabi"
ANDROID_ELF_MACHINE = 40
PHONE_TARGET = "phone-production"
PHONE_SING_BOX_TARGET = "android-arm"
VERSION = re.compile(r"[0-9]+(?:\.[0-9]+){1,3}")
SHA256 = re.compile(r"[0-9a-f]{64}")
TYPED_DIGEST = re.compile(r"b3:[0-9a-f]{64}")


class PhoneRuntimePreparationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PhoneRuntimePreparationError(message)


def _load_object(path: Path, label: str) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PhoneRuntimePreparationError(f"cannot load {label}: {exc}") from exc
    require(isinstance(value, dict), f"{label} root must be an object")
    return value


def _safe_relative(value: object, label: str) -> PurePosixPath:
    require(isinstance(value, str) and bool(value), f"{label} is invalid")
    path = PurePosixPath(value)
    require(not path.is_absolute(), f"{label} must be relative")
    require(".." not in path.parts and "." not in path.parts, f"{label} escapes repository root")
    return path


def resolve_phone_build_inputs(
    repository_root: Path,
    contract_path: Path,
) -> dict[str, object]:
    repository_root = repository_root.resolve()
    contract = _load_object(contract_path.resolve(), "phone-production runtime component contract")
    require(contract.get("contract_version") == 1, "phone-production runtime contract version differs")
    require(contract.get("status") == "protected", "phone-production runtime contract is not protected")
    require(contract.get("target") == PHONE_TARGET, "phone-production runtime target differs")

    abi = contract.get("runtime_abi")
    require(isinstance(abi, dict), "phone-production runtime ABI is missing")
    require(abi.get("os") == "android", "phone-production runtime OS differs")
    require(abi.get("arch") == "arm", "phone-production runtime architecture differs")
    require(abi.get("rust_target") == ANDROID_TARGET, "phone-production Rust target differs")
    require(abi.get("elf_machine") == ANDROID_ELF_MACHINE, "phone-production ELF machine differs")

    toolchain = contract.get("build_toolchain")
    require(isinstance(toolchain, dict), "phone-production build toolchain is missing")
    ndk_version = toolchain.get("android_ndk_version")
    api_level = toolchain.get("android_api_level")
    rust_profile = toolchain.get("rust_profile")
    require(
        isinstance(ndk_version, str) and VERSION.fullmatch(ndk_version) is not None,
        "phone-production Android NDK version is invalid",
    )
    require(
        isinstance(api_level, int) and not isinstance(api_level, bool) and 21 <= api_level <= 35,
        "phone-production Android API level is invalid",
    )
    require(rust_profile == "release", "phone-production Rust profile must be release")

    third_party = contract.get("third_party_runtime")
    require(isinstance(third_party, dict), "phone-production third-party runtime contract is invalid")
    sing_box = third_party.get("sing-box")
    require(isinstance(sing_box, dict), "phone-production sing-box contract is missing")
    lock_target = sing_box.get("lock_target")
    require(lock_target == PHONE_SING_BOX_TARGET, "phone-production sing-box target must remain android-arm")
    lock_relative = _safe_relative(sing_box.get("lock_file"), "phone-production sing-box lock file")
    lock = _load_object(
        repository_root / Path(*lock_relative.parts),
        "sing-box artifact lock",
    )
    require(lock.get("schema_version") == 1, "sing-box artifact lock schema differs")
    sing_box_version = lock.get("version")
    require(
        isinstance(sing_box_version, str) and VERSION.fullmatch(sing_box_version) is not None,
        "sing-box pinned version is invalid",
    )
    artifacts = lock.get("artifacts")
    require(isinstance(artifacts, dict), "sing-box artifact lock targets are invalid")
    pin = artifacts.get(lock_target)
    require(isinstance(pin, dict), "sing-box android-arm pin is missing")
    size = pin.get("size")
    upstream_sha256 = pin.get("upstream_sha256")
    content_digest = pin.get("content_digest")
    require(
        isinstance(size, int) and not isinstance(size, bool) and size > 0,
        "sing-box android-arm size is invalid",
    )
    require(
        isinstance(upstream_sha256, str) and SHA256.fullmatch(upstream_sha256) is not None,
        "sing-box android-arm upstream checksum metadata is invalid",
    )
    require(
        isinstance(content_digest, str) and TYPED_DIGEST.fullmatch(content_digest) is not None,
        "sing-box android-arm typed digest is invalid",
    )

    return {
        "android_api_level": api_level,
        "android_ndk_version": ndk_version,
        "rust_profile": rust_profile,
        "rust_target": ANDROID_TARGET,
        "sing_box": {
            "archive_content_digest": content_digest,
            "archive_size": size,
            "lock_target": PHONE_SING_BOX_TARGET,
            "version": sing_box_version,
        },
    }


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    capture: bool = False,
    timeout: int = 1200,
) -> subprocess.CompletedProcess[str]:
    try:
        kwargs: dict[str, object] = {
            "cwd": cwd,
            "env": dict(env) if env is not None else None,
            "check": True,
            "text": True,
            "timeout": timeout,
        }
        if capture:
            kwargs["capture_output"] = True
        else:
            kwargs["stdout"] = sys.stderr
            kwargs["stderr"] = sys.stderr
        return subprocess.run(command, **kwargs)  # type: ignore[arg-type]
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise PhoneRuntimePreparationError(
            f"command failed: {' '.join(command)}"
        ) from exc


def _typed_sing_box_archive_digest(path: Path, repository_root: Path) -> str:
    result = _run(
        [
            "cargo",
            "run",
            "--quiet",
            "--locked",
            "--release",
            "-p",
            "operator-cli",
            "--bin",
            "upstream-sing-box-archive-digest",
            "--",
            str(path),
        ],
        cwd=repository_root,
        capture=True,
    )
    digest = result.stdout.strip()
    require(
        TYPED_DIGEST.fullmatch(digest) is not None,
        "sing-box archive typed digest output is invalid",
    )
    return digest


def _verify_elf(path: Path, expected_machine: int, label: str) -> None:
    require(path.is_file() and path.stat().st_size > 0, f"missing {label}: {path}")
    with path.open("rb") as handle:
        header = handle.read(20)
    require(len(header) == 20, f"{label} ELF header is truncated")
    require(header[:4] == b"\x7fELF", f"{label} is not ELF")
    require(header[5] == 1, f"{label} is not little-endian ELF")
    machine = int.from_bytes(header[18:20], byteorder="little")
    require(machine == expected_machine, f"{label} ELF machine differs")


def _install_exact_ndk(
    repository_root: Path,
    android_sdk_root: Path,
    ndk_version: str,
) -> Path:
    sdkmanager = shutil.which("sdkmanager")
    require(sdkmanager is not None, "sdkmanager is unavailable")
    _run([sdkmanager, f"ndk;{ndk_version}"], cwd=repository_root)
    ndk = android_sdk_root / "ndk" / ndk_version
    require(ndk.is_dir(), f"exact Android NDK is unavailable after sdkmanager: {ndk_version}")
    return ndk


def _build_first_party_runtime(
    repository_root: Path,
    ndk: Path,
    api_level: int,
) -> None:
    toolchain_bin = ndk / "toolchains" / "llvm" / "prebuilt" / "linux-x86_64" / "bin"
    clang = toolchain_bin / f"armv7a-linux-androideabi{api_level}-clang"
    ar = toolchain_bin / "llvm-ar"
    strip = toolchain_bin / "llvm-strip"
    for path, label in (
        (clang, "Android clang"),
        (ar, "Android llvm-ar"),
        (strip, "Android llvm-strip"),
    ):
        require(path.is_file(), f"exact pinned NDK is missing {label}: {path}")

    _run(["rustup", "target", "add", ANDROID_TARGET], cwd=repository_root)
    env = os.environ.copy()
    env.update(
        {
            "AR_armv7_linux_androideabi": str(ar),
            "CARGO_INCREMENTAL": "0",
            "CARGO_TARGET_ARMV7_LINUX_ANDROIDEABI_LINKER": str(clang),
            "CC_armv7_linux_androideabi": str(clang),
        }
    )
    epoch = _run(
        ["git", "show", "-s", "--format=%ct", "HEAD"],
        cwd=repository_root,
        capture=True,
    ).stdout.strip()
    require(epoch.isdigit(), "source commit timestamp is invalid")
    env["SOURCE_DATE_EPOCH"] = epoch
    _run(
        [
            "cargo",
            "build",
            "--release",
            "--locked",
            "-p",
            "runtime-supervisor",
            "-p",
            "host-daemon",
            "--target",
            ANDROID_TARGET,
        ],
        cwd=repository_root,
        env=env,
    )

    source_root = repository_root / "target" / ANDROID_TARGET / "release"
    destination_root = repository_root / "deploy" / "device-runtime" / "bin"
    destination_root.mkdir(parents=True, exist_ok=True)
    for name in ("runtime-supervisor", "host-daemon"):
        source = source_root / name
        destination = destination_root / name
        require(source.is_file(), f"built phone runtime binary is missing: {name}")
        shutil.copyfile(source, destination)
        destination.chmod(0o755)
        _run([str(strip), str(destination)], cwd=repository_root)
        _verify_elf(destination, ANDROID_ELF_MACHINE, name)


def _safe_archive_members(archive: Path, repository_root: Path) -> None:
    listing = _run(
        ["tar", "-tzf", str(archive)],
        cwd=repository_root,
        capture=True,
    ).stdout.splitlines()
    require(bool(listing), "sing-box archive is empty")
    for raw in listing:
        value = raw[:-1] if raw.endswith("/") else raw
        require(bool(value), "sing-box archive contains an empty path")
        path = PurePosixPath(value)
        require(not path.is_absolute(), "sing-box archive contains an absolute path")
        require(".." not in path.parts, "sing-box archive contains parent traversal")


def _prepare_sing_box(
    repository_root: Path,
    pin: Mapping[str, object],
) -> None:
    version = str(pin["version"])
    target = str(pin["lock_target"])
    expected_size = int(pin["archive_size"])
    expected_digest = str(pin["archive_content_digest"])
    cache = repository_root / "target" / "artifacts" / "phone-production" / "sing-box"
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / f"sing-box-{version}-{target}.tar.gz"

    def matches() -> bool:
        return (
            archive.is_file()
            and archive.stat().st_size == expected_size
            and _typed_sing_box_archive_digest(archive, repository_root) == expected_digest
        )

    if not matches():
        archive.unlink(missing_ok=True)
        url = (
            f"https://github.com/SagerNet/sing-box/releases/download/v{version}/"
            f"sing-box-{version}-{target}.tar.gz"
        )
        _run(
            ["curl", "-fL", "--retry", "3", "--retry-all-errors", "-o", str(archive), url],
            cwd=repository_root,
        )
    require(archive.stat().st_size == expected_size, "sing-box android-arm archive size differs")
    require(
        _typed_sing_box_archive_digest(archive, repository_root) == expected_digest,
        "sing-box android-arm typed archive digest differs",
    )
    _safe_archive_members(archive, repository_root)

    with tempfile.TemporaryDirectory(prefix="phone-runtime-sing-box-", dir=cache) as temporary:
        extract_root = Path(temporary)
        _run(["tar", "-xzf", str(archive), "-C", str(extract_root)], cwd=repository_root)
        candidates = sorted(
            path for path in extract_root.rglob("sing-box") if path.is_file()
        )
        require(len(candidates) == 1, "sing-box android-arm archive payload is ambiguous")
        destination = repository_root / "deploy" / "device-runtime" / "bin" / "sing-box"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(candidates[0], destination)
        destination.chmod(0o755)
        _verify_elf(destination, ANDROID_ELF_MACHINE, "sing-box")


def prepare_phone_runtime(
    *,
    repository_root: Path,
    android_sdk_root: Path,
    contract_path: Path,
) -> dict[str, object]:
    repository_root = repository_root.resolve()
    android_sdk_root = android_sdk_root.resolve()
    require(repository_root.is_dir(), "repository root is missing")
    require(android_sdk_root.is_dir(), "Android SDK root is missing")
    inputs = resolve_phone_build_inputs(repository_root, contract_path)
    ndk = _install_exact_ndk(
        repository_root,
        android_sdk_root,
        str(inputs["android_ndk_version"]),
    )
    _build_first_party_runtime(
        repository_root,
        ndk,
        int(inputs["android_api_level"]),
    )
    sing_box = inputs["sing_box"]
    require(isinstance(sing_box, dict), "resolved sing-box input is invalid")
    _prepare_sing_box(repository_root, sing_box)

    for name in ("runtime-supervisor", "host-daemon", "sing-box"):
        _verify_elf(
            repository_root / "deploy" / "device-runtime" / "bin" / name,
            ANDROID_ELF_MACHINE,
            name,
        )
    return {
        "android_api_level": inputs["android_api_level"],
        "android_ndk_version": inputs["android_ndk_version"],
        "rust_profile": inputs["rust_profile"],
        "rust_target": inputs["rust_target"],
        "sing_box_archive_content_digest": sing_box["archive_content_digest"],
        "sing_box_lock_target": sing_box["lock_target"],
        "sing_box_version": sing_box["version"],
        "target": PHONE_TARGET,
        "vm_runtime_prepared": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--android-sdk-root", type=Path, required=True)
    parser.add_argument("--phone-runtime-contract", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare_phone_runtime(
            repository_root=args.repository_root,
            android_sdk_root=args.android_sdk_root,
            contract_path=args.phone_runtime_contract,
        )
    except (OSError, PhoneRuntimePreparationError) as exc:
        print(f"phone-production runtime preparation refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
