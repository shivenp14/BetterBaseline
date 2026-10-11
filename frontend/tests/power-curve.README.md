# #73 curve and comparison handoff

The standalone components accept #66 analytic response values and the merged
#72 WorkspaceState through `workspaceCurveProps` / `workspaceComparisonProps`.
They make no API requests and compute no statistical power. #76 owns final
page/API/state assembly; completing that assembly is not a prerequisite for
merging these components.

At grid request start, capture a detached workspace snapshot. Preserve the raw
canonical grid response before the current frontend adapter replaces point
objects with coordinates. Its raw `power_curve`, `planned_point.power`,
`selected_point.power`, `fixed_enrollment`, target and input hash are required.
The response's selected scenario must match the captured state's stress inputs;
this handoff uses the workspace's planned effect without a separate override.
Do not cast a coordinate-only normalized response into this contract.

```tsx
const requestState = structuredClone(workspaceAtRequestStart);
// response: CurveApiResponse from the existing grid request, before normalization
const completed = { requestState, response };
const curveProps = workspaceCurveProps(currentWorkspace, completed);
const comparisonProps = workspaceComparisonProps(currentWorkspace, completed);
// In #76's page assembly:
<PowerCurve {...curveProps} onSelectBaseline={onBaselineChange} />
<DesignComparison {...comparisonProps} />
```

Retain `completed` together as one request/result snapshot. Revisions, calculated
plan identity, full planning assumptions, frozen counts, stress inputs and
provenance are checked against current state. Changed-back inputs do not revive
an old response across revisions. Loading, errors and stale state hide numeric
output. Missing raw powers/curve produce an explicit error, never a fallback to
an arbitrary grid row, interpolation, fixture or extra Monte Carlo runs.

The triangle and original-plan comparison use the API's original planned point
at its original dropout. The curve and circle use the exact selected dropout.
These powers can differ even at the same baseline; the legend explains that.
Off-grid selected points retain the API's supplied power. Null powers remain
unavailable rather than becoming zero. Existing manually supplied snapshots
without plannedPointDropout retain their selected-dropout marker semantics.

## Verification

From frontend, with installed locked dependencies:

```sh
node tests/power-curve.test.cjs
npm run lint
npm run typecheck
npm run build
```

To require the real HTTP handoff test, start the committed locked backend in
another terminal, then run:

```sh
BETTERBASELINE_CURVE_API=http://127.0.0.1:8000 node tests/power-curve.test.cjs
```

That test calculates an actual design, requests a nonsquare grid with selected
baseline .12 and dropout .13 (both off grid nodes), and renders both components
through the workspace adapter. A missing/failing API fails; no fixture substitutes
for this explicitly requested live test. Normal component tests use clearly
hand-authored witnesses and do not claim live execution.

Recorded local run on base main fb08719e5247e0fc1bbb8875a87ce51f840e2cc4:
14 component/handoff tests pass, plus the required live test. Actual grid hash:
sha256:5b28026f87806cd0d95c2ed9c7997206e6d7238ecd9291a40caaae2be920fe36.
Original planned power: 0.8002861288461955; selected power: 0.4934706317083679.
Curve at dropout .13: .10→0.4197188860678374, .20→0.7431617107622405,
.30→0.9228923002219931. Python 3.12.14, NumPy 2.5.4, SciPy 1.18.1,
statsmodels 0.15.0. This verifies the component handoff; final page wiring and
UI export/offline acceptance belong to #76/#79/#81.
