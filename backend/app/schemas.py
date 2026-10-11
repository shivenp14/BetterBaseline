"""Pydantic v2 schemas for Better Baseline API v1 contracts.

Provides strongly typed models for:
- Trial assumptions and effects (RR, ARR)
- Design calculation request/response
- Scenario evaluation request/response (with separate MCSEs)
- Sensitivity grid request/response (with point/frontier structures and invalid masks)
- Standardized error envelopes and provenance tracking
"""

from typing import Annotated, Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, model_validator

# ── DOMAIN PRIMITIVES ──

ModelVersion = Literal["binary-v1"]
EffectKind = Literal["relative_risk", "absolute_risk_reduction"]
AnalyticalMethod = Literal["cohen_h_normal_v1"]
SimulationMethod = Literal["pooled_two_proportion_z_v1"]


class RelativeRiskEffect(BaseModel):
    kind: Literal["relative_risk"] = "relative_risk"
    value: Annotated[float, Field(gt=0.0, lt=1.0, description="Relative risk ratio (0, 1)")]


class AbsoluteRiskReductionEffect(BaseModel):
    kind: Literal["absolute_risk_reduction"] = "absolute_risk_reduction"
    value: Annotated[float, Field(gt=0.0, lt=1.0, description="Absolute risk reduction (0, 1)")]


Effect = Annotated[Union[RelativeRiskEffect, AbsoluteRiskReductionEffect], Field(discriminator="kind")]


class ArmProportions(BaseModel):
    control: Annotated[float, Field(ge=0.0, lt=1.0, description="Control arm rate")]
    treatment: Annotated[float, Field(ge=0.0, lt=1.0, description="Treatment arm rate")]


class ArmCounts(BaseModel):
    control: Annotated[int, Field(ge=1, description="Control arm count")]
    treatment: Annotated[int, Field(ge=1, description="Treatment arm count")]


class TrialAssumptions(BaseModel):
    model_version: ModelVersion = "binary-v1"
    control_event_rate: Annotated[float, Field(gt=0.0, lt=1.0, description="Baseline control event probability")]
    effect: Effect
    alpha: Annotated[float, Field(gt=0.0, lt=1.0, default=0.05, description="Significance level")]
    target_power: Annotated[float, Field(gt=0.0, lt=1.0, default=0.80, description="Target statistical power")]
    allocation_ratio: Annotated[float, Field(default=1.0, description="Allocation ratio (MVP: 1.0)")]
    dropout: ArmProportions = Field(default_factory=lambda: ArmProportions(control=0.0, treatment=0.0))

    @model_validator(mode="after")
    def validate_assumptions(self) -> "TrialAssumptions":
        if self.allocation_ratio != 1.0:
            raise ValueError("allocation_ratio must be 1.0 in MVP")
        if self.target_power <= self.alpha:
            raise ValueError("target_power must be strictly greater than alpha")
        if self.effect.kind == "absolute_risk_reduction" and self.effect.value >= self.control_event_rate:
            raise ValueError(
                f"ARR {self.effect.value} cannot equal or exceed control_event_rate {self.control_event_rate}"
            )
        return self


class StressScenario(BaseModel):
    control_event_rate: Annotated[float, Field(gt=0.0, lt=1.0, description="Hypothetical true control rate")]
    dropout: ArmProportions = Field(default_factory=lambda: ArmProportions(control=0.0, treatment=0.0))
    effect_override: Optional[Effect] = Field(default=None, description="Optional effect override")


class SimulationOptions(BaseModel):
    replicates: Annotated[int, Field(ge=100, le=50_000, default=10_000, description="Replication count")]
    seed: Optional[int] = Field(default=42, description="Random seed for reproducibility")


# ── REQUEST & RESPONSE CONTRACTS ──

# 1. POST /api/v1/design/calculate
class DesignCalculateRequest(TrialAssumptions):
    pass


class DesignCalculateResponse(BaseModel):
    model_version: ModelVersion = "binary-v1"
    method: AnalyticalMethod = "cohen_h_normal_v1"
    p_treatment: float = Field(gt=0.0, lt=1.0)
    evaluable_n: ArmCounts
    enrolled_n: ArmCounts
    nominal_power_evaluable: float = Field(ge=0.0, le=1.0)
    warnings: List[str] = Field(default_factory=list)
    inputs_hash: str


# 2. POST /api/v1/scenarios/evaluate
class ScenarioEvaluateRequest(BaseModel):
    planned_design: TrialAssumptions
    fixed_enrollment: ArmCounts
    stress_scenario: StressScenario
    simulation: SimulationOptions = Field(default_factory=SimulationOptions)

    @model_validator(mode="after")
    def validate_scenario(self) -> "ScenarioEvaluateRequest":
        eff = self.stress_scenario.effect_override or self.planned_design.effect
        pc = self.stress_scenario.control_event_rate
        if eff.kind == "absolute_risk_reduction" and eff.value >= pc:
            raise ValueError(
                f"Invalid ARR: value {eff.value} must be strictly less than stressed control rate {pc}"
            )
        return self


class AnalyticEvaluation(BaseModel):
    method: AnalyticalMethod = "cohen_h_normal_v1"
    conditional_power_approx: float = Field(ge=0.0, le=1.0)
    assumed_evaluable_n: ArmCounts


class MonteCarloEvaluation(BaseModel):
    method: SimulationMethod = "pooled_two_proportion_z_v1"
    significant_two_sided_fraction: float = Field(ge=0.0, le=1.0)
    significant_favorable_fraction: float = Field(ge=0.0, le=1.0)
    mcse_two_sided: float = Field(ge=0.0)
    mcse_favorable: float = Field(ge=0.0)
    invalid_test_fraction: float = Field(ge=0.0, le=1.0)
    replicates: int = Field(ge=100)
    seed: Optional[int] = None


class ScenarioMetadata(BaseModel):
    computed_at: str
    inputs_hash: str


class ScenarioEvaluateResponse(BaseModel):
    model_version: ModelVersion = "binary-v1"
    analytic: AnalyticEvaluation
    monte_carlo: MonteCarloEvaluation
    warnings: List[str] = Field(default_factory=list)
    metadata: ScenarioMetadata


# 3. POST /api/v1/scenarios/grid
class GridAxisSpec(BaseModel):
    min: Annotated[float, Field(gt=0.0, lt=1.0)]
    max: Annotated[float, Field(gt=0.0, lt=1.0)]
    steps: Annotated[int, Field(ge=2, le=81)]

    @model_validator(mode="after")
    def validate_range(self) -> "GridAxisSpec":
        if self.min >= self.max:
            raise ValueError("Axis min must be strictly less than max")
        return self


class GridDropoutAxisSpec(BaseModel):
    min: Annotated[float, Field(ge=0.0, lt=1.0, default=0.0)]
    max: Annotated[float, Field(ge=0.0, lt=1.0, default=0.30)]
    steps: Annotated[int, Field(ge=2, le=61, default=10)]

    @model_validator(mode="after")
    def validate_range(self) -> "GridDropoutAxisSpec":
        if self.min >= self.max:
            raise ValueError("Dropout axis min must be strictly less than max")
        return self


class ScenarioGridRequest(BaseModel):
    planned_design: TrialAssumptions
    fixed_enrollment: ArmCounts
    x_baseline: GridAxisSpec = Field(
        default_factory=lambda: GridAxisSpec(min=0.05, max=0.30, steps=15)
    )
    y_dropout: GridDropoutAxisSpec = Field(
        default_factory=lambda: GridDropoutAxisSpec(min=0.0, max=0.30, steps=10)
    )
    effect_override: Optional[Effect] = None


class GridPoint(BaseModel):
    p_control: float
    dropout: float
    power: Optional[float] = None
    is_safe: bool = False
    is_valid: bool = True


class ScenarioGridResponse(BaseModel):
    model_version: ModelVersion = "binary-v1"
    method: AnalyticalMethod = "cohen_h_normal_v1"
    x_baseline: List[float]
    y_dropout: List[float]
    power: List[List[Optional[float]]]  # [dropout_index][baseline_index]
    invalid_mask: List[List[bool]]     # [dropout_index][baseline_index]
    target_power: float
    planned_point: GridPoint
    selected_point: Optional[GridPoint] = None
    frontier_points: List[GridPoint] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    computed_at: str
    inputs_hash: str


# 4. Standard Error Envelope
class ErrorDetail(BaseModel):
    code: str
    message: str
    field: Optional[str] = None
    recoverable: bool = True


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


# 5. Provenance tracking
SourceTag = Literal[
    "manual_user",
    "synthetic_preset",
    "protocol_curated",
    "clinicaltrials_registry",
]


class FieldProvenance(BaseModel):
    source: SourceTag
    description: Optional[str] = None
    retrieved_at: Optional[str] = None
    source_url: Optional[str] = None


class ExportPayload(BaseModel):
    export_schema_version: int = 1
    model_version: ModelVersion = "binary-v1"
    planned_design: TrialAssumptions
    fixed_enrollment: ArmCounts
    stress_scenario: Optional[StressScenario] = None
    evaluation_result: Optional[ScenarioEvaluateResponse] = None
    provenance: Dict[str, FieldProvenance] = Field(default_factory=dict)
    exported_at: str
