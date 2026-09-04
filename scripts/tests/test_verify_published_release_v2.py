from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.verify_published_release_v2 import PublishedReleaseError, validate_release


TAG = "v0.1.4"
DOMAIN = "mobile-proxy/product-release-asset/v2"


def fake_digest(_repository_root: Path, asset_name: str, path: Path) -> str:
    seed = (sum(asset_name.encode("utf-8")) + len(path.read_bytes())) % 16
    return "b3:" + format(seed, "x") * 64


class VerifyPublishedReleaseV2Tests(unittest.TestCase):
    def make_bundle(self, root: Path) -> list[str]:
        covered = [
            f"mobile-proxy-linux-x86_64-{TAG}.tar.gz",
            f"mobile-proxy-android-{TAG}.apk",
            "release-manifest.json",
            "provenance.json",
        ]
        for index, name in enumerate(covered, start=1):
            (root / name).write_bytes(f"asset-{index}-{name}\n".encode())
        typed = {
            "algorithm": "blake3-256",
            "assets": [
                {"digest": fake_digest(root, name, root / name), "name": name}
                for name in sorted(covered)
            ],
            "digest_domain": DOMAIN,
            "format_version": 1,
        }
        (root / "artifact-digests.json").write_text(
            json.dumps(typed, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return [*covered, "artifact-digests.json"]

    def make_release(self, root: Path, *, draft: bool = False, immutable: bool = True) -> dict[str, object]:
        names = self.make_bundle(root)
        return {
            "id": 123,
            "tag_name": TAG,
            "draft": draft,
            "prerelease": False,
            "immutable": immutable,
            "assets": [
                {
                    "id": index,
                    "name": name,
                    "state": "uploaded",
                    "digest": "sha256:" + format(index % 16, "x") * 64,
                }
                for index, name in enumerate(names, start=1)
            ],
        }

    def verify(self, release: dict[str, object], root: Path, *, allow_draft: bool = False) -> int:
        return validate_release(
            release,
            repository_root=root,
            tag=TAG,
            release_dir=root,
            allow_draft=allow_draft,
            digest_file=fake_digest,
        )

    def test_published_immutable_release_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release = self.make_release(root)
            self.assertEqual(self.verify(release, root), 123)

    def test_mutable_published_release_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release = self.make_release(root, immutable=False)
            with self.assertRaisesRegex(PublishedReleaseError, "not immutable"):
                self.verify(release, root)

    def test_exact_draft_can_be_verified_only_in_recovery_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release = self.make_release(root, draft=True, immutable=False)
            self.assertEqual(self.verify(release, root, allow_draft=True), 123)
            with self.assertRaisesRegex(PublishedReleaseError, "not published"):
                self.verify(release, root)

    def test_invalid_github_platform_digest_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release = self.make_release(root)
            release["assets"][0]["digest"] = "invalid"  # type: ignore[index]
            with self.assertRaisesRegex(PublishedReleaseError, "lacks platform digest"):
                self.verify(release, root)

    def test_typed_local_digest_mismatch_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release = self.make_release(root)
            value = json.loads((root / "artifact-digests.json").read_text(encoding="utf-8"))
            value["assets"][0]["digest"] = "b3:" + "f" * 64
            (root / "artifact-digests.json").write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(PublishedReleaseError, "local typed digest differs"):
                self.verify(release, root)

    def test_missing_or_extra_asset_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release = self.make_release(root)
            release["assets"] = release["assets"][:-1]  # type: ignore[index]
            with self.assertRaisesRegex(PublishedReleaseError, "asset set differs"):
                self.verify(release, root)

    def test_non_uploaded_asset_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release = self.make_release(root)
            release["assets"][0]["state"] = "new"  # type: ignore[index]
            with self.assertRaisesRegex(PublishedReleaseError, "not uploaded"):
                self.verify(release, root)

    def test_invalid_asset_id_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release = self.make_release(root)
            release["assets"][0]["id"] = 0  # type: ignore[index]
            with self.assertRaisesRegex(PublishedReleaseError, "asset id is invalid"):
                self.verify(release, root)


if __name__ == "__main__":
    unittest.main()
