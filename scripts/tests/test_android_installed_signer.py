from __future__ import annotations

import base64
import os
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from scripts import verify_android_installed_signer as module

SHA = "a" * 40
SERIAL = "registered-device"
CERTIFICATE_FINGERPRINT = "12" * 32
KEYTOOL_FINGERPRINT = ":".join(
    CERTIFICATE_FINGERPRINT[index : index + 2].upper()
    for index in range(0, len(CERTIFICATE_FINGERPRINT), 2)
)
KEYSTORE = b"bounded-test-keystore"
KEYSTORE_B64 = base64.b64encode(KEYSTORE).decode("ascii")


class AndroidInstalledSignerTests(unittest.TestCase):
    def test_selects_unique_base_apk_from_split_inventory(self) -> None:
        output = "\n".join(
            [
                "package:/data/app/example/split_config.en.apk",
                "package:/data/app/example/base.apk",
                "package:/data/app/example/split_config.xxhdpi.apk",
            ]
        )
        self.assertEqual(
            module.select_installed_apk_path(output),
            "/data/app/example/base.apk",
        )

    def test_rejects_missing_or_ambiguous_installed_apk_inventory(self) -> None:
        with self.assertRaises(module.SigningIdentityFailure):
            module.select_installed_apk_path("")
        with self.assertRaises(module.SigningIdentityFailure):
            module.select_installed_apk_path(
                "package:/data/a.apk\npackage:/data/b.apk\n"
            )
        with self.assertRaises(module.SigningIdentityFailure):
            module.select_installed_apk_path("unexpected:/data/base.apk")

    def test_parses_exact_single_tool_reported_fingerprints(self) -> None:
        apksigner_output = (
            "Signer #1 certificate DN: CN=redacted\n"
            "Signer #1 certificate SHA-256 digest: "
            f"{CERTIFICATE_FINGERPRINT}\n"
        )
        self.assertEqual(
            module.parse_single_apksigner_fingerprint(apksigner_output),
            CERTIFICATE_FINGERPRINT,
        )
        self.assertEqual(
            module.parse_single_keytool_fingerprint(
                f"Certificate fingerprints:\n\t SHA256: {KEYTOOL_FINGERPRINT}\n"
            ),
            CERTIFICATE_FINGERPRINT,
        )
        with self.assertRaises(module.SigningIdentityFailure):
            module.parse_single_apksigner_fingerprint("")
        with self.assertRaises(module.SigningIdentityFailure):
            module.parse_single_apksigner_fingerprint(
                apksigner_output
                + "Signer #2 certificate SHA-256 digest: "
                + CERTIFICATE_FINGERPRINT
                + "\n"
            )
        with self.assertRaises(module.SigningIdentityFailure):
            module.parse_single_keytool_fingerprint(
                f"SHA256: {KEYTOOL_FINGERPRINT}\nSHA256: {KEYTOOL_FINGERPRINT}\n"
            )

    def test_private_inputs_are_required_and_canonical(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(module.SigningIdentityFailure):
                module.require_private_text(module._KEY_ALIAS_ENV, maximum=256)
        with mock.patch.dict(
            os.environ,
            {module._KEY_ALIAS_ENV: "alias\nleak"},
            clear=True,
        ):
            with self.assertRaises(module.SigningIdentityFailure):
                module.require_private_text(module._KEY_ALIAS_ENV, maximum=256)

        self.assertEqual(
            module.decode_canonical_base64(
                KEYSTORE_B64,
                "keystore",
                maximum_bytes=1024,
            ),
            KEYSTORE,
        )
        with self.assertRaises(module.SigningIdentityFailure):
            module.decode_canonical_base64(
                "not-base64",
                "keystore",
                maximum_bytes=1024,
            )
        with self.assertRaises(module.SigningIdentityFailure):
            module.decode_canonical_base64(
                base64.b64encode(b"too-large").decode("ascii"),
                "keystore",
                maximum_bytes=2,
            )

    def _fake_run_checked(
        self,
        command: list[str] | tuple[str, ...],
        *,
        timeout: int = 20,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del timeout
        values = list(command)
        if values[:6] == [
            "adb",
            "-s",
            SERIAL,
            "shell",
            "pm",
            "path",
        ]:
            return subprocess.CompletedProcess(
                values,
                0,
                stdout="package:/data/app/production/base.apk\n",
                stderr="",
            )
        if values[:4] == ["adb", "-s", SERIAL, "pull"]:
            Path(values[-1]).write_bytes(b"installed-apk")
            return subprocess.CompletedProcess(values, 0, stdout="", stderr="")
        if values[:3] == ["apksigner", "verify", "--print-certs"]:
            return subprocess.CompletedProcess(
                values,
                0,
                stdout=(
                    "Signer #1 certificate DN: CN=redacted\n"
                    "Signer #1 certificate SHA-256 digest: "
                    f"{CERTIFICATE_FINGERPRINT}\n"
                ),
                stderr="",
            )
        if values[:3] == ["keytool", "-list", "-v"]:
            self.assertIn("-storepass:env", values)
            self.assertNotIn("test-store-password", values)
            self.assertIsNotNone(env)
            assert env is not None
            self.assertEqual(
                env[module._KEYSTORE_PASSWORD_ENV],
                "test-store-password",
            )
            return subprocess.CompletedProcess(
                values,
                0,
                stdout=(
                    "Certificate fingerprints:\n"
                    f"\t SHA256: {KEYTOOL_FINGERPRINT}\n"
                ),
                stderr="",
            )
        self.fail(f"unexpected command: {values!r}")

    def test_verifies_recovered_keystore_against_installed_apk_without_secret_evidence(self) -> None:
        private_env = {
            "ANDROID_RELEASE_KEYSTORE_B64": KEYSTORE_B64,
            "ANDROID_RELEASE_KEYSTORE_PASSWORD": "test-store-password",
            "ANDROID_RELEASE_KEY_ALIAS": "release",
        }
        with (
            mock.patch.object(module, "require_tools"),
            mock.patch.object(module, "require_expected_serial", return_value=SERIAL),
            mock.patch.object(module, "prove_registered_device") as preflight,
            mock.patch.object(module, "run_checked", side_effect=self._fake_run_checked),
            mock.patch.dict(os.environ, private_env, clear=True),
        ):
            report = module.verify_installed_signer(SHA)

        preflight.assert_called_once_with(SERIAL)
        self.assertTrue(report["accepted"])
        self.assertTrue(report["registered_device_match"])
        self.assertTrue(report["installed_apk_signer_verified"])
        self.assertTrue(report["recovered_keystore_signer_match"])
        self.assertFalse(report["phone_mutation_performed"])
        self.assertFalse(report["signing_key_generated"])
        self.assertFalse(report["raw_device_identifier_recorded"])
        self.assertFalse(report["signer_digest_recorded"])
        self.assertFalse(report["signing_material_recorded"])
        self.assertEqual(
            set(report),
            {
                "format_version",
                "repository",
                "canonical_sha",
                "package",
                "mode",
                "registered_device_match",
                "installed_apk_signer_verified",
                "recovered_keystore_signer_match",
                "raw_device_identifier_recorded",
                "signer_digest_recorded",
                "signing_material_recorded",
                "phone_mutation_performed",
                "signing_key_generated",
                "accepted",
            },
        )
        serialized = repr(report)
        self.assertNotIn(SERIAL, serialized)
        self.assertNotIn(CERTIFICATE_FINGERPRINT, serialized)
        self.assertNotIn(KEYSTORE_B64, serialized)
        self.assertNotIn("test-store-password", serialized)

    def test_signer_mismatch_fails_closed(self) -> None:
        private_env = {
            "ANDROID_RELEASE_KEYSTORE_B64": KEYSTORE_B64,
            "ANDROID_RELEASE_KEYSTORE_PASSWORD": "test-store-password",
            "ANDROID_RELEASE_KEY_ALIAS": "release",
        }
        wrong_fingerprint = "34" * 32

        def fake_mismatch(
            command: list[str] | tuple[str, ...],
            *,
            timeout: int = 20,
            env: dict[str, str] | None = None,
        ) -> subprocess.CompletedProcess[str]:
            values = list(command)
            if values[:3] == ["apksigner", "verify", "--print-certs"]:
                return subprocess.CompletedProcess(
                    values,
                    0,
                    stdout=(
                        "Signer #1 certificate DN: CN=redacted\n"
                        "Signer #1 certificate SHA-256 digest: "
                        f"{wrong_fingerprint}\n"
                    ),
                    stderr="",
                )
            return self._fake_run_checked(values, timeout=timeout, env=env)

        with (
            mock.patch.object(module, "require_tools"),
            mock.patch.object(module, "require_expected_serial", return_value=SERIAL),
            mock.patch.object(module, "prove_registered_device"),
            mock.patch.object(module, "run_checked", side_effect=fake_mismatch),
            mock.patch.dict(os.environ, private_env, clear=True),
        ):
            with self.assertRaises(module.SigningIdentityFailure):
                module.verify_installed_signer(SHA)

    def test_source_has_no_phone_mutation_or_signing_key_generation_surface(self) -> None:
        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertIn('"adb", "-s", expected_serial, "pull"', source)
        self.assertIn('"apksigner", "verify", "--print-certs"', source)
        self.assertIn('"keytool",\n            "-list",\n            "-v"', source)
        self.assertIn("from scripts.run_private_phone_preflight", source)
        self.assertIn("from run_private_phone_preflight", source)
        self.assertNotIn('"adb", "-s", expected_serial, "install"', source)
        self.assertNotIn("adb install", source)
        self.assertNotIn("install -r", source)
        self.assertNotIn("keytool -genkey", source)
        self.assertNotIn("-genkeypair", source)
        self.assertNotIn("VULTR_API_KEY", source)
        self.assertNotIn("requests.", source)
        self.assertNotIn("urllib.request", source)
        self.assertNotIn("hashlib", source)


if __name__ == "__main__":
    unittest.main()
