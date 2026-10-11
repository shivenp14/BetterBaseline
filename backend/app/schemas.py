"""Pydantic v2 schemas for Better Baseline API v1 contracts.

Provides strongly typed models for:
- Trial assumptions and effects (RR, ARR)
- Design calculation request/response
- Scenario evaluation request/response (with separate MCSEs)
- Sensitivity grid request/response (with contour segments, power curve, and invalid masks)
- Standardized error envelopes and provenance tracking
"""

import math
from typing import Annotated, Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator

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

    @model_validator(mode="after")
    def validate_symmetric(self) -> "ArmProportions":
        if self.control != self.treatment:
            raise ValueError(
                f"Symmetric dropout required in P0 MVP: control ({self.control}) != treatment ({self.treatment})"
            )
        return self


class ArmCounts(BaseModel):
    control: Annotated[int, Field(strict=True, ge=1, description="Control arm count")]
    treatment: Annotated[int, Field(strict=True, ge=1, description="Treatment arm count")]

    @model_validator(mode="after")
    def validate_equal(self) -> "ArmCounts":
        if self.control != self.treatment:
            raise ValueError(
                f"Equal 1:1 enrollment required in P0 MVP: control ({self.control}) != treatment ({self.treatment})"
            )
        return self



class ExpectedRetainedCounts(BaseModel):
    """Floored expected retention, distinct from positive enrollment counts."""

    control: int = Field(strict=True, ge=0)
    treatment: int = Field(strict=True, ge=0)

    @model_validator(mode="after")
    def validate_equal(self) -> "ExpectedRetainedCounts":
        if self.control != self.treatment:
            raise ValueError("Equal expected retention required in P0 MVP")
        return self


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
    seed: Optional[int] = Field(default=42, ge=0, le=2**32 - 1, description="Random seed for reproducibility")


# ── REQUEST & RESPONSE CONTRACTS ──

# 1. POST /api/v1/design/calculate
class DesignCalculateRequest(TrialAssumptions):
    pass


class DesignCalculateResponse(BaseModel):
    model_version: ModelVersion = "binary-v1"
    method: AnalyticalMethod = "cohen_h_normal_v1"
    p_treatment: float = Field(gt=0.0, lt=1.0, allow_inf_nan=False)
    evaluable_n: ArmCounts
    enrolled_n: ArmCounts
    nominal_power_evaluable: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
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
    conditional_power_approx: Optional[float] = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    assumed_evaluable_n: ExpectedRetainedCounts

    @model_validator(mode="after")
    def validate_power_availability(self) -> "AnalyticEvaluation":
        if (self.assumed_evaluable_n.control == 0) != (self.conditional_power_approx is None):
            raise ValueError("Analytic power must be null exactly when expected retention is zero")
        return self


class MonteCarloEvaluation(BaseModel):
    method: SimulationMethod = "pooled_two_proportion_z_v1"
    significant_two_sided_fraction: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    significant_favorable_fraction: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    mcse_two_sided: float = Field(ge=0.0, allow_inf_nan=False)
    mcse_favorable: float = Field(ge=0.0, allow_inf_nan=False)
    invalid_test_fraction: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    replicates: int = Field(ge=100)
    seed: Optional[int] = Field(default=None, ge=0, le=2**32 - 1)


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
    """Request for generating the 2D power grid surface and 1D power curve.

    The power curve slices analytic power across x_baseline holding dropout fixed
    at selected_scenario.dropout (or 0.0 if omitted). Each curve point uses floored
    expected retention floor(enrolled_n * (1 - dropout)) and the effective effect.
    """
    planned_design: TrialAssumptions
    fixed_enrollment: ArmCounts
    x_baseline: GridAxisSpec = Field(
        default_factory=lambda: GridAxisSpec(min=0.05, max=0.30, steps=15)
    )
    y_dropout: GridDropoutAxisSpec = Field(
        default_factory=lambda: GridDropoutAxisSpec(min=0.0, max=0.30, steps=10)
    )
    effect_override: Optional[Effect] = None
    selected_scenario: Optional[StressScenario] = Field(
        default=None,
        description="Selected stress scenario providing the selected baseline risk and dropout level for selected_point and power_curve",
    )

    @model_validator(mode="after")
    def validate_effect_consistency(self) -> "ScenarioGridRequest":
        if self.effect_override and self.selected_scenario and self.selected_scenario.effect_override:
            if (
                self.effect_override.kind != self.selected_scenario.effect_override.kind
                or self.effect_override.value != self.selected_scenario.effect_override.value
            ):
                raise ValueError(
                    "Conflicting effect_override: top-level effect_override and "
                    "selected_scenario.effect_override must not conflict."
                )
        return self

    @property
    def effective_grid_effect(self) -> Effect:
        """Effective effect for computing the 2D grid matrix and 1D power curve."""
        return (
            self.effect_override
            or (self.selected_scenario.effect_override if self.selected_scenario else None)
            or self.planned_design.effect
        )


class GridPoint(BaseModel):
    p_control: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    dropout: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    power: Optional[float] = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    is_safe: bool = False
    is_valid: bool = True


class ContourPoint(BaseModel):
    p_control: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    dropout: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)


class ContourSegment(BaseModel):
    start: ContourPoint
    end: ContourPoint


class PowerCurvePoint(BaseModel):
    p_control: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    power: Optional[float] = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    is_valid: bool = True


class ScenarioGridResponse(BaseModel):
    model_version: ModelVersion = "binary-v1"
    method: AnalyticalMethod = "cohen_h_normal_v1"
    x_baseline: List[float]
    y_dropout: List[float]
    power: List[List[Optional[float]]]  # [dropout_index][baseline_index]
    invalid_mask: List[List[bool]]     # [dropout_index][baseline_index]
    target_power: float = Field(gt=0.0, lt=1.0, allow_inf_nan=False)
    planned_point: GridPoint
    selected_point: Optional[GridPoint] = None
    frontier_points: List[GridPoint] = Field(default_factory=list)
    contour_segments: List[ContourSegment] = Field(default_factory=list)
    power_curve: List[PowerCurvePoint] = Field(default_factory=list)
    invalid_cell_count: int = Field(ge=0)
    worst_case_power: Optional[float] = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    warnings: List[str] = Field(default_factory=list)
    computed_at: str
    inputs_hash: str

    @field_validator("x_baseline", "y_dropout", mode="after")
    @classmethod
    def validate_finite_axis(cls, v: List[float]) -> List[float]:
        for val in v:
            if not math.isfinite(val):
                raise ValueError(f"Axis values must be finite numbers, got {val}")
        return v


    @model_validator(mode="after")
    def validate_grid_matrix(self) -> "ScenarioGridResponse":
        n_dropouts = len(self.y_dropout)
        n_baselines = len(self.x_baseline)

        if len(self.power) != n_dropouts:
            raise ValueError(f"power matrix outer dimension ({len(self.power)}) != y_dropout length ({n_dropouts})")
        if len(self.invalid_mask) != n_dropouts:
            raise ValueError(f"invalid_mask outer dimension ({len(self.invalid_mask)}) != y_dropout length ({n_dropouts})")

        computed_invalid_count = 0
        powers: List[float] = []

        for r_idx in range(n_dropouts):
            row_p = self.power[r_idx]
            row_m = self.invalid_mask[r_idx]
            if len(row_p) != n_baselines:
                raise ValueError(
                    f"power row {r_idx} length ({len(row_p)}) != x_baseline length ({n_baselines})"
                )
            if len(row_m) != n_baselines:
                raise ValueError(
                    f"invalid_mask row {r_idx} length ({len(row_m)}) != x_baseline length ({n_baselines})"
                )
            for c_idx in range(n_baselines):
                val = row_p[c_idx]
                mask = row_m[c_idx]
                if mask:
                    computed_invalid_count += 1
                    if val is not None:
                        raise ValueError(f"Cell at ({r_idx}, {c_idx}) has mask=True but power is not None ({val})")
                else:
                    if val is None or math.isnan(val) or not (0.0 <= val <= 1.0):
                        raise ValueError(
                            f"Cell at ({r_idx}, {c_idx}) has mask=False but power is invalid ({val})"
                        )
                    powers.append(val)

        if self.invalid_cell_count != computed_invalid_count:
            raise ValueError(
                f"invalid_cell_count ({self.invalid_cell_count}) does not match masked cell count ({computed_invalid_count})"
            )

        if powers:
            min_power = min(powers)
            if self.worst_case_power is None or abs(self.worst_case_power - min_power) > 1e-4:
                raise ValueError(
                    f"worst_case_power ({self.worst_case_power}) does not match minimum valid power ({min_power})"
                )
        elif self.worst_case_power is not None:
            raise ValueError("worst_case_power must be null when no valid cells exist")
        return self


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
    design_result: Optional[DesignCalculateResponse] = None
    evaluation_result: Optional[ScenarioEvaluateResponse] = None
    grid_result: Optional[ScenarioGridResponse] = None
    software_versions: Dict[str, str] = Field(
        default_factory=dict,
        description="Software and package versions for reproducible calculation",
    )
    provenance: Dict[str, FieldProvenance] = Field(default_factory=dict)
    exported_at: str
