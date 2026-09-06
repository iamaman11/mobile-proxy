import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class GitDeliveryWorkflowTests(unittest.TestCase):
    def test_release_is_product_publication_only(self) -> None:
        release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

        self.assertIn("actions: read", release)
        self.assertIn("contents: write", release)
        self.assertIn("environment: product-release", release)
        self.assertIn("scripts/build_signed_android_release.py", release)
        self.assertIn("scripts/prepare_phone_release_runtime.py", release)
        self.assertIn(
            "contracts/operations/phone-production-release-components-v1.json",
            release,
        )
        self.assertIn("mobile-proxy-phone-production-runtime-", release)
        self.assertIn("repos/$GITHUB_REPOSITORY/immutable-releases", release)
        self.assertIn("gh release create", release)
        self.assertIn("--draft", release)
        self.assertNotIn("gh workflow run deploy-production.yml", release)
        self.assertNotIn("/deploy ", release)
        self.assertNotIn("adb ", release)
        self.assertNotIn("runs-on: self-hosted", release)
        self.assertNotIn("mobile-proxy-production", release)

    def test_release_exposes_hosted_sdkmanager_to_phone_runtime_builder(self) -> None:
        release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

        self.assertIn('sdkmanager="$sdk_root/cmdline-tools/latest/bin/sdkmanager"', release)
        self.assertIn('test -x "$sdkmanager"', release)
        self.assertIn('export PATH="$(dirname "$sdkmanager"):$PATH"', release)
        self.assertIn('test "$(command -v sdkmanager)" = "$sdkmanager"', release)

    def test_release_tag_explicitly_dispatches_publication(self) -> None:
        release_tag = (ROOT / ".github/workflows/release-tag.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("actions: write", release_tag)
        self.assertIn("gh workflow run release.yml", release_tag)
        self.assertIn('--repo "$GITHUB_REPOSITORY"', release_tag)
        self.assertIn("--ref main", release_tag)
        self.assertIn('-f "release_tag=$RELEASE_TAG"', release_tag)

    def test_release_tag_recovery_never_moves_existing_tag(self) -> None:
        release_tag = (ROOT / ".github/workflows/release-tag.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn('git merge-base --is-ancestor "$TARGET_SHA" origin/main', release_tag)
        self.assertIn('test "$(git cat-file -t "refs/tags/$RELEASE_TAG")" = tag', release_tag)
        self.assertIn('test "$(git rev-list -n 1 "$RELEASE_TAG")" = "$TARGET_SHA"', release_tag)
        self.assertIn("state=existing", release_tag)
        self.assertIn("if: steps.tag_state.outputs.state == 'absent'", release_tag)
        self.assertIn('test "$TARGET_SHA" = "$CURRENT_MAIN_SHA"', release_tag)
        self.assertNotIn("Require absent product tag", release_tag)

    def test_quality_gate_owns_immutable_release_candidate_evidence(self) -> None:
        quality = (ROOT / ".github/workflows/quality.yml").read_text(encoding="utf-8")

        self.assertFalse(
            (ROOT / ".github/workflows/software-release-candidate.yml").exists()
        )
        self.assertIn("release-candidate-evidence:", quality)
        self.assertIn("Immutable release-candidate evidence", quality)
        self.assertIn("github.event_name != 'merge_group'", quality)
        self.assertIn("scripts/write_release_candidate_evidence.py", quality)
        self.assertIn("software-release-candidate-${{ env.CANDIDATE_SHA }}", quality)
        self.assertIn("release_candidate=$RELEASE_CANDIDATE_RESULT", quality)
        self.assertIn("test \"$RELEASE_CANDIDATE_RESULT\" = success", quality)


if __name__ == "__main__":
    unittest.main()
