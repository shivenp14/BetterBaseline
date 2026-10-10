"""Tests for structured CSV parser and numeric validation (#23)."""

import sys
import unittest
from pathlib import Path
from uuid import UUID

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.ingestion.csv_parser import (
    CSVValidationError,
    compare_csv_fact_sets,
    parse_csv_file,
    parse_csv_text,
)


class TestCSVParser(unittest.TestCase):
    """Test CSV schema validation, numeric parsing, row evidence, and change detection."""

    @classmethod
    def setUpClass(cls):
        cls.repo_root = backend_dir.parent
        cls.sources_dir = cls.repo_root / "demo" / "sources"
        cls.v1_csv = cls.sources_dir / "corrected-data-v1.csv"
        cls.v2_csv = cls.sources_dir / "corrected-data-v2.csv"

    def test_sources_exist(self):
        """Verify demo CSV source files exist."""
        self.assertTrue(self.v1_csv.is_file(), "corrected-data-v1.csv missing")
        self.assertTrue(self.v2_csv.is_file(), "corrected-data-v2.csv missing")

    def test_parse_valid_csv(self):
        """Valid CSV parses into typed facts with row citations."""
        facts = parse_csv_file(self.v1_csv)
        self.assertEqual(len(facts), 5, "Expected 5 facts from v1 CSV")

        # Verify enrolled participants (integer)
        enrolled = next(f for f in facts if f["logical_key"] == "study.population.enrolled")
        self.assertEqual(enrolled["value"], 240)
        self.assertIsInstance(enrolled["value"], int)
        self.assertEqual(enrolled["unit"], "participants")
        self.assertIn("Row 2", enrolled["source"]["locator"])
        self.assertIn("study.population.enrolled,Enrolled Participants,240,participants", enrolled["source"]["quote"])

        # Verify baseline CRP (float)
        crp = next(f for f in facts if f["logical_key"] == "endpoint.biomarker.baseline_crp")
        self.assertEqual(crp["value"], 14.5)
        self.assertIsInstance(crp["value"], float)
        self.assertEqual(crp["unit"], "mg/L")

        # Verify all IDs are valid UUIDs
        for f in facts:
            UUID(f["id"])
            UUID(f["artifact_id"])
            UUID(f["version_id"])
            UUID(f["source"]["fragment_id"])

    def test_corrected_numeric_change_detection(self):
        """Comparing v1 and v2 produces exactly one aligned change for corrected population."""
        v1_facts = parse_csv_file(self.v1_csv)
        v2_facts = parse_csv_file(self.v2_csv)

        changes = compare_csv_fact_sets(v1_facts, v2_facts)
        self.assertEqual(len(changes), 1, "Expected exactly 1 change between v1 and v2")

        change = changes[0]
        self.assertEqual(change["logical_key"], "study.population.evaluable")
        self.assertEqual(change["before_value"], 235)
        self.assertEqual(change["after_value"], 228)
        self.assertEqual(change["kind"], "modified")
        UUID(change["id"])

    def test_missing_required_column_raises_error(self):
        """CSV missing a required column (e.g. 'unit') raises CSVValidationError."""
        bad_csv = "logical_key,label,value\nstudy.enrolled,Enrolled,240\n"
        with self.assertRaises(CSVValidationError) as ctx:
            parse_csv_text(bad_csv)
        self.assertIn("missing required column", str(ctx.exception).lower())

    def test_invalid_numeric_value_raises_error(self):
        """Non-numeric value in data row raises CSVValidationError with row number."""
        bad_csv = (
            "logical_key,label,value,unit\n"
            "study.enrolled,Enrolled,not_a_number,participants\n"
        )
        with self.assertRaises(CSVValidationError) as ctx:
            parse_csv_text(bad_csv)
        self.assertIn("row 2", str(ctx.exception).lower())
        self.assertIn("invalid numeric value", str(ctx.exception).lower())

    def test_empty_csv_raises_error(self):
        """Empty CSV or header-only CSV raises CSVValidationError."""
        with self.assertRaises(CSVValidationError):
            parse_csv_text("")

        with self.assertRaises(CSVValidationError):
            parse_csv_text("logical_key,label,value,unit\n")


if __name__ == "__main__":
    unittest.main()
