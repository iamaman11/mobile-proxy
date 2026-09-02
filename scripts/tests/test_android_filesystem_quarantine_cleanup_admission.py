from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "run_android_filesystem_quarantine_recovery.py"
SPEC = importlib.util.spec_from_file_location("android_filesystem_quarantine_cleanup_admission", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class AndroidFilesystemQuarantineCleanupAdmissionTests(unittest.TestCase):
    def _base(self, *, node=None, writable=None, executable=None):
        return {
            "node_state": node or MODULE.DIRECTORY,
            "writable": writable or MODULE.SUPPORTED,
            "executable": executable or MODULE.SUPPORTED,
        }

    def test_present_child_requires_writable_executable_directory_parent(self) -> None:
        self.assertTrue(
            MODULE._scope_cleanup_admissible(
                self._base(),
                [MODULE.DIRECTORY],
            )
        )
        self.assertFalse(
            MODULE._scope_cleanup_admissible(
                self._base(writable=MODULE.UNSUPPORTED),
                [MODULE.DIRECTORY],
            )
        )
        self.assertFalse(
            MODULE._scope_cleanup_admissible(
                self._base(executable=MODULE.UNSUPPORTED),
                [MODULE.DIRECTORY],
            )
        )

    def test_absent_parent_requires_all_exact_children_absent(self) -> None:
        absent_parent = self._base(
            node=MODULE.ABSENT,
            writable=MODULE.UNSUPPORTED,
            executable=MODULE.UNSUPPORTED,
        )
        self.assertTrue(
            MODULE._scope_cleanup_admissible(
                absent_parent,
                [MODULE.ABSENT, MODULE.ABSENT],
            )
        )
        self.assertFalse(
            MODULE._scope_cleanup_admissible(
                absent_parent,
                [MODULE.DIRECTORY],
            )
        )

    def test_no_present_child_does_not_require_parent_write(self) -> None:
        read_only_directory = self._base(
            writable=MODULE.UNSUPPORTED,
            executable=MODULE.SUPPORTED,
        )
        self.assertTrue(
            MODULE._scope_cleanup_admissible(
                read_only_directory,
                [MODULE.ABSENT],
            )
        )

    def test_unsafe_parent_or_child_type_is_rejected(self) -> None:
        for parent_state in (MODULE.SYMLINK, MODULE.OTHER, MODULE.UNKNOWN):
            with self.subTest(parent_state=parent_state):
                self.assertFalse(
                    MODULE._scope_cleanup_admissible(
                        self._base(node=parent_state),
                        [MODULE.ABSENT],
                    )
                )
        for child_state in (MODULE.SYMLINK, MODULE.OTHER, MODULE.UNKNOWN):
            with self.subTest(child_state=child_state):
                self.assertFalse(
                    MODULE._scope_cleanup_admissible(
                        self._base(),
                        [child_state],
                    )
                )


if __name__ == "__main__":
    unittest.main()
