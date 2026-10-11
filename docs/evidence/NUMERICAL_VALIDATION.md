# Independent numerical evidence — #109 draft

The first measured check covers the shipped analytic model only. It does not
complete #109 or validate Monte Carlo calibration, clinical utility or regulatory
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

- Independent pooled-z rejection-rule checks and prespecified Monte Carlo/null
  calibration with binomial uncertainty, including favorable alpha/2 semantics.
- Invalid-test nonrejection policy, seed/batch repeatability and measured MCSE
  scaling, with a supported test-only null seam rather than weakened API limits.
- Broader low-event and boundary regimes; publish approximation disagreements
  instead of forcing analytic and pooled-z estimates to match.
- Complete #79's actual export/provenance acceptance and reconcile #82's method
  documentation. #60/#68 are merged; those remaining handoffs gate completion.
- A separate validation CI workflow once the complete suite is established.

This draft is isolated preparatory evidence. It does not replace current P0
integration work, report clinical predictive accuracy or claim a historical
trial could have been saved.
