from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from create_release_bundle_v2 import ReleaseBundleError, create_bundle


class ReleaseBundleV2Tests(unittest.TestCase):
    tag = "v0.1.4"
    sha = "a" * 40

    def fixture(self, root: Path) -> Path:
        release = root / "release"
        release.mkdir()
        (release / f"mobile-proxy-linux-x86_64-{self.tag}.tar.gz").write_bytes(b"linux-artifact")
        (release / f"mobile-proxy-android-{self.tag}.apk").write_bytes(b"android-artifact")
        evidence = {
            "format_version": 1,
            "repository": "iamaman11/mobile-proxy",
            "canonical_sha": self.sha,
            "application_id": "com.example.mobileproxy",
            "version_name": "0.1.4",
            "version_code": 1004,
            "artifact_name": f"mobile-proxy-android-{self.tag}.apk",
            "release_contract_verified": True,
            "keystore_verified": True,
            "apk_signature_verified": True,
            "apk_signer_matches_private_key": True,
            "production_apk_signed": True,
            "phone_access_performed": False,
            "phone_mutation_performed": False,
            "signing_material_recorded": False,
            "signer_fingerprint_recorded": False,
            "accepted": True,
        }
        evidence_path = release / "android-release-evidence.json"
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        return evidence_path

    def build(self, release: Path, evidence: Path, **overrides):
        kwargs = {
            "release_dir": release,
            "tag": self.tag,
            "source_sha": self.sha,
            "android_evidence_path": evidence,
            "builder": "https://github.com/iamaman11/mobile-proxy/actions/runs/123",
            "workflow_ref": "iamaman11/mobile-proxy/.github/workflows/release.yml@refs/tags/v0.1.4",
            "github_native_attestation": True,
        }
        kwargs.update(overrides)
        return create_bundle(**kwargs)

    def test_valid_bundle_binds_linux_android_and_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            release = Path(raw) / "release"
            evidence = self.fixture(Path(raw))
            manifest, provenance, checksums = self.build(release, evidence)
            self.assertEqual(manifest["format_version"], 2)
            self.assertEqual(provenance["format_version"], 2)
            artifacts = {item["name"]: item for item in manifest["artifacts"]}
            apk_name = f"mobile-proxy-android-{self.tag}.apk"
            linux_name = f"mobile-proxy-linux-x86_64-{self.tag}.tar.gz"
            self.assertEqual(set(artifacts), {apk_name, linux_name})
            self.assertEqual(artifacts[apk_name]["kind"], "android-apk")
            self.assertEqual(artifacts[apk_name]["package_name"], "com.example.mobileproxy")
            self.assertEqual(artifacts[apk_name]["version_name"], "0.1.4")
            self.assertEqual(artifacts[apk_name]["version_code"], 1004)
            self.assertEqual(checksums[apk_name], hashlib.sha256(b"android-artifact").hexdigest())
            self.assertEqual(checksums[linux_name], hashlib.sha256(b"linux-artifact").hexdigest())
            sums = (release / "SHA256SUMS").read_text(encoding="utf-8")
            self.assertIn("release-manifest.json", sums)
            self.assertIn("provenance.json", sums)
            self.assertNotIn("SHA256SUMS  SHA256SUMS", sums)

    def test_wrong_android_version_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            release = Path(raw) / "release"
            evidence = self.fixture(Path(raw))
            value = json.loads(evidence.read_text(encoding="utf-8"))
            value["version_name"] = "0.1.5"
            evidence.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(ReleaseBundleError):
                self.build(release, evidence)

    def test_wrong_android_package_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            release = Path(raw) / "release"
            evidence = self.fixture(Path(raw))
            value = json.loads(evidence.read_text(encoding="utf-8"))
            value["application_id"] = "other.package"
            evidence.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(ReleaseBundleError):
                self.build(release, evidence)

    def test_unverified_or_phone_tainted_android_evidence_is_refused(self) -> None:
        for field, value in (("apk_signature_verified", False), ("phone_access_performed", True)):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as raw:
                release = Path(raw) / "release"
                evidence = self.fixture(Path(raw))
                body = json.loads(evidence.read_text(encoding="utf-8"))
                body[field] = value
                evidence.write_text(json.dumps(body), encoding="utf-8")
                with self.assertRaises(ReleaseBundleError):
                    self.build(release, evidence)

    def test_missing_product_artifact_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            release = Path(raw) / "release"
            evidence = self.fixture(Path(raw))
            (release / f"mobile-proxy-android-{self.tag}.apk").unlink()
            with self.assertRaises(ReleaseBundleError):
                self.build(release, evidence)

    def test_contract_does_not_copy_private_build_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            release = Path(raw) / "release"
            evidence = self.fixture(Path(raw))
            manifest, provenance, _ = self.build(release, evidence)
            serialized = json.dumps({"manifest": manifest, "provenance": provenance})
            for forbidden in (
                "ANDROID_RELEASE_KEYSTORE",
                "signer_fingerprint",
                "target_binding",
                "phone_access_performed",
            ):
                self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
