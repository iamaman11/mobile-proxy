from __future__ import annotations

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

    @staticmethod
    def fake_digest(_repository_root: Path, asset_name: str, path: Path) -> str:
        seed = (sum(asset_name.encode("utf-8")) + len(path.read_bytes())) % 16
        return "b3:" + format(seed, "x") * 64

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
            "repository_root": release.parent,
            "release_dir": release,
            "tag": self.tag,
            "source_sha": self.sha,
            "android_evidence_path": evidence,
            "builder": "https://github.com/iamaman11/mobile-proxy/actions/runs/123",
            "workflow_ref": "iamaman11/mobile-proxy/.github/workflows/release.yml@refs/tags/v0.1.4",
            "github_native_attestation": True,
            "digest_file": self.fake_digest,
        }
        kwargs.update(overrides)
        return create_bundle(**kwargs)

    def test_valid_bundle_binds_linux_android_and_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            release = Path(raw) / "release"
            evidence = self.fixture(Path(raw))
            manifest, provenance, digests = self.build(release, evidence)
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
            self.assertEqual(artifacts[apk_name]["content_digest"], digests[apk_name])
            self.assertEqual(artifacts[linux_name]["content_digest"], digests[linux_name])
            digest_set = json.loads((release / "artifact-digests.json").read_text(encoding="utf-8"))
            self.assertEqual(digest_set["format_version"], 1)
            self.assertEqual(digest_set["algorithm"], "blake3-256")
            self.assertEqual(digest_set["digest_domain"], "mobile-proxy/product-release-asset/v2")
            covered = {entry["name"] for entry in digest_set["assets"]}
            self.assertEqual(
                covered,
                {apk_name, linux_name, "release-manifest.json", "provenance.json"},
            )
            self.assertNotIn("artifact-digests.json", covered)

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

    def test_invalid_typed_digest_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            release = Path(raw) / "release"
            evidence = self.fixture(Path(raw))
            with self.assertRaises(ReleaseBundleError):
                self.build(release, evidence, digest_file=lambda *_args: "invalid")

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
