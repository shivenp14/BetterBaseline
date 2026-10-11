# Better Baseline D6 core benchmarks

Run from the repository root in an installed backend environment:

```sh
PYTHONPATH=backend python scripts/benchmarks/core.py --workload design --output /tmp/design-benchmark.json
PYTHONPATH=backend python scripts/benchmarks/core.py --workload grid --output /tmp/grid-benchmark.json
PYTHONPATH=backend python scripts/benchmarks/core.py --workload monte-carlo --output /tmp/mc-benchmark.json
```

Defaults use D1's `baseline-collapse-v1` preset, three excluded warmups and 30
measured calls. `--preset` also accepts `stable-design-v1` and
`attrition-shock-v1`. Outputs contain exact inputs, validated D1 input hash,
per-field fixture provenance, source hashes, commit, Python/library versions,
hardware, every raw duration, nearest-rank p95, median, and a real result.
Seeded results must replay identically; timing never has a pass/fail threshold.

The scope is a direct uncached numerical call and local result conversion;
fixture parsing and scenario setup occur before timing. Grid per-cell effect
resolution and contour extraction are included. The design workload
is the integer solver, enrollment inflation, and dataclass-to-dictionary conversion.
Monte Carlo uses the preset's frozen enrollment, selected
stress inputs, seed 42, and 10,000 replicates. It does not recompute enrollment.
These reports are core timings, not API or browser round trips. A7's separate
opt-in profiler lives in `backend/tests/benchmark_simulation.py`.

## Dependency boundary

The grid workload calls the landed A4 engine at explicit synthetic axes:
31 baselines `.05.. .35` and 21 dropouts `.00.. .20` in `.01` steps. Frozen
N, planned/selected coordinates, alpha, target and effect come from D1.
All 651 cell powers and selected-dropout curve points are checked against
real scalar analytical calculations outside timing; masks, dimensions and
summary values must agree. Axes are labeled benchmark-origin parameters,
not provenance supplied by D1. Computation hashes include axes/method/fixture
inputs. Design checks verify minimum N and enrollment inflation; simulation
checks verify seed/replicate identity and separate MCSE. Every measured call
must replay the reference result exactly.

The merged routes can now be measured with the isolated uncached HTTP command
below. Cold/warm cache and frontend round-trip measurements remain gated on
#68 (PR #116) and live frontend integration. Before recording those results:

1. Select the real fresh-calculation frontend adapter, not C1 mock fixtures.
2. Measure from the user-triggered request until its result is rendered; retain
   scenario identity and validate the returned numeric result.
3. Use #68's supported reset/inspection controls to identify actual cache misses
   and hits. Browser cache settings alone do not clear a backend result cache.
4. Exclude the cache reset operation from the timed request. Label process-cold,
   API-cache-cold, and warm-cache conditions separately; record server/process
   state and concurrency. Do not invent a cache-reset endpoint.
5. Capture at least 30 runs per reported condition and retain raw samples,
   environment, payload/hash, methods, and latency scope with median/p95.

Real local uncached HTTP timings are retained below. No completed #68 cache or
browser timings are claimed.

## Retained evidence and verification

The three [raw reports](reports/) retain the baseline-collapse workload results,
30 samples each, environment/source identity and checked numerical outputs.
See [the methods notes](../../docs/STATISTICAL_METHODS.md) for measured median/p95.
Reports were generated using an isolated Python 3.12 environment because the
system SciPy binary did not import. Its exact package versions are recorded.
Use an environment containing the backend's declared numerical dependencies.
From the repository root:

```sh
PYTHONPATH=backend python -m unittest discover -s scripts/benchmarks -p 'test_*.py' -v
```

Checks cover all three real D1 presets/workloads, direct numerical agreement,
903 evaluable versus 1004 enrolled with 10% dropout, approximately `.470` stress
power, malformed grid witnesses, seeded replay and raw-report percentile/hash
integrity. No runtime threshold is asserted. Stored reports describe their
original capture; rerunning measures new hardware/load conditions.

This is partial D6 delivery. Cold/warm API cache and actual browser round-trip
workloads remain pending the B6 and live integration handoffs.

## Real uncached HTTP benchmark (pre-#116)

```sh
PYTHONPATH=backend python scripts/benchmarks/http_uncached.py --workload design --output /tmp/design-http.json
PYTHONPATH=backend python scripts/benchmarks/http_uncached.py --workload grid --output /tmp/grid-http.json
PYTHONPATH=backend python scripts/benchmarks/http_uncached.py --workload monte-carlo --output /tmp/mc-http.json
```

Each command starts and stops its own single-worker loopback uvicorn service
from this checkout. Run commands sequentially without competing benchmark
processes. It uses a persistent HTTP/1.1 connection, three excluded warmups and
30 measured requests. Timing starts immediately before sending the POST and ends
after receiving the complete response body; server input validation, computation
and response serialization are included. Client JSON decoding, numerical checks,
service startup, fixture parsing and reporting are outside timing. This is not
a browser render measurement.

Every response passes its registered Pydantic response model and agrees with
real numerical calculations: design counts/nominal power, all 651 grid cells
and the exact selected-dropout curve, or seeded simulation metrics plus analytic
point power. This checks route agreement, not an independent statistical oracle.
Replay comparison excludes only `computed_at` (grid) or
`metadata.computed_at` (simulation); hashes, numeric results, methods, warnings,
seed and software fields must remain identical. Actual timestamps are retained.

The harness verifies the exact source hash of the current pass-through compute
scaffold and refuses changed implementations. It must be revisited after #116;
that refusal is the explicit dependency boundary, not a cache-control mechanism.
It installs no hooks, clears no cache and edits no product files. It cannot label
requests as #68 cache misses/hits or establish a speedup.

[HTTP reports](reports/http/) include raw timings, representative real responses,
fixture provenance, exact requests, hardware/library metadata, checkout commit,
all service source hashes and the HTTP harness hash. Measurements describe the
recorded sources; their checkout includes local harness work identified by hash.
The original core reports remain unchanged. Run the unittest command above to
audit both sets of reports and reject mutated result identities/numeric values.
