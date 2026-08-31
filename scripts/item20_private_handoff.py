#!/usr/bin/env python3
"""Canonical Item 20 sealed public-to-private handoff primitive.

The module performs no GitHub, provider, phone, ADB, or network I/O. It implements
only the application-level sealed envelope defined by
contracts/operations/item20-private-handoff-v1.json.

Plaintext transport endpoints are accepted only through caller-provided files and
are never printed. Sealing/unsealing uses the system libsodium crypto_box_seal /
crypto_box_seal_open API through ctypes. Missing libsodium fails closed.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import ctypes
import ctypes.util
import json
import os
from pathlib import Path
import re
import secrets
from typing import Mapping, Protocol

_CANONICAL_REPOSITORY = "iamaman11/mobile-proxy"
_PRIVATE_REPOSITORY = "iamaman11/mobile-proxy-production"
_IMMUTABLE_CANDIDATE = "d151dbdd156279e32a5361d304c90f996bd2d565"
_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_NONCE_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_KEY_BYTES = 32
_SEAL_OVERHEAD = 48
_MAX_ENDPOINT_BYTES = 512
_ENVELOPE_KEYS = {
    "format_version",
    "candidate_sha",
    "control_plane_sha",
    "session_nonce",
    "transport_endpoint",
}


class SealedBoxBackend(Protocol):
    def seal(self, plaintext: bytes, recipient_public_key: bytes) -> bytes: ...

    def unseal(self, ciphertext: bytes, recipient_private_key: bytes) -> bytes: ...


class LibsodiumSealedBox:
    """Small fail-closed ctypes adapter for libsodium sealed boxes."""

    def __init__(self) -> None:
        library_name = ctypes.util.find_library("sodium")
        if not library_name:
            raise RuntimeError("libsodium runtime is unavailable")
        try:
            self._lib = ctypes.CDLL(library_name)
        except OSError as error:
            raise RuntimeError("libsodium runtime is unavailable") from error

        self._lib.sodium_init.argtypes = []
        self._lib.sodium_init.restype = ctypes.c_int
        self._lib.crypto_box_seal.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_ulonglong,
            ctypes.c_void_p,
        ]
        self._lib.crypto_box_seal.restype = ctypes.c_int
        self._lib.crypto_box_seal_open.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_ulonglong,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        self._lib.crypto_box_seal_open.restype = ctypes.c_int
        self._lib.crypto_scalarmult_base.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self._lib.crypto_scalarmult_base.restype = ctypes.c_int

        if self._lib.sodium_init() < 0:
            raise RuntimeError("libsodium initialization failed")

    @staticmethod
    def _buffer(data: bytes) -> ctypes.Array[ctypes.c_ubyte]:
        array_type = ctypes.c_ubyte * len(data)
        return array_type.from_buffer_copy(data)

    def seal(self, plaintext: bytes, recipient_public_key: bytes) -> bytes:
        if len(recipient_public_key) != _KEY_BYTES:
            raise ValueError("recipient public key must decode to exactly 32 bytes")
        message = self._buffer(plaintext)
        public_key = self._buffer(recipient_public_key)
        output_type = ctypes.c_ubyte * (len(plaintext) + _SEAL_OVERHEAD)
        output = output_type()
        result = self._lib.crypto_box_seal(
            output,
            message,
            ctypes.c_ulonglong(len(plaintext)),
            public_key,
        )
        if result != 0:
            raise RuntimeError("libsodium sealed-box encryption failed")
        return bytes(output)

    def unseal(self, ciphertext: bytes, recipient_private_key: bytes) -> bytes:
        if len(recipient_private_key) != _KEY_BYTES:
            raise ValueError("recipient private key must decode to exactly 32 bytes")
        if len(ciphertext) <= _SEAL_OVERHEAD:
            raise ValueError("sealed ciphertext is too short")

        secret_key = self._buffer(recipient_private_key)
        public_key_type = ctypes.c_ubyte * _KEY_BYTES
        public_key = public_key_type()
        if self._lib.crypto_scalarmult_base(public_key, secret_key) != 0:
            raise RuntimeError("libsodium recipient public-key derivation failed")

        sealed = self._buffer(ciphertext)
        plaintext_type = ctypes.c_ubyte * (len(ciphertext) - _SEAL_OVERHEAD)
        plaintext = plaintext_type()
        result = self._lib.crypto_box_seal_open(
            plaintext,
            sealed,
            ctypes.c_ulonglong(len(ciphertext)),
            public_key,
            secret_key,
        )
        if result != 0:
            raise ValueError("sealed ciphertext authentication failed")
        return bytes(plaintext)


def validate_sha(value: object, kind: str) -> str:
    if not isinstance(value, str) or _SHA_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{kind} SHA must be an exact lowercase 40-character hexadecimal identity")
    return value


def validate_nonce(value: object) -> str:
    if not isinstance(value, str) or _NONCE_PATTERN.fullmatch(value) is None:
        raise ValueError("session nonce must be exactly 128 bits encoded as 32 lowercase hexadecimal characters")
    return value


def validate_endpoint(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("transport endpoint must be text")
    encoded = value.encode("utf-8")
    if not encoded or len(encoded) > _MAX_ENDPOINT_BYTES:
        raise ValueError("transport endpoint length is invalid")
    if any(character.isspace() or ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ValueError("transport endpoint contains whitespace or control characters")
    return value


def _decode_key(value: str, kind: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError(f"{kind} must be canonical base64") from error
    if len(decoded) != _KEY_BYTES:
        raise ValueError(f"{kind} must decode to exactly 32 bytes")
    if base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError(f"{kind} must use canonical padded base64")
    return decoded


def build_envelope(
    candidate_sha: str,
    control_plane_sha: str,
    session_nonce: str,
    transport_endpoint: str,
) -> dict[str, object]:
    candidate_sha = validate_sha(candidate_sha, "candidate")
    control_plane_sha = validate_sha(control_plane_sha, "control-plane")
    session_nonce = validate_nonce(session_nonce)
    transport_endpoint = validate_endpoint(transport_endpoint)
    if candidate_sha != _IMMUTABLE_CANDIDATE:
        raise ValueError("candidate SHA does not match the protected Item 19 closeout")
    return {
        "format_version": 1,
        "candidate_sha": candidate_sha,
        "control_plane_sha": control_plane_sha,
        "session_nonce": session_nonce,
        "transport_endpoint": transport_endpoint,
    }


def serialize_envelope(envelope: Mapping[str, object]) -> bytes:
    if set(envelope) != _ENVELOPE_KEYS:
        raise ValueError("handoff envelope schema differs from the protected contract")
    validated = build_envelope(
        str(envelope.get("candidate_sha", "")),
        str(envelope.get("control_plane_sha", "")),
        str(envelope.get("session_nonce", "")),
        envelope.get("transport_endpoint"),
    )
    if envelope.get("format_version") != 1:
        raise ValueError("unsupported handoff envelope format version")
    return json.dumps(validated, sort_keys=True, separators=(",", ":")).encode("utf-8")


def parse_envelope(
    plaintext: bytes,
    expected_candidate_sha: str,
    expected_control_plane_sha: str,
    expected_session_nonce: str,
) -> dict[str, object]:
    try:
        decoded = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("decrypted handoff envelope is not valid canonical JSON") from error
    if not isinstance(decoded, dict):
        raise ValueError("decrypted handoff envelope must be a JSON object")
    canonical = serialize_envelope(decoded)
    if canonical != plaintext:
        raise ValueError("decrypted handoff envelope is not canonical JSON")
    if decoded["candidate_sha"] != validate_sha(expected_candidate_sha, "expected candidate"):
        raise ValueError("handoff candidate SHA does not match the expected tuple")
    if decoded["control_plane_sha"] != validate_sha(expected_control_plane_sha, "expected control-plane"):
        raise ValueError("handoff control-plane SHA does not match the expected tuple")
    if decoded["session_nonce"] != validate_nonce(expected_session_nonce):
        raise ValueError("handoff session nonce does not match the expected tuple")
    return decoded


def seal_envelope(
    envelope: Mapping[str, object],
    recipient_public_key_b64: str,
    backend: SealedBoxBackend | None = None,
) -> str:
    recipient_public_key = _decode_key(recipient_public_key_b64, "recipient public key")
    sealed = (backend or LibsodiumSealedBox()).seal(serialize_envelope(envelope), recipient_public_key)
    return base64.b64encode(sealed).decode("ascii")


def unseal_envelope(
    sealed_envelope_b64: str,
    recipient_private_key_b64: str,
    expected_candidate_sha: str,
    expected_control_plane_sha: str,
    expected_session_nonce: str,
    backend: SealedBoxBackend | None = None,
) -> dict[str, object]:
    try:
        ciphertext = base64.b64decode(sealed_envelope_b64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("sealed handoff envelope must be canonical base64") from error
    if base64.b64encode(ciphertext).decode("ascii") != sealed_envelope_b64:
        raise ValueError("sealed handoff envelope must use canonical padded base64")
    private_key = _decode_key(recipient_private_key_b64, "recipient private key")
    plaintext = (backend or LibsodiumSealedBox()).unseal(ciphertext, private_key)
    return parse_envelope(
        plaintext,
        expected_candidate_sha,
        expected_control_plane_sha,
        expected_session_nonce,
    )


def generate_session_nonce() -> str:
    return secrets.token_hex(16)


def _read_text(path: Path, field: str) -> str:
    try:
        value = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"cannot read {field} file") from error
    if value.endswith("\n"):
        value = value[:-1]
    if "\n" in value or "\r" in value:
        raise ValueError(f"{field} file must contain exactly one line")
    return value


def _write_private_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")
    os.chmod(path, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    nonce = subparsers.add_parser("generate-nonce")
    nonce.add_argument("--output", type=Path, required=True)

    seal = subparsers.add_parser("seal")
    seal.add_argument("--candidate-sha", required=True)
    seal.add_argument("--control-plane-sha", required=True)
    seal.add_argument("--session-nonce", required=True)
    seal.add_argument("--endpoint-file", type=Path, required=True)
    seal.add_argument("--recipient-public-key-b64", required=True)
    seal.add_argument("--output", type=Path, required=True)

    unseal = subparsers.add_parser("unseal")
    unseal.add_argument("--candidate-sha", required=True)
    unseal.add_argument("--control-plane-sha", required=True)
    unseal.add_argument("--session-nonce", required=True)
    unseal.add_argument("--sealed-envelope-file", type=Path, required=True)
    unseal.add_argument("--private-key-env", default="ITEM20_HANDOFF_PRIVATE_KEY_B64")
    unseal.add_argument("--endpoint-output", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "generate-nonce":
        _write_private_text(args.output, generate_session_nonce())
        return 0

    if args.command == "seal":
        envelope = build_envelope(
            args.candidate_sha,
            args.control_plane_sha,
            args.session_nonce,
            _read_text(args.endpoint_file, "transport endpoint"),
        )
        sealed = seal_envelope(envelope, args.recipient_public_key_b64)
        _write_private_text(args.output, sealed)
        return 0

    private_key = os.environ.get(args.private_key_env, "")
    if not private_key:
        raise ValueError("private handoff decryption key is unavailable")
    envelope = unseal_envelope(
        _read_text(args.sealed_envelope_file, "sealed handoff envelope"),
        private_key,
        args.candidate_sha,
        args.control_plane_sha,
        args.session_nonce,
    )
    endpoint = envelope["transport_endpoint"]
    assert isinstance(endpoint, str)
    _write_private_text(args.endpoint_output, endpoint)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
