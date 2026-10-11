"""Provenance tracking and normalization scaffold (owned by Issue #67)."""

from typing import Any, Dict, Optional

from ..schemas import FieldProvenance


def normalize_provenance(
    raw_provenance: Optional[Dict[str, Any]] = None,
) -> Dict[str, FieldProvenance]:
    """Normalize input field provenance mappings.

    Pass-through scaffold for Issue #64. Issue #67 implements full origin/source
    validation and registry vs protocol checking.
    """
    if not raw_provenance:
        return {}
    result: Dict[str, FieldProvenance] = {}
    for key, val in raw_provenance.items():
        if isinstance(val, FieldProvenance):
            result[key] = val
        elif isinstance(val, dict):
            result[key] = FieldProvenance(**val)
    return result
