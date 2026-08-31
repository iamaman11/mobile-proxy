from __future__ import annotations

import base64
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "item20_private_handoff.py"
CANDIDATE = "d151dbdd156279e32a5361d304c90f996bd2d565"
CONTROL = "a" * 40
NONCE = "0123456789abcdef0123456789abcdef"
ENDPOINT = "198.51.100.10:443"
PUBLIC_KEY_B64 = base64.b64encode(bytes(range(32))).decode("ascii")
PRIVATE_KEY_B64 = base64.b64encode(bytes(reversed(range(32)))).decode("ascii")

spec = importlib.util.spec_from_file_location("item20_private_handoff", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class FakeBackend:
    def __init__(self, *, fail_derivation: bool = False) -> None:
        self.sealed_plaintext: bytes | None = None
        self.sealed_key: bytes | None = None
        self.fail_derivation = fail_derivation

    def derive_public_key(self, recipient_private_key: bytes) -> bytes:
        if self.fail_derivation:
            raise RuntimeError("derivation failed")
        if len(recipient_private_key) != 32:
            raise ValueError("bad private key")
        return bytes(reversed(recipient_private_key))

    def seal(self, plaintext: bytes, recipient_public_key: bytes) -> bytes:
        self.sealed_plaintext = plaintext
        self.sealed_key = recipient_public_key
        return b"sealed:" + plaintext

    def unseal(self, ciphertext: bytes, recipient_private_key: bytes) -> bytes:
        if len(recipient_private_key) != 32:
            raise ValueError("bad private key")
        if not ciphertext.startswith(b"sealed:"):
            raise ValueError("bad ciphertext")
        return ciphertext[len(b"sealed:") :]


def envelope() -> dict[str, object]:
    return module.build_envelope(CANDIDATE, CONTROL, NONCE, ENDPOINT)


class Item20PrivateHandoffTests(unittest.TestCase):
    def test_builds_exact_bounded_envelope(self) -> None:
        value = envelope()
        self.assertEqual(
            set(value),
            {
                "format_version",
                "candidate_sha",
                "control_plane_sha",
                "session_nonce",
                "transport_endpoint",
            },
        )
        self.assertEqual(value["candidate_sha"], CANDIDATE)
        self.assertEqual(value["control_plane_sha"], CONTROL)
        self.assertEqual(value["session_nonce"], NONCE)
        self.assertEqual(value["transport_endpoint"], ENDPOINT)
        self.assertNotIn("provider_uuid", value)
        self.assertNotIn("provider_credentials", value)
        self.assertNotIn("phone_credentials", value)

    def test_nonce_is_exact_128_bit_lowercase_hex(self) -> None:
        generated = module.generate_session_nonce()
        self.assertRegex(generated, r"^[0-9a-f]{32}$")
        self.assertEqual(len(bytes.fromhex(generated)), 16)
        for invalid in ("a" * 31, "A" * 32, "g" * 32, "a" * 64):
            with self.assertRaises(ValueError):
                module.validate_nonce(invalid)

    def test_rejects_wrong_candidate_and_unsafe_endpoint(self) -> None:
        with self.assertRaises(ValueError):
            module.build_envelope("b" * 40, CONTROL, NONCE, ENDPOINT)
        for invalid in ("", "host name:443", "host:443\nother", "x" * 513):
            with self.assertRaises(ValueError):
                module.build_envelope(CANDIDATE, CONTROL, NONCE, invalid)

    def test_serialization_is_canonical_and_exact_schema(self) -> None:
        serialized = module.serialize_envelope(envelope())
        self.assertEqual(
            serialized,
            (
                '{"candidate_sha":"%s","control_plane_sha":"%s","format_version":1,'
                '"session_nonce":"%s","transport_endpoint":"%s"}'
                % (CANDIDATE, CONTROL, NONCE, ENDPOINT)
            ).encode("utf-8"),
        )
        expanded = envelope()
        expanded["provider_uuid"] = "forbidden"
        with self.assertRaises(ValueError):
            module.serialize_envelope(expanded)

    def test_verifies_exact_recipient_key_pair(self) -> None:
        module.verify_recipient_key_pair(PUBLIC_KEY_B64, PRIVATE_KEY_B64, FakeBackend())

        wrong_public_key = base64.b64encode(b"x" * 32).decode("ascii")
        with self.assertRaises(ValueError):
            module.verify_recipient_key_pair(wrong_public_key, PRIVATE_KEY_B64, FakeBackend())

    def test_recipient_key_pair_verifier_rejects_invalid_keys_and_derivation_failure(self) -> None:
        short_key = base64.b64encode(b"short").decode("ascii")
        with self.assertRaises(ValueError):
            module.verify_recipient_key_pair(short_key, PRIVATE_KEY_B64, FakeBackend())
        with self.assertRaises(ValueError):
            module.verify_recipient_key_pair(PUBLIC_KEY_B64, short_key, FakeBackend())
        with self.assertRaises(ValueError):
            module.verify_recipient_key_pair("not-base64", PRIVATE_KEY_B64, FakeBackend())
        with self.assertRaises(RuntimeError):
            module.verify_recipient_key_pair(
                PUBLIC_KEY_B64,
                PRIVATE_KEY_B64,
                FakeBackend(fail_derivation=True),
            )

    def test_private_key_environment_is_fixed_and_fail_closed(self) -> None:
        self.assertEqual(module._PRIVATE_KEY_ENV, "ITEM20_HANDOFF_PRIVATE_KEY_B64")
        with mock.patch.dict(module.os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                module._read_private_key_from_environment()
        with mock.patch.dict(
            module.os.environ,
            {"ITEM20_HANDOFF_PRIVATE_KEY_B64": PRIVATE_KEY_B64},
            clear=True,
        ):
            self.assertEqual(module._read_private_key_from_environment(), PRIVATE_KEY_B64)

    def test_seal_uses_only_recipient_public_key_and_canonical_plaintext(self) -> None:
        backend = FakeBackend()
        sealed = module.seal_envelope(envelope(), PUBLIC_KEY_B64, backend)
        self.assertEqual(backend.sealed_plaintext, module.serialize_envelope(envelope()))
        self.assertEqual(backend.sealed_key, bytes(range(32)))
        self.assertEqual(base64.b64decode(sealed), b"sealed:" + module.serialize_envelope(envelope()))

    def test_unseal_exact_matches_candidate_control_and_nonce(self) -> None:
        backend = FakeBackend()
        sealed = module.seal_envelope(envelope(), PUBLIC_KEY_B64, backend)
        opened = module.unseal_envelope(
            sealed,
            PRIVATE_KEY_B64,
            CANDIDATE,
            CONTROL,
            NONCE,
            backend,
        )
        self.assertEqual(opened["transport_endpoint"], ENDPOINT)

        with self.assertRaises(ValueError):
            module.unseal_envelope(sealed, PRIVATE_KEY_B64, CANDIDATE, "b" * 40, NONCE, backend)
        with self.assertRaises(ValueError):
            module.unseal_envelope(
                sealed,
                PRIVATE_KEY_B64,
                CANDIDATE,
                CONTROL,
                "f" * 32,
                backend,
            )

    def test_rejects_noncanonical_keys_and_ciphertext(self) -> None:
        with self.assertRaises(ValueError):
            module.seal_envelope(envelope(), base64.b64encode(b"short").decode("ascii"), FakeBackend())
        with self.assertRaises(ValueError):
            module.unseal_envelope(
                "not-base64",
                PRIVATE_KEY_B64,
                CANDIDATE,
                CONTROL,
                NONCE,
                FakeBackend(),
            )

    def test_implementation_is_libsodium_sealed_box_and_non_live(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("crypto_box_seal", source)
        self.assertIn("crypto_box_seal_open", source)
        self.assertIn("crypto_scalarmult_base", source)
        self.assertIn('find_library("sodium")', source)
        self.assertIn('subparsers.add_parser("verify-recipient-key-pair")', source)
        self.assertIn('_PRIVATE_KEY_ENV = "ITEM20_HANDOFF_PRIVATE_KEY_B64"', source)
        self.assertNotIn("--private-key-env", source)
        self.assertNotIn("verify-recipient-key\")", source)
        self.assertNotIn("subprocess.", source)
        self.assertNotIn("urllib.request", source)
        self.assertNotIn("requests.", source)
        self.assertNotIn("http.client", source)
        self.assertNotIn("socket.", source)
        self.assertNotIn("adb ", source.lower())
        self.assertNotIn("vultr_api_key", source.lower())
        self.assertNotIn("vultr_ssh_private_key", source.lower())
        self.assertNotIn("gh workflow run", source.lower())
        self.assertNotIn("print(", source)

    def test_cli_never_accepts_plaintext_endpoint_as_argument(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('seal.add_argument("--endpoint-file"', source)
        self.assertIn('unseal.add_argument("--endpoint-output"', source)
        self.assertNotIn('add_argument("--endpoint"', source)


if __name__ == "__main__":
    unittest.main()
