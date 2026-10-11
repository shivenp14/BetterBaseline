# Better Baseline statistical methods

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

For retention flooring, interpret the validated dropout float using its shortest
round-trip decimal string, then use exact rational integer arithmetic. This
preserves `1000` enrolled at dropout `0.8` as `200` expected retained, avoiding
binary subtraction rounding to `199.99999999999994`. Genuinely fractional counts
still floor down, including values immediately below an integer; no epsilon or
nearest-integer tolerance is applied.

`StatisticalInputError` extends `ValueError`, with a readable message, stable
`code`, and `field`. Invalid values use `INVALID_MODEL_INPUT`. API adapters may
map these to structured 422 responses without depending on exception text.
No API routes or shared transport schemas are implemented by this task.

Run the task's acceptance checks from the repo root:

```sh
PYTHONPATH=backend python3 -m pytest backend/tests/test_effect.py -q
```

## Analytical planning and reference fixture

The landed A2 core uses the two-sided Cohen's-h normal approximation. With
`h = 2 asin(sqrt(pT)) - 2 asin(sqrt(pC))`, equal evaluable N per arm gives
`delta = abs(h) * sqrt(N/2)`. Power is the sum of both normal rejection tails
at two-sided alpha. The implementation evaluates the tails without subtracting
small probabilities from one and handles very small alpha explicitly.

`minimum_sample_size` brackets and searches integers starting at 2, testing the
inclusive configured ceiling (default 1,000,000 evaluable per arm). Planning
requires `0 < alpha < target_power < 1`. A null effect or a ceiling below target
returns `UNBOUNDED_OR_INFEASIBLE`.

The canonical entered assumptions `.20/.15`, alpha `.05`, target `.80` require
**903 evaluable participants per arm**: 902 misses target and 903 meets it.
With symmetric 10% planned dropout, `ceil(903/.9) = 1004` **enrolled per arm**.
At fixed 903 enrolled per arm and zero stress dropout, `.10/.075` yields
approximately `.470` conditional analytical power. These are model-dependent
reference values, not observed clinical outcomes. Return computed nominal power
at the chosen N rather than replacing it with the rounded target `.80`.

The local core reports method `cohen_h_normal`, version `1.0.0`; the landed B1 API schema
uses `cohen_h_normal_v1`. Preserve the version and use an explicit API adapter,
not an undocumented method substitution.

## Synthetic Monte Carlo

The landed A3 primitive uses `pooled_two_proportion_z_v1` with explicit NumPy
PCG64 state. Its draw order is retained control count, retained treatment count,
control events, then treatment events. Dropout and outcomes are independent
under the illustrative model. Enrollment remains frozen.

Two-sided significance rejects for either direction. Favorable significance
also requires fewer observed adverse events in treatment. Under a sufficiently
large null scenario, expected rates are approximately alpha and alpha/2,
respectively. Report `mcse_two_sided` and `mcse_favorable` separately, each as
`sqrt(fraction * (1-fraction) / replicates)`. MCSE is simulation error, not
uncertainty about real treatment efficacy.

Undefined tests (empty retained arm, zero variance, or nonfinite statistic)
count as nonrejections over all replicates and contribute to
`invalid_test_fraction`. Retained/event means are simulated aggregates, distinct
from deterministic floored expected counts. Rare expected event/non-event
counts produce warnings; this does not validate the pooled-z approximation in
that regime.

The Cohen's-h planning approximation and discrete pooled-z simulation are
different methods; small numerical differences are expected. Reproducibility
requires identical inputs, seed, RNG draw order, and recorded software versions.
Simulation is synthetic and conditional; it is not evidence that treatment works.

## Fixed-enrollment analytical grid

The landed A4 core returns a dropout-major matrix `[dropout][baseline]` and
keeps the declared equal enrollment frozen. Each valid cell uses floored
expected retained counts. Impossible ARR cells and fewer than two expected
retained participants per arm are null, with an agreeing invalid mask and
null target status. These are unavailable scenarios, not zero-power results.

The power curve evaluates every baseline at the exact selected dropout.
Planned/selected points can be off-axis and are evaluated directly. Every
point reports `below_target` against the requested target. Analytical delta is
selected minus planned power as a fraction. All-invalid domains return null
worst-case power and an empty frontier with a warning. Independent valid off-grid
points retain their power; the merged #66 API preserves their selected-minus-
original-planned delta even when the entire grid domain is invalid. The A4 core
summary alone returns a null delta for an all-invalid domain.

Frontiers use linear interpolation on valid grid edges, restricted to cells
with four valid corners. Separate connected paths are canonically oriented
and sorted by coordinates. Exact-target vertices belong to the above-target
side; isolated vertices and flat plateaus emit no zero-length paths. Saddle
connectivity uses the mean corner power, with ties above. Branches terminate
rather than joining arbitrarily. These interpolated contours are approximate,
not exact roots of the analytical function. Axis size limits and API metadata
belong to the route adapter, not the numerical grid.

## D6 local core measurements

The commands and retained raw reports are in
[scripts/benchmarks](../scripts/benchmarks/README.md). These measurements were
captured on 11 October 2026 against numerical-core commit `98719af`, using the
synthetic D1 `baseline-collapse-v1` fixture. Each workload had three excluded
warmups and 30 measured calls; p95 is nearest rank `ceil(.95 * 30)`, the 29th
sorted observation. Timing uses `perf_counter_ns`, with replay and numerical
invariant checks outside the timed interval. Timing includes local dataclass
conversion for design/grid and core-provided metadata for Monte Carlo; it
excludes HTTP, rendering, fixture/setup work and report serialization.

Recorded environment: macOS 27.0, arm64, eight logical CPUs, Python 3.12.4,
NumPy 2.5.4, SciPy 1.18.1 and statsmodels 0.15.0. Exact source/harness hashes,
method identifiers, axes, seed, provenance, inputs and individual nanosecond
observations are retained in each JSON report. The recorded commit identifies
the numerical core; the harness was local work identified by its source hash.
No API cache is involved. These are warm-process, uncached direct calls on
local hardware under uncontrolled background load.

| Workload | Median (ms) | p95 (ms) | Raw evidence |
|---|---:|---:|---|
| Design solver + enrollment inflation | 0.072 | 0.158 | [JSON](../scripts/benchmarks/reports/baseline-collapse-design.json) |
| 31-baseline × 21-dropout grid | 5.994 | 6.527 | [JSON](../scripts/benchmarks/reports/baseline-collapse-grid.json) |
| Selected 10,000-replicate Monte Carlo | 1.549 | 1.728 | [JSON](../scripts/benchmarks/reports/baseline-collapse-monte-carlo.json) |

Grid axes are explicit synthetic benchmark inputs: baseline `.05` through
`.35`, dropout `.00` through `.20`, both in `.01` steps. These axes are not D1
source assumptions or clinical evidence. The report hashes the axes and method
alongside the fixture input identity. The canonical fixture has 903 enrolled
per arm and zero planned dropout; the separate 10% inflation example above
uses 1004 enrolled per arm and is checked independently.

All three D1 presets pass real design/grid/simulation checks and seed replay.
The published runtime table reports only the named baseline-collapse condition;
other presets' checks do not establish their runtime distributions. Seed-42
engine results are actual draws from the synthetic model, kept distinct from
D1's hand-authored mock response values.

| Remaining measurement | Status |
|---|---|
| API cold/warm compute cache | Not yet measured; requires B6 #68 controls (PR #116) |
| Fresh frontend round trip | Not yet measured; requires live frontend/API integration and B6 cache identity |

D6 remains incomplete at the B6 dependency boundary (PR #116). Cold/warm API conditions
must use B6's supported reset and inspection controls, with cache clearing
outside timing. A browser cache reset does not clear the backend cache. Frontend
measurements must cover a fresh request through rendered real output, retain
scenario identity, and include at least 30 observations per condition. No
fixture-only shell or cached result can establish that acceptance.

This documentation describes tested computational behavior and its limits;
it makes no speedup, clinical, regulatory, or rare-event validation claim.


## D6 real local HTTP measurements before #116

The [HTTP harness](../scripts/benchmarks/README.md#real-uncached-http-benchmark-pre-116)
measured the merged design/grid/evaluate routes from this checkout on 11 October
2026. Each workload used its own new single-worker loopback service, a persistent
HTTP/1.1 connection, three excluded warmups and 30 measured serial requests. The
process was warm and the compute wrapper was the exact uncached pass-through
scaffold. These are **not** measurements of #116's cold/warm cache behavior.

Timing covers POST transmission through complete response-body receipt, including
server validation, numerical work and serialization. Client JSON parsing, result
checks, server startup and frontend rendering are excluded. Every response was
checked against its typed response model and actual numerical calculations outside
timing. Grid checks use each API-returned axis coordinate, including its floating
representation. The original core reports use explicit decimal axes; the measured
HTTP route constructs its axes with linspace. Neither check is independent
scientific validation.

| Real HTTP workload | Median (ms) | p95 (ms) | Raw evidence |
|---|---:|---:|---|
| Design calculation | 0.514 | 0.605 | [JSON](../scripts/benchmarks/reports/http/baseline-collapse-design.json) |
| 31-baseline × 21-dropout grid | 9.704 | 11.453 | [JSON](../scripts/benchmarks/reports/http/baseline-collapse-grid.json) |
| Selected 10,000-replicate simulation | 4.419 | 4.538 | [JSON](../scripts/benchmarks/reports/http/baseline-collapse-monte-carlo.json) |

The recorded environment is macOS 27.0 arm64 with eight logical CPUs, Python
3.12.4, NumPy 2.5.4, SciPy 1.18.1 and statsmodels 0.15.0. Reports retain every
raw duration, source/harness hashes and the exact real response. API timestamps
vary per computation and are recorded; only those generation timestamps are
excluded from semantic replay comparison. No cache key or speedup is inferred.
The HTTP harness deliberately stops when the compute-wrapper source changes.

**Stop boundary:** #68 / PR #116 must merge before implementing its supported
cold/warm cache conditions, reset/inspection behavior and cache timestamp claims.
Fresh frontend request-to-render measurements additionally require the real
frontend/API handoff. Neither remaining condition has been measured; #82 stays
open and its delivery PR stays a draft.
