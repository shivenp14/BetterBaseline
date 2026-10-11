# Contracts and Schema Decisions for Better Baseline (API v1)

**Issue:** #63 (`[P0][B1] Freeze Better Baseline API v1 types and resolve contract doc gaps`)  
**Status:** Approved & Frozen  
**Collaborators & Signoffs:** Statistical & frontend signoff by @roland-aranas, @shivenp14, @dersual.

## 1. Domain Types and Decisions

1. **Fraction-Valued Probabilities:**
   - All probabilities (`control_event_rate`, `dropout`, `alpha`, `target_power`, etc.) are decimal fractions in `(0, 1)`, never percentages (e.g. `0.20`, not `20`).
2. **Equal 1:1 Enrollment in MVP:**
   - `allocation_ratio` must equal `1.0`. Non-1.0 ratios are rejected with structured validation errors.
3. **Symmetric P0 Dropout:**
   - Planned and stress dropout rates are validated as arm-specific floats in `[0, 1)`.
4. **Separation of Planned Design vs. Stress Scenario:**
   - `planned_design` establishes the immutable planned benchmark.
   - `fixed_enrollment` is frozen and passed explicitly into `scenarios/evaluate` and `scenarios/grid` so changing stress controls never silently recalculates $N$.
5. **Distinct Monte Carlo Standard Errors:**
   - `mcse_two_sided` and `mcse_favorable` are reported as distinct fields, along with separate `significant_two_sided_fraction` and `significant_favorable_fraction`.
6. **Heatmap Grid Matrix Orientation:**
   - `power` matrix is shaped `[dropout_index][baseline_index]` with a matching `invalid_mask[dropout_index][baseline_index]`. Invalid cells contain `null`, not zero power.
7. **Invalid ARR Handling:**
   - In `/api/v1/scenarios/evaluate`, an invalid ARR scenario ($ARR \ge p_C$) returns a structured 422 error.
   - In `/api/v1/scenarios/grid`, points where $ARR \ge p_C$ are marked `is_valid: false`, `power: null`, and set to `true` in `invalid_mask` without failing the request.
8. **Provenance Tracking:**
   - Source provenance tags (`manual_user`, `synthetic_preset`, `protocol_curated`, `clinicaltrials_registry`) are preserved through `ExportPayload` with `export_schema_version = 1`.
9. **Strict Integer Participant Counts:**
   - `ArmCounts` uses strict integer fields (`strict=True`), rejecting string coercion (`"903"`), floats (`903.0`), and boolean flags (`True`).
10. **Finite Floating-Point Enforcement:**
   - Response models (including MCSE, axis specs, and power outputs) disallow `NaN` and infinity (`allow_inf_nan=False`), preventing illegal null serialization.
11. **Grid Selected Stress Scenario & Power Curve Semantics:**
   - `ScenarioGridRequest` accepts an optional `selected_scenario: StressScenario` to determine `selected_point` and fix the dropout slice for `power_curve`.
   - `power_curve` evaluates analytic power across `x_baseline` at the selected dropout using floored expected retention $\lfloor N \times (1 - \text{dropout}) \rfloor$.
12. **Development & Test Dependencies:**
   - Test execution requires the `dev` extra declared in `backend/pyproject.toml`.
   - Install command: `pip install -e ".[dev]"` (includes `pytest>=8.0.0` and `jsonschema>=4.20.0`).
13. **Grid Effect Precedence & Full Export Reproducibility:**
   - In `ScenarioGridRequest`, top-level `effect_override` and `selected_scenario.effect_override` must not specify conflicting values. If both are specified with different values, validation fails with `INVALID_MODEL_INPUT`. Precedence resolves via `effective_grid_effect` (`effect_override` or `selected_scenario.effect_override` or `planned_design.effect`).
   - `ExportPayload` contains typed fields for all displayed calculation results (`design_result: Optional[DesignCalculateResponse]`, `grid_result: Optional[ScenarioGridResponse]`) alongside `evaluation_result`.
   - Software and package versions are captured in `software_versions: Dict[str, str]` (e.g. `python`, `numpy`, `scipy`, `statsmodels`, `betterbaseline`) to ensure full auditability and reproduction of exports.
