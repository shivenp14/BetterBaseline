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
HTTP calculate/evaluate/grid calls for synthetic, manual and ARR cases. Seven
tests cover JSON download/reopen, full result/provenance preservation, both MCSEs,
RNG/count aggregates, curve/contours/null masks, stale/pending/error guards,
independent operation tokens, canonical export hash integrity and backend schema
validation. `EXPORT_TEST_OUTPUT=/tmp/export-review` saves fresh artifacts.

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
