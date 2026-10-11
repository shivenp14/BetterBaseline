"""Immutable, validated core inputs; HTTP schemas are owned by the API layer."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from .errors import StatisticalInputError
from .validation import probability

EffectKind = Literal["relative_risk", "absolute_risk_reduction"]


def expected_retained_count(enrolled_n: int, dropout: float) -> int:
    """Floor expected retention for one arm; this is not a random draw.

    P0 callers use the same enrollment and shared dropout for both arms.
    Interpret dropout via its shortest round-trip decimal representation and
    floor with integer arithmetic, avoiding binary rounding at integer counts.
    """
    enrollment = FixedEnrollment(enrolled_n, enrolled_n)
    retention = Dropout(dropout, dropout)
    numerator, denominator = Decimal(str(retention.control)).as_integer_ratio()
    return enrollment.control * (denominator - numerator) // denominator


@dataclass(frozen=True)
class FixedEnrollment:
    """Positive equal arm enrollment; unequal allocation is outside P0."""

    control: int
    treatment: int

    def __post_init__(self) -> None:
        for arm in ("control", "treatment"):
            count = getattr(self, arm)
            if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
                raise StatisticalInputError(
                    "Expected a positive integer enrollment", field=f"enrolled_n.{arm}",
                )
        if self.control != self.treatment:
            raise StatisticalInputError(
                "Unequal arm enrollment is outside the supported P0 model",
                field="enrolled_n", code="UNSUPPORTED_MODEL",
            )


@dataclass(frozen=True)
class Effect:
    kind: EffectKind
    value: float

    def __post_init__(self) -> None:
        if self.kind not in ("relative_risk", "absolute_risk_reduction"):
            raise StatisticalInputError("Unsupported effect kind", field="effect.kind")
        object.__setattr__(self, "value", probability(self.value, field="effect.value"))


@dataclass(frozen=True)
class Dropout:
    """Independent arm dropout probabilities; P0 supports symmetric values only."""

    control: float
    treatment: float

    def __post_init__(self) -> None:
        control = probability(self.control, field="dropout.control", allow_zero=True)
        treatment = probability(self.treatment, field="dropout.treatment", allow_zero=True)
        if control != treatment:
            raise StatisticalInputError(
                "Arm-asymmetric dropout is outside the supported P0 model",
                field="dropout", code="UNSUPPORTED_MODEL",
            )
        object.__setattr__(self, "control", control)
        object.__setattr__(self, "treatment", treatment)
