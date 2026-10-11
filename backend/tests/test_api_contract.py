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
    assert (
        "Dropout inflation represents expected retention, not guaranteed evaluable counts."
        in data["warnings"]
    )


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
    assert (
        "Dropout inflation represents expected retention, not guaranteed evaluable counts."
        not in data["warnings"]
    )


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


def test_scenarios_evaluate_registered_handoff(client: TestClient) -> None:
    """The completed #65 handoff evaluates through the registered router."""
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
    assert response.status_code == 200
    data = response.json()
    assert data["analytic"]["assumed_evaluable_n"] == {"control": 853, "treatment": 853}
    assert data["monte_carlo"]["replicates"] == 10_000
    assert data["metadata"]["fixed_enrollment"] == payload["fixed_enrollment"]


def test_scenarios_grid_registered_endpoint(client: TestClient) -> None:
    """#66 replaces the handed-off grid scaffold with a real calculation."""
    payload = {
        "planned_design": {
            "model_version": "binary-v1",
            "control_event_rate": 0.20,
            "effect": {"kind": "relative_risk", "value": 0.75},
        },
        "fixed_enrollment": {"control": 1004, "treatment": 1004},
    }
    response = client.post("/api/v1/scenarios/grid", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["power"]) == 10
    assert all(len(row) == 15 for row in data["power"])
    assert data["fixed_enrollment"] == payload["fixed_enrollment"]
    assert data["method"] == "cohen_h_normal_v1"


def test_cors_preflight_default_allowed_origins(client: TestClient) -> None:
    """Default configuration allows localhost preflight."""
    response = client.options(
        "/api/v1/design/calculate",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_preflight_configured_environment_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configured ALLOWED_ORIGINS in environment is parsed and honored in preflight."""
    from app.main import create_app

    monkeypatch.setenv("ALLOWED_ORIGINS", '["https://review.example"]')
    test_app = create_app()
    test_client = TestClient(test_app)

    response = test_client.options(
        "/api/v1/design/calculate",
        headers={
            "Origin": "https://review.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://review.example"

    disallowed = test_client.options(
        "/api/v1/design/calculate",
        headers={
            "Origin": "https://disallowed.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert disallowed.status_code == 400


def test_parse_allowed_origins_formats() -> None:
    """parse_allowed_origins supports JSON arrays, comma-delimited strings, and lists."""
    from app.settings import parse_allowed_origins

    assert parse_allowed_origins('["https://a.com", "https://b.com"]') == [
        "https://a.com",
        "https://b.com",
    ]
    assert parse_allowed_origins("https://a.com, https://b.com") == [
        "https://a.com",
        "https://b.com",
    ]
    assert parse_allowed_origins(["https://a.com", "https://b.com"]) == [
        "https://a.com",
        "https://b.com",
    ]
    assert parse_allowed_origins(None) == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_openapi_documents_error_envelope_for_422() -> None:
    """OpenAPI schema declares ErrorEnvelope for 422 responses and omits HTTPValidationError."""
    schema = app.openapi()
    for endpoint in ["/api/v1/design/calculate", "/api/v1/scenarios/evaluate", "/api/v1/scenarios/grid"]:
        post_op = schema["paths"][endpoint]["post"]
        resp_422 = post_op["responses"]["422"]
        schema_ref = resp_422["content"]["application/json"]["schema"]["$ref"]
        assert schema_ref == "#/components/schemas/ErrorEnvelope"

    schemas = schema["components"]["schemas"]
    assert "ErrorEnvelope" in schemas
    assert "ErrorDetail" in schemas
    assert "HTTPValidationError" not in schemas
    assert "ValidationError" not in schemas


def test_design_calculate_routes_through_compute_helper(client: TestClient) -> None:
    """POST /api/v1/design/calculate routes computation through execute_guarded_computation."""
    from unittest.mock import patch
    from app.routers import design

    called = False

    def spy_compute(func, *args, **kwargs):
        nonlocal called
        called = True
        return func(*args, **kwargs)

    with patch.object(design, "execute_guarded_computation", side_effect=spy_compute):
        payload = {
            "model_version": "binary-v1",
            "control_event_rate": 0.20,
            "effect": {"kind": "relative_risk", "value": 0.75},
            "alpha": 0.05,
            "target_power": 0.80,
            "allocation_ratio": 1.0,
            "dropout": {"control": 0.10, "treatment": 0.10},
        }
        response = client.post("/api/v1/design/calculate", json=payload)
        assert response.status_code == 200
        assert called is True


def test_custom_app_settings_reflected_in_health_and_meta() -> None:
    """create_app with custom Settings propagates settings to healthz and meta routes."""
    from app.main import create_app
    from app.settings import Settings

    custom_settings = Settings(
        app_name="Custom Clinical Service",
        app_version="1.2.3",
        model_version="custom-v2",
    )
    custom_app = create_app(custom_settings)
    custom_client = TestClient(custom_app)

    health_resp = custom_client.get("/healthz")
    assert health_resp.status_code == 200
    assert health_resp.json()["model_version"] == "custom-v2"

    meta_resp = custom_client.get("/api/v1/meta")
    assert meta_resp.status_code == 200
    meta_data = meta_resp.json()
    assert meta_data["app_name"] == "Custom Clinical Service"
    assert meta_data["app_version"] == "1.2.3"
    assert meta_data["model_version"] == "custom-v2"


def test_openapi_scaffold_501_responses() -> None:
    """OpenAPI schema documents 501 ErrorEnvelope responses for scenarios evaluate and grid."""
    schema = app.openapi()
    for endpoint in ["/api/v1/scenarios/evaluate", "/api/v1/scenarios/grid"]:
        post_op = schema["paths"][endpoint]["post"]
        assert "501" in post_op["responses"]
        resp_501 = post_op["responses"]["501"]
        schema_ref = resp_501["content"]["application/json"]["schema"]["$ref"]
        assert schema_ref == "#/components/schemas/ErrorEnvelope"


def test_dropout_inflation_exact_decimal_boundary() -> None:
    """Dropout inflation uses exact rational arithmetic to avoid float round-up at decimal boundaries."""
    from app.statistics.inputs import Dropout as StatDropout
    from app.statistics.sample_size import minimum_sample_size

    # Evaluated minimum N = 2, dropout = 0.8
    # In float arithmetic: ceil(2 / (1.0 - 0.8)) == ceil(2 / 0.19999999999999996) == 11
    # In exact arithmetic: ceil(2 / 0.2) == 10
    result = minimum_sample_size(
        p_control=0.99,
        p_treatment=0.01,
        target_power=0.50,
        alpha=0.05,
        dropout=StatDropout(0.8, 0.8),
    )
    assert result.evaluable_per_arm == 2
    assert result.enrolled_per_arm == 10
