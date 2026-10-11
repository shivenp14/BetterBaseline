"""Contract and functional API tests for Better Baseline FastAPI application."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import ErrorEnvelope


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_healthz_endpoint(client: TestClient) -> None:
    """GET /healthz returns 200 with status ok and model_version binary-v1."""
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["model_version"] == "binary-v1"


def test_metadata_endpoint(client: TestClient) -> None:
    """GET /api/v1/meta returns application metadata and canonical methods."""
    response = client.get("/api/v1/meta")
    assert response.status_code == 200
    data = response.json()
    assert data["model_version"] == "binary-v1"
    assert data["analytical_method"] == "cohen_h_normal_v1"
    assert data["simulation_method"] == "pooled_two_proportion_z_v1"


def test_design_calculate_reference_scenario(client: TestClient) -> None:
    """POST /api/v1/design/calculate with reference inputs.

    pC=0.20, RR=0.75 (pT=0.15), alpha=0.05, target_power=0.80, dropout=0.10.
    Expected: 903 evaluable per arm, 1004 enrolled per arm.
    """
    payload = {
        "model_version": "binary-v1",
        "control_event_rate": 0.20,
        "effect": {
            "kind": "relative_risk",
            "value": 0.75,
        },
        "alpha": 0.05,
        "target_power": 0.80,
        "allocation_ratio": 1.0,
        "dropout": {
            "control": 0.10,
            "treatment": 0.10,
        },
    }
    response = client.post("/api/v1/design/calculate", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["model_version"] == "binary-v1"
    assert data["method"] == "cohen_h_normal_v1"
    assert pytest.approx(data["p_treatment"], abs=1e-4) == 0.15
    assert data["evaluable_n"] == {"control": 903, "treatment": 903}
    assert data["enrolled_n"] == {"control": 1004, "treatment": 1004}
    assert data["nominal_power_evaluable"] >= 0.80
    assert data["nominal_power_evaluable"] == pytest.approx(0.80, abs=0.01)
    assert "inputs_hash" in data and len(data["inputs_hash"]) > 0


def test_design_calculate_arr_effect(client: TestClient) -> None:
    """POST /api/v1/design/calculate with absolute risk reduction."""
    payload = {
        "model_version": "binary-v1",
        "control_event_rate": 0.20,
        "effect": {
            "kind": "absolute_risk_reduction",
            "value": 0.05,
        },
        "alpha": 0.05,
        "target_power": 0.80,
        "allocation_ratio": 1.0,
        "dropout": {
            "control": 0.0,
            "treatment": 0.0,
        },
    }
    response = client.post("/api/v1/design/calculate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert pytest.approx(data["p_treatment"], abs=1e-4) == 0.15
    assert data["evaluable_n"] == {"control": 903, "treatment": 903}
    assert data["enrolled_n"] == {"control": 903, "treatment": 903}


def test_design_calculate_invalid_arr_returns_structured_422(client: TestClient) -> None:
    """ARR >= pC must return structured 422 ErrorEnvelope."""
    payload = {
        "model_version": "binary-v1",
        "control_event_rate": 0.04,
        "effect": {
            "kind": "absolute_risk_reduction",
            "value": 0.05,
        },
        "alpha": 0.05,
        "target_power": 0.80,
    }
    response = client.post("/api/v1/design/calculate", json=payload)
    assert response.status_code == 422
    data = response.json()
    envelope = ErrorEnvelope.model_validate(data)
    assert envelope.error.code == "INVALID_MODEL_INPUT"
    assert "cannot equal or exceed" in envelope.error.message.lower() or "arr" in envelope.error.message.lower()


def test_design_calculate_asymmetric_dropout_rejected(client: TestClient) -> None:
    """Asymmetric dropout is unsupported in P0 and must return structured 422."""
    payload = {
        "model_version": "binary-v1",
        "control_event_rate": 0.20,
        "effect": {
            "kind": "relative_risk",
            "value": 0.75,
        },
        "dropout": {
            "control": 0.10,
            "treatment": 0.15,
        },
    }
    response = client.post("/api/v1/design/calculate", json=payload)
    assert response.status_code == 422
    envelope = ErrorEnvelope.model_validate(response.json())
    assert envelope.error.code == "INVALID_MODEL_INPUT"
    assert "symmetric" in envelope.error.message.lower()


def test_design_calculate_non_1_to_1_allocation_rejected(client: TestClient) -> None:
    """Non-1:1 allocation ratio is unsupported in MVP and must return structured 422."""
    payload = {
        "model_version": "binary-v1",
        "control_event_rate": 0.20,
        "effect": {
            "kind": "relative_risk",
            "value": 0.75,
        },
        "allocation_ratio": 2.0,
    }
    response = client.post("/api/v1/design/calculate", json=payload)
    assert response.status_code == 422
    envelope = ErrorEnvelope.model_validate(response.json())
    assert envelope.error.code == "INVALID_MODEL_INPUT"
    assert "allocation_ratio" in envelope.error.message.lower()


def test_scenarios_evaluate_stub_501(client: TestClient) -> None:
    """POST /api/v1/scenarios/evaluate returns 501 scaffold for #65 handoff."""
    payload = {
        "planned_design": {
            "model_version": "binary-v1",
            "control_event_rate": 0.20,
            "effect": {"kind": "relative_risk", "value": 0.75},
        },
        "fixed_enrollment": {"control": 1004, "treatment": 1004},
        "stress_scenario": {
            "control_event_rate": 0.25,
            "dropout": {"control": 0.15, "treatment": 0.15},
        },
    }
    response = client.post("/api/v1/scenarios/evaluate", json=payload)
    assert response.status_code == 501


def test_scenarios_grid_stub_501(client: TestClient) -> None:
    """POST /api/v1/scenarios/grid returns 501 scaffold for #66 handoff."""
    payload = {
        "planned_design": {
            "model_version": "binary-v1",
            "control_event_rate": 0.20,
            "effect": {"kind": "relative_risk", "value": 0.75},
        },
        "fixed_enrollment": {"control": 1004, "treatment": 1004},
    }
    response = client.post("/api/v1/scenarios/grid", json=payload)
    assert response.status_code == 501
