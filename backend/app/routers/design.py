"""Design calculation route."""

import hashlib
import json
from typing import Any
from fastapi import APIRouter, Request

from ..cache import make_cache_key
from ..data.provenance import normalize_provenance
from ..schemas import (
    ArmCounts,
    DesignCalculateRequest,
    DesignCalculateResponse,
    ErrorEnvelope,
)
from ..services.compute import execute_guarded_computation
from ..statistics.effect import resolve_treatment_risk
from ..statistics.diagnostics import analytic_diagnostics
from ..statistics.inputs import Dropout as StatDropout, Effect as StatEffect
from ..statistics.sample_size import minimum_sample_size

router = APIRouter(
    prefix="/api/v1/design",
    tags=["design"],
    responses={
        422: {"model": ErrorEnvelope, "description": "Validation Error"},
        413: {"model": ErrorEnvelope, "description": "Payload Too Large"},
        429: {
            "model": ErrorEnvelope,
            "description": "Compute Resource Saturated",
            "headers": {
                "Retry-After": {
                    "description": "Seconds to wait before retrying.",
                    "schema": {"type": "integer"},
                }
            },
        },
    },
)


def compute_inputs_hash(request: DesignCalculateRequest) -> str:
    values = request.model_dump(mode="json", exclude_none=True)
    # Keep the historical digest for older clients that omit provenance.
    if not values.get("provenance"):
        values.pop("provenance", None)
    raw = json.dumps(values, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@router.post("/calculate", response_model=DesignCalculateResponse)
def calculate_design(request: DesignCalculateRequest, http_request: Request) -> DesignCalculateResponse:
    guard = http_request.app.state.compute_guard
    stat_effect = StatEffect(kind=request.effect.kind, value=request.effect.value)
    p_treatment = resolve_treatment_risk(request.control_event_rate, stat_effect)

    stat_dropout = StatDropout(
        control=request.dropout.control,
        treatment=request.dropout.treatment,
    )

    cache_key = make_cache_key(
        route="/api/v1/design/calculate",
        model_version="binary-v1",
        params=request,
    )

    def _compute(**_kwargs: Any) -> Any:
        return minimum_sample_size(
            p_control=request.control_event_rate,
            p_treatment=p_treatment,
            target_power=request.target_power,
            alpha=request.alpha,
            dropout=stat_dropout,
        )

    size_result = execute_guarded_computation(
        _compute,
        cache_key=cache_key,
        guard=guard,
    )

    # Verify inflated enrollment ceiling before returning response
    guard.check_enrollment(
        control_enrolled=size_result.enrolled_per_arm,
        treatment_enrolled=size_result.enrolled_per_arm,
    )

    evaluable_n = ArmCounts(
        control=size_result.evaluable_per_arm,
        treatment=size_result.evaluable_per_arm,
    )
    enrolled_n = ArmCounts(
        control=size_result.enrolled_per_arm,
        treatment=size_result.enrolled_per_arm,
    )

    warnings = []
    if request.dropout.control > 0.0 or request.dropout.treatment > 0.0:
        warnings.append(
            "Dropout inflation represents expected retention, not guaranteed evaluable counts."
        )
    if request.control_event_rate < 0.05 or request.control_event_rate > 0.40:
        warnings.append(
            f"Control event rate {request.control_event_rate} is near or outside common binary trial planning regimes (0.05 - 0.40)."
        )

    diagnostics = analytic_diagnostics(
        request.control_event_rate, p_treatment,
        evaluable_n.control, evaluable_n.treatment, request.alpha,
    )["diagnostics"]

    return DesignCalculateResponse(
        model_version="binary-v1",
        method="cohen_h_normal_v1",
        p_treatment=p_treatment,
        evaluable_n=evaluable_n,
        enrolled_n=enrolled_n,
        nominal_power_evaluable=size_result.achieved_power,
        warnings=warnings,
        diagnostics=diagnostics,
        provenance=normalize_provenance(request.provenance),
        inputs_hash=compute_inputs_hash(request),
    )
