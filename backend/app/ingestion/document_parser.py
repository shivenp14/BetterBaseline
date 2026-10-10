"""Document parser for TrialSync clinical trial documents.

Extracts source-backed text fragments with stable locators (page, section) from
plain-text documents and selectable-text PDFs. Flags scanned/non-selectable PDFs
with explicit errors per Issue #22 requirements.
"""

from __future__ import annotations

import hashlib
import io
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO, Sequence
from uuid import UUID

# Optional dependency: pypdf is imported lazily inside parse_pdf
try:
    import pypdf
except ImportError:
    pypdf = None

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
    """Generate a deterministic UUIDv5 for a fragment based on location and content SHA-256.

    Uses SHA-256 instead of Python's built-in hash() so fragment IDs remain 100% stable
    across processes regardless of PYTHONHASHSEED.
    """
    text_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    seed = f"{artifact_name}:p{page or 0}:idx{index}:{text_digest}"
    return uuid.uuid5(_FRAGMENT_NAMESPACE, seed)


def _detect_heading(line: str) -> str | None:
    """Detect if a line represents a section heading.

    Matches patterns like:
    - 'section: endpoint' (demo locator tag)
    - '1. STUDY SYNOPSIS AND OBJECTIVES' (uppercase numbered section)
    - '1.1 Primary Objective' (mixed-case numbered subsection)
    - 'RATIONALE FOR PROTOCOL AMENDMENT' (all-caps header)
    """
    stripped = line.strip()
    if not stripped:
        return None

    # Explicit 'section: <name>' locator pattern used in TrialSync demo sources
    if stripped.lower().startswith("section:"):
        return stripped

    # Numbered section headers supporting mixed-case (e.g. '1.1 Primary Objective', '3. SCHEDULE')
    if re.match(r"^\d+(\.\d+)*\s+[A-Za-z0-9\s\-_/]+$", stripped):
        return stripped

    # Short all-caps headings (e.g., 'RATIONALE FOR PROTOCOL AMENDMENT')
    if stripped.isupper() and len(stripped) <= 60 and not stripped.endswith("."):
        return stripped

    return None


def parse_text(text: str, artifact_name: str = "document", page_number: int | None = None) -> list[DocumentFragment]:
    """Parse plain text into structured fragments with section-aware locators.

    Splits text along paragraph boundaries while preserving section headings.
    Ensures start_char and end_char match the exact slice of text in source.
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
        raw_chunk = "".join(buffer_lines)
        buffer_lines = []
        chunk = raw_chunk.strip()
        if not chunk:
            return

        # Calculate exact trimmed bounds within the source text
        leading_ws = len(raw_chunk) - len(raw_chunk.lstrip())
        trailing_ws = len(raw_chunk) - len(raw_chunk.rstrip())
        exact_start = buffer_start + leading_ws
        exact_end = buffer_start + len(raw_chunk) - trailing_ws

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
                start_char=exact_start,
                end_char=exact_end,
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
        DocumentParserError: If pypdf is not installed or PDF is corrupt.
        ScannedDocumentError: If PDF has no extractable text across all pages.
    """
    if pypdf is None:
        raise DocumentParserError(
            "The 'pypdf' package is required to parse PDF documents. "
            "Please install it using: pip install 'pypdf>=5.0.0'"
        )

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
