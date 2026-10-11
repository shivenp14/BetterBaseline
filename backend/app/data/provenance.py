"""Provenance normalization and export helpers (Issue #67).

Provenance keys are field names or JSON pointers. Keeping those keys intact is
important because the same assumption can occur in both the planned design and
the stress scenario.
"""

from datetime import datetime, timezone
import hashlib
import importlib
import json
import sys
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel

from ..schemas import (
    ArmCounts,
    compute_export_inputs_hash,
    DesignCalculateResponse,
    ExportPayload,
    FieldProvenance,
    ScenarioEvaluateResponse,
    ScenarioGridResponse,
    StressScenario,
    TrialAssumptions,
)


class FieldProvenanceRecord(FieldProvenance):
    """Normalized field record, including the optional audit metadata in v1."""


ProvenanceInput = Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]


def normalize_provenance(
    raw_provenance: ProvenanceInput = None,
) -> Dict[str, FieldProvenance]:
    """Normalize provenance dictionaries or D1 manifest record lists.

    Dict keys and manifest ``field``/``name`` values are preserved verbatim.
    ``origin`` is accepted as the fixture alias for the API's ``source`` field.
    """
    if not raw_provenance:
        return {}

    result: Dict[str, FieldProvenance] = {}
    if isinstance(raw_provenance, list):
        for item in raw_provenance:
            if not isinstance(item, dict):
                raise ValueError("Each provenance list entry must be an object")
            field_name = item.get("field") or item.get("name")
            if not field_name:
                raise ValueError("Each provenance list entry requires a field or name")
            result[str(field_name)] = _validate_and_build_record(item)
    else:
        for key, value in raw_provenance.items():
            if isinstance(value, FieldProvenance):
                data = value.model_dump(mode="python")
            elif isinstance(value, BaseModel):
                data = value.model_dump(mode="python")
            elif isinstance(value, dict):
                data = value
            else:
                raise ValueError(f"Provenance for {key!r} must be an object")
            result[str(key)] = _validate_and_build_record(data)
    return result


def _validate_and_build_record(data: Dict[str, Any]) -> FieldProvenanceRecord:
    source = data.get("source")
    origin = data.get("origin")
    if source and origin and source != origin:
        raise ValueError("Field provenance source and origin tags must agree")
    source = source or origin
    if not source:
        raise ValueError("Field provenance requires a source or origin tag")

    description = data.get("description") or data.get("basis")
    source_url = data.get("source_url")
    observed = (
        data.get("is_observed_registry_result") is True
        or (
            "clinicaltrials.gov" in str(source_url or "").lower()
            and "observed" in str(description or "").lower()
        )
    )
    if source == "protocol_curated" and observed:
        raise ValueError("Registry observed results cannot be relabeled as protocol_curated")

    return FieldProvenanceRecord(
        source=source,
        description=description,
        retrieved_at=data.get("retrieved_at"),
        source_url=source_url,
        source_location=data.get("source_location"),
        verified_by_user=data.get("verified_by_user"),
        is_observed_registry_result=observed or None,
    )


def get_current_software_versions() -> Dict[str, str]:
    """Return software versions used to reproduce an exported calculation."""
    versions = {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "betterbaseline": "0.1.0",
    }
    for module_name in ("numpy", "scipy", "statsmodels", "pydantic", "fastapi"):
        try:
            module = sys.modules.get(module_name) or importlib.import_module(module_name)
            versions[module_name] = str(getattr(module, "__version__", "unknown"))
        except (ImportError, ModuleNotFoundError):
            continue
    return versions


def compute_inputs_hash(data: Union[BaseModel, Dict[str, Any]]) -> str:
    """Compute a stable SHA-256 digest for JSON-compatible inputs."""
    json_obj = data.model_dump(mode="json") if isinstance(data, BaseModel) else data
    serialized = json.dumps(
        json_obj, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return "sha256:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_export_payload(
    planned_design: TrialAssumptions,
    fixed_enrollment: ArmCounts,
    stress_scenario: Optional[StressScenario] = None,
    design_result: Optional[DesignCalculateResponse] = None,
    evaluation_result: Optional[ScenarioEvaluateResponse] = None,
    grid_result: Optional[ScenarioGridResponse] = None,
    provenance: ProvenanceInput = None,
    software_versions: Optional[Dict[str, str]] = None,
    exported_at: Optional[str] = None,
) -> ExportPayload:
    """Construct an export envelope retaining complete typed route results."""
    normalized_provenance = normalize_provenance(provenance)
    inputs_hash = compute_export_inputs_hash(
        planned_design, fixed_enrollment, stress_scenario, normalized_provenance
    )
    return ExportPayload(
        export_schema_version=1,
        model_version=planned_design.model_version,
        planned_design=planned_design,
        fixed_enrollment=fixed_enrollment,
        stress_scenario=stress_scenario,
        design_result=design_result,
        evaluation_result=evaluation_result,
        grid_result=grid_result,
        software_versions=software_versions or get_current_software_versions(),
        provenance=normalized_provenance,
        exported_at=exported_at or datetime.now(timezone.utc).isoformat(),
        inputs_hash=inputs_hash,
    )
