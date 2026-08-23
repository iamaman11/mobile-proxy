import importlib.util
import os
import pathlib
import tarfile
import tempfile
import unittest


MODULE_PATH = pathlib.Path(__file__).parents[1] / "create_release_archive.py"
SPEC = importlib.util.spec_from_file_location("create_release_archive", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class CreateReleaseArchiveTests(unittest.TestCase):
    def _tree(self, parent: pathlib.Path, mtime: int) -> pathlib.Path:
        root = parent / "mobile-proxy-v1"
        (root / "bin").mkdir(parents=True)
        executable = root / "bin" / "operator-cli"
        executable.write_bytes(b"stable-binary")
        executable.chmod(0o755)
        (root / "Cargo.lock").write_text("locked\n", encoding="utf-8")
        for path in (root, root / "bin", executable, root / "Cargo.lock"):
            os.utime(path, (mtime, mtime))
        return root

    def test_different_filesystem_times_produce_identical_bytes(self):
        with tempfile.TemporaryDirectory() as first_dir:
            with tempfile.TemporaryDirectory() as second_dir:
                first_parent = pathlib.Path(first_dir)
                second_parent = pathlib.Path(second_dir)
                first = self._tree(first_parent, 100)
                second = self._tree(second_parent, 999_999)
                first_archive = first_parent / "first.tar.gz"
                second_archive = second_parent / "second.tar.gz"
                MODULE.create_archive(first, first_archive, 1234)
                MODULE.create_archive(second, second_archive, 1234)
                self.assertEqual(
                    first_archive.read_bytes(),
                    second_archive.read_bytes(),
                )

                with tarfile.open(first_archive, "r:gz") as archive:
                    members = archive.getmembers()
                self.assertTrue(members)
                self.assertTrue(all(member.mtime == 1234 for member in members))
                self.assertTrue(all(member.uid == member.gid == 0 for member in members))
                modes = {member.name: member.mode for member in members}
                self.assertEqual(modes["mobile-proxy-v1/bin/operator-cli"], 0o755)
                self.assertEqual(modes["mobile-proxy-v1/Cargo.lock"], 0o644)

    def test_output_inside_release_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._tree(pathlib.Path(directory), 100)
            with self.assertRaises(ValueError):
                MODULE.create_archive(root, root / "bad.tar.gz", 1)
