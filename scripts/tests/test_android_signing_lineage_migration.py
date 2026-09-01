import argparse
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parents[1] / "migrate_android_signing_lineage.py"
SPEC = importlib.util.spec_from_file_location("migrate_android_signing_lineage", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


class AndroidSigningLineageMigrationTests(unittest.TestCase):
    def test_parse_package_version(self):
        code, name = module.parse_package_version(
            """
            Package [com.example.mobileproxy] (abc):
              versionCode=2 minSdk=24 targetSdk=36
              versionName=1.1.0
            """
        )
        self.assertEqual(code, 2)
        self.assertEqual(name, "1.1.0")

    def release_evidence(self, *, source_preserved: bool = True) -> dict[str, object]:
        return {
            "format_version": 1,
            "repository": "iamaman11/mobile-proxy",
            "canonical_sha": "a" * 40,
            "android_baseline_ref": "v0.1.3",
            "android_functional_source_preserved": source_preserved,
            "application_id": "com.example.mobileproxy",
            "version_name": "0.1.4",
            "version_code": 1004,
            "release_contract_verified": True,
            "keystore_verified": True,
            "apk_signature_verified": True,
            "apk_signer_matches_private_key": True,
            "production_apk_signed": True,
            "phone_access_performed": False,
            "phone_mutation_performed": False,
            "artifact_digest": "b3:" + "b" * 64,
            "artifact_digest_algorithm": "blake3-256",
            "artifact_digest_domain": "mobile-proxy/android-apk/v1",
            "accepted": True,
        }

    def migration_args(self, root: Path) -> argparse.Namespace:
        apk = root / "candidate.apk"
        apk.write_bytes(b"signed-apk")
        evidence = root / "release.json"
        evidence.write_text("{}", encoding="utf-8")
        digest_tool = root / "android-artifact-digest"
        digest_tool.write_text("tool", encoding="utf-8")
        os.chmod(digest_tool, 0o700)
        return argparse.Namespace(
            canonical_sha="a" * 40,
            authorization=module._AUTHORIZATION,
            apk=apk,
            release_evidence=evidence,
            digest_tool=digest_tool,
            retained_old_apk=root / "old.apk",
            expected_old_version_name="1.1.0",
            expected_old_version_code=2,
            expected_version_name="0.1.4",
            expected_version_code=1004,
        )

    def test_release_evidence_requires_preserved_august_source(self):
        with tempfile.TemporaryDirectory() as raw:
            apk = Path(raw) / "app.apk"
            apk.write_bytes(b"signed-apk")
            with self.assertRaises(module.MigrationFailure):
                module.verify_release_evidence(
                    self.release_evidence(source_preserved=False),
                    "a" * 40,
                    apk,
                    Path(raw) / "digest-tool",
                    "0.1.4",
                    1004,
                )

    def test_release_evidence_requires_exact_apk_digest(self):
        with tempfile.TemporaryDirectory() as raw:
            apk = Path(raw) / "app.apk"
            apk.write_bytes(b"signed-apk")
            with mock.patch.object(
                module,
                "typed_artifact_digest",
                return_value="b3:" + "c" * 64,
            ):
                with self.assertRaises(module.MigrationFailure):
                    module.verify_release_evidence(
                        self.release_evidence(),
                        "a" * 40,
                        apk,
                        Path(raw) / "digest-tool",
                        "0.1.4",
                        1004,
                    )

    def test_installed_apk_digest_must_match_exact_signed_candidate(self):
        expected = "b3:" + "b" * 64
        with mock.patch.object(
            module,
            "capture_installed_apk",
            return_value="b3:" + "c" * 64,
        ):
            with self.assertRaises(module.MigrationFailure):
                module.verify_installed_apk_digest(
                    "registered-device",
                    expected,
                    Path("digest-tool"),
                )

    def test_installed_apk_digest_accepts_exact_signed_candidate(self):
        expected = "b3:" + "b" * 64
        with mock.patch.object(
            module,
            "capture_installed_apk",
            return_value=expected,
        ) as capture:
            module.verify_installed_apk_digest(
                "registered-device",
                expected,
                Path("digest-tool"),
            )
        capture.assert_called_once()

    def test_post_install_identity_mismatch_triggers_existing_rollback(self):
        new_digest = "b3:" + "b" * 64
        old_digest = "b3:" + "c" * 64
        rollback_state = module.rollback_state_template()
        rollback_state.update(
            rollback_package_installed=True,
            rollback_package_version_verified=True,
        )
        with tempfile.TemporaryDirectory() as raw:
            args = self.migration_args(Path(raw))
            with (
                mock.patch.object(module, "require_expected_serial", return_value="registered-device"),
                mock.patch.object(module.shutil, "which", return_value="/usr/bin/adb"),
                mock.patch.object(module, "load_json", return_value={}),
                mock.patch.object(module, "verify_release_evidence", return_value=new_digest),
                mock.patch.object(module, "exact_preflight"),
                mock.patch.object(
                    module,
                    "package_version",
                    side_effect=[(2, "1.1.0"), (1004, "0.1.4")],
                ),
                mock.patch.object(module, "capture_installed_apk", return_value=old_digest),
                mock.patch.object(module, "uninstall"),
                mock.patch.object(module, "install"),
                mock.patch.object(
                    module,
                    "verify_installed_apk_digest",
                    side_effect=module.MigrationFailure("installed candidate differs"),
                ),
                mock.patch.object(module, "bootstrap_runtime") as bootstrap,
                mock.patch.object(module, "wait_for_local_health") as health,
                mock.patch.object(module, "restore_old_generation", return_value=rollback_state) as rollback,
            ):
                report, accepted = module.migrate(args)

        self.assertFalse(accepted)
        self.assertTrue(report["rollback_attempted"])
        self.assertTrue(report["rollback_package_installed"])
        self.assertTrue(report["rollback_package_version_verified"])
        self.assertFalse(report["rollback_runtime_healthy"])
        rollback.assert_called_once()
        bootstrap.assert_not_called()
        health.assert_not_called()

    def test_each_mutation_calls_registered_device_preflight_first(self):
        serial = "registered-device"
        apk = Path("app.apk")
        with mock.patch.object(module, "exact_preflight") as preflight, mock.patch.object(
            module, "adb"
        ) as adb_call, mock.patch.object(module, "package_present", side_effect=[False, True]):
            adb_call.return_value.stdout = "Success\n"
            module.uninstall(serial)
            module.install(serial, apk)
        self.assertEqual(preflight.call_count, 2)
        self.assertEqual(
            adb_call.call_args_list[0].args[:3],
            (serial, "uninstall", module._PACKAGE),
        )
        self.assertEqual(
            adb_call.call_args_list[1].args[:3],
            (serial, "install", str(apk)),
        )

    def test_runtime_bootstrap_uses_owned_service_entrypoint_only(self):
        shell = module._runtime_bootstrap_shell()
        self.assertIn("/data/adb/mobile-proxy-node/current/service.sh", shell)
        self.assertIn("/data/adb/mobile-proxy-node/current/bin/runtime-supervisor", shell)
        self.assertIn("/data/adb/mobile-proxy-node/current/config/host-daemon.json", shell)
        self.assertNotIn("reboot", shell)
        self.assertNotIn("svc data", shell)
        self.assertNotIn("airplane", shell)

    def test_runtime_bootstrap_requires_registered_device_preflight(self):
        with mock.patch.object(module, "exact_preflight") as preflight, mock.patch.object(
            module, "adb"
        ) as adb_call:
            module.bootstrap_runtime("registered-device")
        preflight.assert_called_once_with("registered-device")
        self.assertEqual(
            adb_call.call_args.args[:6],
            ("registered-device", "shell", "su", "0", "sh", "-c"),
        )
        self.assertIn(module._RUNTIME_SERVICE, adb_call.call_args.args[6])

    def test_rollback_evidence_distinguishes_package_restore_from_runtime_health(self):
        with (
            mock.patch.object(module, "package_present", return_value=True),
            mock.patch.object(module, "uninstall"),
            mock.patch.object(module, "install"),
            mock.patch.object(module, "package_version", return_value=(2, "1.1.0")),
            mock.patch.object(module, "bootstrap_runtime"),
            mock.patch.object(
                module,
                "wait_for_local_health",
                side_effect=module.MigrationFailure("runtime unhealthy"),
            ),
        ):
            state = module.restore_old_generation(
                "registered-device",
                Path("old.apk"),
                2,
                "1.1.0",
            )

        self.assertTrue(state["rollback_package_removed_before_restore"])
        self.assertTrue(state["rollback_package_installed"])
        self.assertTrue(state["rollback_package_version_verified"])
        self.assertTrue(state["rollback_runtime_bootstrap_invoked"])
        self.assertFalse(state["rollback_runtime_healthy"])
        self.assertFalse(state["rollback_succeeded"])

    def test_successful_migration_bootstraps_runtime_after_install(self):
        new_digest = "b3:" + "b" * 64
        old_digest = "b3:" + "c" * 64
        health_state = {
            "runtime_supervisor_running": True,
            "cellular_egress_service_running": True,
            "local_proxy_ports_ready": True,
        }
        with tempfile.TemporaryDirectory() as raw:
            args = self.migration_args(Path(raw))
            with (
                mock.patch.object(module, "require_expected_serial", return_value="registered-device"),
                mock.patch.object(module.shutil, "which", return_value="/usr/bin/adb"),
                mock.patch.object(module, "load_json", return_value={}),
                mock.patch.object(module, "verify_release_evidence", return_value=new_digest),
                mock.patch.object(module, "exact_preflight"),
                mock.patch.object(
                    module,
                    "package_version",
                    side_effect=[(2, "1.1.0"), (1004, "0.1.4")],
                ),
                mock.patch.object(module, "capture_installed_apk", return_value=old_digest),
                mock.patch.object(module, "uninstall"),
                mock.patch.object(module, "install"),
                mock.patch.object(module, "verify_installed_apk_digest"),
                mock.patch.object(module, "bootstrap_runtime") as bootstrap,
                mock.patch.object(module, "wait_for_local_health", return_value=health_state),
                mock.patch.object(module, "restore_old_generation") as rollback,
            ):
                report, accepted = module.migrate(args)

        self.assertTrue(accepted)
        self.assertTrue(report["accepted"])
        self.assertEqual(report["format_version"], 2)
        self.assertTrue(report["runtime_bootstrap_invoked"])
        self.assertTrue(report["runtime_supervisor_running"])
        self.assertTrue(report["cellular_egress_service_running"])
        bootstrap.assert_called_once_with("registered-device")
        rollback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
