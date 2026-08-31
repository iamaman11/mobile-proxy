import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "verify_android_release_contract.py"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("verify_android_release_contract", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


class AndroidReleaseContractTests(unittest.TestCase):
    def test_current_repository_release_contract(self):
        report = module.verify_contract(REPOSITORY_ROOT)
        self.assertTrue(report["accepted"])
        self.assertEqual(report["application_id"], "com.example.mobileproxy")

    def test_semver_maps_to_monotonic_android_version_code(self):
        self.assertEqual(module.android_version_code("0.1.3"), 1003)
        self.assertEqual(module.android_version_code("0.1.4"), 1004)
        self.assertEqual(module.android_version_code("0.2.0"), 2000)
        self.assertEqual(module.android_version_code("1.0.0"), 1_000_000)

    def test_contract_accepts_matching_release_identity(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "apps/android-app/app").mkdir(parents=True)
            (root / "Cargo.toml").write_text(
                '[workspace]\n[workspace.package]\nversion = "0.1.4"\n',
                encoding="utf-8",
            )
            (root / "apps/android-app/app/build.gradle.kts").write_text(
                '''
applicationId = "com.example.mobileproxy"
versionCode = 1004
versionName = "0.1.4"
val a = providers.environmentVariable("ANDROID_RELEASE_KEYSTORE_PATH")
val b = providers.environmentVariable("ANDROID_RELEASE_KEYSTORE_PASSWORD")
val c = providers.environmentVariable("ANDROID_RELEASE_KEY_ALIAS")
val d = providers.environmentVariable("ANDROID_RELEASE_KEY_PASSWORD")
create("productionRelease")
signingConfig = signingConfigs.getByName("productionRelease")
''',
                encoding="utf-8",
            )
            report = module.verify_contract(root, "0.1.4")
            self.assertTrue(report["accepted"])
            self.assertEqual(report["version_code"], 1004)

    def test_contract_rejects_historical_android_numbering_drift(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "apps/android-app/app").mkdir(parents=True)
            (root / "Cargo.toml").write_text(
                '[workspace]\n[workspace.package]\nversion = "0.1.4"\n',
                encoding="utf-8",
            )
            (root / "apps/android-app/app/build.gradle.kts").write_text(
                '''
applicationId = "com.example.mobileproxy"
versionCode = 2
versionName = "1.1.0"
val a = providers.environmentVariable("ANDROID_RELEASE_KEYSTORE_PATH")
val b = providers.environmentVariable("ANDROID_RELEASE_KEYSTORE_PASSWORD")
val c = providers.environmentVariable("ANDROID_RELEASE_KEY_ALIAS")
val d = providers.environmentVariable("ANDROID_RELEASE_KEY_PASSWORD")
create("productionRelease")
signingConfig = signingConfigs.getByName("productionRelease")
''',
                encoding="utf-8",
            )
            with self.assertRaises(module.ContractFailure):
                module.verify_contract(root, "0.1.4")


if __name__ == "__main__":
    unittest.main()
