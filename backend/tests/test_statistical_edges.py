"""Numerical edge cases, sample-size ceiling behavior, and stress boundaries.

Validates issue #60 (A5 core hardening) requirements:
1. Solver bracketing in the final power-of-two bracket up to MAX_EVALUABLE_PER_ARM,
   finite custom ceilings, integer minimality, and infeasibility signaling.
2. Stress grid edge cases: target <= alpha, impossible ARR, expected retained
   counts below 2, non-default target power, valid-cell worst-case power,
   and disconnected/all-invalid contour frontiers that never bridge invalid cells.
3. Vectorized Monte Carlo count semantics and diagnostics: expected retention below 2,
   degenerate standard errors, denominator accounting, and near-boundary probabilities.
"""

import math

import pytest

from app.statistics.analytic import (
    COHEN_H_NORMAL_METHOD,
    COHEN_H_NORMAL_VERSION,
)
from app.statistics.diagnostics import (
    analytic_diagnostics,
    simulation_diagnostics,
)
from app.statistics.errors import StatisticalInputError
from app.statistics.inputs import (
    Effect,
    FixedEnrollment,
)
from app.statistics.sample_size import (
    MAX_EVALUABLE_PER_ARM,
    minimum_sample_size,
)
from app.statistics.simulation import (
    METHOD,
    simulate_binary,
)
from app.statistics.stress_grid import (
    GridCoordinate,
    stress_grid,
)


# ============================================================================
# 1. Sample Size Solver, Ceiling Bracketing, and Boundary Validation
# ============================================================================

class TestSampleSizeSolverEdges:
    """Exercise solver bracketing, custom ceilings, and feasibility boundaries."""

    def test_solver_brackets_final_power_of_two_interval_up_to_max_ceiling(self):
        """Exercise the clamped doubling bracket between 2^19 (524,288) and 1,000,000."""
        # p_c=0.20 and p_t=0.1982 at alpha=0.05 and target=0.80 requires N=772,573.
        # This falls in the final clamped interval [524,288, 1,000,000].
        p_c = 0.20
        p_t = 0.1982
        res = minimum_sample_size(
            p_c,
            p_t,
            target_power=0.80,
            alpha=0.05,
            max_evaluable_per_arm=MAX_EVALUABLE_PER_ARM,
        )

        assert 524_288 < res.evaluable_per_arm <= MAX_EVALUABLE_PER_ARM
        assert res.evaluable_per_arm == 772_573
        assert res.max_evaluable_per_arm == MAX_EVALUABLE_PER_ARM

        # Integer minimality: n meets target, n - 1 falls short
        assert res.achieved_power >= 0.80
        assert res.power_at_previous_n is not None
        assert res.power_at_previous_n < 0.80
        assert res.method == COHEN_H_NORMAL_METHOD
        assert res.method_version == COHEN_H_NORMAL_VERSION

    def test_custom_ceiling_feasibility_boundary(self):
        """A solution exactly at ceiling is feasible; ceiling below is infeasible."""
        p_c = 0.20
        p_t = 0.1982
        exact_n = 772_573

        feasible = minimum_sample_size(
            p_c, p_t, target_power=0.80, alpha=0.05, max_evaluable_per_arm=exact_n,
        )
        assert feasible.evaluable_per_arm == exact_n
        assert feasible.achieved_power >= 0.80
        assert feasible.power_at_previous_n < 0.80

        with pytest.raises(StatisticalInputError) as caught:
            minimum_sample_size(
                p_c, p_t, target_power=0.80, alpha=0.05, max_evaluable_per_arm=exact_n - 1,
            )
        assert caught.value.code == "UNBOUNDED_OR_INFEASIBLE"
        assert caught.value.field == "max_evaluable_per_arm"

    def test_effect_exceeding_max_evaluable_per_arm_raises_infeasible_code(self):
        """Microscopic effect requiring N > 1,000,000 raises UNBOUNDED_OR_INFEASIBLE."""
        p_c = 0.20
        p_t = 0.19999
        with pytest.raises(StatisticalInputError) as caught:
            minimum_sample_size(
                p_c,
                p_t,
                target_power=0.80,
                alpha=0.05,
                max_evaluable_per_arm=MAX_EVALUABLE_PER_ARM,
            )
        assert caught.value.code == "UNBOUNDED_OR_INFEASIBLE"
        assert caught.value.field == "max_evaluable_per_arm"

    @pytest.mark.parametrize(
        "target,alpha",
        [
            (0.05, 0.05),
            (0.04, 0.05),
            (0.01, 0.05),
            (0.50, 0.50),
        ],
    )
    def test_target_power_less_than_or_equal_to_alpha_rejected(self, target, alpha):
        """Target power <= alpha cannot define a valid power-seeking sample size."""
        with pytest.raises(StatisticalInputError) as caught:
            minimum_sample_size(0.20, 0.15, target_power=target, alpha=alpha)
        assert caught.value.field == "target_power"
        assert "greater than alpha" in str(caught.value)

    def test_null_effect_infeasible_code(self):
        """Identical event rates cannot reach power > alpha at any finite N."""
        with pytest.raises(StatisticalInputError) as caught:
            minimum_sample_size(0.35, 0.35, target_power=0.80, alpha=0.05)
        assert caught.value.code == "UNBOUNDED_OR_INFEASIBLE"
        assert caught.value.field == "p_treatment"


# ============================================================================
# 2. Stress Domain & Grid Edge Conditions
# ============================================================================

class TestStressGridEdges:
    """Exercise grid evaluations on invalid domains, ARR boundaries, and small retention."""

    def test_impossible_arr_yields_invalid_mask_and_null_power_not_zero(self):
        """When baseline <= ARR, the cell carries None with reason INVALID_EFFECT_AT_BASELINE."""
        enrollment = FixedEnrollment(500, 500)
        effect = Effect("absolute_risk_reduction", 0.15)
        # Baselines: 0.10 (0.15 >= 0.10, invalid), 0.20 (valid), 0.30 (valid)
        res = stress_grid(
            enrollment,
            effect,
            baselines=[0.10, 0.20, 0.30],
            dropout_rates=[0.0, 0.10],
            planned_point=GridCoordinate(0.20, 0.0),
            selected_point=GridCoordinate(0.20, 0.0),
        )

        for row_idx in range(len(res.y_dropout)):
            assert res.invalid_mask[row_idx][0] is True
            assert res.power[row_idx][0] is None
            assert res.below_target[row_idx][0] is None

            assert res.invalid_mask[row_idx][1] is False
            assert res.power[row_idx][1] is not None
            assert 0.0 < res.power[row_idx][1] < 1.0

        assert res.selected_point.power is not None
        assert res.invalid_cell_count == 2
        # Worst-case power evaluates strictly over valid cells, never fabricating zero
        valid_powers = [
            res.power[r][c]
            for r in range(len(res.y_dropout))
            for c in range(len(res.x_baseline))
            if res.power[r][c] is not None
        ]
        assert len(valid_powers) == 4
        assert res.worst_case_power == min(valid_powers)

    def test_insufficient_expected_retained_counts_yields_insufficient_code(self):
        """When floored expected retention < 2, cell is invalid with INSUFFICIENT_EXPECTED_RETAINED."""
        enrollment = FixedEnrollment(2, 2)
        effect = Effect("relative_risk", 0.75)
        # Dropout 0.60 on enrollment 2 yields floor(2 * 0.40) = 0 retained
        res = stress_grid(
            enrollment,
            effect,
            baselines=[0.20],
            dropout_rates=[0.60],
            planned_point=GridCoordinate(0.20, 0.0),
            selected_point=GridCoordinate(0.20, 0.60),
        )

        cell = res.selected_point
        assert cell.power is None
        assert cell.expected_evaluable_per_arm < 2
        assert cell.invalid_reason == "INSUFFICIENT_EXPECTED_RETAINED"
        assert res.invalid_mask[0][0] is True
        assert res.power[0][0] is None

    def test_all_invalid_grid_frontier_and_worst_case_behavior(self):
        """All-invalid grid returns None worst_case_power, None delta, and empty frontier."""
        enrollment = FixedEnrollment(100, 100)
        effect = Effect("absolute_risk_reduction", 0.35)
        res = stress_grid(
            enrollment,
            effect,
            baselines=[0.10, 0.20, 0.30],
            dropout_rates=[0.0, 0.10],
            planned_point=GridCoordinate(0.40, 0.0),
            selected_point=GridCoordinate(0.40, 0.0),
        )

        assert res.worst_case_power is None
        assert res.analytic_delta is None
        assert res.frontier_points == ()
        assert res.invalid_cell_count == 6
        assert all(all(val is True for val in row) for row in res.invalid_mask)
        assert all(all(val is None for val in row) for row in res.power)
        assert any("All grid cells are invalid" in w for w in res.warnings)

    def test_frontier_terminates_at_invalid_cell_boundary_without_bridging(self):
        """Contour crosses adjacent to invalid cells and terminates on boundary without bridging."""
        # ARR=0.10 renders baseline 0.08 invalid across all dropouts.
        # At baseline 0.17 (adjacent column), power crosses 0.80 between dropout 0.0 (0.815)
        # and dropout 0.10 (0.772), forcing the contour to intersect the vertical seam at baseline 0.17.
        enrollment = FixedEnrollment(165, 165)
        effect = Effect("absolute_risk_reduction", 0.10)
        baselines = [0.08, 0.17, 0.25, 0.35]
        dropouts = [0.0, 0.10, 0.20, 0.30]

        res = stress_grid(
            enrollment,
            effect,
            baselines,
            dropouts,
            planned_point=GridCoordinate(0.25, 0.0),
            selected_point=GridCoordinate(0.25, 0.0),
            target_power=0.80,
        )

        assert res.invalid_cell_count == len(dropouts)
        assert len(res.frontier_points) == 1
        segment = res.frontier_points[0]
        # The contour terminates exactly on the boundary edge baseline=0.17 without bridging into 0.08
        assert segment.points[0].baseline == pytest.approx(0.17)
        assert all(pt.baseline >= 0.17 for pt in segment.points)

    def test_disconnected_frontier_components_across_inflection_and_invalid_domain(self):
        """Variance inflection produces distinct disconnected contour components in valid region."""
        # N=300 with ARR=0.10: baseline 0.05 is invalid.
        # Variance peaks near p=0.50, causing the 0.80 power contour to split into two
        # topologically disjoint components: one in [0.22, 0.32] and one in [0.75, 0.85].
        enrollment = FixedEnrollment(300, 300)
        effect = Effect("absolute_risk_reduction", 0.10)
        baselines = [0.05, 0.15, 0.35, 0.60, 0.85]
        dropouts = [0.0, 0.05, 0.10, 0.20, 0.35]

        res = stress_grid(
            enrollment,
            effect,
            baselines,
            dropouts,
            planned_point=GridCoordinate(0.35, 0.0),
            selected_point=GridCoordinate(0.35, 0.0),
            target_power=0.80,
        )

        assert res.invalid_cell_count == len(dropouts)
        assert len(res.frontier_points) == 2
        comp1, comp2 = res.frontier_points
        # Assert topological separation between the two contour components
        assert max(pt.baseline for pt in comp1.points) < min(pt.baseline for pt in comp2.points)
        assert all(pt.baseline >= 0.15 for pt in comp1.points + comp2.points)

    def test_grid_contours_follow_non_default_target_power(self):
        """Frontier contour shifts with non-default target power."""
        enrollment = FixedEnrollment(903, 903)
        effect = Effect("relative_risk", 0.75)
        baselines = [0.10, 0.15, 0.20, 0.25]
        dropouts = [0.0, 0.05, 0.10, 0.15]

        grid_70 = stress_grid(
            enrollment,
            effect,
            baselines,
            dropouts,
            planned_point=GridCoordinate(0.20, 0.0),
            selected_point=GridCoordinate(0.20, 0.0),
            target_power=0.70,
        )
        grid_90 = stress_grid(
            enrollment,
            effect,
            baselines,
            dropouts,
            planned_point=GridCoordinate(0.20, 0.0),
            selected_point=GridCoordinate(0.20, 0.0),
            target_power=0.90,
        )

        assert grid_70.target_power == 0.70
        assert grid_90.target_power == 0.90
        assert grid_70.frontier_points != grid_90.frontier_points

    def test_grid_rejects_target_power_less_than_or_equal_to_alpha(self):
        """stress_grid raises StatisticalInputError when target_power <= alpha."""
        enrollment = FixedEnrollment(100, 100)
        effect = Effect("relative_risk", 0.75)
        with pytest.raises(StatisticalInputError) as caught:
            stress_grid(
                enrollment,
                effect,
                baselines=[0.20],
                dropout_rates=[0.0],
                planned_point=GridCoordinate(0.20, 0.0),
                selected_point=GridCoordinate(0.20, 0.0),
                alpha=0.05,
                target_power=0.05,
            )
        assert caught.value.field == "target_power"


# ============================================================================
# 3. Vectorized Monte Carlo & Diagnostics Edge Behavior
# ============================================================================

class TestSimulationAndDiagnosticsEdges:
    """Exercise Monte Carlo edge retention, zero variance, and diagnostics warnings."""

    def test_simulation_handles_all_invalid_replicates_without_crash_or_nan(self):
        """Extreme dropout dropping all subjects reports invalid fraction 1.0 without NaN."""
        res = simulate_binary(
            n_c=1,
            n_t=1,
            p_c=0.20,
            p_t=0.15,
            d_c=0.9999,
            d_t=0.9999,
            reps=100,
            seed=42,
        )

        assert res["method"] == METHOD
        assert res["invalid_test_fraction"] == 1.0
        assert res["invalid_test_policy"] == "nonrejection_over_all_replicates"
        assert res["significant_two_sided_fraction"] == 0.0
        assert res["significant_favorable_fraction"] == 0.0
        assert res["mcse_two_sided"] == 0.0
        assert res["mcse_favorable"] == 0.0
        assert not math.isnan(res["mcse_two_sided"])
        assert not math.isnan(res["mcse_favorable"])

        diag = simulation_diagnostics(
            1, 1, 0.20, 0.15, 0.9999, 0.9999,
            invalid_test_fraction=res["invalid_test_fraction"],
            replicates=res["replicates"],
        )
        assert diag["valid"] is True
        codes = [entry["code"] for entry in diag["diagnostics"]]
        assert "ALL_SIMULATED_TESTS_INVALID" in codes

    def test_simulation_count_semantics_when_expected_retention_below_two(self):
        """When expected retention is in (0, 2), simulation still samples and tallies correctly."""
        # N=3 with dropout 0.60 gives expected retention 3 * 0.40 = 1.2 subjects per arm
        reps = 1_000
        res = simulate_binary(
            n_c=3,
            n_t=3,
            p_c=0.25,
            p_t=0.15,
            d_c=0.60,
            d_t=0.60,
            reps=reps,
            seed=42,
        )

        assert 0.0 < res["invalid_test_fraction"] < 1.0
        assert res["invalid_test_policy"] == "nonrejection_over_all_replicates"
        assert 0.0 <= res["mean_retained_control"] <= 3.0
        assert 0.0 <= res["mean_retained_treatment"] <= 3.0
        assert 0.0 <= res["significant_two_sided_fraction"] <= (1.0 - res["invalid_test_fraction"])

    def test_simulation_count_semantics_and_mcse_bounds(self):
        """Simulation fractions obey statistical bounds and MCSE theoretical ceiling."""
        reps = 2_000
        n_c, n_t = 10, 10
        res = simulate_binary(
            n_c=n_c,
            n_t=n_t,
            p_c=0.30,
            p_t=0.20,
            d_c=0.40,
            d_t=0.40,
            reps=reps,
            seed=123,
        )

        assert res["replicates"] == reps
        for field in (
            "significant_two_sided_fraction",
            "significant_favorable_fraction",
            "invalid_test_fraction",
        ):
            val = res[field]
            assert 0.0 <= val <= 1.0
            assert math.isfinite(val)

        # Favorable direction rejection is a subset of two-sided rejection
        assert res["significant_favorable_fraction"] <= res["significant_two_sided_fraction"]
        assert res["significant_two_sided_fraction"] <= (1.0 - res["invalid_test_fraction"] + 1e-9)

        # Binomial MCSE is mathematically bounded by sqrt(0.25 / reps) = 0.5 / sqrt(reps)
        max_possible_mcse = 0.5 / math.sqrt(reps)
        assert 0.0 <= res["mcse_two_sided"] <= max_possible_mcse
        assert 0.0 <= res["mcse_favorable"] <= max_possible_mcse

        assert 0.0 <= res["mean_retained_control"] <= n_c
        assert 0.0 <= res["mean_retained_treatment"] <= n_t
        assert 0.0 <= res["mean_control_events"] <= res["mean_retained_control"]
        assert 0.0 <= res["mean_treatment_events"] <= res["mean_retained_treatment"]

    @pytest.mark.parametrize(
        "p_c,p_t",
        [
            (0.005, 0.002),  # Lower boundary <= 0.01
            (0.995, 0.992),  # Upper boundary >= 0.99
        ],
    )
    def test_near_boundary_probabilities_trigger_diagnostics_warnings(self, p_c, p_t):
        """Both lower (<= 0.01) and upper (>= 0.99) event rates trigger warnings without rejecting."""
        diag_sim = simulation_diagnostics(
            100, 100, p_c, p_t, 0.0, 0.0,
            invalid_test_fraction=0.0, replicates=1000,
        )
        assert diag_sim["valid"] is True
        sim_codes = {d["code"] for d in diag_sim["diagnostics"]}
        assert "NEAR_BOUNDARY_PROBABILITY" in sim_codes

        diag_ana = analytic_diagnostics(p_c, p_t, 100, 100)
        assert diag_ana["valid"] is True
        ana_codes = {d["code"] for d in diag_ana["diagnostics"]}
        assert "NEAR_BOUNDARY_PROBABILITY" in ana_codes
