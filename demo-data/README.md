# Better Baseline offline presets

`index.json` lists three self-contained, versioned synthetic presets. Each folder
contains a manifest, explicit planned/stress inputs, a **draft mock response**,
and a separate **generated final response**. Mocks remain for frontend work before
the backend is available; they are hand-authored illustrations and are never
measured evidence. Final responses come from the merged backend design,
evaluation, and grid functions. Read each manifest and response status before use.

| Preset | Planned baseline / dropout | Stress baseline / dropout | Fixed enrollment per arm | Stress expected retained floor |
| --- | --- | --- | ---: | ---: |
| baseline-collapse-v1 | .20 / .00 | .10 / .00 | 903 | 903 |
| attrition-shock-v1 | .20 / .05 | .20 / .25 | 951 | 713 |
| stable-design-v1 | .20 / .05 | .19 / .06 | 951 | 893 |

All inputs use fractions, RR=.75, alpha=.05, target power=.80, equal enrollment,
and symmetric dropout. Stress inputs never resize the original design. Planned
evaluable N=903 is the documented Cohen's-h/NormalIndPower reference; the baseline
shock reference is approximately .470. These are reference expectations from the
playbook. Generated results measure backend calculations for synthetic inputs;
they are not clinical evidence. Enrollment uses
`ceil(903 / (1 - planned_dropout))`; analytic retention uses
`floor(enrolled * (1 - stress_dropout))`. The separate 10% dropout example is
`ceil(903 / .90) = 1004`, not either 5% preset's enrollment.

Every leaf in `inputs.json`, including null effect override and simulation options,
has a JSON-pointer provenance entry in its manifest. `synthetic_preset` describes
origin, not verified clinical evidence; no patient or inferred clinical values
are included. `inputs_hash` is SHA-256 of UTF-8 JSON with sorted keys and compact
separators, prefixed by `sha256:`.

## Illustrative mock status and consumption

**All numerical response values in `mock-response.json` are hand-authored
schematic illustrations.** Seed 42 and 10,000 replicates describe the intended
run; those Monte Carlo values are not seed-42 results. Mock MCSE fields are the
binomial error formula applied to illustrative fractions, not observed error.
Random retention aggregates are deliberately separate from floored analytic
counts. Mock nominal power .80 is rounded and cannot prove integer minimality.

The mock grid is `[dropout_index][baseline_index]`, with explicit axes, target
power, and a same-shaped invalid mask. These RR presets have valid cells
throughout; future invalid ARR cells must be `null` with a true mask, never zero
power. No contour has been computed: `frontier_points` is empty and
`frontier_status` states this explicitly. Keep the illustrative warning visible.
Do not treat mocks as API golden snapshots or measured acceptance evidence.

## Generated final responses

`final-response.json` contains canonical response bodies returned by the merged
backend design route, evaluation service, and grid service. Each records complete
requests, seed 42, 10,000 replicates, API input hashes, backend source commit,
generation command, and Python/NumPy/SciPy/statsmodels/FastAPI/Pydantic versions.
The design output includes the backend's actual integer sample size and achieved
power; analytic retention floors and simulated random aggregates remain distinct.

Operational `computed_at` timestamps are intentionally omitted from response
bodies so regeneration is byte-for-byte stable. The omission is listed in each
snapshot. No other response fields are synthesized or rounded. These are measured
computations of synthetic inputs, not clinical evidence or independent statistical
validation.

With the repository's locked Python 3.12 dependencies, regenerate or validate
snapshots from the repository root:

```bash
uv run --locked --directory backend python ../demo-data/generate_snapshots.py
uv run --locked --directory backend python ../demo-data/generate_snapshots.py --check
```

The fixture suite runs the `--check` command to guard deterministic content.
Keep `mock-response.json` clearly marked illustrative for build-before-backend
use; do not overwrite it with generated data.

Run fixture checks in the locked backend environment:

```bash
uv run --locked --directory backend pytest -q ../tests/fixtures/test_demo_presets.py
```
