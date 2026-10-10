"""Document parser for TrialSync clinical trial documents.

Extracts source-backed text fragments with stable locators (page, section) from
plain-text documents and selectable-text PDFs. Flags scanned/non-selectable PDFs
with explicit errors per Issue #22 requirements.
"""

from __future__ import annotations

import io
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO, Sequence
from uuid import UUID

import pypdf

# Deterministic namespace for fragment UUID generation
_FRAGMENT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://trialsync.local/fragments")


class DocumentParserError(Exception):
    """Base exception for document parsing failures."""


class ScannedDocumentError(DocumentParserError):
    """Raised when a PDF contains no selectable text (scanned/image-only document)."""


class UnsupportedDocumentError(DocumentParserError):
    """Raised when an unsupported file extension or format is supplied."""


@dataclass(frozen=True)
class DocumentFragment:
    """A granular piece of document text tied to a verifiable source locator."""

    id: UUID
    text: str
    page_number: int | None
    section_heading: str | None
    locator: str
    start_char: int
    end_char: int

    def to_dict(self) -> dict[str, object]:
        """Convert fragment to dictionary representation matching API contract."""
        data = asdict(self)
        data["id"] = str(self.id)
        return data


def _generate_fragment_id(artifact_name: str, page: int | None, index: int, text: str) -> UUID:
    """Generate a deterministic UUIDv5 for a fragment based on location and content digest."""
    seed = f"{artifact_name}:p{page or 0}:idx{index}:{hash(text)}"
    return uuid.uuid5(_FRAGMENT_NAMESPACE, seed)


def _detect_heading(line: str) -> str | None:
    """Detect if a line represents a section heading.

    Matches patterns like 'section: endpoint', '1. STUDY SYNOPSIS', '1.1 Primary Objective',
    or standalone all-caps headers.
    """
    stripped = line.strip()
    if not stripped:
        return None

    # Explicit 'section: <name>' locator pattern used in TrialSync demo sources
    if stripped.lower().startswith("section:"):
        return stripped

    # Numbered section headers (e.g., '1. STUDY SYNOPSIS', '1.1 Primary Objective')
    if re.match(r"^\d+(\.\d+)*\s+[A-Z0-9\s\-_/]+$", stripped):
        return stripped

    # Short all-caps headings (e.g., 'RATIONALE FOR PROTOCOL AMENDMENT')
    if stripped.isupper() and len(stripped) <= 60 and not stripped.endswith("."):
        return stripped

    return None


def parse_text(text: str, artifact_name: str = "document", page_number: int | None = None) -> list[DocumentFragment]:
    """Parse plain text into structured fragments with section-aware locators.

    Splits text along paragraph boundaries while preserving section headings.
    """
    if not text.strip():
        return []

    lines = text.splitlines(keepends=True)
    fragments: list[DocumentFragment] = []
    current_section: str | None = None
    buffer_lines: list[str] = []
    char_offset = 0
    buffer_start = 0

    def flush_buffer() -> None:
        nonlocal buffer_lines, buffer_start, char_offset
        if not buffer_lines:
            return
        chunk = "".join(buffer_lines).strip()
        buffer_lines = []
        if not chunk:
            return

        # Build locator string
        loc_parts: list[str] = []
        if page_number is not None:
            loc_parts.append(f"Page {page_number}")
        if current_section:
            loc_parts.append(current_section)
        locator = ", ".join(loc_parts) if loc_parts else "Document text"

        frag_id = _generate_fragment_id(artifact_name, page_number, len(fragments), chunk)
        fragments.append(
            DocumentFragment(
                id=frag_id,
                text=chunk,
                page_number=page_number,
                section_heading=current_section,
                locator=locator,
                start_char=buffer_start,
                end_char=char_offset,
            )
        )

    for line in lines:
        line_len = len(line)
        detected = _detect_heading(line)
        if detected:
            flush_buffer()
            current_section = detected
            buffer_start = char_offset
            # If the heading itself is a 'section: ...' tag, store subsequent text under it
            if not line.strip().lower().startswith("section:"):
                buffer_lines.append(line)
        elif not line.strip():
            # Blank line signifies a paragraph break
            if buffer_lines:
                flush_buffer()
            buffer_start = char_offset + line_len
        else:
            if not buffer_lines:
                buffer_start = char_offset
            buffer_lines.append(line)

        char_offset += line_len

    flush_buffer()
    return fragments


def parse_pdf(
    source: str | Path | bytes | BinaryIO,
    artifact_name: str = "document",
) -> list[DocumentFragment]:
    """Parse selectable-text PDF into page- and section-aware fragments.

    Raises:
        ScannedDocumentError: If PDF has no extractable text across all pages.
        DocumentParserError: If PDF parsing fails due to corrupt payload.
    """
    stream: BinaryIO
    if isinstance(source, (str, Path)):
        file_path = Path(source)
        if not file_path.is_file():
            raise FileNotFoundError(f"PDF file not found at: {file_path}")
        stream = open(file_path, "rb")
        name = artifact_name if artifact_name != "document" else file_path.name
    elif isinstance(source, bytes):
        stream = io.BytesIO(source)
        name = artifact_name
    else:
        stream = source
        name = artifact_name

    try:
        reader = pypdf.PdfReader(stream)
        if len(reader.pages) == 0:
            raise ScannedDocumentError("PDF contains 0 pages.")

        all_fragments: list[DocumentFragment] = []
        total_extracted_chars = 0

        for page_idx, page in enumerate(reader.pages):
            page_num = page_idx + 1
            page_text = page.extract_text() or ""
            total_extracted_chars += len(page_text.strip())

            page_fragments = parse_text(
                page_text,
                artifact_name=name,
                page_number=page_num,
            )
            all_fragments.extend(page_fragments)

        # Detect image-only or scanned PDFs with zero selectable text
        if total_extracted_chars == 0:
            raise ScannedDocumentError(
                "PDF contains no selectable text. OCR is not supported; upload a selectable-text PDF."
            )

        return all_fragments
    except pypdf.errors.PdfReadError as exc:
        raise DocumentParserError(f"Corrupt or unreadable PDF: {exc}") from exc
    finally:
        if isinstance(source, (str, Path)):
            stream.close()


def parse_document(file_path: str | Path) -> list[DocumentFragment]:
    """Inspect file extension and parse supported document (.txt, .pdf).

    Raises:
        UnsupportedDocumentError: For unsupported extensions (e.g. .docx, .csv, .bin).
        FileNotFoundError: If the specified file path does not exist.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".txt":
        content = path.read_text(encoding="utf-8")
        return parse_text(content, artifact_name=path.name)
    elif suffix == ".pdf":
        return parse_pdf(path, artifact_name=path.name)
    else:
        raise UnsupportedDocumentError(
            f"Unsupported file format '{suffix}'. Supported formats are: .txt, .pdf"
        )


def find_fragments_by_text(
    fragments: Sequence[DocumentFragment],
    query: str,
) -> list[DocumentFragment]:
    """Find all fragments containing a verbatim or case-insensitive query string."""
    q = query.strip().lower()
    return [f for f in fragments if q in f.text.lower()]
