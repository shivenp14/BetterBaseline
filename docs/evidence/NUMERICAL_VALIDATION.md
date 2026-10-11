# Independent numerical evidence — #109 draft

Measured checks cover the shipped analytic model and the supported simulation
primitive. They do not complete #109 or validate clinical utility or regulatory
use. Final integration/provenance/export and #82's method handoff remain pending.

## Oracle and prescribed checks

`scripts/validation/validate_analytic_http.py` imports no application module,
NumPy, SciPy or statsmodels. It implements Cohen's h with math.asin/sqrt and the
normal tails with math.erfc; statistics.NormalDist supplies the critical value.
A separate integer binary search finds the smallest equal-arm evaluable N that
meets the target. Decimal arithmetic checks dropout inflation and retained floors.

This is a separate implementation of the same documented mathematical
approximation, not an independent clinical model. It checks actual registered
HTTP endpoints rather than importing their calculators. Eight prespecified design
cases cover RR/ARR, risks .05–.30, alpha .01/.05, targets .70–.90 and planned
dropout 0–.30. Thirty-two stress cases include halved risk, dropout .25/.58 and
fixed original enrollment. The tolerance is fixed at 1e-10 before execution;
minimum-N and count comparisons are exact. Simulation is explicitly disabled.

Every API failure or numerical/count mismatch fails the run. No fixture output
substitutes for actual responses, and no report is written until all checks pass.
The committed report contains raw requests/responses, oracle values, errors,
timestamps, software versions, the source reference and limitations.

## Rerun

With Python 3.12 and the committed lock installed, start the backend from the
checkout being validated:

```sh
PYTHONPATH=backend uv run --project backend --locked --extra dev python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

In another terminal at the repository root:

```sh
uv run --project backend --locked --extra dev python scripts/validation/validate_analytic_http.py --base-url http://127.0.0.1:8765 --engine-commit "$(git rev-parse HEAD)" --output /tmp/betterbaseline-analytic-evidence.json
```

The caller records the source SHA; the server does not attest that identity.
Confirm the backend is serving the named checkout before running. Only local
HTTP origins are accepted. Write a new report for a new environment; do not
hand-edit or overwrite historical measured evidence.

## Recorded result

[evidence/validation/analytic-http-fb08719.json](../../evidence/validation/analytic-http-fb08719.json)
records a real run against backend source from main
fb08719e5247e0fc1bbb8875a87ce51f840e2cc4. The local curve-handoff edits are frontend
only and do not change that backend source. Python 3.12.14, NumPy 2.5.4, SciPy
1.18.1 and statsmodels 0.15.0 are recorded from actual endpoint metadata.
All eight designs and 32 stress evaluations pass. Maximum absolute power error
is 2.220446049250313e-16; minimum evaluable N, enrollment inflation and retained
floors match exactly. This includes 903 evaluable per arm, ~.470 stressed power
at frozen 903 with halved risk, and 1,004 enrolled at planned dropout .10.

## Still required before #109 can close

- Reconcile the measured primitive checks below with #82's final method handoff
  and #79's exported response contracts. HTTP/UI acceptance is separate.
- Extend coverage when new supported regimes or discrepancies are identified;
  the prespecified matrix is finite, not exhaustive.
- Complete #79's actual export/provenance acceptance and reconcile #82's method
  documentation. #60/#68 are merged; those remaining handoffs gate completion.
- Confirm the separate validation workflow on the final integrated stack.

This draft is isolated preparatory evidence. It does not replace current P0
integration work, report clinical predictive accuracy or claim a historical
trial could have been saved.

## Combined rerun and simulation evidence

After installing the committed backend lock, one command starts a fresh local
backend, waits for its actual `/healthz` route, runs both validators and stops it:

```sh
uv run --project backend --locked --extra dev python scripts/validation/run_validation.py --output-dir /tmp/new-betterbaseline-validation
```

The output directory must be new. Validators preserve historical reports rather
than overwrite them. A failure returns nonzero; logs remain in that directory.
The separate `.github/workflows/validation.yml` runs the same command and uploads
raw reports/logs, including on failure. Core, integration and E2E CI are untouched.

[analytic-boundaries-80f00dd.json](../../evidence/validation/analytic-boundaries-80f00dd.json)
extends the matrix to ten designs and forty stress evaluations, including .001
and .99 control risks and .80 planned dropout. All exact counts match and maximum
power error remains 2.220446049250313e-16. Backend source is unchanged from the
first report; checkout identity is recorded separately.

[simulation-80f00dd.json](../../evidence/validation/simulation-80f00dd.json)
records thirty runs: five scenarios, three seeds (42, 31415, 27182), and
25,000/100,000 replicates per seed. The existing `simulate_binary` primitive
explicitly accepts equal true risks for calibration. Production RR/ARR request
validation is unchanged. The independent scalar oracle uses an integer
cross-product form of pooled z and `math.erfc`; all rejection counts, favorable
counts, invalid counts and separate MCSEs match the shipped primitive.

Replay intentionally shares NumPy PCG64/binomial draws to isolate the rejection
rule and aggregation. It is not an independent test of the random sampler.
An additional small-N oracle enumerates the complete retained/event distribution
with standard-library combinatorics, independent of the random stream.

Calibration uses a prespecified five-standard-deviation Wilson interval aggregated
across seeds. Well-populated null cases compare with alpha and alpha/2. Sparse
cases compare with their exact finite-N rejection probability; they are not
forced to have nominal alpha. Batch streams are not claimed to be prefixes:
changing the vector size changes how the fixed draw order consumes the RNG.
Repeatability is exact only at the same seed, batch and software environment.

| Scenario, 300,000 pooled replicates | Two-sided | Favorable | Invalid | Interpretation |
| --- | ---: | ---: | ---: | --- |
| N=5,000/arm, risk=.20, alpha=.05 | .0502167 | .0252633 | 0 | Consistent with .05/.025 in the prespecified interval |
| N=5,000/arm, risk=.20, dropout=.25, alpha=.01 | .0100700 | .0051033 | 0 | Consistent with .01/.005 |
| N=903/arm, control=.10, treatment=.075 | .4702800 | .4702233 | 0 | Conditional simulation; analytic ~.4701 is a different approximation |
| N=10/arm, equal risk=.01 | 0 | 0 | .8185667 | Exact two-sided size ~.00000362, far below .05 |
| N=1/arm, equal risk=.20, dropout=.90 | 0 | 0 | .9966633 | Exact invalid fraction .9968; no possible rejection |

Zero observed sparse rejections does not imply zero underlying probability.
Undefined tests remain nonrejections over all replicates. The rare-case finding
demonstrates how poorly nominal-alpha intuition transfers to sparse binary data;
it is a documented approximation limitation, not evidence that a trial failed.
Measured MCSE ratios with four times the replicates range .5000–.5117 in the
well-populated cases (prespecified acceptance .45–.55). More simulation improves
precision of the estimated detection fraction; it does not reduce trial variance.
