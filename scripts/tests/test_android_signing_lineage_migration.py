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
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            apk = root / "candidate.apk"
            apk.write_bytes(b"signed-apk")
            evidence = root / "release.json"
            evidence.write_text("{}", encoding="utf-8")
            digest_tool = root / "android-artifact-digest"
            digest_tool.write_text("tool", encoding="utf-8")
            os.chmod(digest_tool, 0o700)
            args = argparse.Namespace(
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
            with (
                mock.patch.object(module, "require_expected_serial", return_value="registered-device"),
                mock.patch.object(module.shutil, "which", return_value="/usr/bin/adb"),
                mock.patch.object(module, "load_json", return_value={}),
                mock.patch.object(module, "verify_release_evidence", return_value=new_digest),
                mock.patch.object(module, "exact_preflight"),
                mock.patch.object(module, "package_version", side_effect=[(2, "1.1.0"), (1004, "0.1.4")]),
                mock.patch.object(module, "capture_installed_apk", return_value=old_digest),
                mock.patch.object(module, "uninstall"),
                mock.patch.object(module, "install"),
                mock.patch.object(
                    module,
                    "verify_installed_apk_digest",
                    side_effect=module.MigrationFailure("installed candidate differs"),
                ),
                mock.patch.object(module, "restart_runtime_supervisor") as restart,
                mock.patch.object(module, "wait_for_local_health") as health,
                mock.patch.object(module, "restore_old_generation", return_value=True) as rollback,
            ):
                report, accepted = module.migrate(args)

        self.assertFalse(accepted)
        self.assertTrue(report["rollback_attempted"])
        self.assertTrue(report["rollback_succeeded"])
        rollback.assert_called_once()
        restart.assert_not_called()
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

    def test_supervisor_restart_is_exact_runtime_process_only(self):
        shell = module._supervisor_restart_shell()
        self.assertIn("/data/adb/mobile-proxy-node/current/bin/runtime-supervisor", shell)
        self.assertIn("--runtime-root /data/adb/mobile-proxy-node/current", shell)
        self.assertNotIn("reboot", shell)
        self.assertNotIn("svc data", shell)
        self.assertNotIn("airplane", shell)


if __name__ == "__main__":
    unittest.main()
