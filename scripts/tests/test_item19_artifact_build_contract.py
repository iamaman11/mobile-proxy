import re
import tomllib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/item19-acceptance-lifecycle.yml"
SERVER_PACKAGES = (
    ("control-plane", ROOT / "services/control-plane"),
    ("relay-gate", ROOT / "services/relay-gate"),
    ("reverse-tunnel-server", ROOT / "services/reverse-tunnel-server"),
)


class Item19ArtifactBuildContractTests(unittest.TestCase):
    def test_server_packages_have_default_binary_targets_matching_artifact_names(self):
        for expected_name, package_root in SERVER_PACKAGES:
            with self.subTest(package=expected_name):
                manifest = tomllib.loads(
                    (package_root / "Cargo.toml").read_text(encoding="utf-8")
                )
                self.assertEqual(manifest["package"]["name"], expected_name)
                self.assertTrue((package_root / "src/main.rs").is_file())

    def test_item19_build_does_not_filter_server_packages_to_lifecycle_bin(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        step = re.search(
            r"- name: Build exact server and lifecycle binaries\n"
            r"(?P<body>.*?)(?=\n      - name: Assemble and seal bounded server artifact)",
            workflow,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(step)
        body = step.group("body")

        server_build = (
            "cargo build --release --locked \\\n"
            "            -p control-plane \\\n"
            "            -p relay-gate \\\n"
            "            -p reverse-tunnel-server"
        )
        lifecycle_build = (
            "cargo build --release --locked \\\n"
            "            -p operator-cli --bin item19-acceptance-lifecycle"
        )
        self.assertIn(server_build, body)
        self.assertIn(lifecycle_build, body)
        self.assertLess(body.index(server_build), body.index(lifecycle_build))
        self.assertNotIn(
            "-p reverse-tunnel-server \\\n"
            "            -p operator-cli --bin item19-acceptance-lifecycle",
            body,
        )

        for binary, _ in SERVER_PACKAGES:
            self.assertIn(
                f"install -m 0755 target/release/{binary} "
                f"item19-server-artifact/bin/{binary}",
                workflow,
            )
        self.assertIn(
            "install -m 0755 target/release/item19-acceptance-lifecycle "
            "item19-server-artifact/bin/item19-acceptance-lifecycle",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
