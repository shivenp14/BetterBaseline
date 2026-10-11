import json
import math
from pathlib import Path
import jsonschema
import pytest
from pydantic import ValidationError

from app.main import create_app
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
    MonteCarloEvaluation,
    StressScenario,
    AnalyticEvaluation,
    StatisticalDiagnostic,
    ExpectedRetainedCounts,
    PowerCurvePoint,
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
    assert req.selected_scenario is not None
    assert req.selected_scenario.control_event_rate == 0.10


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
    assert exp.inputs_hash == example_fixtures["export_payload"]["inputs_hash"]


def test_provenance_metadata_and_export_hash_are_in_frozen_schema(json_schema):
    field_schema = json_schema["$defs"]["FieldProvenance"]["properties"]
    assert {"source_location", "verified_by_user", "is_observed_registry_result"} <= set(field_schema)
    assert "provenance" in json_schema["$defs"]["DesignCalculateRequest"]["properties"]
    assert "provenance" in json_schema["$defs"]["DesignCalculateResponse"]["properties"]
    export_schema = json_schema["$defs"]["ExportPayload"]
    assert "inputs_hash" in export_schema["required"]


def test_error_envelope_fixture(example_fixtures):
    err = ErrorEnvelope.model_validate(example_fixtures["error_envelope"])
    assert err.error.code == "INVALID_MODEL_INPUT"
    assert err.error.recoverable is True


def test_validate_fixtures_against_json_schema(example_fixtures, json_schema):
    """Validate example fixtures directly against the machine-readable api-v1.schema.json."""
    jsonschema.validate(instance=example_fixtures, schema=json_schema)


def test_statistical_diagnostic_schema_matches_generated_model(json_schema):
    assert json_schema["$defs"]["StatisticalDiagnostic"] == StatisticalDiagnostic.model_json_schema()
    for model in (DesignCalculateResponse, ScenarioEvaluateResponse, ScenarioGridResponse):
        generated = model.model_json_schema()["properties"]["diagnostics"]
        assert json_schema["$defs"][model.__name__]["properties"]["diagnostics"] == generated


def test_openapi_snapshot_matches_registered_app():
    snapshot_path = Path(__file__).resolve().parents[2] / "contracts" / "openapi.snapshot.json"
    assert json.loads(snapshot_path.read_text(encoding="utf-8")) == create_app().openapi()


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


def test_arm_counts_strict_integer_rejected():
    # Booleans rejected
    with pytest.raises(ValidationError):
        ArmCounts(control=True, treatment=True)
    # Strings rejected
    with pytest.raises(ValidationError):
        ArmCounts(control="903", treatment="903")
    # Floats rejected
    with pytest.raises(ValidationError):
        ArmCounts(control=903.0, treatment=903.0)
    # Valid ints accepted
    counts = ArmCounts(control=903, treatment=903)
    assert counts.control == 903


def test_mcse_nonfinite_rejected():
    # Infinity rejected
    with pytest.raises(ValidationError):
        MonteCarloEvaluation(
            significant_two_sided_fraction=0.5,
            significant_favorable_fraction=0.5,
            mcse_two_sided=float("inf"),
            mcse_favorable=0.01,
            invalid_test_fraction=0.0,
            replicates=1000,
        )
    # NaN rejected
    with pytest.raises(ValidationError):
        MonteCarloEvaluation(
            significant_two_sided_fraction=0.5,
            significant_favorable_fraction=0.5,
            mcse_two_sided=float("nan"),
            mcse_favorable=0.01,
            invalid_test_fraction=0.0,
            replicates=1000,
        )


def test_grid_axes_nonfinite_rejected():
    with pytest.raises(ValidationError, match="Axis values must be finite numbers"):
        ScenarioGridResponse(
            model_version="binary-v1",
            method="cohen_h_normal_v1",
            x_baseline=[0.1, float("nan")],
            y_dropout=[0.0],
            power=[[0.5, 0.6]],
            invalid_mask=[[False, False]],
            target_power=0.80,
            planned_point=GridPoint(p_control=0.2, dropout=0.0, power=0.8),
            invalid_cell_count=0,
            worst_case_power=0.5,
            computed_at="2026-10-10T00:00:00Z",
            inputs_hash="hash",
        )

    with pytest.raises(ValidationError, match="Axis values must be finite numbers"):
        ScenarioGridResponse(
            model_version="binary-v1",
            method="cohen_h_normal_v1",
            x_baseline=[0.1, 0.2],
            y_dropout=[float("inf")],
            power=[[0.5, 0.6]],
            invalid_mask=[[False, False]],
            target_power=0.80,
            planned_point=GridPoint(p_control=0.2, dropout=0.0, power=0.8),
            invalid_cell_count=0,
            worst_case_power=0.5,
            computed_at="2026-10-10T00:00:00Z",
            inputs_hash="hash",
        )


def test_grid_request_conflicting_effect_rejected():
    from app.schemas import (
        AbsoluteRiskReductionEffect,
        RelativeRiskEffect,
        ScenarioGridRequest,
        StressScenario,
        TrialAssumptions,
    )

    base_design = TrialAssumptions(
        control_event_rate=0.20,
        effect=RelativeRiskEffect(value=0.75),
    )
    enrollment = ArmCounts(control=903, treatment=903)

    # Conflicting effect override between top-level and selected_scenario
    with pytest.raises(ValidationError, match="Conflicting effect_override"):
        ScenarioGridRequest(
            planned_design=base_design,
            fixed_enrollment=enrollment,
            effect_override=RelativeRiskEffect(value=0.75),
            selected_scenario=StressScenario(
                control_event_rate=0.20,
                effect_override=AbsoluteRiskReductionEffect(value=0.05),
            ),
        )

    # Consistent effect override succeeds
    req = ScenarioGridRequest(
        planned_design=base_design,
        fixed_enrollment=enrollment,
        effect_override=RelativeRiskEffect(value=0.75),
        selected_scenario=StressScenario(
            control_event_rate=0.20,
            effect_override=RelativeRiskEffect(value=0.75),
        ),
    )
    assert req.effective_grid_effect.value == 0.75


def test_export_payload_preserves_results_and_software_versions():
    from app.schemas import (
        DesignCalculateResponse,
        ExportPayload,
        RelativeRiskEffect,
        TrialAssumptions,
    )

    design = TrialAssumptions(
        control_event_rate=0.20,
        effect=RelativeRiskEffect(value=0.75),
    )
    enrollment = ArmCounts(control=903, treatment=903)

    design_res = DesignCalculateResponse(
        model_version="binary-v1",
        method="cohen_h_normal_v1",
        p_treatment=0.15,
        evaluable_n=enrollment,
        enrolled_n=enrollment,
        nominal_power_evaluable=0.80,
        warnings=[],
        inputs_hash="test-hash",
    )

    versions = {
        "python": "3.12.3",
        "numpy": "1.26.4",
        "betterbaseline": "0.1.0",
    }

    payload = ExportPayload(
        planned_design=design,
        fixed_enrollment=enrollment,
        design_result=design_res,
        software_versions=versions,
        exported_at="2026-10-10T00:00:00Z",
    )

    dumped = payload.model_dump(mode="json")
    assert dumped["design_result"] is not None
    assert dumped["design_result"]["p_treatment"] == 0.15
    assert dumped["software_versions"] == versions

    # Round-trip validate
    loaded = ExportPayload.model_validate(dumped)
    assert loaded.design_result is not None
    assert loaded.design_result.p_treatment == 0.15
    assert loaded.software_versions == versions


def test_zero_expected_retention_response_round_trip(example_fixtures, json_schema):
    request = example_fixtures["scenario_evaluate_request"]
    request["fixed_enrollment"] = {"control": 1, "treatment": 1}
    request["stress_scenario"]["dropout"] = {"control": 0.9, "treatment": 0.9}
    parsed = ScenarioEvaluateRequest.model_validate(request)
    retained = math.floor(parsed.fixed_enrollment.control * (1 - parsed.stress_scenario.dropout.control))
    assert retained == 0
    response = example_fixtures["scenario_evaluate_response"]
    response["analytic"] = {
        "conditional_power_approx": None,
        "assumed_evaluable_n": {"control": retained, "treatment": retained},
    }
    response["warnings"] = ["Analytic power unavailable: zero expected retention"]
    result = ScenarioEvaluateResponse.model_validate(response)
    dumped = result.model_dump(mode="json")
    assert ScenarioEvaluateResponse.model_validate(dumped).analytic.assumed_evaluable_n.control == 0
    jsonschema.validate(dumped, {"$ref": "#/$defs/ScenarioEvaluateResponse", "$defs": json_schema["$defs"]})
    with pytest.raises(ValidationError):
        ArmCounts(control=0, treatment=0)


@pytest.mark.parametrize("value", [-1, True, "0", 0.0])
def test_expected_retention_rejects_invalid_counts(value):
    with pytest.raises(ValidationError):
        ExpectedRetainedCounts(control=value, treatment=value)


def test_expected_retention_rejects_unequal_arms():
    with pytest.raises(ValidationError, match="Equal expected retention"):
        ExpectedRetainedCounts(control=0, treatment=1)


@pytest.mark.parametrize("count,power", [(0, 0.0), (1, None)])
def test_analytic_power_availability_matches_retention(count, power):
    with pytest.raises(ValidationError, match="Analytic power must be null"):
        AnalyticEvaluation(conditional_power_approx=power, assumed_evaluable_n={"control": count, "treatment": count})


def test_grid_requires_minimum_with_valid_cells(example_fixtures):
    grid = example_fixtures["scenario_grid_response"]
    grid["worst_case_power"] = None
    with pytest.raises(ValidationError, match="worst_case_power"):
        ScenarioGridResponse.model_validate(grid)


def test_all_invalid_grid_requires_null_minimum(example_fixtures):
    grid = example_fixtures["scenario_grid_response"]
    grid["power"] = [[None for _ in grid["x_baseline"]] for _ in grid["y_dropout"]]
    grid["invalid_mask"] = [[True for _ in grid["x_baseline"]] for _ in grid["y_dropout"]]
    grid["invalid_cell_count"] = len(grid["x_baseline"]) * len(grid["y_dropout"])
    grid["worst_case_power"] = 0.75
    with pytest.raises(ValidationError, match="no valid cells"):
        ScenarioGridResponse.model_validate(grid)
    grid["worst_case_power"] = None
    assert ScenarioGridResponse.model_validate(grid).worst_case_power is None


@pytest.mark.parametrize("model", [GridPoint, PowerCurvePoint])
@pytest.mark.parametrize("is_valid,power", [(True, None), (False, 0.8)])
def test_point_validity_rejects_contradictory_power(model, is_valid, power):
    with pytest.raises(ValidationError, match="exactly when is_valid"):
        model(p_control=0.2, dropout=0.1, is_valid=is_valid, power=power)


@pytest.mark.parametrize("model", [GridPoint, PowerCurvePoint])
@pytest.mark.parametrize("is_valid,power", [(True, 0.8), (False, None)])
def test_point_validity_accepts_consistent_power(model, is_valid, power):
    result = model(p_control=0.2, dropout=0.1, is_valid=is_valid, power=power)
    assert result.is_valid == is_valid
    assert result.power == power


@pytest.mark.parametrize("field", ["planned_point", "selected_point", "frontier_points", "power_curve"])
@pytest.mark.parametrize("is_valid,power", [(True, None), (False, 0.8)])
def test_grid_rejects_contradictory_nested_points(example_fixtures, field, is_valid, power):
    grid = example_fixtures["scenario_grid_response"]
    point = {"p_control": 0.2, "dropout": 0.1, "is_valid": is_valid, "power": power}
    grid[field] = [point] if field in ("frontier_points", "power_curve") else point
    with pytest.raises(ValidationError, match="exactly when is_valid"):
        ScenarioGridResponse.model_validate(grid)
