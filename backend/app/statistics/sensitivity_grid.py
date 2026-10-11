"""Two-dimensional sensitivity grid generator and safety envelope calculation.

Computes a grid of conditional statistical powers across:
- Control event rates p_C (e.g. 0.05 to 0.30)
- Dropout rates d (e.g. 0.00 to 0.30)
at fixed originally planned enrollment N.
Identifies the Assumption Safety Envelope (power >= target_power).
"""

from dataclasses import dataclass
from typing import List, Literal, Optional
import numpy as np
from app.statistics.effect import Effect, calculate_treatment_risk
from app.statistics.power_solver import analytic_power


@dataclass(frozen=True)
class CellResult:
    p_control: float
    p_treatment: Optional[float]
    dropout: float
    effective_n_per_arm: int
    power: Optional[float]
    is_safe: bool
    is_valid: bool
    reason_invalid: Optional[str] = None


@dataclass(frozen=True)
class SensitivityGridResult:
    p_control_steps: List[float]
    dropout_steps: List[float]
    grid: List[List[CellResult]]
    target_power: float
    fixed_n_enrolled_per_arm: int


def generate_stress_grid(
    fixed_n_enrolled_per_arm: int,
    effect: Effect,
    target_power: float = 0.80,
    alpha: float = 0.05,
    p_control_min: float = 0.05,
    p_control_max: float = 0.30,
    p_control_count: int = 15,
    dropout_min: float = 0.0,
    dropout_max: float = 0.30,
    dropout_count: int = 10,
) -> SensitivityGridResult:
    """Generate 2D matrix of conditional powers under fixed planned enrollment.

    Args:
        fixed_n_enrolled_per_arm: Originally frozen enrollment per arm.
        effect: Planned effect assumption (RR or ARR).
        target_power: Power threshold for safety envelope (default: 0.80).
        alpha: Significance level (default: 0.05).
        p_control_min: Lowest control event rate in grid.
        p_control_max: Highest control event rate in grid.
        p_control_count: Number of control rate steps.
        dropout_min: Lowest dropout rate in grid.
        dropout_max: Highest dropout rate in grid.
        dropout_count: Number of dropout steps.

    Returns:
        SensitivityGridResult with full grid and safety envelope flags.
    """
    p_control_vals = [float(x) for x in np.linspace(p_control_min, p_control_max, p_control_count)]
    dropout_vals = [float(x) for x in np.linspace(dropout_min, dropout_max, dropout_count)]

    grid: List[List[CellResult]] = []

    for pc in p_control_vals:
        row: List[CellResult] = []
        for d in dropout_vals:
            # Expected retained / evaluable subjects
            eff_n = int(round(fixed_n_enrolled_per_arm * (1.0 - d)))

            # Attempt to resolve treatment risk
            try:
                pt = calculate_treatment_risk(pc, effect)
                valid = True
                reason = None
            except ValueError as e:
                valid = False
                reason = str(e)
                pt = None

            if not valid or pt is None:
                row.append(
                    CellResult(
                        p_control=pc,
                        p_treatment=None,
                        dropout=d,
                        effective_n_per_arm=eff_n,
                        power=None,
                        is_safe=False,
                        is_valid=False,
                        reason_invalid=reason,
                    )
                )
                continue

            if eff_n < 2:
                row.append(
                    CellResult(
                        p_control=pc,
                        p_treatment=pt,
                        dropout=d,
                        effective_n_per_arm=eff_n,
                        power=0.0,
                        is_safe=False,
                        is_valid=True,
                    )
                )
                continue

            pwr = analytic_power(
                p_control=pc,
                p_treatment=pt,
                n_per_arm=eff_n,
                alpha=alpha,
            )

            is_safe = pwr >= target_power
            row.append(
                CellResult(
                    p_control=pc,
                    p_treatment=pt,
                    dropout=d,
                    effective_n_per_arm=eff_n,
                    power=pwr,
                    is_safe=is_safe,
                    is_valid=True,
                )
            )
        grid.append(row)

    return SensitivityGridResult(
        p_control_steps=p_control_vals,
        dropout_steps=dropout_vals,
        grid=grid,
        target_power=target_power,
        fixed_n_enrolled_per_arm=fixed_n_enrolled_per_arm,
    )
