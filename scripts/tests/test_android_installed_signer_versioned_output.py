from __future__ import annotations

import unittest

from scripts import verify_android_installed_signer as module

CERTIFICATE_FINGERPRINT = "12" * 32
OTHER_FINGERPRINT = "34" * 32


class AndroidInstalledSignerVersionedOutputTests(unittest.TestCase):
    def test_accepts_build_tools_37_scheme_qualified_output(self) -> None:
        output = (
            "V2 Signer: certificate SHA-256 digest: "
            f"{CERTIFICATE_FINGERPRINT}\n"
            "V3.0 Signer: certificate SHA-256 digest: "
            f"{CERTIFICATE_FINGERPRINT}\n"
        )
        self.assertEqual(
            module.parse_single_apksigner_fingerprint(output),
            CERTIFICATE_FINGERPRINT,
        )

    def test_accepts_versioned_sdk_range_records_for_one_identity(self) -> None:
        output = (
            "V3.0 Signer (minSdkVersion=28, maxSdkVersion=32): "
            "certificate SHA-256 digest: "
            f"{CERTIFICATE_FINGERPRINT}\n"
            "V3.1 Signer (minSdkVersion=33, maxSdkVersion=2147483647): "
            "certificate SHA-256 digest: "
            f"{CERTIFICATE_FINGERPRINT}\n"
        )
        self.assertEqual(
            module.parse_single_apksigner_fingerprint(output),
            CERTIFICATE_FINGERPRINT,
        )

    def test_rejects_distinct_versioned_signing_identities(self) -> None:
        output = (
            "V2 Signer: certificate SHA-256 digest: "
            f"{CERTIFICATE_FINGERPRINT}\n"
            "V3.0 Signer: certificate SHA-256 digest: "
            f"{OTHER_FINGERPRINT}\n"
        )
        with self.assertRaises(module.SigningIdentityFailure):
            module.parse_single_apksigner_fingerprint(output)

    def test_rejects_mixed_legacy_and_versioned_formats(self) -> None:
        output = (
            "Signer #1 certificate SHA-256 digest: "
            f"{CERTIFICATE_FINGERPRINT}\n"
            "V3.0 Signer: certificate SHA-256 digest: "
            f"{CERTIFICATE_FINGERPRINT}\n"
        )
        with self.assertRaises(module.SigningIdentityFailure):
            module.parse_single_apksigner_fingerprint(output)

    def test_rejects_unknown_versioned_signer_record(self) -> None:
        output = (
            "V3.3 Signer: certificate SHA-256 digest: "
            f"{CERTIFICATE_FINGERPRINT}\n"
        )
        with self.assertRaises(module.SigningIdentityFailure):
            module.parse_single_apksigner_fingerprint(output)


if __name__ == "__main__":
    unittest.main()
