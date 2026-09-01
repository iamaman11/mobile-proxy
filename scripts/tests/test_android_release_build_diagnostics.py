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
BADGING = "package: name='com.example.mobileproxy' versionCode='1004' versionName='0.1.4'\n"


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
            (["/sdk/build-tools/37.0.0/aapt2", "dump", "private.apk"], "APK metadata verification subprocess failed"),
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

    def test_apk_identity_prefers_aapt2(self) -> None:
        with (
            mock.patch.object(module, "resolve_android_build_tool", return_value="/sdk/aapt2") as resolve,
            mock.patch.object(module, "run_checked", return_value=mock.Mock(stdout=BADGING)) as run,
        ):
            identity = module.read_apk_identity(Path("release.apk"))
        self.assertEqual(identity, ("com.example.mobileproxy", 1004, "0.1.4"))
        resolve.assert_called_once_with("aapt2")
        self.assertEqual(run.call_args.args[0][0], "/sdk/aapt2")

    def test_apk_identity_falls_back_to_legacy_aapt(self) -> None:
        def resolve(name: str) -> str:
            return f"/sdk/{name}"

        with (
            mock.patch.object(module, "resolve_android_build_tool", side_effect=resolve),
            mock.patch.object(
                module,
                "run_checked",
                side_effect=[
                    module.AndroidBuildFailure("APK metadata verification subprocess failed"),
                    mock.Mock(stdout=BADGING),
                ],
            ) as run,
        ):
            identity = module.read_apk_identity(Path("release.apk"))
        self.assertEqual(identity, ("com.example.mobileproxy", 1004, "0.1.4"))
        self.assertEqual(run.call_args_list[0].args[0][0], "/sdk/aapt2")
        self.assertEqual(run.call_args_list[1].args[0][0], "/sdk/aapt")

    def test_apk_identity_fails_closed_when_all_readers_fail(self) -> None:
        with (
            mock.patch.object(module, "resolve_android_build_tool", side_effect=lambda name: f"/sdk/{name}"),
            mock.patch.object(
                module,
                "run_checked",
                side_effect=module.AndroidBuildFailure("APK metadata verification subprocess failed"),
            ),
        ):
            with self.assertRaisesRegex(module.AndroidBuildFailure, "APK metadata verification subprocess failed"):
                module.read_apk_identity(Path("release.apk"))


if __name__ == "__main__":
    unittest.main()
