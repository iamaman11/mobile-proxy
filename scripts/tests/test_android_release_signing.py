from __future__ import annotations

import subprocess
import unittest
from unittest import mock

from scripts import android_release_signing as module

SHA = "a" * 40
CERTIFICATE_FINGERPRINT = "12" * 32
OTHER_FINGERPRINT = "34" * 32
KEYTOOL_FINGERPRINT = ":".join(
    CERTIFICATE_FINGERPRINT[index : index + 2].upper()
    for index in range(0, len(CERTIFICATE_FINGERPRINT), 2)
)


class AndroidReleaseSigningTests(unittest.TestCase):
    def test_canonical_sha_is_exactly_lowercase_git_sha(self) -> None:
        self.assertEqual(module.require_canonical_sha(SHA), SHA)
        for invalid in ("", "A" * 40, "a" * 39, "a" * 41, "g" * 40):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    module.require_canonical_sha(invalid)

    def test_parses_supported_single_tool_reported_fingerprints(self) -> None:
        numbered = (
            "Signer #1 certificate SHA-256 digest: "
            f"{CERTIFICATE_FINGERPRINT}\n"
        )
        ranged = (
            "Signer (minSdkVersion=28, maxSdkVersion=32) certificate SHA-256 digest: "
            f"{CERTIFICATE_FINGERPRINT}\n"
            "Signer (minSdkVersion=33 (dev release=true), maxSdkVersion=2147483647) "
            "certificate SHA-256 digest: "
            f"{CERTIFICATE_FINGERPRINT}\n"
        )
        versioned = (
            "V2 Signer: certificate SHA-256 digest: "
            f"{CERTIFICATE_FINGERPRINT}\n"
            "V3.0 Signer: certificate SHA-256 digest: "
            f"{CERTIFICATE_FINGERPRINT}\n"
        )
        versioned_ranges = (
            "V3.0 Signer (minSdkVersion=28, maxSdkVersion=32): "
            "certificate SHA-256 digest: "
            f"{CERTIFICATE_FINGERPRINT}\n"
            "V3.1 Signer (minSdkVersion=33, maxSdkVersion=2147483647): "
            "certificate SHA-256 digest: "
            f"{CERTIFICATE_FINGERPRINT}\n"
        )
        for output in (numbered, ranged, versioned, versioned_ranges):
            with self.subTest(output=output.splitlines()[0]):
                self.assertEqual(
                    module.parse_single_apksigner_fingerprint(output),
                    CERTIFICATE_FINGERPRINT,
                )
        self.assertEqual(
            module.parse_single_keytool_fingerprint(
                f"Certificate fingerprints:\n\t SHA256: {KEYTOOL_FINGERPRINT}\n"
            ),
            CERTIFICATE_FINGERPRINT,
        )

    def test_signer_inventory_variants_fail_closed(self) -> None:
        numbered = (
            "Signer #1 certificate SHA-256 digest: " + CERTIFICATE_FINGERPRINT + "\n"
        )
        ranged = (
            "Signer (minSdkVersion=28, maxSdkVersion=32) certificate SHA-256 digest: "
            + CERTIFICATE_FINGERPRINT
            + "\n"
        )
        for output in (
            "",
            numbered
            + "Signer #2 certificate SHA-256 digest: "
            + CERTIFICATE_FINGERPRINT
            + "\n",
            numbered + ranged,
            "V2 Signer: certificate SHA-256 digest: "
            + CERTIFICATE_FINGERPRINT
            + "\nV3.0 Signer: certificate SHA-256 digest: "
            + OTHER_FINGERPRINT
            + "\n",
            "V3.3 Signer: certificate SHA-256 digest: "
            + CERTIFICATE_FINGERPRINT
            + "\n",
        ):
            with self.subTest(output=output):
                with self.assertRaises(module.AndroidReleaseSigningFailure):
                    module.parse_single_apksigner_fingerprint(output)

    def test_keystore_fingerprint_uses_password_environment_not_argv(self) -> None:
        completed = subprocess.CompletedProcess(
            ["keytool"],
            0,
            stdout=f"Certificate fingerprints:\n\t SHA256: {KEYTOOL_FINGERPRINT}\n",
            stderr="",
        )
        with mock.patch.object(module, "run_checked", return_value=completed) as run:
            fingerprint = module.read_keystore_fingerprint(
                __import__("pathlib").Path("release.keystore"),
                "release",
                "private-store-password",
            )
        self.assertEqual(fingerprint, CERTIFICATE_FINGERPRINT)
        command = run.call_args.args[0]
        self.assertIn("-storepass:env", command)
        self.assertNotIn("private-store-password", command)
        env = run.call_args.kwargs["env"]
        self.assertEqual(
            env[module._KEYSTORE_PASSWORD_ENV],
            "private-store-password",
        )


if __name__ == "__main__":
    unittest.main()
