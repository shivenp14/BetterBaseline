"""Tests for field provenance normalization and export payload roundtrips (Issue #67)."""

import hashlib
import json
from pathlib import Path
import pytest
from pydantic import ValidationError

from app.data.provenance import (
    FieldProvenanceRecord,
    normalize_provenance,
    build_export_payload,
    compute_inputs_hash,
    get_current_software_versions,
)
from app.data.presets import load_demo_preset, list_demo_presets
from app.schemas import (
    ArmCounts,
    DesignCalculateResponse,
    ExportPayload,
    FieldProvenance,
    RelativeRiskEffect,
    ScenarioEvaluateResponse,
    StressScenario,
    TrialAssumptions,
)


def test_normalize_provenance_from_dict_and_models():
    raw = {
        "control_event_rate": {
            "source": "manual_user",
            "source_url": "https://example.com/protocol.pdf",
            "source_location": "Section 4.1",
            "verified_by_user": True,
            "description": "User verified protocol rate",
        },
        "target_power": FieldProvenance(
            source="synthetic_preset",
            description="Playbook default power",
        ),
    }

    normalized = normalize_provenance(raw)
    assert len(normalized) == 2
    assert "control_event_rate" in normalized
    assert normalized["control_event_rate"].source == "manual_user"
    assert normalized["control_event_rate"].source_url == "https://example.com/protocol.pdf"
    assert normalized["control_event_rate"].source_location == "Section 4.1"
    assert normalized["control_event_rate"].verified_by_user is True

    assert "target_power" in normalized
    assert normalized["target_power"].source == "synthetic_preset"


def test_normalize_provenance_empty():
    assert normalize_provenance(None) == {}
    assert normalize_provenance({}) == {}


def test_registry_observed_cannot_be_relabeled_as_protocol_curated():
    """Negative case: clinicaltrials_registry observed data cannot be relabeled as protocol_curated."""
    invalid_record = {
        "source": "protocol_curated",
        "description": "Observed results from NCT registry",
        "source_url": "https://clinicaltrials.gov/study/NCT12345678",
        "is_observed_registry_result": True,
    }
    with pytest.raises(ValueError, match="Registry observed results cannot be relabeled as protocol_curated"):
        normalize_provenance({"control_event_rate": invalid_record})


def test_load_and_normalize_d1_demo_presets():
    """Verify loading and normalizing demo presets preserves field provenance."""
    presets = list_demo_presets()
    assert len(presets) == 3
    assert "stable-design-v1" in presets
    assert "attrition-shock-v1" in presets
    assert "baseline-collapse-v1" in presets

    stable = load_demo_preset("stable-design-v1")
    assert stable["manifest"]["preset_id"] == "stable-design-v1"
    assert stable["planned_design"].control_event_rate == 0.20
    assert stable["fixed_enrollment"].control == 951

    # Provenance preserved and normalized
    provenance = stable["provenance"]
    assert "control_event_rate" in provenance
    assert provenance["control_event_rate"].source == "synthetic_preset"
    assert provenance["control_event_rate"].verified_by_user is False
    assert "docs/03_IMPLEMENTATION_PLAYBOOK.md" in (provenance["control_event_rate"].source_location or "")


def test_export_payload_roundtrip_serialization():
    """Contract round-trip test: ExportPayload preserves assumptions, results, provenance, and hashes."""
    planned = TrialAssumptions(
        model_version="binary-v1",
        control_event_rate=0.20,
        effect=RelativeRiskEffect(kind="relative_risk", value=0.75),
        alpha=0.05,
        target_power=0.80,
        allocation_ratio=1.0,
        dropout={"control": 0.05, "treatment": 0.05},
    )
    enrollment = ArmCounts(control=951, treatment=951)
    stress = StressScenario(
        control_event_rate=0.19,
        dropout={"control": 0.06, "treatment": 0.06},
    )
    prov = {
        "control_event_rate": {
            "source": "manual_user",
            "source_url": "https://example.org/study-protocol.pdf",
            "source_location": "Page 14 Table 2",
            "verified_by_user": True,
            "description": "Manual entry verified from SAP",
        }
    }

    payload = build_export_payload(
        planned_design=planned,
        fixed_enrollment=enrollment,
        stress_scenario=stress,
        provenance=prov,
    )

    # Serialize to JSON string and back
    json_str = payload.model_dump_json()
    parsed = json.loads(json_str)

    # Re-parse into ExportPayload
    reloaded = ExportPayload.model_validate(parsed)
    assert reloaded.export_schema_version == 1
    assert reloaded.model_version == "binary-v1"
    assert reloaded.planned_design.control_event_rate == 0.20
    assert reloaded.fixed_enrollment.control == 951
    assert reloaded.stress_scenario.control_event_rate == 0.19
    assert "control_event_rate" in reloaded.provenance
    assert reloaded.provenance["control_event_rate"].source == "manual_user"
    assert reloaded.provenance["control_event_rate"].source_url == "https://example.org/study-protocol.pdf"
    assert "betterbaseline" in reloaded.software_versions


def test_inputs_hash_matches_d1_manifest_inputs():
    """Verify input hash calculation on D1 presets is stable and reproducible."""
    demo_dir = Path(__file__).resolve().parents[2] / "demo-data"
    for preset_name in ["stable-design-v1", "attrition-shock-v1", "baseline-collapse-v1"]:
        inputs_file = demo_dir / preset_name / "inputs.json"
        manifest_file = demo_dir / preset_name / "manifest.json"
        with open(inputs_file, "r", encoding="utf-8") as f:
            raw_inputs = json.load(f)
        with open(manifest_file, "r", encoding="utf-8") as f:
            raw_manifest = json.load(f)

        computed = compute_inputs_hash(raw_inputs)
        assert computed == raw_manifest["inputs_hash"]
