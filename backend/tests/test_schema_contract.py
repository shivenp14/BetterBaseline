import json
from pathlib import Path
import jsonschema
import pytest
from pydantic import ValidationError

from app.schemas import (
    DesignCalculateRequest,
    DesignCalculateResponse,
    ScenarioEvaluateRequest,
    ScenarioEvaluateResponse,
    ScenarioGridRequest,
    ScenarioGridResponse,
    ExportPayload,
    ErrorEnvelope,
    TrialAssumptions,
    RelativeRiskEffect,
    AbsoluteRiskReductionEffect,
    ArmCounts,
    ArmProportions,
    SimulationOptions,
    GridPoint,
)


@pytest.fixture
def example_fixtures():
    fixtures_path = Path(__file__).resolve().parents[2] / "contracts" / "api-v1.example.json"
    with open(fixtures_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def json_schema():
    schema_path = Path(__file__).resolve().parents[2] / "contracts" / "api-v1.schema.json"
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_calculate_fixtures(example_fixtures):
    req = DesignCalculateRequest.model_validate(example_fixtures["design_calculate_request"])
    assert req.control_event_rate == 0.20
    assert req.effect.kind == "relative_risk"

    res = DesignCalculateResponse.model_validate(example_fixtures["design_calculate_response"])
    assert res.evaluable_n.control == 903
    assert res.enrolled_n.control == 1004


def test_evaluate_fixtures(example_fixtures):
    req = ScenarioEvaluateRequest.model_validate(example_fixtures["scenario_evaluate_request"])
    assert req.stress_scenario.control_event_rate == 0.10

    res = ScenarioEvaluateResponse.model_validate(example_fixtures["scenario_evaluate_response"])
    assert res.analytic.conditional_power_approx == 0.470
    assert res.monte_carlo.significant_two_sided_fraction == 0.472
    assert res.monte_carlo.mcse_two_sided == 0.005


def test_grid_fixtures(example_fixtures):
    req = ScenarioGridRequest.model_validate(example_fixtures["scenario_grid_request"])
    assert req.x_baseline.min == 0.05
    assert req.x_baseline.max == 0.30

    res = ScenarioGridResponse.model_validate(example_fixtures["scenario_grid_response"])
    assert len(res.power) == 2
    assert len(res.power[0]) == 3
    assert res.target_power == 0.80
    assert len(res.contour_segments) == 1
    assert len(res.power_curve) == 3
    assert res.invalid_cell_count == 0
    assert res.worst_case_power == 0.21


def test_export_payload_fixture(example_fixtures):
    exp = ExportPayload.model_validate(example_fixtures["export_payload"])
    assert exp.export_schema_version == 1
    assert "control_event_rate" in exp.provenance


def test_error_envelope_fixture(example_fixtures):
    err = ErrorEnvelope.model_validate(example_fixtures["error_envelope"])
    assert err.error.code == "INVALID_MODEL_INPUT"
    assert err.error.recoverable is True


def test_validate_fixtures_against_json_schema(example_fixtures, json_schema):
    """Validate example fixtures directly against the machine-readable api-v1.schema.json."""
    jsonschema.validate(instance=example_fixtures, schema=json_schema)


# ── ROLAND REVIEW BOUNDARY TESTS ──

def test_unequal_arm_counts_rejected():
    with pytest.raises(ValidationError, match="Equal 1:1 enrollment required"):
        ArmCounts(control=1004, treatment=999)


def test_asymmetric_dropout_rejected():
    with pytest.raises(ValidationError, match="Symmetric dropout required"):
        ArmProportions(control=0.10, treatment=0.20)


def test_negative_simulation_seed_rejected():
    with pytest.raises(ValidationError):
        SimulationOptions(seed=-1)


def test_grid_response_ragged_dimensions_rejected():
    # Outer dimension mismatch
    with pytest.raises(ValidationError, match="outer dimension"):
        ScenarioGridResponse(
            model_version="binary-v1",
            method="cohen_h_normal_v1",
            x_baseline=[0.1, 0.2],
            y_dropout=[0.0, 0.1, 0.2],
            power=[[0.5, 0.6], [0.4, 0.5]],  # only 2 rows for 3 dropout values
            invalid_mask=[[False, False], [False, False], [False, False]],
            target_power=0.80,
            planned_point=GridPoint(p_control=0.2, dropout=0.0, power=0.8),
            invalid_cell_count=0,
            worst_case_power=0.4,
            computed_at="2026-10-10T00:00:00Z",
            inputs_hash="hash",
        )


def test_grid_response_null_without_mask_rejected():
    # Power has null but mask is False
    with pytest.raises(ValidationError, match="mask=False but power is invalid"):
        ScenarioGridResponse(
            model_version="binary-v1",
            method="cohen_h_normal_v1",
            x_baseline=[0.1, 0.2],
            y_dropout=[0.0],
            power=[[None, 0.6]],
            invalid_mask=[[False, False]],
            target_power=0.80,
            planned_point=GridPoint(p_control=0.2, dropout=0.0, power=0.8),
            invalid_cell_count=0,
            worst_case_power=0.6,
            computed_at="2026-10-10T00:00:00Z",
            inputs_hash="hash",
        )


def test_grid_response_mask_true_with_value_rejected():
    # Mask is True but power is not None
    with pytest.raises(ValidationError, match="mask=True but power is not None"):
        ScenarioGridResponse(
            model_version="binary-v1",
            method="cohen_h_normal_v1",
            x_baseline=[0.1, 0.2],
            y_dropout=[0.0],
            power=[[0.5, 0.6]],
            invalid_mask=[[True, False]],
            target_power=0.80,
            planned_point=GridPoint(p_control=0.2, dropout=0.0, power=0.8),
            invalid_cell_count=1,
            worst_case_power=0.6,
            computed_at="2026-10-10T00:00:00Z",
            inputs_hash="hash",
        )
