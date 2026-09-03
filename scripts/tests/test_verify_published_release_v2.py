from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.verify_published_release_v2 import PublishedReleaseError, validate_release


TAG = "v0.1.4"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class VerifyPublishedReleaseV2Tests(unittest.TestCase):
    def make_bundle(self, root: Path) -> list[str]:
        names = [
            f"mobile-proxy-linux-x86_64-{TAG}.tar.gz",
            f"mobile-proxy-android-{TAG}.apk",
            "release-manifest.json",
            "provenance.json",
            "SHA256SUMS",
        ]
        for index, name in enumerate(names, start=1):
            (root / name).write_bytes(f"asset-{index}-{name}\n".encode())
        return names

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
                    "name": name,
                    "state": "uploaded",
                    "digest": f"sha256:{digest(root / name)}",
                }
                for name in names
            ],
        }

    def test_published_immutable_release_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release = self.make_release(root)
            self.assertEqual(validate_release(release, tag=TAG, release_dir=root), 123)

    def test_mutable_published_release_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release = self.make_release(root, immutable=False)
            with self.assertRaisesRegex(PublishedReleaseError, "not immutable"):
                validate_release(release, tag=TAG, release_dir=root)

    def test_exact_draft_can_be_verified_only_in_recovery_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release = self.make_release(root, draft=True, immutable=False)
            self.assertEqual(
                validate_release(release, tag=TAG, release_dir=root, allow_draft=True),
                123,
            )
            with self.assertRaisesRegex(PublishedReleaseError, "not published"):
                validate_release(release, tag=TAG, release_dir=root)

    def test_asset_digest_mismatch_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release = self.make_release(root)
            release["assets"][0]["digest"] = "sha256:" + "0" * 64  # type: ignore[index]
            with self.assertRaisesRegex(PublishedReleaseError, "digest differs"):
                validate_release(release, tag=TAG, release_dir=root)

    def test_missing_or_extra_asset_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release = self.make_release(root)
            release["assets"] = release["assets"][:-1]  # type: ignore[index]
            with self.assertRaisesRegex(PublishedReleaseError, "asset set differs"):
                validate_release(release, tag=TAG, release_dir=root)

    def test_non_uploaded_asset_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release = self.make_release(root)
            release["assets"][0]["state"] = "new"  # type: ignore[index]
            with self.assertRaisesRegex(PublishedReleaseError, "not uploaded"):
                validate_release(release, tag=TAG, release_dir=root)


if __name__ == "__main__":
    unittest.main()
