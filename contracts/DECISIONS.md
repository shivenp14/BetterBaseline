# Contracts and Schema Decisions for Better Baseline (API v1)

**Issue:** #63 (`[P0][B1] Freeze Better Baseline API v1 types and resolve contract doc gaps`)
**Status:** Contract revision under review
**Review:** Statistical/frontend review requested from @roland-aranas and @shivenp14; this revision must be reviewed before freeze.

## 1. Domain Types and Decisions

1. **Fraction-Valued Probabilities:**
   - All probabilities (`control_event_rate`, `dropout`, `alpha`, `target_power`, etc.) are decimal fractions in `(0, 1)`, never percentages (e.g. `0.20`, not `20`).
2. **Equal 1:1 Enrollment in MVP:**
   - `allocation_ratio` must equal `1.0`. Non-1.0 ratios are rejected with structured validation errors.
3. **Symmetric P0 Dropout:**
   - Planned and stress dropout rates are represented by equal control/treatment floats in `[0, 1)`; asymmetric values are rejected.
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

14. **Zero Expected Retention:**
   - Positive enrollment uses `ArmCounts`; floored expected retention uses strict, equal, nonnegative `ExpectedRetainedCounts`.
   - `assumed_evaluable_n` is exactly `floor(fixed_enrollment * (1 - stress_dropout))` per arm, never a sampled Monte Carlo count.
   - At zero expected retention, `conditional_power_approx` is `null` and the endpoint includes an unavailable-analytic warning. Monte Carlo still samples actual retained counts; undefined tests are nonrejections over all replicates and included in `invalid_test_fraction`.
   - At positive expected retention, `conditional_power_approx` is a finite fraction in `[0, 1]`.
15. **Worst-Case Grid Summary:**
   - `worst_case_power` is required to contain the minimum over valid grid cells (comparison tolerance `1e-4`); it is `null` exactly when no valid cells exist.
   - Contour segments follow `target_power` and never bridge invalid cells; 80% is only the default/demo target.
   - Grid points and power-curve entries carry numeric `power` exactly when `is_valid` is true; invalid entries carry `null`.
16. **Canonical Planning Documentation:**
   - The three planning docs use Better Baseline naming and these canonical API fields. A/B/C/D denote task categories; live issue assignees and recorded file handoffs determine ownership.
   - JSON Schema describes structural types and scalar constraints; Pydantic validators additionally enforce cross-field/domain invariants such as equal arms and grid summary consistency.
17. **Provenance Audit Metadata and Origin Integrity (Issue #67):**
   - `FieldProvenance` preserves optional audit fields (`source_location`, `verified_by_user`, and `is_observed_registry_result`) across normalization and serialized `ExportPayload` outputs.
   - Full JSON pointers (e.g. `/planned_design/control_event_rate` vs `/stress_scenario/control_event_rate`) are retained as unique map keys without lossy path stripping.
   - Observed registry records (`clinicaltrials_registry` or with `is_observed_registry_result: true`) cannot be relabeled as `protocol_curated` planning assumptions.
