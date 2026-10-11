# Better Baseline D6 benchmarks

These opt-in commands measure real computations; normal CI has no timing threshold.
Run from the repository root in an installed backend environment. Live reports
also record the installed frontend runtime, so install the committed frontend
lock with `npm ci` and build it before running them. No manifests are changed.

## Direct core

```sh
PYTHONPATH=backend python scripts/benchmarks/core.py --workload design --output /tmp/design.json
PYTHONPATH=backend python scripts/benchmarks/core.py --workload grid --output /tmp/grid.json
PYTHONPATH=backend python scripts/benchmarks/core.py --workload monte-carlo --output /tmp/mc.json
```

Defaults: synthetic D1 baseline-collapse-v1, three excluded warmups, 30 measured
calls. The other two presets are supported with `--preset`. Grid axes are 31
baselines .05–.35 and 21 dropouts .00–.20 in .01 steps. Axes are synthetic benchmark
parameters, separately identified from the fixture ledger. Setup, fixture parsing,
validation and reporting are outside timing; local result conversion is included.
The core reports retain exact inputs, provenance, seed, versions, raw timings and
source/result hashes. Seed replay, all cell/scalar agreement, minimum N and
inflation checks run outside timing. These are route-agreement checks, not an
independent scientific oracle. A7's profiler remains in backend/tests/benchmark_simulation.py.

## Merged #68 real HTTP and cache measurements

```sh
PYTHONPATH=backend python scripts/benchmarks/live.py --output /tmp/live-http.json
```

The harness owns one single-worker loopback uvicorn service in a background
thread. It sends serial requests over a persistent HTTP/1.1 connection. Timing
covers request send through receipt of the entire response body, including
server validation, numerical work and serialization. Startup, client JSON
parsing, result checks, cache reset/inspection and reporting are excluded.

A benchmark-only observer delegates to the real cache's get/set/clear/len
methods without changing their behavior. Cache clearing occurs before each cold
request and outside timing; warm requests must show an actual hit and no write.
An initial priming request and three warmups are excluded, then 30 requests are
retained per condition. Design and simulation are measured cold/warm. The grid
route supplies no cache key, so it is measured and labeled **uncached-grid**.
No cache-hit grid latency is claimed, and no control endpoint is installed.

Separate real requests confirm same-seed hits and changed-seed/replicate misses.
The key helper is also checked with differing version parameters. Current route
keys use route, model version and normalized request, including effective
defaults. They do not separately include numerical method version or software
signature. Each report uses a new benchmark process and application; never treat cached results across software changes as validated.

Design caches the solver result and constructs its response anew; it has no
computed-at field. Simulation caches the full response, preserving its original
metadata.computed_at on hits. Grid recomputes and has new timestamps. Semantic
replay excludes only generation timestamps; all numeric/hash/method/source fields
must agree. Raw timestamps and per-request cache keys/hit witnesses are retained.

## Production frontend action-to-result measurements

In frontend/, build and start the unchanged production app:

```sh
npm ci
npm run build
npm run start
```

Leave localhost:3000 available and port 8000 free. In another terminal, from the
repo root with a separately installed Playwright/Chromium:

```sh
PYTHONPATH=backend PLAYWRIGHT_BROWSERS_PATH=/path/to/browsers D6_PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs python scripts/benchmarks/live.py --browser --output /tmp/live-browser.json
```

The command starts/stops its own real backend on 127.0.0.1:8000. The production
frontend must use its default live API URL (no demo mode or URL override).
There is no temporary page, custom render harness, intercepted fetch or injected
statistical result. Native Calculate/Load grid/Evaluate actions use the committed
shared helper, reducer and UI. Playwright checks the real HTTP payload/response,
rendered counts/grid/MCSE values, seed, replicates, live execution and page errors.

A browser performance clock starts immediately before the native action and
ends at the MutationObserver callback after the pending control returns to its
completed state. React updates its result and status together. This measures
client/helper/HTTP/React DOM commit; **paint is excluded**. Navigation, setup,
priming, validation and cache control are excluded. Browser timers can be
quantized. The backend cache observer is controlled through local process pipes,
not a network endpoint; its work is outside timing. Each condition has 30 raw
observations after one priming request and three excluded warmups.

The current production preset grid is **6 baselines × 4 dropouts**, not 31×21.
Its exact request is retained. The separate HTTP benchmark measures the required
31×21 grid. Do not compare these grid workloads as though their sizes were equal.
The browser page is warm; cache-cold describes backend compute cache misses,
not process startup, browser cache, navigation or first-paint latency.

## Evidence and audit

[Current HTTP/browser reports](reports/live/) retain 30 samples per condition,
median and nearest-rank p95 (29th sorted sample), cache observations, exact real
requests/results, timestamps, source hashes and hardware/software metadata.
[Methods notes](../../docs/STATISTICAL_METHODS.md) summarize them. Results depend
on local hardware/load; no general speedup or clinical validation is claimed.

```sh
PYTHONPATH=backend python -m unittest discover -s scripts/benchmarks -p 'test_*.py' -v
```

Audit checks cover numerical references, all three presets through the core,
raw percentile/hash integrity, replay identity, mutated values, false cache
labels and changed-seed/replicate misses. Assertions must remain enabled (no -O).

Original core reports and [pre-#116 HTTP reports](reports/http/) remain unchanged
as historical evidence. http_uncached.py intentionally refuses the merged wrapper;
reproduce that historical command from its recorded source revision rather than
removing its guard. Current commands use live.py. Historical timings use separate
capture environments and must not be presented as a controlled before/after trial.

#76 owns final screen/export assembly. These measurements cover the currently
shipped workspace and do not claim downloaded-export or clinical validation.
