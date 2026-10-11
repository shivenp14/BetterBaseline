# Contract integration checks (#79)

The checks now cover the assembled production UI and the real calculate/evaluate/
grid endpoints. Fixture mutation witnesses remain illustrative; measured evidence
comes from real HTTP responses and independently downloaded browser files.

```sh
python -m unittest discover -s tests/integration -p 'test_*.py' -v
python tests/integration/run_point_checks.py --base-url http://127.0.0.1:8000
```

The point checker covers 903/.470, 1,004 enrolled with .10 planned dropout, exact
seed repeatability, nonsquare 2×3 matrix/point agreement, the off-grid .13 dropout
curve, original planning comparisons and invalid ARR null cells. Fourteen mutation
regressions reject transposition, conflated expected/sampled retention, lost MCSE
splits, wrong denominators, invalid-test rejection, lost provenance and input drift.

## Independently downloaded UI exports

Install backend's committed lock, frontend lock and this folder's browser lock:

```sh
uv sync --project backend --locked --extra dev
npm ci --prefix frontend
npm ci --prefix tests/integration
(cd tests/integration && npx playwright install chromium --with-deps)
(cd frontend && NEXT_PUBLIC_API_MODE=live NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8765 npm run build)
bash tests/integration/run_browser_checks.sh
```

The runner starts and cleans up local production frontend/backend processes.
Backend socket connections outside loopback fail under a test-only startup guard;
HTTP/WebSocket browser routing allows only the exact two configured origins and
blocks service workers. This is application-level egress isolation, not a claim
that the entire CI runner has no internet. Setup/build needs connectivity.

The browser calculates the synthetic preset, runs the explicit seeded simulation,
downloads/reopens JSON, changes to fresh manual stress inputs and seed/replicates,
then repeats the seed. It records actual requests and unmodified responses before
reading the download; it never constructs an export. Every result and all seven
provenance fields are compared after the documented HTTP-envelope-to-export-map
normalization. Missing schema fields, malformed downloads or failures return
nonzero. Null calibration is measured by #109's supported simulation seam, since
production RR=1 remains intentionally invalid.

Artifacts go to `/tmp/betterbaseline-integration`: raw capture bundles, downloaded
JSON, request counts, versions, hashes, logs and browser report. integration.yml
builds and runs this flow, then uploads the evidence even on failure. The core CI
and separate E2E workflow remain unchanged.

`evidence/offline/` preserves the measured production-container rehearsal against
main 86e834e. Three independent downloads and eight real POST responses passed;
fresh .12 risk/.13 dropout retained 903 enrolled/arm, seed 43 with 1,000 replicates
replayed identically, with zero page errors/external browser requests. #94's
infra/deploy/offline-report.json records healthy non-root containers and a Docker
internal network with no external route (backend probe failed ENETUNREACH).
These are synthetic numerical checks, not clinical efficacy evidence.
