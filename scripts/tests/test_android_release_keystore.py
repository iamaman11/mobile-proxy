from __future__ import annotations

import base64
import os
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from scripts import verify_android_release_keystore as module

SHA = "a" * 40
KEYSTORE = b"bounded-test-keystore"
KEYSTORE_B64 = base64.b64encode(KEYSTORE).decode("ascii")
SECRET_ALIAS = "supersecretalias"


class AndroidReleaseKeystoreTests(unittest.TestCase):
    def test_private_inputs_are_required_and_canonical(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(module.ReleaseKeystoreFailure):
                module.require_private_text(module._KEY_ALIAS_ENV, maximum=256)
        with mock.patch.dict(os.environ, {module._KEY_ALIAS_ENV: "alias\nleak"}, clear=True):
            with self.assertRaises(module.ReleaseKeystoreFailure):
                module.require_private_text(module._KEY_ALIAS_ENV, maximum=256)
        self.assertEqual(
            module.decode_canonical_base64(KEYSTORE_B64, "keystore", maximum_bytes=1024),
            KEYSTORE,
        )
        with self.assertRaises(module.ReleaseKeystoreFailure):
            module.decode_canonical_base64("not-base64", "keystore", maximum_bytes=1024)

    def test_probe_jar_is_ephemeral_non_production_content(self) -> None:
        with self.subTest("jar creation"):
            from tempfile import TemporaryDirectory

            with TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / "proof.jar"
                module.create_probe_jar(path)
                self.assertTrue(path.is_file())
                self.assertGreater(path.stat().st_size, 0)

    def _fake_run_checked(
        self,
        command: list[str] | tuple[str, ...],
        *,
        timeout: int = 30,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del timeout
        values = list(command)
        if values[:2] == ["keytool", "-list"]:
            self.assertIn("-storepass:env", values)
            self.assertNotIn("test-store-password", values)
            self.assertIsNotNone(env)
            assert env is not None
            self.assertEqual(env[module._KEYSTORE_PASSWORD_ENV], "test-store-password")
            return subprocess.CompletedProcess(values, 0, stdout="", stderr="")
        if values and values[0] == "jarsigner" and "-verify" not in values:
            self.assertIn("-storepass:env", values)
            self.assertIn("-keypass:env", values)
            self.assertNotIn("test-store-password", values)
            self.assertNotIn("test-key-password", values)
            self.assertIsNotNone(env)
            assert env is not None
            self.assertEqual(env[module._KEYSTORE_PASSWORD_ENV], "test-store-password")
            self.assertEqual(env[module._KEY_PASSWORD_ENV], "test-key-password")
            return subprocess.CompletedProcess(values, 0, stdout="", stderr="")
        if values[:2] == ["jarsigner", "-verify"]:
            return subprocess.CompletedProcess(values, 0, stdout="jar verified", stderr="")
        self.fail(f"unexpected command: {values!r}")

    def test_verifies_all_four_private_inputs_without_phone_access(self) -> None:
        private_env = {
            "ANDROID_RELEASE_KEYSTORE_B64": KEYSTORE_B64,
            "ANDROID_RELEASE_KEYSTORE_PASSWORD": "test-store-password",
            "ANDROID_RELEASE_KEY_ALIAS": SECRET_ALIAS,
            "ANDROID_RELEASE_KEY_PASSWORD": "test-key-password",
        }
        with (
            mock.patch.object(module, "require_tools"),
            mock.patch.object(module, "run_checked", side_effect=self._fake_run_checked),
            mock.patch.dict(os.environ, private_env, clear=True),
        ):
            report = module.verify_release_keystore(SHA)
        self.assertTrue(report["accepted"])
        self.assertTrue(report["keystore_decoded"])
        self.assertTrue(report["keystore_password_verified"])
        self.assertTrue(report["key_alias_verified"])
        self.assertTrue(report["private_key_password_verified"])
        self.assertTrue(report["ephemeral_signature_verified"])
        self.assertFalse(report["phone_access_performed"])
        self.assertFalse(report["phone_mutation_performed"])
        self.assertFalse(report["production_apk_signed"])
        self.assertFalse(report["signing_key_generated"])
        self.assertFalse(report["signing_material_recorded"])
        self.assertFalse(report["secret_derived_value_recorded"])
        serialized = repr(report)
        for forbidden in (
            KEYSTORE_B64,
            "test-store-password",
            "test-key-password",
            SECRET_ALIAS,
        ):
            self.assertNotIn(forbidden, serialized)

    def test_invalid_alias_fails_before_signing(self) -> None:
        private_env = {
            "ANDROID_RELEASE_KEYSTORE_B64": KEYSTORE_B64,
            "ANDROID_RELEASE_KEYSTORE_PASSWORD": "test-store-password",
            "ANDROID_RELEASE_KEY_ALIAS": "bad alias",
            "ANDROID_RELEASE_KEY_PASSWORD": "test-key-password",
        }
        with (
            mock.patch.object(module, "require_tools"),
            mock.patch.dict(os.environ, private_env, clear=True),
        ):
            with self.assertRaises(module.ReleaseKeystoreFailure):
                module.verify_release_keystore(SHA)

    def test_source_has_no_phone_provider_or_key_generation_surface(self) -> None:
        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertIn('"jarsigner",', source)
        self.assertIn('"keytool",', source)
        for forbidden in (
            '"adb"',
            "adb install",
            "install -r",
            "-genkeypair",
            "keytool -genkey",
            "VULTR_API_KEY",
            "requests.",
            "urllib.request",
            "apksigner",
            "hashlib",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
