"""Lower-is-better binary endpoint effect transformations."""

from .errors import StatisticalInputError
from .inputs import Effect
from .validation import probability


def resolve_treatment_risk(p_control: float, effect: Effect) -> float:
    """Resolve RR/ARR at the supplied risk, without clipping invalid scenarios.

    ARR validity depends on this control risk, so validate it on every call,
    including evaluation of a stress scenario against a frozen design.
    """
    control = probability(p_control, field="control_event_rate")
    if not isinstance(effect, Effect):
        raise StatisticalInputError("Expected an Effect input", field="effect")
    if effect.kind == "relative_risk":
        treatment = control * effect.value
    else:
        if effect.value >= control:
            raise StatisticalInputError(
                "Absolute risk reduction must be smaller than the control event rate",
                field="effect.value",
            )
        treatment = control - effect.value
    return probability(treatment, field="treatment_event_rate")
