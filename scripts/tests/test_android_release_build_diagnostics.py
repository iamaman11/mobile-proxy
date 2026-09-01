from __future__ import annotations

import importlib.util
import subprocess
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

    def test_subprocess_stage_labels_are_fixed_and_bounded(self) -> None:
        cases = [
            (["git", "status", "secret-ref"], "canonical source proof subprocess failed"),
            (["bash", "./gradlew", "--secret=value"], "Android Gradle release build subprocess failed"),
            (["/sdk/build-tools/37.0.0/apksigner", "verify", FINGERPRINT], "APK signature verification subprocess failed"),
            (["/sdk/build-tools/37.0.0/aapt", "dump", "private.apk"], "APK metadata verification subprocess failed"),
            (["cargo", "run", "--", "private.apk"], "typed Android artifact digest subprocess failed"),
            (["unexpected-tool", "private-value"], "canonical Android release build or verification subprocess failed"),
        ]
        for command, expected in cases:
            with self.subTest(command=command[0]):
                message = module.safe_subprocess_failure_message(command)
                self.assertEqual(message, expected)
                self.assertNotIn(FINGERPRINT, message)
                self.assertNotIn("secret", message)
                self.assertNotIn("private", message)

    def test_run_checked_does_not_echo_child_output_or_command_arguments(self) -> None:
        child_error = subprocess.CalledProcessError(
            1,
            ["bash", "./gradlew", "--password=private-label"],
            output=f"fingerprint={FINGERPRINT}",
            stderr="certificate DN: CN=private-label",
        )
        with mock.patch.object(module.subprocess, "run", side_effect=child_error):
            with self.assertRaises(module.AndroidBuildFailure) as captured:
                module.run_checked(["bash", "./gradlew", "--password=private-label"])
        message = str(captured.exception)
        self.assertEqual(message, "Android Gradle release build subprocess failed")
        self.assertNotIn(FINGERPRINT, message)
        self.assertNotIn("private-label", message)
        self.assertNotIn("password", message)


if __name__ == "__main__":
    unittest.main()
