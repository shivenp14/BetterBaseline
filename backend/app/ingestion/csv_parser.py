"""Structured CSV parser for TrialSync clinical trial parameters.

Validates declared CSV schemas, enforces numeric type safety, and produces
source-backed Fact models with precise row-level citations per Issue #23.
"""

from __future__ import annotations

import csv
import io
import uuid
from pathlib import Path
from typing import Any
from uuid import UUID

_CSV_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://trialsync.local/csv_facts")

REQUIRED_COLUMNS: tuple[str, ...] = ("logical_key", "label", "value", "unit")


class CSVParserError(Exception):
    """Base exception for CSV parsing errors."""


class CSVValidationError(CSVParserError):
    """Raised when CSV fails schema validation, missing headers, or invalid types."""


def _parse_numeric_value(raw: str, row_idx: int, key: str) -> int | float:
    """Parse string value into strict int or float; raises CSVValidationError if non-numeric."""
    cleaned = raw.strip()
    if not cleaned:
        raise CSVValidationError(f"Row {row_idx}: Empty value for logical_key '{key}'.")

    # Try parsing integer
    try:
        val_int = int(cleaned)
        # Avoid treating "2.0" as int if float string
        if str(val_int) == cleaned:
            return val_int
    except ValueError:
        pass

    # Try parsing float
    try:
        return float(cleaned)
    except ValueError as exc:
        raise CSVValidationError(
            f"Row {row_idx}: Invalid numeric value '{raw}' for logical_key '{key}'."
        ) from exc


def parse_csv_text(
    csv_text: str,
    artifact_id: UUID | None = None,
    version_id: UUID | None = None,
    filename: str = "data.csv",
) -> list[dict[str, Any]]:
    """Parse CSV text conforming to declared schema into contract-shaped Fact dictionaries.

    Schema:
        logical_key: str  - Dot-separated canonical parameter key
        label: str        - Human-readable description
        value: num        - Strictly validated int or float
        unit: str         - Measurement unit (e.g. 'participants', 'mg/L')
    """
    if not csv_text.strip():
        raise CSVValidationError("CSV file is empty.")

    f = io.StringIO(csv_text.strip())
    reader = csv.reader(f)

    try:
        headers = [h.strip() for h in next(reader, [])]
    except StopIteration:
        raise CSVValidationError("CSV file contains no rows.")

    # Validate required columns
    missing = [col for col in REQUIRED_COLUMNS if col not in headers]
    if missing:
        raise CSVValidationError(f"CSV missing required column(s): {', '.join(missing)}")

    key_idx = headers.index("logical_key")
    label_idx = headers.index("label")
    val_idx = headers.index("value")
    unit_idx = headers.index("unit")

    art_uuid = artifact_id or uuid.uuid5(_CSV_NAMESPACE, f"artifact:{filename}")
    ver_uuid = version_id or uuid.uuid5(_CSV_NAMESPACE, f"version:{filename}")

    facts: list[dict[str, Any]] = []
    lines = csv_text.strip().splitlines()

    for row_num, row in enumerate(reader, start=2):
        if not row or all(c.strip() == "" for c in row):
            continue  # skip blank lines

        if len(row) < len(REQUIRED_COLUMNS):
            raise CSVValidationError(
                f"Row {row_num}: Incomplete row; expected at least {len(REQUIRED_COLUMNS)} columns, got {len(row)}."
            )

        logical_key = row[key_idx].strip()
        label = row[label_idx].strip()
        raw_val = row[val_idx].strip()
        unit = row[unit_idx].strip() or None

        if not logical_key:
            raise CSVValidationError(f"Row {row_num}: Missing 'logical_key'.")

        parsed_val = _parse_numeric_value(raw_val, row_num, logical_key)

        # Reconstruct exact raw quote for evidence citation
        quote_line = lines[row_num - 1] if row_num - 1 < len(lines) else ",".join(row)
        frag_id = uuid.uuid5(_CSV_NAMESPACE, f"frag:{ver_uuid}:row{row_num}:{logical_key}")
        fact_id = uuid.uuid5(_CSV_NAMESPACE, f"fact:{ver_uuid}:row{row_num}:{logical_key}")

        fact: dict[str, Any] = {
            "id": str(fact_id),
            "artifact_id": str(art_uuid),
            "version_id": str(ver_uuid),
            "logical_key": logical_key,
            "label": label,
            "value": parsed_val,
            "unit": unit,
            "source": {
                "fragment_id": str(frag_id),
                "locator": f"Row {row_num} (logical_key: {logical_key})",
                "quote": quote_line.strip(),
            },
        }
        facts.append(fact)

    if not facts:
        raise CSVValidationError("CSV file contains no data rows.")

    return facts


def parse_csv_file(
    file_path: str | Path,
    artifact_id: UUID | None = None,
    version_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Read a CSV file from disk and parse into structured Fact records."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"CSV file not found: {path}")

    content = path.read_text(encoding="utf-8")
    return parse_csv_text(
        content,
        artifact_id=artifact_id,
        version_id=version_id,
        filename=path.name,
    )


def compare_csv_fact_sets(
    v1_facts: list[dict[str, Any]],
    v2_facts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compare baseline and revised CSV facts by logical key, generating change records."""
    v1_map = {f["logical_key"]: f for f in v1_facts}
    v2_map = {f["logical_key"]: f for f in v2_facts}

    changes: list[dict[str, Any]] = []
    all_keys = sorted(set(v1_map.keys()) | set(v2_map.keys()))

    for key in all_keys:
        f1 = v1_map.get(key)
        f2 = v2_map.get(key)

        if f1 and f2:
            if f1["value"] != f2["value"]:
                change_id = uuid.uuid5(_CSV_NAMESPACE, f"change:mod:{f1['id']}:{f2['id']}")
                changes.append({
                    "id": str(change_id),
                    "artifact_id": f2["artifact_id"],
                    "logical_key": key,
                    "before_fact_id": f1["id"],
                    "after_fact_id": f2["id"],
                    "before_value": f1["value"],
                    "after_value": f2["value"],
                    "kind": "modified",
                })
        elif f1 and not f2:
            change_id = uuid.uuid5(_CSV_NAMESPACE, f"change:rem:{f1['id']}")
            changes.append({
                "id": str(change_id),
                "artifact_id": f1["artifact_id"],
                "logical_key": key,
                "before_fact_id": f1["id"],
                "after_fact_id": None,
                "before_value": f1["value"],
                "after_value": None,
                "kind": "removed",
            })
        elif not f1 and f2:
            change_id = uuid.uuid5(_CSV_NAMESPACE, f"change:add:{f2['id']}")
            changes.append({
                "id": str(change_id),
                "artifact_id": f2["artifact_id"],
                "logical_key": key,
                "before_fact_id": None,
                "after_fact_id": f2["id"],
                "before_value": None,
                "after_value": f2["value"],
                "kind": "added",
            })

    return changes
