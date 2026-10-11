# Issue #76 export and assembly checks

Run from `frontend` after `npm ci`, using a Python 3.12 environment with the
backend's locked development dependencies:

```sh
EXPORT_TEST_PYTHON=/path/to/backend/.venv/bin/python node tests/export.test.cjs
npm run lint
npm run typecheck
npm run build
```

The tests start and clean up a temporary local Uvicorn process, then make fresh
HTTP calculate/evaluate/grid calls for synthetic, manual and ARR cases. Eight
tests cover JSON download/reopen, full result/provenance preservation, both MCSEs,
RNG/count aggregates, curve/contours/null masks, stale/pending/error guards,
independent operation tokens, canonical export hash integrity and backend schema
validation, including exact decimal retention at 1000 enrolled/.07 dropout
(930 retained) through download/reopen. `EXPORT_TEST_OUTPUT=/tmp/export-review` saves fresh artifacts.

## Captured inputs and raw results

#97 merged at b9b8025 and the recorded handoff transfers page/API/state integration
to #76. #126/#127's API/provenance contracts and export hash seam are incorporated
from main. Do not edit other owners' component files.

The parent captures detached workspace state when each operation starts.
`getStressGrid` captures the canonical backend response before adding coordinate
aliases or UI provenance envelopes. Both chart adapters receive that raw response;
the chart revision is the workspace input generation, so independent evaluation
and grid operation tokens do not invalidate current charts. Full evaluation
metadata/diagnostics and all seven provenance record fields survive export,
including source_location, verified_by_user and is_observed_registry_result.
Omitted optional audit fields compare equal to null; backend observed-registry
normalization is respected without inventing protocol assumptions.

`buildScenarioExport` requires current successful design/evaluation/grid statuses,
matching captured input generations/planning/enrollment/selection/provenance, and
matching endpoint hashes. Seed/replicate edits advance input generation and
invalidate export; the parent additionally checks the simulation result against
the displayed options. Superseded, failed, aborted, incomplete, invalid and demo
runs cannot produce a current complete export.

Endpoint hashes describe different requests and must not be compared to one
another. The canonical export-level `inputs_hash` is generated with merged
`computeWorkspaceExportInputsHash`; it covers planned assumptions, locked
counts, stress assumptions and normalized full provenance. It is mandatory in
the downloaded artifact and recomputed during reopen validation. Backend
validation must retain the supplied hash, not auto-populate an omitted one.
Schema/hash validation does not independently verify statistical correctness.

The production screen assembles planning form/summary, stress controls,
comparison, curve, heatmap/table, one selected Monte Carlo panel, provenance,
method disclosures and export. Stress edits debounce analytic evaluation/grid;
only submitting the Monte Carlo panel performs seeded simulation. Browser
acceptance evidence and its reproduction command are recorded with the final PR.

## Production browser acceptance

Start the backend and frontend from this checkout with matching CORS and live API
configuration (for example frontend `http://127.0.0.1:8176`, backend
`http://127.0.0.1:8177`). Use an installed Playwright module and Chromium:

```sh
PAGE_URL=http://127.0.0.1:8176 \
PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs \
CHROMIUM_EXECUTABLE=/path/to/chromium \
EXPORT_TEST_PYTHON=/path/to/backend/.venv/bin/python \
node tests/export.browser.mjs
```

`CHROMIUM_EXECUTABLE` is optional when Playwright's matching browser is installed.
The script uses the production page and fresh real HTTP numerical responses.
It verifies all panels, calculate/freeze/stress/chart assembly, exact mouse/Enter/
Space heatmap selection, one selected MC request per submit, default and edited
seed/reps, synthetic/manual/ARR and switched-preset exports, seven actual file
downloads and file-input reopens, canonical hash rejection, invalid planning/seed/
ARR inputs, failure recovery, and delayed real grid/MC response rejection.
Failure injection supplies only explicit HTTP errors; delayed numerical responses
come from the running backend. No numerical mock/cached fallback is used.

Evidence is saved to `EXPORT_BROWSER_OUTPUT` (default
`/private/tmp/issue76-browser-acceptance`): downloaded JSON, a report and a full-page
screenshot. Latest run: 34 numerical requests, 9 explicit selected simulation
requests (7 completed exports, 1 injected failure, 1 superseded run), 0 page errors.
RR enrollment stays 903/903 throughout stress edits; ARR locks 195/195 and retains
literal null cells/masks; switching to stable preset locks 951/951. These are
conditional synthetic calculations, not clinical evidence.

The T3 browser snapshot provider timed out twice. Acceptance used the repository's
Playwright workflow with the installed cached Chromium executable; no package or
lockfile changes were needed. Existing StressControls/PresetSelector inline styles
are inherited from their merged components; this issue adds no custom styling and
does not modify those component files.
