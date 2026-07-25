import importlib.util
import json
import pathlib
import sys
import tempfile
import tarfile
import unittest


SCRIPTS_DIR = pathlib.Path(__file__).parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
MODULE_PATH = SCRIPTS_DIR / "verify_physical_deployment.py"
SPEC = importlib.util.spec_from_file_location("physical_deployment", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class PhysicalDeploymentTests(unittest.TestCase):
    def write_release(self, root: pathlib.Path, paths: list[str]) -> None:
        entries = []
        for relative in sorted(paths):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = f"payload:{relative}".encode()
            path.write_bytes(payload)
            entries.append(
                {
                    "path": relative,
                    "digest": "b3:" + "a" * 64,
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

    def write_host_config(self, root: pathlib.Path, owner: str) -> None:
        reverse = owner == "first_party_reverse_tunnel"
        path = root / "config" / "host-daemon.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "wireguard": {"enabled": not reverse, "owner": owner},
                    "reverse_tunnel": {"enabled": reverse},
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

    def test_release_owner_is_inferred_and_modes_are_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self.write_host_config(root, "first_party_reverse_tunnel")
            self.assertEqual(MODULE.release_tunnel_owner(root), "first_party_reverse_tunnel")

            self.write_host_config(root, "stock_wireguard_bridge")
            self.assertEqual(MODULE.release_tunnel_owner(root), "stock_wireguard_bridge")

            config = json.loads((root / "config" / "host-daemon.json").read_text())
            config["reverse_tunnel"]["enabled"] = True
            (root / "config" / "host-daemon.json").write_text(json.dumps(config))
            with self.assertRaisesRegex(MODULE.AcceptanceFailure, "leaves reverse tunnel enabled"):
                MODULE.release_tunnel_owner(root)

    def test_inventory_rejects_path_escape_duplicate_unsorted_and_size_drift(self):
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

            self.write_release(root, ["z", "a"])
            manifest = json.loads(manifest_path.read_text())
            manifest["entries"].reverse()
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(MODULE.AcceptanceFailure, "path-sorted"):
                MODULE.load_release_inventory(root)

            self.write_release(root, ["bin/host-daemon"])
            manifest = json.loads(manifest_path.read_text())
            manifest["entries"][0]["size_bytes"] += 1
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(MODULE.AcceptanceFailure, "size differs"):
                MODULE.load_release_inventory(root)

    def test_android_vpn_owner_parsers_are_strict(self):
        packages = "package:com.wireguard.android uid:10123\n"
        self.assertEqual(MODULE.parse_package_uid(packages, "com.wireguard.android"), 10123)
        self.assertIsNone(MODULE.parse_package_uid(packages, "com.example.mobileproxy"))
        connectivity = "NetworkAgentInfo Transports: VPN WIFI OwnerUid: 10123 Score: 60"
        self.assertEqual(MODULE.parse_active_vpn_owner_uid(connectivity), 10123)
        self.assertIsNone(MODULE.parse_active_vpn_owner_uid("Transports: WIFI OwnerUid: 10123"))

    def test_vm_verification_archive_contains_exact_static_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self.write_release(root, ["bin/a", "config/b"])
            archive = MODULE._write_verification_archive(root, ["bin/a", "config/b"])
            try:
                with tarfile.open(archive, "r") as bundle:
                    self.assertEqual(sorted(bundle.getnames()), ["bin/a", "config/b"])
                    self.assertEqual(bundle.extractfile("bin/a").read(), b"payload:bin/a")
            finally:
                archive.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
