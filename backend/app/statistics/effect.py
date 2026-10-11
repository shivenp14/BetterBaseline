"""Effect size transformations and treatment risk calculations for clinical trials.

Supports:
- Relative Risk (RR)
- Absolute Risk Reduction (ARR)
Enforces strictly lower-is-better event outcomes within (0, 1) probability space.
"""

from dataclasses import dataclass
from typing import Literal

EffectKind = Literal["relative_risk", "absolute_risk_reduction"]


@dataclass(frozen=True)
class Effect:
    kind: EffectKind
    value: float


def calculate_treatment_risk(p_control: float, effect: Effect) -> float:
    """Calculate the treatment arm event probability given control risk and effect.

    Args:
        p_control: Baseline event probability in control arm, strictly in (0, 1).
        effect: Effect specification (relative_risk or absolute_risk_reduction).

    Returns:
        p_treatment: Implied event probability in treatment arm.

    Raises:
        ValueError: If inputs fall outside valid domain bounds or produce impossible rates.
    """
    if not (0.0 < p_control < 1.0):
        raise ValueError(f"p_control must be in (0, 1), received {p_control}")

    if effect.kind == "relative_risk":
        if not (0.0 < effect.value < 1.0):
            raise ValueError(f"RR must be in (0, 1) for lower-is-better outcome, received {effect.value}")
        p_treatment = p_control * effect.value
    elif effect.kind == "absolute_risk_reduction":
        if not (0.0 < effect.value < p_control):
            raise ValueError(
                f"ARR must be in (0, p_control), received ARR={effect.value} for p_control={p_control}"
            )
        p_treatment = p_control - effect.value
    else:
        raise ValueError(f"Unsupported effect kind: {effect.kind}")

    if not (0.0 < p_treatment < 1.0):
        raise ValueError(f"Derived p_treatment {p_treatment} must be strictly in (0, 1)")

    return p_treatment
