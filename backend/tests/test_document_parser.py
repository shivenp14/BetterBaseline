"""Tests for selectable-text PDF and plain text document parser (#22)."""

import os
import subprocess
import sys
import unittest
from pathlib import Path
from uuid import UUID

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.ingestion.document_parser import (
    DocumentFragment,
    ScannedDocumentError,
    UnsupportedDocumentError,
    find_fragments_by_text,
    parse_document,
    parse_pdf,
    parse_text,
)


class TestDocumentParser(unittest.TestCase):
    """Test parsing plain text, selectable PDFs, and scanned document errors."""

    @classmethod
    def setUpClass(cls):
        cls.repo_root = backend_dir.parent
        cls.sources_dir = cls.repo_root / "demo" / "sources"
        cls.txt_path = cls.sources_dir / "protocol-v1.txt"
        cls.pdf_path = cls.sources_dir / "protocol-v1.pdf"
        cls.scanned_pdf_path = cls.sources_dir / "scanned-sample.pdf"

    def test_sources_exist(self):
        """Verify test document files exist."""
        self.assertTrue(self.txt_path.is_file(), "protocol-v1.txt missing")
        self.assertTrue(self.pdf_path.is_file(), "protocol-v1.pdf missing")
        self.assertTrue(self.scanned_pdf_path.is_file(), "scanned-sample.pdf missing")

    def test_parse_text_fragments(self):
        """Plain text is parsed into structured fragments with section locators."""
        content = self.txt_path.read_text(encoding="utf-8")
        fragments = parse_text(content, artifact_name="protocol-v1.txt")

        self.assertGreater(len(fragments), 3, "Expected multiple structured fragments")

        for frag in fragments:
            self.assertIsInstance(frag.id, UUID)
            self.assertTrue(len(frag.locator) > 0)
            self.assertGreater(len(frag.text.strip()), 0)

        # Check section: endpoint detection
        endpoint_frags = [f for f in fragments if "section: endpoint" in f.locator]
        self.assertGreater(len(endpoint_frags), 0)
        self.assertIn("Primary endpoint assessment occurs at week 24.", endpoint_frags[0].text)

    def test_mixed_case_numbered_headings(self):
        """Mixed-case numbered headings like '1.1 Primary Objective' are recognized."""
        sample = (
            "1. STUDY SYNOPSIS AND OBJECTIVES\n"
            "This is the study synopsis.\n\n"
            "1.1 Primary Objective\n"
            "The primary objective is clinical efficacy.\n\n"
            "1.2 Secondary Objectives\n"
            "Assess safety and tolerability.\n"
        )
        frags = parse_text(sample)
        self.assertEqual(len(frags), 3)
        self.assertEqual(frags[0].section_heading, "1. STUDY SYNOPSIS AND OBJECTIVES")
        self.assertEqual(frags[1].section_heading, "1.1 Primary Objective")
        self.assertEqual(frags[2].section_heading, "1.2 Secondary Objectives")
        self.assertIn("1.1 Primary Objective", frags[1].locator)

    def test_exact_character_offsets(self):
        """Character offsets start_char:end_char must reproduce fragment text exactly."""
        content = self.txt_path.read_text(encoding="utf-8")
        fragments = parse_text(content, artifact_name="protocol-v1.txt")

        for frag in fragments:
            slice_text = content[frag.start_char : frag.end_char]
            self.assertEqual(
                slice_text,
                frag.text,
                f"Offset mismatch for locator '{frag.locator}': expected '{frag.text[:30]}...', got '{slice_text[:30]}...'",
            )

    def test_fragment_id_stability_across_processes(self):
        """Fragment UUIDs must remain identical across processes regardless of PYTHONHASHSEED."""
        test_script = (
            "import sys; from pathlib import Path; "
            f"sys.path.insert(0, r'{backend_dir}'); "
            "from app.ingestion.document_parser import parse_text; "
            "frags = parse_text('Section 1\\nSample content\\n\\nSection 2\\nSecond paragraph'); "
            "print(','.join(str(f.id) for f in frags))"
        )

        res1 = subprocess.run(
            [sys.executable, "-c", test_script],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": "1"},
        )
        res2 = subprocess.run(
            [sys.executable, "-c", test_script],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": "2"},
        )
        self.assertEqual(res1.stdout.strip(), res2.stdout.strip(), "Fragment IDs differed across PYTHONHASHSEED runs")

    def test_parse_pdf_selectable(self):
        """Selectable-text PDF extracts page-aware fragments matching protocol text."""
        fragments = parse_pdf(self.pdf_path, artifact_name="protocol-v1.pdf")
        self.assertGreater(len(fragments), 0)

        page_nums = {f.page_number for f in fragments if f.page_number is not None}
        self.assertIn(1, page_nums)
        self.assertIn(2, page_nums)

        endpoint_query = "Primary endpoint assessment occurs at week 24."
        matches = find_fragments_by_text(fragments, endpoint_query)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].page_number, 2)
        self.assertIn("Page 2", matches[0].locator)

    def test_scanned_pdf_raises_error(self):
        """Image-only/scanned PDF without extractable text raises ScannedDocumentError."""
        with self.assertRaises(ScannedDocumentError) as ctx:
            parse_pdf(self.scanned_pdf_path)
        self.assertIn("no selectable text", str(ctx.exception).lower())

    def test_unsupported_format_raises_error(self):
        """Unsupported file extensions raise UnsupportedDocumentError."""
        dummy_file = self.sources_dir / "unsupported_data.docx"
        dummy_file.write_text("dummy", encoding="utf-8")
        try:
            with self.assertRaises(UnsupportedDocumentError):
                parse_document(dummy_file)
        finally:
            if dummy_file.exists():
                dummy_file.unlink()

    def test_text_and_pdf_parity(self):
        """Both plain text and PDF representations extract the exact primary endpoint fact quote."""
        txt_frags = parse_text(self.txt_path.read_text(encoding="utf-8"))
        pdf_frags = parse_pdf(self.pdf_path)

        target_quote = "Primary endpoint assessment occurs at week 24."
        txt_matches = find_fragments_by_text(txt_frags, target_quote)
        pdf_matches = find_fragments_by_text(pdf_frags, target_quote)

        self.assertEqual(len(txt_matches), 1)
        self.assertEqual(len(pdf_matches), 1)
        self.assertIn(target_quote, txt_matches[0].text)
        self.assertIn(target_quote, pdf_matches[0].text)


if __name__ == "__main__":
    unittest.main()
