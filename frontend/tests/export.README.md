# Issue #76 isolated export handoff

Run from `frontend` after `npm ci`:

```sh
EXPORT_TEST_PYTHON=/path/to/backend/.venv/bin/python node tests/export.test.cjs
npm run lint
npm run typecheck
npm run build
```

The Python interpreter must have the backend's locked development dependencies.
Tests start and clean up a temporary local Uvicorn process, then make fresh HTTP
calculate/evaluate/grid requests for synthetic, manual and ARR cases. They verify
JSON download/reopen, all numeric results and provenance, both MCSEs, RNG/count
aggregates, raw curve/contours, detached request identities, stale/pending/error
guards and validation with backend `ExportPayload` and `EvaluationResponse`.
Set `EXPORT_TEST_OUTPUT=/tmp/export-review` to save these fresh artifacts for a
manual download/reopen check. No fixture files are added to the repository.

## Pending shared integration gate

This isolated delivery does not complete #76. Its production page/API/state
integration is gated on #74 / PR #97 merging and the recorded handoff. Do not
change #74's component files. #72 / PR #105, #67 / PR #103 and #77's preset PRs
are merged; open issue states do not override those merged records.

After the handoff, the parent owns captured `ExportRuns` and passes only the
output of `buildScenarioExport(currentState, runs)` to `ScenarioExport`. Catch
validation failures and supply `payload={null}` with the failure reason. Capture
a detached workspace state at request start. Keep the full raw grid response
before coordinate normalization for both `workspaceHeatmapProps` and
`workspaceCurveProps`, and retain evaluation diagnostics/metadata extensions.
Strip app-only `mock`, `execution` and provenance envelopes from the design;
the export uses the backend v1 field set and per-field provenance ledger.

Design, evaluation and grid hashes describe different endpoint requests and
must not be compared for equality. The builder matches each captured hash to
its workspace result and matches request identities to current inputs. Reload
validation checks structural and cross-result consistency, not cryptographic
hash integrity or statistical correctness. No automatic replay is claimed.
The grid result must carry its source ledger, software versions, complete domain,
matrix/masks, selected-dropout curve and separate contour segments. Evaluation
must carry full MC metadata. Missing metadata disables export.

The parent must invalidate export during new simulation requests, seed/replicate
edits, aborted/failed runs and planned/stress/provenance changes. Simulation
configuration provenance must reflect the options actually sent to the API.
Final acceptance still requires the real calculate → freeze → stress → charts
→ selected simulation → export flow, stale/invalid/error behavior and complete
unstyled component assembly; these gates remain pending in this isolated PR.
