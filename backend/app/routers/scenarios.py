"""Fixed-enrollment evaluation endpoint owned by #65.

Typed extensions of the shared #63 models preserve #65's optional simulation,
strict 1..100,000 replicate options, sampled count aggregates and reproducibility
metadata. Shared schema/export owners must carry these extensions through export;
this router does not change their files. The #68 compute wrapper is the stable
seam for later concurrency/cache policy, including computed-at preservation.
"""
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import platform
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import ConfigDict, Field

from ..cache import make_cache_key
from ..data.provenance import normalize_provenance
from ..schemas import (
    AnalyticEvaluation, ArmCounts, ErrorEnvelope, ExpectedRetainedCounts,
    FieldProvenance, MonteCarloEvaluation, ScenarioEvaluateRequest,
    ScenarioEvaluateResponse, ScenarioMetadata, SimulationOptions,
)
from ..services.compute import ComputeResourceGuard, execute_guarded_computation
from ..statistics.analytic import analytic_power
from ..statistics.diagnostics import analytic_diagnostics, simulation_diagnostics
from ..statistics.effect import resolve_treatment_risk
from ..statistics.errors import StatisticalInputError
from ..statistics.inputs import Effect, expected_retained_count
from ..statistics.simulation import MAX_ENROLLED_PER_ARM, simulate_binary


class EvaluationSimulationOptions(SimulationOptions):
    replicates: int = Field(default=10_000, strict=True, ge=1, le=100_000)
    seed: int = Field(default=42, strict=True, ge=0, le=2**32 - 1)
    model_config = ConfigDict(extra='forbid')


class EvaluationRequest(ScenarioEvaluateRequest):
    simulation: EvaluationSimulationOptions | None = Field(default_factory=EvaluationSimulationOptions)
    provenance: dict[str, FieldProvenance] = Field(default_factory=dict)
    model_config = ConfigDict(extra='forbid')


class EvaluationMonteCarlo(MonteCarloEvaluation):
    replicates: int = Field(strict=True, ge=1, le=100_000)
    seed: int = Field(strict=True, ge=0, le=2**32 - 1)
    invalid_test_policy: Literal['nonrejection_over_all_replicates']
    mean_retained_control: float = Field(ge=0, allow_inf_nan=False)
    mean_retained_treatment: float = Field(ge=0, allow_inf_nan=False)
    mean_control_events: float = Field(ge=0, allow_inf_nan=False)
    mean_treatment_events: float = Field(ge=0, allow_inf_nan=False)
    rng: str
    software_versions: dict[str, str]


class EvaluationMetadata(ScenarioMetadata):
    software_versions: dict[str, str]
    fixed_enrollment: ArmCounts


class EvaluationResponse(ScenarioEvaluateResponse):
    monte_carlo: EvaluationMonteCarlo | None
    metadata: EvaluationMetadata
    provenance: dict[str, FieldProvenance]


router = APIRouter(
    prefix='/api/v1/scenarios', tags=['scenarios'],
    responses={
        422: {'model': ErrorEnvelope, 'description': 'Validation Error'},
        413: {'model': ErrorEnvelope, 'description': 'Payload Too Large'},
        429: {
            'model': ErrorEnvelope,
            'description': 'Compute Resource Saturated',
            'headers': {
                'Retry-After': {
                    'description': 'Seconds to wait before retrying.',
                    'schema': {'type': 'integer'},
                }
            },
        },
    },
)


def _evaluate(request: EvaluationRequest, guard: ComputeResourceGuard) -> EvaluationResponse:
    enrollment = request.fixed_enrollment
    guard.check_enrollment(enrollment.control, enrollment.treatment)
    for arm in ('control', 'treatment'):
        if getattr(enrollment, arm) > MAX_ENROLLED_PER_ARM:
            raise StatisticalInputError(
                f'Enrollment exceeds {MAX_ENROLLED_PER_ARM} per arm',
                field=f'fixed_enrollment.{arm}', code='RESOURCE_LIMIT',
            )
    if request.simulation is not None:
        guard.check_simulation_options(request.simulation.replicates, request.simulation.seed)

    stress = request.stress_scenario
    effect = stress.effect_override or request.planned_design.effect
    p_control = stress.control_event_rate
    p_treatment = resolve_treatment_risk(p_control, Effect(effect.kind, effect.value))
    counts = ExpectedRetainedCounts(
        control=expected_retained_count(enrollment.control, stress.dropout.control),
        treatment=expected_retained_count(enrollment.treatment, stress.dropout.treatment),
    )
    diagnostics = analytic_diagnostics(p_control, p_treatment, counts.control,
                                       counts.treatment, request.planned_design.alpha)
    diagnostic_records = list(diagnostics['diagnostics'])
    warnings = [item['message'] for item in diagnostic_records]
    power = None
    if counts.control:
        power = analytic_power(p_control, p_treatment, counts.control, counts.treatment,
                               request.planned_design.alpha).power
    warnings.append('Analytic counts are floored expected retention, not actual simulated retained counts.')
    mc = None
    if request.simulation is not None:
        simulated = simulate_binary(
            enrollment.control, enrollment.treatment, p_control, p_treatment,
            stress.dropout.control, stress.dropout.treatment,
            alpha=request.planned_design.alpha, reps=request.simulation.replicates,
            seed=request.simulation.seed,
        )
        mc = EvaluationMonteCarlo.model_validate(simulated)
        warnings.extend(simulated['warnings'])
        simulated_diagnostics = simulation_diagnostics(
            enrollment.control, enrollment.treatment, p_control, p_treatment,
            stress.dropout.control, stress.dropout.treatment,
            alpha=request.planned_design.alpha,
            invalid_test_fraction=simulated['invalid_test_fraction'],
            replicates=simulated['replicates'],
        )
        diagnostic_records.extend(simulated_diagnostics['diagnostics'])
    versions = {'python': platform.python_version(),
                **{package: version(package) for package in ('numpy', 'scipy', 'statsmodels')}}
    canonical = json.dumps(request.model_dump(mode='json'), sort_keys=True,
                           separators=(',', ':'), allow_nan=False)
    return EvaluationResponse(
        model_version='binary-v1',
        analytic=AnalyticEvaluation(method='cohen_h_normal_v1', conditional_power_approx=power,
                                    assumed_evaluable_n=counts),
        monte_carlo=mc, warnings=list(dict.fromkeys(warnings)),
        diagnostics=diagnostic_records,
        metadata=EvaluationMetadata(
            computed_at=datetime.now(timezone.utc).isoformat(),
            inputs_hash='sha256:' + hashlib.sha256(canonical.encode()).hexdigest(),
            software_versions=versions, fixed_enrollment=enrollment.model_copy(deep=True),
        ),
        provenance=normalize_provenance(request.provenance),
    )


@router.post('/evaluate', response_model=EvaluationResponse)
def evaluate_scenario(request: EvaluationRequest, http_request: Request) -> EvaluationResponse:
    """Evaluate stressed reality without solving or modifying planned enrollment."""
    cache_key = make_cache_key(
        route='/api/v1/scenarios/evaluate',
        model_version='binary-v1',
        params=request,
    )
    guard = http_request.app.state.compute_guard
    return execute_guarded_computation(_evaluate, request, guard, cache_key=cache_key, guard=guard)
