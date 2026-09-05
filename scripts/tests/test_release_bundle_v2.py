from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPOSITORY = SCRIPTS.parent
PHONE_CONTRACT = REPOSITORY / "contracts/operations/phone-production-release-components-v1.json"
sys.path.insert(0, str(SCRIPTS))

from create_release_bundle_v2 import ReleaseBundleError, create_bundle


class ReleaseBundleV2Tests(unittest.TestCase):
    tag = "v0.1.4"
    sha = "a" * 40

    @staticmethod
    def fake_digest(_repository_root: Path, asset_name: str, path: Path) -> str:
        data = path.read_bytes()
        seed = sum(asset_name.encode("utf-8")) + sum(data) + len(data)
        return "b3:" + format(seed, "064x")[-64:]

    def populate_phone_runtime(self, root: Path) -> None:
        contract = json.loads(PHONE_CONTRACT.read_text(encoding="utf-8"))
        for component in contract["components"]:
            path = root / component["source"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"phone-runtime:{component['name']}\n".encode("utf-8"))
        lock = {
            "schema_version": 1,
            "version": "1.13.12",
            "artifacts": {
                "android-arm": {
                    "size": 18350858,
                    "upstream_sha256": "50f0c71c711b5f5398b0416a0a7fe2b0813a85b42cae43c6f1cac9c881cbf8a4",
                    "content_digest": "b3:" + "3" * 64,
                },
                "linux-amd64-glibc": {
                    "size": 24594492,
                    "upstream_sha256": "11cf6d5fb93c60525771bc5652b46b734ee033ef72831056735fc658243e1fdb",
                    "content_digest": "b3:" + "2" * 64,
                },
            },
        }
        lock_path = root / "deploy/sing-box-artifacts.lock.json"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(json.dumps(lock), encoding="utf-8")

    def fixture(self, root: Path) -> Path:
        release = root / "release"
        release.mkdir()
        (release / f"mobile-proxy-linux-x86_64-{self.tag}.tar.gz").write_bytes(b"linux-artifact")
        (release / f"mobile-proxy-android-{self.tag}.apk").write_bytes(b"android-artifact")
        self.populate_phone_runtime(root)
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
            "phone_runtime_contract_path": PHONE_CONTRACT,
            "source_date_epoch": 1_700_000_000,
            "builder": "https://github.com/iamaman11/mobile-proxy/actions/runs/123",
            "workflow_ref": "iamaman11/mobile-proxy/.github/workflows/release.yml@refs/tags/v0.1.4",
            "github_native_attestation": True,
            "digest_file": self.fake_digest,
        }
        kwargs.update(overrides)
        return create_bundle(**kwargs)

    def test_valid_bundle_binds_linux_android_phone_runtime_and_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            release = Path(raw) / "release"
            evidence = self.fixture(Path(raw))
            manifest, provenance, digests = self.build(release, evidence)
            self.assertEqual(manifest["format_version"], 2)
            self.assertEqual(provenance["format_version"], 2)
            artifacts = {item["name"]: item for item in manifest["artifacts"]}
            apk_name = f"mobile-proxy-android-{self.tag}.apk"
            linux_name = f"mobile-proxy-linux-x86_64-{self.tag}.tar.gz"
            phone_name = f"mobile-proxy-phone-production-runtime-{self.tag}.tar.gz"
            self.assertEqual(set(artifacts), {apk_name, linux_name, phone_name})
            self.assertEqual(artifacts[apk_name]["kind"], "android-apk")
            self.assertEqual(artifacts[apk_name]["package_name"], "com.example.mobileproxy")
            self.assertEqual(artifacts[apk_name]["version_name"], "0.1.4")
            self.assertEqual(artifacts[apk_name]["version_code"], 1004)
            self.assertEqual(artifacts[phone_name]["kind"], "phone-production-runtime-tar")
            self.assertEqual(artifacts[phone_name]["target"], "phone-production")
            self.assertEqual(artifacts[phone_name]["runtime_abi"]["rust_target"], "armv7-linux-androideabi")
            component_names = {item["name"] for item in artifacts[phone_name]["components"]}
            self.assertEqual(
                component_names,
                {
                    "runtime-supervisor",
                    "host-daemon",
                    "sing-box",
                    "magisk-module-prop",
                    "magisk-service",
                    "profile-a1-by",
                    "profile-default",
                    "profile-mts-by",
                    "app-wireguard-template",
                    "host-daemon-template",
                    "sing-box-template",
                },
            )
            serialized_phone = json.dumps(artifacts[phone_name], sort_keys=True)
            self.assertIn("android-arm", serialized_phone)
            self.assertNotIn("linux-amd64-glibc", serialized_phone)
            self.assertNotIn("deploy/vm-runtime", serialized_phone)
            self.assertTrue((release / phone_name).is_file())
            for name in (apk_name, linux_name, phone_name):
                self.assertEqual(artifacts[name]["content_digest"], digests[name])
            digest_set = json.loads((release / "artifact-digests.json").read_text(encoding="utf-8"))
            covered = {entry["name"] for entry in digest_set["assets"]}
            self.assertEqual(
                covered,
                {apk_name, linux_name, phone_name, "release-manifest.json", "provenance.json"},
            )
            self.assertNotIn("artifact-digests.json", covered)

    def test_required_phone_runtime_component_cannot_disappear(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            release = root / "release"
            evidence = self.fixture(root)
            (root / "deploy/device-runtime/bin/host-daemon").unlink()
            with self.assertRaisesRegex(ReleaseBundleError, "component is missing"):
                self.build(release, evidence)

    def test_phone_runtime_byte_change_changes_component_and_release_identity(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            release = root / "release"
            evidence = self.fixture(root)
            first_manifest, _, first_digests = self.build(release, evidence)
            phone_name = f"mobile-proxy-phone-production-runtime-{self.tag}.tar.gz"
            first_phone = next(item for item in first_manifest["artifacts"] if item["name"] == phone_name)
            first_component = next(item for item in first_phone["components"] if item["name"] == "runtime-supervisor")
            runtime = root / "deploy/device-runtime/bin/runtime-supervisor"
            runtime.write_bytes(runtime.read_bytes() + b"changed-runtime-bytes")
            second_manifest, _, second_digests = self.build(release, evidence)
            second_phone = next(item for item in second_manifest["artifacts"] if item["name"] == phone_name)
            second_component = next(item for item in second_phone["components"] if item["name"] == "runtime-supervisor")
            self.assertNotEqual(first_component["content_digest"], second_component["content_digest"])
            self.assertNotEqual(first_digests[phone_name], second_digests[phone_name])

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
