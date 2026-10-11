# Better Baseline offline presets

`index.json` lists three self-contained, versioned synthetic presets. Each folder
contains a manifest, explicit planned/stress inputs, and a **draft mock response**
for design, selected point, analytic grid, and Monte Carlo display development.
Read the manifest first and preserve its provenance alongside inputs and exports.
No network, registry, credentials, patient data, or backend is needed to load them.

| Preset | Planned baseline / dropout | Stress baseline / dropout | Fixed enrollment per arm | Stress expected retained floor |
| --- | --- | --- | ---: | ---: |
| baseline-collapse-v1 | .20 / .00 | .10 / .00 | 903 | 903 |
| attrition-shock-v1 | .20 / .05 | .20 / .25 | 951 | 713 |
| stable-design-v1 | .20 / .05 | .19 / .06 | 951 | 893 |

All inputs use fractions, RR=.75, alpha=.05, target power=.80, equal enrollment,
and symmetric dropout. Stress inputs never resize the original design. Planned
evaluable N=903 is the documented Cohen's-h/NormalIndPower reference; the baseline
shock reference is approximately .470. These are reference expectations from the
playbook, not measurements made by these fixtures. Enrollment uses
`ceil(903 / (1 - planned_dropout))`; analytic retention uses
`floor(enrolled * (1 - stress_dropout))`. The separate 10% dropout example is
`ceil(903 / .90) = 1004`, not either 5% preset's enrollment.

Every leaf in `inputs.json`, including null effect override and simulation options,
has a JSON-pointer provenance entry in its manifest. `synthetic_preset` describes
origin, not verified clinical evidence; no patient or inferred clinical values
are included. `inputs_hash` is SHA-256 of UTF-8 JSON with sorted keys and compact
separators, prefixed by `sha256:`.

## Mock status and consumption

**All numerical response values are hand-authored schematic illustrations.**
In particular, seed 42 and 10,000 replicates describe the intended future run;
the Monte Carlo numbers are not seed-42 results. The mock MCSE fields are the
binomial error formula applied to the illustrative fractions, not observed error.
Random retention aggregates are deliberately separate from floored analytic
counts. Mock nominal power .80 is rounded and cannot prove integer minimality.

The grid is `[dropout_index][baseline_index]`, with explicit axes, target power,
and a same-shaped invalid mask. These RR presets have valid cells throughout;
future invalid ARR cells must be `null` with a true mask, never zero power.
No contour has been computed: `frontier_points` is empty and `frontier_status`
states this explicitly. Display the analytic label and illustrative warning.
Do not treat these mocks as API golden snapshots or measured acceptance evidence.

The draft follows the architecture's field names except the issue's agreed split
`mcse_two_sided` / `mcse_favorable`, replacing the older ambiguous `mcse` field.
Contracts are owned by B; align these D-owned fixtures after B1 without modifying
`contracts/`. Real endpoint responses need an adapter to the mock wrapper's
`design`, `point`, and `grid` sections; this wrapper is not an endpoint contract.

## Snapshot handoff

Once A/B functions and frozen contracts exist, generate separate measured
snapshots from actual design, point, grid, and simulation functions. Record exact
inputs/hash, seed, replicates, engine commit, Python/NumPy/SciPy/statsmodels and
backend versions, and generation command. Check documented reference tolerances
and integer minimality against the engine; never replace measured results with
rounded values. Keep illustrative fixtures clearly labeled for offline UI work.
Each manifest records this pending handoff. No measured snapshot ships here.

Run the dependency-free fixture checks from the repository root:

```bash
python3 -m unittest discover -s tests/fixtures -p 'test_demo_presets.py' -v
```

These checks verify fixture integrity and semantics; live numerical/API/E2E
acceptance belongs to the later integration issues.
