import json
from pathlib import Path
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
    TrialAssumptions,
    RelativeRiskEffect,
    AbsoluteRiskReductionEffect,
)


@pytest.fixture
def example_fixtures():
    fixtures_path = Path(__file__).resolve().parents[2] / "contracts" / "api-v1.example.json"
    with open(fixtures_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_calculate_fixtures(example_fixtures):
    req = DesignCalculateRequest.model_validate(example_fixtures["calculate_request"])
    assert req.control_event_rate == 0.20
    assert req.effect.kind == "relative_risk"

    res = DesignCalculateResponse.model_validate(example_fixtures["calculate_response"])
    assert res.evaluable_n.control == 903
    assert res.enrolled_n.control == 1004


def test_evaluate_fixtures(example_fixtures):
    req = ScenarioEvaluateRequest.model_validate(example_fixtures["evaluate_request"])
    assert req.stress_scenario.control_event_rate == 0.10

    res = ScenarioEvaluateResponse.model_validate(example_fixtures["evaluate_response"])
    assert res.analytic.conditional_power_approx == 0.470
    assert res.monte_carlo.significant_two_sided_fraction == 0.472
    assert res.monte_carlo.mcse_two_sided == 0.005


def test_grid_fixtures(example_fixtures):
    req = ScenarioGridRequest.model_validate(example_fixtures["grid_request"])
    assert req.x_baseline.min == 0.05
    assert req.x_baseline.max == 0.30

    res = ScenarioGridResponse.model_validate(example_fixtures["grid_response"])
    assert len(res.power) == 2
    assert len(res.power[0]) == 3
    assert res.target_power == 0.80


def test_export_payload_fixture(example_fixtures):
    exp = ExportPayload.model_validate(example_fixtures["export_payload"])
    assert exp.export_schema_version == 1
    assert "control_event_rate" in exp.provenance


def test_invalid_arr_in_calculate():
    with pytest.raises(ValidationError):
        TrialAssumptions(
            control_event_rate=0.10,
            effect=AbsoluteRiskReductionEffect(kind="absolute_risk_reduction", value=0.15),
            alpha=0.05,
            target_power=0.80,
        )


def test_invalid_target_power_below_alpha():
    with pytest.raises(ValidationError):
        TrialAssumptions(
            control_event_rate=0.20,
            effect=RelativeRiskEffect(kind="relative_risk", value=0.75),
            alpha=0.05,
            target_power=0.04,
        )


def test_unsupported_allocation_ratio():
    with pytest.raises(ValidationError):
        TrialAssumptions(
            control_event_rate=0.20,
            effect=RelativeRiskEffect(kind="relative_risk", value=0.75),
            allocation_ratio=2.0,
        )
