import importlib.util
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

    def test_release_evidence_requires_preserved_august_source(self):
        with tempfile.TemporaryDirectory() as raw:
            apk = Path(raw) / "app.apk"
            apk.write_bytes(b"signed-apk")
            evidence = {
                "format_version": 1,
                "repository": "iamaman11/mobile-proxy",
                "canonical_sha": "a" * 40,
                "android_baseline_ref": "v0.1.3",
                "android_functional_source_preserved": False,
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
                "artifact_sha256": "b" * 64,
                "accepted": True,
            }
            with self.assertRaises(module.MigrationFailure):
                module.verify_release_evidence(evidence, "a" * 40, apk, "0.1.4", 1004)

    def test_release_evidence_requires_exact_apk_checksum(self):
        with tempfile.TemporaryDirectory() as raw:
            apk = Path(raw) / "app.apk"
            apk.write_bytes(b"signed-apk")
            evidence = {
                "format_version": 1,
                "repository": "iamaman11/mobile-proxy",
                "canonical_sha": "a" * 40,
                "android_baseline_ref": "v0.1.3",
                "android_functional_source_preserved": True,
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
                "artifact_sha256": "b" * 64,
                "accepted": True,
            }
            with mock.patch.object(module, "sha256_file", return_value="c" * 64):
                with self.assertRaises(module.MigrationFailure):
                    module.verify_release_evidence(evidence, "a" * 40, apk, "0.1.4", 1004)

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
        self.assertEqual(adb_call.call_args_list[0].args[:3], (serial, "uninstall", module._PACKAGE))
        self.assertEqual(adb_call.call_args_list[1].args[:3], (serial, "install", str(apk)))

    def test_supervisor_restart_is_exact_runtime_process_only(self):
        shell = module._supervisor_restart_shell()
        self.assertIn("/data/adb/mobile-proxy-node/current/bin/runtime-supervisor", shell)
        self.assertIn("--runtime-root /data/adb/mobile-proxy-node/current", shell)
        self.assertNotIn("reboot", shell)
        self.assertNotIn("svc data", shell)
        self.assertNotIn("airplane", shell)


if __name__ == "__main__":
    unittest.main()
