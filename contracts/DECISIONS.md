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
