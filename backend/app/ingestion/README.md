# Ingestion Workstream

This package provides deterministic ingestion adapters, document parsers (plain text and selectable-text PDF), and structured CSV parsers for TrialSync clinical trial documents.

## Dependencies

- **Python**: `>= 3.11`
- **Standard Library**: Pure Python for plain text parsing, CSV validation, and fixture adapter (`json`, `csv`, `pathlib`, `hashlib`, `uuid`).
- **PDF Support (Optional / Recommended)**:
  ```sh
  pip install "pypdf>=5.0.0"
  ```
  `parse_text()` operates without third-party dependencies. `parse_pdf()` requires `pypdf`.

## Usage

```python
from app.ingestion.document_parser import parse_document, parse_pdf, parse_text
from app.ingestion.csv_parser import parse_csv_file
from app.ingestion.fixture_adapter import load_demo_fixtures

# Parse document into source fragments with locators
fragments = parse_document("demo/sources/protocol-v1.pdf")
for frag in fragments:
    print(f"[{frag.locator}] {frag.text[:50]}...")

# Parse structured trial CSV parameters
facts = parse_csv_file("demo/sources/corrected-data-v1.csv")
```
