from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operations import install_apk as APK


TX = "apk-install-physical-1"
REF = "b3:" + "a" * 64
OTHER_REF = "b3:" + "b" * 64
SERIAL = "registered-device-1"


class FakeDigest:
    def __init__(self, *values: str) -> None:
        self.values = list(values)
        self.paths: list[Path] = []

    def digest(self, path: Path) -> str:
        self.paths.append(path)
        if not self.values:
            raise AssertionError("unexpected digest request")
        return self.values.pop(0)


class FakeCommands:
    def __init__(
        self,
        *,
        install_stdout: str = "Performing Streamed Install\nSuccess\n",
        package_stdout: str = "package:/data/app/example/base.apk\n",
        fail_install: bool = False,
        materialize_pull: bool = True,
    ) -> None:
        self.install_stdout = install_stdout
        self.package_stdout = package_stdout
        self.fail_install = fail_install
        self.materialize_pull = materialize_pull
        self.calls: list[tuple[tuple[str, ...], int]] = []

    def run(self, arguments, *, timeout_seconds: int):
        argv = tuple(arguments)
        self.calls.append((argv, timeout_seconds))
        if len(argv) >= 4 and argv[0] == "adb" and argv[3] == "install":
            if self.fail_install:
                raise APK.ApkExecutionFailure("simulated install transport failure")
            return APK.CommandResult(self.install_stdout)
        if argv[-4:] == ("shell", "pm", "path", "com.example.mobileproxy"):
            return APK.CommandResult(self.package_stdout)
        if len(argv) >= 4 and argv[0] == "adb" and argv[3] == "pull":
            if self.materialize_pull:
                Path(argv[-1]).write_bytes(b"installed-apk")
            return APK.CommandResult("1 file pulled\n")
        raise AssertionError(f"unexpected command: {argv!r}")


class CanonicalApkInstallExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="apk-executor-test-")
        self.addCleanup(self.temp.cleanup)
        self.apk = Path(self.temp.name) / "candidate.apk"
        self.apk.write_bytes(b"candidate-apk")
        self.request = APK.ApkInstallRequest(TX, REF)

    def executor(
        self,
        *,
        commands: FakeCommands | None = None,
        digests: FakeDigest | None = None,
        admitted_ref: str = REF,
    ) -> tuple[APK.CanonicalApkInstallExecutor, FakeCommands, FakeDigest]:
        command_edge = commands or FakeCommands()
        digest_edge = digests or FakeDigest(REF)
        executor = APK.CanonicalApkInstallExecutor(
            serial=SERIAL,
            apk_path=self.apk,
            admitted_artifact_ref=admitted_ref,
            commands=command_edge,
            digests=digest_edge,
        )
        return executor, command_edge, digest_edge

    def test_dispatch_proves_local_identity_then_invokes_one_replace_install(self) -> None:
        executor, commands, digests = self.executor()

        receipt = executor.dispatch_once(self.request)

        self.assertEqual(receipt.source_ref, f"apk-install:{TX}:{REF}")
        self.assertEqual(digests.paths, [self.apk.resolve()])
        self.assertEqual(
            commands.calls,
            [
                (
                    (
                        "adb",
                        "-s",
                        SERIAL,
                        "install",
                        "-r",
                        str(self.apk.resolve()),
                    ),
                    180,
                )
            ],
        )
        flattened = " ".join(commands.calls[0][0]).lower()
        self.assertNotIn("uninstall", flattened)
        self.assertNotIn("pm clear", flattened)

    def test_request_artifact_mismatch_refuses_before_digest_or_command(self) -> None:
        executor, commands, digests = self.executor(admitted_ref=REF)

        with self.assertRaisesRegex(APK.ApkExecutionFailure, "pre-admitted"):
            executor.dispatch_once(APK.ApkInstallRequest(TX, OTHER_REF))

        self.assertEqual(commands.calls, [])
        self.assertEqual(digests.paths, [])

    def test_local_artifact_mismatch_refuses_before_adb_dispatch(self) -> None:
        executor, commands, digests = self.executor(digests=FakeDigest(OTHER_REF))

        with self.assertRaisesRegex(APK.ApkExecutionFailure, "local APK content"):
            executor.dispatch_once(self.request)

        self.assertEqual(commands.calls, [])
        self.assertEqual(digests.paths, [self.apk.resolve()])

    def test_failed_install_propagates_without_retry(self) -> None:
        executor, commands, _ = self.executor(commands=FakeCommands(fail_install=True))

        with self.assertRaisesRegex(APK.ApkExecutionFailure, "simulated"):
            executor.dispatch_once(self.request)

        install_calls = [call for call in commands.calls if "install" in call[0]]
        self.assertEqual(len(install_calls), 1)

    def test_install_must_report_terminal_success(self) -> None:
        executor, commands, _ = self.executor(
            commands=FakeCommands(install_stdout="Performing Streamed Install\nFailure\n")
        )

        with self.assertRaisesRegex(APK.ApkExecutionFailure, "did not report success"):
            executor.dispatch_once(self.request)

        self.assertEqual(len(commands.calls), 1)

    def test_postcondition_proves_exact_installed_artifact_identity(self) -> None:
        executor, commands, digests = self.executor(digests=FakeDigest(REF))

        proof = executor.verify_postcondition(self.request)

        self.assertTrue(proof.passed)
        self.assertEqual(proof.source_ref, f"installed-apk:{REF}")
        self.assertEqual(len(commands.calls), 2)
        self.assertEqual(
            commands.calls[0],
            (("adb", "-s", SERIAL, "shell", "pm", "path", "com.example.mobileproxy"), 30),
        )
        self.assertEqual(commands.calls[1][0][:5], ("adb", "-s", SERIAL, "pull", "/data/app/example/base.apk"))
        self.assertEqual(len(digests.paths), 1)
        self.assertEqual(digests.paths[0].name, "installed-base.apk")

    def test_postcondition_digest_mismatch_is_known_failed_proof(self) -> None:
        executor, commands, _ = self.executor(digests=FakeDigest(OTHER_REF))

        proof = executor.verify_postcondition(self.request)

        self.assertFalse(proof.passed)
        self.assertEqual(proof.source_ref, f"installed-apk:{OTHER_REF}")
        self.assertEqual(len(commands.calls), 2)

    def test_postcondition_ambiguous_package_path_fails_closed_without_pull(self) -> None:
        commands = FakeCommands(
            package_stdout=(
                "package:/data/app/example/base.apk\n"
                "package:/data/app/example/split_config.apk\n"
            )
        )
        executor, commands, digests = self.executor(commands=commands, digests=FakeDigest(REF))

        proof = executor.verify_postcondition(self.request)

        self.assertFalse(proof.passed)
        self.assertEqual(proof.source_ref, "installed-apk:unobserved")
        self.assertEqual(len(commands.calls), 1)
        self.assertEqual(digests.paths, [])

    def test_postcondition_missing_capture_fails_closed(self) -> None:
        commands = FakeCommands(materialize_pull=False)
        executor, commands, digests = self.executor(commands=commands, digests=FakeDigest(REF))

        proof = executor.verify_postcondition(self.request)

        self.assertFalse(proof.passed)
        self.assertEqual(proof.source_ref, "installed-apk:unobserved")
        self.assertEqual(len(commands.calls), 2)
        self.assertEqual(digests.paths, [])

    def test_external_typed_digest_edge_accepts_only_canonical_shape(self) -> None:
        tool = Path(self.temp.name) / "android-artifact-digest"
        tool.write_text("placeholder", encoding="utf-8")
        tool.chmod(0o700)
        commands = FakeCommands()

        class DigestCommands:
            def __init__(self) -> None:
                self.calls = []

            def run(self, arguments, *, timeout_seconds: int):
                self.calls.append((tuple(arguments), timeout_seconds))
                return APK.CommandResult(REF + "\n")

        digest_commands = DigestCommands()
        edge = APK.ExternalTypedArtifactDigest(tool, digest_commands)
        self.assertEqual(edge.digest(self.apk), REF)
        self.assertEqual(
            digest_commands.calls,
            [((str(tool.resolve()), str(self.apk)), 120)],
        )

    def test_executor_source_has_no_cross_domain_destructive_behavior(self) -> None:
        source = (SCRIPT_DIR / "operations" / "install_apk.py").read_text(encoding="utf-8").lower()
        for forbidden in (
            "adb\", \"uninstall",
            "pm\", \"clear",
            "runtime-supervisor",
            "provider_credentials",
            "reboot",
            "github.com",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()