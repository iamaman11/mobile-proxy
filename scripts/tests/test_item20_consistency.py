from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_item20_consistency import check_repository


class Item20ConsistencyTests(unittest.TestCase):
    def test_repository_item20_identity_and_gate_boundaries_are_consistent(self) -> None:
        self.assertEqual(check_repository(ROOT), [])


if __name__ == "__main__":
    unittest.main()
