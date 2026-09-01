from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parents[1] / "build_signed_android_release.py"
SPEC = importlib.util.spec_from_file_location("build_signed_android_release", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)

FINGERPRINT = "12" * 32


class AndroidReleaseBuildDiagnosticTests(unittest.TestCase):
    def test_safe_signer_shapes_redact_certificate_digest_and_ignore_dn(self) -> None:
        output = (
            "V3.0 Signer: certificate DN: CN=private-label\n"
            "V3.0 Signer: certificate SHA-256 digest: "
            f"{FINGERPRINT}\n"
        )
        shapes = module.safe_apksigner_signer_shapes(output)
        self.assertEqual(
            shapes,
            ["V3.0 Signer: certificate SHA-256 digest: <redacted>"],
        )
        self.assertNotIn(FINGERPRINT, "\n".join(shapes))
        self.assertNotIn("private-label", "\n".join(shapes))

    def test_unsafe_signer_label_is_not_echoed(self) -> None:
        output = (
            "Signer <secret/path>: certificate SHA-256 digest: "
            f"{FINGERPRINT}\n"
        )
        self.assertEqual(
            module.safe_apksigner_signer_shapes(output),
            ["<unavailable-label> certificate SHA-256 digest: <redacted>"],
        )

    def test_safe_apksigner_version_accepts_version_only(self) -> None:
        completed = mock.Mock(stdout="0.9-build37.0.0\n")
        with mock.patch.object(module.subprocess, "run", return_value=completed):
            self.assertEqual(
                module.safe_apksigner_version("/sdk/apksigner"),
                "0.9-build37.0.0",
            )

    def test_safe_apksigner_version_rejects_unexpected_text(self) -> None:
        completed = mock.Mock(stdout="version\nsecret=value\n")
        with mock.patch.object(module.subprocess, "run", return_value=completed):
            self.assertEqual(
                module.safe_apksigner_version("/sdk/apksigner"),
                "unavailable",
            )


if __name__ == "__main__":
    unittest.main()
