"""Issue #67 provenance normalization and frozen API v1 export checks."""

import hashlib
import json
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.data.presets import list_demo_presets, load_demo_preset
from app.data.provenance import (
    build_export_payload,
    compute_inputs_hash,
    normalize_provenance,
)
from app.main import app
from app.schemas import (
    ArmCounts,
    DesignCalculateResponse,
    ExportPayload,
    FieldProvenance,
    RelativeRiskEffect,
    ScenarioEvaluateResponse,
    ScenarioGridResponse,
    StressScenario,
    TrialAssumptions,
)


def test_normalize_dicts_models_and_json_pointer_records():
    normalized = normalize_provenance({
        "/planned_design/control_event_rate": {
            "origin": "manual_user",
            "description": "Entered from trial protocol",
            "source_url": "https://example.org/protocol.pdf",
            "source_location": "Page 14, Table 2",
            "verified_by_user": True,
        },
        "/planned_design/target_power": FieldProvenance(
            source="synthetic_preset", description="Demo assumption"
        ),
    })

    assert normalized["/planned_design/control_event_rate"].source == "manual_user"
    assert normalized["/planned_design/control_event_rate"].source_url == "https://example.org/protocol.pdf"
    assert normalized["/planned_design/control_event_rate"].source_location == "Page 14, Table 2"
    assert normalized["/planned_design/control_event_rate"].verified_by_user is True
    assert normalized["/planned_design/target_power"].source == "synthetic_preset"

    records = normalize_provenance([{
        "field": "/stress_scenario/control_event_rate",
        "origin": "synthetic_preset",
        "description": "Synthetic stress input",
    }])
    assert records["/stress_scenario/control_event_rate"].source == "synthetic_preset"


@pytest.mark.parametrize("value", [None, {}])
def test_empty_provenance(value):
    assert normalize_provenance(value) == {}


def test_invalid_provenance_tags_and_conflicting_aliases_are_rejected():
    with pytest.raises(ValidationError):
        normalize_provenance({"x": {"source": "unknown"}})
    with pytest.raises(ValueError, match="must agree"):
        normalize_provenance({"x": {"source": "manual_user", "origin": "synthetic_preset"}})


def test_registry_observed_results_cannot_be_labeled_protocol_curated():
    invalid = {
        "source": "protocol_curated",
        "description": "Observed results from registry",
        "source_url": "https://clinicaltrials.gov/study/NCT12345678",
    }
    with pytest.raises(ValueError, match="cannot be relabeled"):
        normalize_provenance({"/planned_design/control_event_rate": invalid})

    observed = normalize_provenance({"result": {
        "source": "clinicaltrials_registry",
        "description": "Observed endpoint result",
        "source_url": "https://clinicaltrials.gov/study/NCT12345678",
        "is_observed_registry_result": True,
    }})
    assert observed["result"].is_observed_registry_result is True
    relabeled = observed["result"].model_copy(update={"source": "protocol_curated"})
    with pytest.raises(ValueError, match="cannot be relabeled"):
        normalize_provenance({"result": relabeled})


def test_load_d1_presets_preserves_all_pointer_records():
    assert set(list_demo_presets()) == {
        "stable-design-v1", "attrition-shock-v1", "baseline-collapse-v1"
    }
    preset = load_demo_preset("stable-design-v1")
    records = preset["provenance"]
    assert len(records) == len(preset["manifest"]["provenance"]) == 17
    assert "/planned_design/control_event_rate" in records
    assert "/stress_scenario/control_event_rate" in records
    planned = records["/planned_design/control_event_rate"]
    assert planned.source == "synthetic_preset"
    assert planned.verified_by_user is False
    assert "docs/03_IMPLEMENTATION_PLAYBOOK.md" in planned.source_location


def test_export_roundtrip_contains_assumptions_results_methods_warnings_and_provenance():
    client = TestClient(app)
    design_request = {
        "control_event_rate": .20,
        "effect": {"kind": "relative_risk", "value": .75},
        "alpha": .05,
        "target_power": .80,
        "dropout": {"control": .05, "treatment": .05},
        "provenance": {"/planned_design/control_event_rate": {
            "source": "manual_user",
            "description": "Verified by user",
            "source_url": "https://example.org/protocol.pdf",
            "source_location": "Page 14, Table 2",
            "verified_by_user": True,
        }, "/planned_design/target_power": {
            "origin": "synthetic_preset",
            "description": "Synthetic demo target power",
            "source_location": "Demo manifest",
            "verified_by_user": False,
        }, "/registry/observed_endpoint": {
            "source": "clinicaltrials_registry",
            "description": "Observed registry endpoint result",
            "source_url": "https://clinicaltrials.gov/study/NCT12345678",
            "source_location": "Results section",
            "verified_by_user": False,
            "is_observed_registry_result": True,
        }},
    }
    design_response = client.post("/api/v1/design/calculate", json=design_request)
    assert design_response.status_code == 200, design_response.text
    assert design_response.json()["provenance"]["/planned_design/control_event_rate"]["source"] == "manual_user"
    assert design_response.json()["provenance"]["/planned_design/control_event_rate"]["source_location"] == "Page 14, Table 2"
    assert design_response.json()["provenance"]["/planned_design/control_event_rate"]["verified_by_user"] is True
    assert design_response.json()["provenance"]["/planned_design/target_power"]["source"] == "synthetic_preset"
    assert design_response.json()["provenance"]["/registry/observed_endpoint"]["is_observed_registry_result"] is True

    evaluate_request = {
        "planned_design": {k: v for k, v in design_request.items() if k != "provenance"},
        "fixed_enrollment": {"control": 951, "treatment": 951},
        "stress_scenario": {
            "control_event_rate": .19,
            "dropout": {"control": .06, "treatment": .06},
        },
        "simulation": {"replicates": 100, "seed": 42},
        "provenance": design_request["provenance"],
    }
    eval_response = client.post("/api/v1/scenarios/evaluate", json=evaluate_request)
    assert eval_response.status_code == 200, eval_response.text
    assert eval_response.json()["provenance"]["/planned_design/control_event_rate"]["source"] == "manual_user"
    assert eval_response.json()["provenance"]["/planned_design/control_event_rate"]["source_location"] == "Page 14, Table 2"
    assert eval_response.json()["provenance"]["/planned_design/control_event_rate"]["source_url"] == "https://example.org/protocol.pdf"
    assert eval_response.json()["provenance"]["/planned_design/control_event_rate"]["verified_by_user"] is True
    assert eval_response.json()["provenance"]["/planned_design/target_power"]["source"] == "synthetic_preset"
    assert eval_response.json()["provenance"]["/planned_design/target_power"]["source_location"] == "Demo manifest"

    grid_request = {
        "planned_design": evaluate_request["planned_design"],
        "fixed_enrollment": evaluate_request["fixed_enrollment"],
        "x_baseline": {"min": .10, "max": .30, "steps": 2},
        "y_dropout": {"min": 0, "max": .20, "steps": 2},
        "provenance": design_request["provenance"],
    }
    grid_response = client.post("/api/v1/scenarios/grid", json=grid_request)
    assert grid_response.status_code == 200, grid_response.text
    assert grid_response.json()["provenance"]["/planned_design/control_event_rate"]["source"] == "manual_user"
    assert grid_response.json()["provenance"]["/planned_design/control_event_rate"]["source_url"] == "https://example.org/protocol.pdf"
    assert grid_response.json()["provenance"]["/planned_design/control_event_rate"]["source_location"] == "Page 14, Table 2"
    assert grid_response.json()["provenance"]["/planned_design/control_event_rate"]["verified_by_user"] is True
    assert grid_response.json()["provenance"]["/planned_design/target_power"]["source"] == "synthetic_preset"
    assert grid_response.json()["provenance"]["/planned_design/target_power"]["source_location"] == "Demo manifest"

    payload = build_export_payload(
        planned_design=TrialAssumptions.model_validate(evaluate_request["planned_design"]),
        fixed_enrollment=ArmCounts.model_validate(evaluate_request["fixed_enrollment"]),
        stress_scenario=StressScenario.model_validate(evaluate_request["stress_scenario"]),
        design_result=DesignCalculateResponse.model_validate(design_response.json()),
        evaluation_result=ScenarioEvaluateResponse.model_validate(eval_response.json()),
        grid_result=ScenarioGridResponse.model_validate(grid_response.json()),
        provenance=design_request["provenance"],
        software_versions={"python": "3.12.13", "betterbaseline": "0.1.0"},
        exported_at="2026-10-11T12:00:00+00:00",
    )
    encoded = payload.model_dump_json()
    decoded = json.loads(encoded)
    restored = ExportPayload.model_validate(decoded)

    assert restored.exported_at == "2026-10-11T12:00:00+00:00"
    assert restored.planned_design.control_event_rate == .20
    assert restored.fixed_enrollment == ArmCounts(control=951, treatment=951)
    assert restored.design_result.method == "cohen_h_normal_v1"
    assert restored.evaluation_result.monte_carlo.replicates == 100
    assert restored.evaluation_result.monte_carlo.seed == 42
    assert restored.evaluation_result.monte_carlo.method == "pooled_two_proportion_z_v1"
    assert restored.evaluation_result.warnings
    assert restored.grid_result.method == "cohen_h_normal_v1"
    assert restored.grid_result.warnings
    assert restored.provenance["/planned_design/control_event_rate"].source == "manual_user"
    assert restored.provenance["/planned_design/control_event_rate"].source_url == "https://example.org/protocol.pdf"
    assert restored.provenance["/planned_design/control_event_rate"].source_location == "Page 14, Table 2"
    assert restored.provenance["/planned_design/control_event_rate"].verified_by_user is True
    assert restored.provenance["/planned_design/target_power"].source == "synthetic_preset"
    assert restored.provenance["/planned_design/target_power"].source_location == "Demo manifest"
    assert restored.provenance["/registry/observed_endpoint"].is_observed_registry_result is True
    assert restored.design_result.inputs_hash
    assert restored.evaluation_result.metadata.inputs_hash
    assert restored.grid_result.inputs_hash
    assert restored.inputs_hash and restored.inputs_hash.startswith("sha256:")
    assert restored.evaluation_result.monte_carlo.mean_retained_control is not None
    assert restored.evaluation_result.monte_carlo.rng
    assert restored.evaluation_result.metadata.software_versions
    assert restored.evaluation_result.metadata.fixed_enrollment == ArmCounts(control=951, treatment=951)


def test_export_constructor_guarantees_hash_even_without_results():
    planned = TrialAssumptions(
        control_event_rate=.20,
        effect=RelativeRiskEffect(value=.75),
    )
    enrollment = ArmCounts(control=903, treatment=903)
    legacy_payload = ExportPayload(
        planned_design=planned,
        fixed_enrollment=enrollment,
        exported_at="2026-10-11T12:00:00+00:00",
    )
    assert legacy_payload.inputs_hash.startswith("sha256:")
    restored = ExportPayload.model_validate(json.loads(legacy_payload.model_dump_json()))
    assert restored.inputs_hash == legacy_payload.inputs_hash

    tagged = ExportPayload(
        planned_design=planned,
        fixed_enrollment=enrollment,
        provenance={"/a": {"source": "manual_user"}, "/b": {"origin": "synthetic_preset"}},
        exported_at="2026-10-11T12:00:00+00:00",
    )
    reordered = ExportPayload(
        planned_design=planned,
        fixed_enrollment=enrollment,
        provenance={"/b": {"source": "synthetic_preset"}, "/a": {"source": "manual_user"}},
        exported_at="2026-10-11T12:00:00+00:00",
    )
    assert tagged.inputs_hash == reordered.inputs_hash
    changed = ExportPayload(
        planned_design=planned,
        fixed_enrollment=enrollment,
        provenance={"/a": {"source": "manual_user", "verified_by_user": True}},
        exported_at="2026-10-11T12:00:00+00:00",
    )
    assert changed.inputs_hash != legacy_payload.inputs_hash

    altered = legacy_payload.model_dump(mode="json")
    altered["planned_design"]["target_power"] = .90
    with pytest.raises(ValidationError, match="does not match canonical"):
        ExportPayload.model_validate(altered)


def test_calculate_route_defaults_provenance_and_rejects_registry_relabel():
    client = TestClient(app)
    request = {
        "control_event_rate": .20,
        "effect": {"kind": "relative_risk", "value": .75},
        "alpha": .05,
        "target_power": .80,
    }
    response = client.post("/api/v1/design/calculate", json=request)
    assert response.status_code == 200, response.text
    assert response.json()["provenance"] == {}
    legacy_hash = hashlib.sha256(
        TrialAssumptions.model_validate(request).model_dump_json(exclude_none=True).encode("utf-8")
    ).hexdigest()[:16]
    assert response.json()["inputs_hash"] == legacy_hash

    request["provenance"] = {"/planned_design/control_event_rate": {
        "source": "protocol_curated",
        "description": "Observed endpoint results",
        "source_url": "https://clinicaltrials.gov/study/NCT12345678",
        "is_observed_registry_result": True,
    }}
    rejected = client.post("/api/v1/design/calculate", json=request)
    assert rejected.status_code == 422
    assert "protocol_curated" in rejected.text


def test_input_hash_is_canonical_for_dict_and_model():
    data = {
        "a": 1,
        "b": {"source": "synthetic_preset", "description": "Synthetic"},
    }
    model = TrialAssumptions(
        control_event_rate=.2,
        effect=RelativeRiskEffect(value=.75),
        dropout={"control": 0, "treatment": 0},
    )
    assert compute_inputs_hash(data) == compute_inputs_hash(dict(reversed(list(data.items()))))
    assert compute_inputs_hash(model) == compute_inputs_hash(model.model_dump(mode="json"))
    with pytest.raises(ValueError, match="Out of range float values"):
        compute_inputs_hash({"bad": float("nan")})

