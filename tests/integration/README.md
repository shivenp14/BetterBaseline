# D3 integration preparation (#79)

This draft prepares external request/result/export invariants. It does not
close #79 or report live API-to-export acceptance. #90 is merged; #65/#66/#67/#76
still gate real integration. Core CI #80 (PR #95) is also unmerged, so this draft
adds no integration.yml yet. Add that independent workflow after the #80 handoff;
do not modify ci.yml/e2e.yml or product source.

Run the standard-library fixture checker regressions from the repository root:

```sh
python3 -m unittest discover -s tests/integration -p 'test_*.py' -v
```

These tests consume the three committed synthetic presets as read-only inputs.
Their results remain illustrative. The export witness is explicitly constructed
checker data, never a measured UI export or a production export implementation.
Twelve tests exercise cross-boundary invariants and prove that mutations fail:
transposed nonsquare matrices, null converted to zero, wrong selected-cell values,
conflated retained counts, unsplit MCSE, valid-only MCSE denominators, invalid tests
counted as rejections, seed drift, changed enrollment/results and lost/relabeled
provenance. No product calculators, FastAPI routes or frontend modules are imported.
No simulated numeric result is hardcoded as a seed-42 oracle.

## Real captured flow after the handoffs

Use the actual configured local API and frontend to calculate, evaluate, grid,
simulate and download an export. Record a JSON bundle containing:

- `source`: `real_api_and_ui_export`, plus `engine_commit` and `captured_at`.
- `request`: the exact evaluation body, including frozen equal counts, stress
  inputs and explicit replicate/seed options.
- `design_response`, `evaluation_response`, `grid_response`: unmodified network
  responses from the same run. Use a selected scenario on an exact grid node.
- `export`: the independently downloaded frontend JSON; do not synthesize it
  from the response just to make the checker pass.
- `expected_provenance`: the per-field ledger recorded before export, with its
  final #67 source tags/URLs/verification semantics. Compare the entire ledger.

Then, with #64's locked dev environment (jsonschema required):

```sh
uv run --project backend --locked --extra dev python tests/integration/check_capture.py /path/to/capture.json
```

The tool loads #63's committed JSON schema, validates each named response/export
model and checks the cross-boundary invariants. A missing schema, field, library
or capture fails; there is no fixture substitution or successful skip. The
current branch has no frozen schema file, so a live run is presently blocked.
Proposed count aggregates, optional simulation, RNG/software metadata and richer
provenance must be aligned with the final contracts through their owners before
readiness. Current #89 schemas do not yet express all those fields; this draft
does not edit shared schemas or silently weaken integration expectations.

## Remaining mandatory scenarios

- Actual .20/RR=.75 calculation: 903 evaluable/arm and 1,004 enrolled with 10%
  planned dropout. Evaluate .10/RR=.75 at frozen 903/no dropout: about .470.
- Change stress baseline/dropout and verify fixed enrollment and planned design
  survive through the downloaded export unchanged.
- Compare repeated same-input/seed numeric simulation results in the same
  recorded environment. Check two-sided versus favorable fractions and separate
  MCSE, expected floors versus simulated retained means, all-replicate invalid
  policy and software/RNG metadata. Null calibration (alpha versus alpha/2) must
  use a supported real calibration seam; current adverse-effect design contracts
  forbid RR=1. Do not fabricate null API acceptance via an invalid request.
- Use nonsquare axes and invalid ARR cells to verify orientation, literal nulls
  and masks. Compare the selected point/curve at exactly the selected dropout.
- Capture input provenance before API/export processing, then check it survives
  the real UI export with full method/software/seed metadata. Repeat fresh inputs
  with external internet disconnected, preserving local API connectivity.

Record actual request/response/browser evidence and failures. Fixture checks
passing alone cannot mark the draft ready or close the issue. This capture tool
is preparation for assertions on real evidence; it does not drive the browser,
fetch a backend response, or independently establish that a supplied capture was
obtained live. Add orchestration/CI after the registered API and #76 handoffs.

#65 follow-up: expected-retention assertions now follow the shared decimal-floor
convention and allow null analytic power exactly at zero expected retention.
The registered point API is implemented in #91; full grid/UI-export acceptance
still awaits #66/#67/#76 and the #80 workflow handoff.
