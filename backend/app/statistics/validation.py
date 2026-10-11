"""Strict scalar validation shared by statistical functions."""

import math

from .errors import StatisticalInputError


def finite_number(value: object, *, field: str) -> float:
    """Accept ordinary numeric inputs without coercing strings or booleans."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StatisticalInputError("Expected a finite number", field=field)
    try:
        result = float(value)
    except (OverflowError, ValueError):
        raise StatisticalInputError("Expected a finite number", field=field) from None
    if not math.isfinite(result):
        raise StatisticalInputError("Expected a finite number", field=field)
    return result


def probability(value: object, *, field: str, allow_zero: bool = False) -> float:
    result = finite_number(value, field=field)
    if not (0 <= result < 1 if allow_zero else 0 < result < 1):
        interval = "[0, 1)" if allow_zero else "(0, 1)"
        raise StatisticalInputError(f"Expected a probability in {interval}", field=field)
    return result
