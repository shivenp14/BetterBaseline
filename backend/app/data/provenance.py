"""Provenance tracking, normalization, and export payload serialization (Issue #67).

Preserves per-field provenance metadata through API calculation results and
export contracts. Prevents mislabeling clinical registry observed event counts
as protocol-curated planning assumptions.
"""

from datetime import datetime, timezone
import hashlib
import json
import sys
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field

from ..schemas import (
    ArmCounts,
    DesignCalculateResponse,
    ExportPayload,
    FieldProvenance,
    ScenarioEvaluateResponse,
    ScenarioGridResponse,
    SourceTag,
    StressScenario,
    TrialAssumptions,
)

# Canonical software package versions to capture in export payload
SOFTWARE_DEPENDENCIES = ["betterbaseline", "fastapi", "pydantic", "numpy", "scipy", "statsmodels"]


class FieldProvenanceRecord(FieldProvenance):
    """Extended provenance model supporting optional source location, verification flag,

    and audit trail metadata while remaining drop-in compatible with FieldProvenance.
    """

    origin: Optional[SourceTag] = None  # Alias for source tag in fixture models
    source_location: Optional[str] = None
    verified_by_user: Optional[bool] = None
    is_observed_registry_result: Optional[bool] = None

    def model_post_init(self, __context: Any) -> None:
        if self.origin and not self.source:
            self.source = self.origin
        super().model_post_init(__context)


def normalize_provenance(
    raw_provenance: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
) -> Dict[str, FieldProvenance]:
    """Normalize input field provenance mappings.

    Accepts:
    - Dict of field name -> FieldProvenance or dict
    - List of dicts with 'field' or pointer and provenance fields (e.g., D1 manifest style)

    Validates:
    - Origin/source tags belong to canonical SourceTag
    - Registry observed results cannot be silently relabeled as protocol_curated.
    """
    if not raw_provenance:
        return {}

    result: Dict[str, FieldProvenance] = {}

    if isinstance(raw_provenance, list):
        for item in raw_provenance:
            if not isinstance(item, dict):
                continue
            field_name = item.get("field") or item.get("name")
            if not field_name:
                continue
            # Preserve complete field path/pointer so planned and stress fields remain distinct
            record = _validate_and_build_record(item)
            result[field_name] = record
    elif isinstance(raw_provenance, dict):
        for key, val in raw_provenance.items():
            if isinstance(val, FieldProvenance):
                _check_registry_relabeled(val)
                result[key] = val
            elif isinstance(val, dict):
                result[key] = _validate_and_build_record(val)
            else:
                continue

    return result


def _validate_and_build_record(data: Dict[str, Any]) -> FieldProvenanceRecord:
    source = data.get("source") or data.get("origin")
    if not source:
        raise ValueError("Field provenance requires a source or origin tag")

    is_observed_registry = (
        data.get("is_observed_registry_result") is True
        or "clinicaltrials.gov" in str(data.get("source_url", "")).lower()
        and "observed" in str(data.get("description", "")).lower()
    )

    if source == "protocol_curated" and is_observed_registry:
        raise ValueError("Registry observed results cannot be relabeled as protocol_curated")

    description = data.get("description") or data.get("basis")
    source_url = data.get("source_url")
    retrieved_at = data.get("retrieved_at")
    source_location = data.get("source_location")
    verified_by_user = data.get("verified_by_user")

    return FieldProvenanceRecord(
        source=source,
        description=description,
        retrieved_at=retrieved_at,
        source_url=source_url,
        source_location=source_location,
        verified_by_user=verified_by_user,
        is_observed_registry_result=is_observed_registry if is_observed_registry else None,
    )


def _check_registry_relabeled(val: FieldProvenance) -> None:
    is_observed_flag = getattr(val, "is_observed_registry_result", False) is True
    if val.source == "protocol_curated":
        desc = (val.description or "").lower()
        url = (val.source_url or "").lower()
        if is_observed_flag or ("clinicaltrials.gov" in url and "observed" in desc):
            raise ValueError("Registry observed results cannot be relabeled as protocol_curated")


def get_current_software_versions() -> Dict[str, str]:
    """Capture runtime software and dependency versions for export reproducibility."""
    versions: Dict[str, str] = {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "betterbaseline": "0.1.0",
    }
    for mod_name in ["numpy", "scipy", "statsmodels", "pydantic", "fastapi"]:
        try:
            mod = sys.modules.get(mod_name)
            if mod and hasattr(mod, "__version__"):
                versions[mod_name] = str(mod.__version__)
            else:
                import importlib

                m = importlib.import_module(mod_name)
                versions[mod_name] = str(getattr(m, "__version__", "unknown"))
        except Exception:
            pass
    return versions


def compute_inputs_hash(data: Union[BaseModel, Dict[str, Any]]) -> str:
    """Generate deterministic sha256 input hash over canonical JSON payload."""
    if isinstance(data, BaseModel):
        serialized = data.model_dump_json(exclude_none=True)
    elif isinstance(data, dict):
        serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))
    else:
        serialized = str(data)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def build_export_payload(
    planned_design: TrialAssumptions,
    fixed_enrollment: ArmCounts,
    stress_scenario: Optional[StressScenario] = None,
    design_result: Optional[DesignCalculateResponse] = None,
    evaluation_result: Optional[ScenarioEvaluateResponse] = None,
    grid_result: Optional[ScenarioGridResponse] = None,
    provenance: Optional[Dict[str, Any]] = None,
    software_versions: Optional[Dict[str, str]] = None,
    exported_at: Optional[str] = None,
) -> ExportPayload:
    """Construct complete typed ExportPayload preserving input provenance."""
    norm_provenance = normalize_provenance(provenance)
    versions = software_versions if software_versions is not None else get_current_software_versions()
    timestamp = exported_at if exported_at is not None else datetime.now(timezone.utc).isoformat()

    return ExportPayload(
        export_schema_version=1,
        model_version=planned_design.model_version,
        planned_design=planned_design,
        fixed_enrollment=fixed_enrollment,
        stress_scenario=stress_scenario,
        design_result=design_result,
        evaluation_result=evaluation_result,
        grid_result=grid_result,
        software_versions=versions,
        provenance=norm_provenance,
        exported_at=timestamp,
    )
