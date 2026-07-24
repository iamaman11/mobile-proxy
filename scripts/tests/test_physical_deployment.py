import importlib.util
import json
import pathlib
import tempfile
import unittest


MODULE_PATH = pathlib.Path(__file__).parents[1] / "verify_physical_deployment.py"
SPEC = importlib.util.spec_from_file_location("physical_deployment", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class PhysicalDeploymentTests(unittest.TestCase):
    def write_release(self, root: pathlib.Path, paths: list[str]) -> None:
        entries = []
        for relative in paths:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = f"payload:{relative}".encode()
            path.write_bytes(payload)
            entries.append(
                {
                    "path": relative,
                    "digest": "blake3:placeholder",
                    "size_bytes": len(payload),
                }
            )
        (root / "integrity-manifest.json").write_text(
            json.dumps(
                {
                    "format_version": 1,
                    "algorithm": "blake3-256",
                    "domain": "mobile-proxy/release-file/v1",
                    "entries": entries,
                }
            ),
            encoding="utf-8",
        )

    def test_inventory_and_device_metadata_are_bound_to_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self.write_release(root, ["bin/host-daemon", "release-metadata.json"])
            (root / "release-metadata.json").write_text(
                json.dumps(
                    {
                        "format_version": 1,
                        "git_sha": "a" * 40,
                        "git_worktree_clean": True,
                    }
                ),
                encoding="utf-8",
            )
            manifest = json.loads((root / "integrity-manifest.json").read_text())
            for entry in manifest["entries"]:
                if entry["path"] == "release-metadata.json":
                    entry["size_bytes"] = (root / "release-metadata.json").stat().st_size
            (root / "integrity-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            self.assertEqual(
                MODULE.load_release_inventory(root),
                ["bin/host-daemon", "release-metadata.json"],
            )
            MODULE.verify_device_release_metadata(root, "a" * 40)
            with self.assertRaisesRegex(MODULE.AcceptanceFailure, "differs"):
                MODULE.verify_device_release_metadata(root, "b" * 40)

    def test_inventory_rejects_path_escape_duplicate_and_size_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self.write_release(root, ["bin/host-daemon"])
            manifest_path = root / "integrity-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["entries"][0]["path"] = "../secret"
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(MODULE.AcceptanceFailure, "escapes"):
                MODULE.load_release_inventory(root)

            self.write_release(root, ["bin/host-daemon"])
            manifest = json.loads(manifest_path.read_text())
            manifest["entries"].append(dict(manifest["entries"][0]))
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(MODULE.AcceptanceFailure, "duplicate"):
                MODULE.load_release_inventory(root)

            self.write_release(root, ["bin/host-daemon"])
            manifest = json.loads(manifest_path.read_text())
            manifest["entries"][0]["size_bytes"] += 1
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(MODULE.AcceptanceFailure, "size differs"):
                MODULE.load_release_inventory(root)

    def test_vm_digest_output_is_strict_and_complete(self):
        parsed = MODULE._parse_sha256sum(
            f"{'a' * 64}  /opt/a\n{'b' * 64} */opt/b\n"
        )
        self.assertEqual(parsed, {"/opt/a": "a" * 64, "/opt/b": "b" * 64})
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "invalid"):
            MODULE._parse_sha256sum("not-a-digest /opt/a")


if __name__ == "__main__":
    unittest.main()
