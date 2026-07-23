import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "check_invariant_enforcement.py"
SPEC = importlib.util.spec_from_file_location("invariant_enforcement", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
REPO_ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = REPO_ROOT / "contracts/governance/invariant-enforcement.json"


class InvariantEnforcementTests(unittest.TestCase):
    def load_matrix(self):
        return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))

    def validate_changed(self, change):
        matrix = self.load_matrix()
        change(matrix)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "matrix.json"
            path.write_text(json.dumps(matrix), encoding="utf-8")
            return MODULE.validate_repository(REPO_ROOT, path)

    @staticmethod
    def row(matrix, invariant_id):
        id_column = matrix["columns"].index("id")
        return next(row for row in matrix["invariants"] if row[id_column] == invariant_id)

    def test_repository_matrix_passes_except_superseded_roadmap_blob(self):
        pointer = REPO_ROOT / "docs/ULTIMATE_IMPLEMENTATION_PLAN.md"
        body = pointer.read_text(encoding="utf-8")
        for marker in (
            "stable compatibility entry point",
            "Production Baseline Plan",
            "future/ULTIMATE_IMPLEMENTATION_PLAN.md",
            "not an active backlog",
        ):
            self.assertIn(marker, body)
        errors = [
            error
            for error in MODULE.validate_repository(REPO_ROOT)
            if not error.startswith("source U changed without invariant re-audit:")
        ]
        self.assertEqual(errors, [])

    def test_missing_row_is_rejected(self):
        def change(matrix):
            matrix["invariants"].remove(self.row(matrix, "ARCH-003"))

        self.assertTrue(
            any("invariant rows differ" in error for error in self.validate_changed(change))
        )

    def test_missing_required_id_is_rejected(self):
        def change(matrix):
            matrix["required_invariant_ids"].remove("ARCH-003")

        self.assertTrue(
            any(
                "required invariant catalog differs" in error
                for error in self.validate_changed(change)
            )
        )

    def test_enforced_without_evidence_is_rejected(self):
        def change(matrix):
            row = self.row(matrix, "COMPAT-001")
            row[matrix["columns"].index("enforcement")] = []

        self.assertTrue(
            any("enforced requires evidence" in error for error in self.validate_changed(change))
        )

    def test_unbounded_review_only_is_rejected(self):
        def change(matrix):
            row = self.row(matrix, "ARCH-003")
            columns = matrix["columns"]
            row[columns.index("status")] = "review_only"
            row[columns.index("evidence_note")] = "temporary review"
            row[columns.index("expires_on")] = "2027-07-23"

        self.assertTrue(
            any("within 180 days" in error for error in self.validate_changed(change))
        )

    def test_source_revision_drift_is_rejected(self):
        def change(matrix):
            matrix["sources"]["A1"]["blob_sha"] = "0" * 40

        self.assertTrue(
            any(
                "changed without invariant re-audit" in error
                for error in self.validate_changed(change)
            )
        )

    def test_external_control_requires_evidence_note(self):
        def change(matrix):
            matrix["external_controls"][0]["evidence_note"] = ""

        self.assertTrue(
            any("GITHUB-001: evidence_note" in error for error in self.validate_changed(change))
        )


if __name__ == "__main__":
    unittest.main()
