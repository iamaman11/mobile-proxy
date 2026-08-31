from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_item20_consistency import (
    PHYSICAL_RUNBOOK,
    check_physical_runbook_text,
    check_repository,
)


class Item20ConsistencyTests(unittest.TestCase):
    def test_repository_item20_identity_and_gate_boundaries_are_consistent(self) -> None:
        self.assertEqual(check_repository(ROOT), [])

    def test_physical_runbook_matches_current_item20_state(self) -> None:
        physical = (ROOT / PHYSICAL_RUNBOOK).read_text(encoding="utf-8")
        self.assertEqual(check_physical_runbook_text(physical), [])

    def test_stale_item19_active_wording_fails_closed(self) -> None:
        physical = (ROOT / PHYSICAL_RUNBOOK).read_text(encoding="utf-8")
        stale = physical.replace(
            "Item 19 provider proof is COMPLETE",
            "while Item 19 is ACTIVE",
            1,
        )
        self.assertNotEqual(check_physical_runbook_text(stale), [])

    def test_stale_item19_execution_plane_fails_closed(self) -> None:
        physical = (ROOT / PHYSICAL_RUNBOOK).read_text(encoding="utf-8")
        stale = physical.replace(
            "protected typed Item 20 acceptance lifecycle",
            "GitHub-hosted item-19 Vultr acceptance lifecycle",
            1,
        )
        self.assertNotEqual(check_physical_runbook_text(stale), [])


if __name__ == "__main__":
    unittest.main()
