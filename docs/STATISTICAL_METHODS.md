# Statistical methods

## Task #56: binary inputs and effect transformation

The statistical core is independent of FastAPI. Import `Effect`, `Dropout`, `FixedEnrollment`,
`resolve_treatment_risk`, and `StatisticalInputError` from `app.statistics`.
API request models and HTTP error adapters remain the API owner's responsibility.

All probabilities use decimal fractions. Inputs accept finite Python integers or
floats; strings, booleans, NaN, and infinity are rejected without coercion.
Control and derived treatment event risks must be strictly between zero and one.
The endpoint is lower-is-better:

- Relative risk: `p_treatment = p_control * RR`, with `0 < RR < 1`.
- Absolute risk reduction: `p_treatment = p_control - ARR`, with `0 < ARR < p_control`.

ARR is checked against the control risk on every transformation. A reduction
valid for the planned baseline may be invalid for a stress baseline; it is
rejected rather than clipped or represented as zero power. A derived probability
that underflows to zero is also rejected.

`Dropout(control, treatment)` requires each probability in `[0,1)` and exact
equality between arms. Unequal dropout is outside P0 and returns an
`UNSUPPORTED_MODEL` domain error. Inputs are frozen dataclasses.

`FixedEnrollment(control, treatment)` requires positive integer counts and equal
arm enrollment. Unequal counts return `UNSUPPORTED_MODEL`; booleans, floating
counts, and nonpositive counts return `INVALID_MODEL_INPUT`. Enrollment is a
participant count; probability inputs and outputs remain decimal fractions.

`expected_retained_count(enrolled_n, dropout)` accepts one per-arm enrollment
and a shared dropout fraction and returns `floor(enrolled_n * (1-dropout))`.
This deterministic expected-count approximation can be zero; it is separate
from actual retained counts drawn by later Monte Carlo simulation.

`StatisticalInputError` extends `ValueError`, with a readable message, stable
`code`, and `field`. Invalid values use `INVALID_MODEL_INPUT`. API adapters may
map these to structured 422 responses without depending on exception text.
No API routes or shared transport schemas are implemented by this task.

Run the task's acceptance checks from the repo root:

```sh
PYTHONPATH=backend python3 -m pytest backend/tests/test_effect.py -q
```
