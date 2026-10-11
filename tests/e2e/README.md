# E2E acceptance suite

This suite exercises the browser against the local production frontend and the
real FastAPI service. A passing result requires the UI to make actual API
requests. Fixture-only responses, intercepted success responses, skipped
exports, or expected failures do not satisfy acceptance.

## Local setup and run

From the repository root, install the backend and frontend dependencies and
build the production frontend:

```sh
cd backend && uv sync --locked --extra dev
cd ../frontend && npm ci
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001 NEXT_PUBLIC_API_MODE=live npm run build
cd ../tests/e2e && npm ci
npx playwright install chromium
npm test
```

`npm test` first checks the test-only backend socket egress guard, then starts
the backend and frontend using the built frontend. The browser allows HTTP
requests and WebSockets only to the exact configured local origins; Playwright
blocks service workers so page routing can enforce the HTTP allowlist. The
Python startup hook blocks non-loopback sockets and DNS lookups in the backend
process. GitHub Actions runner egress is not globally disabled; workflow setup
and package installation use outbound network access.

## Current integration status

Current main includes the final product assembly from PR #128. The suite uses
named regions for Planned design summary, Sensitivity heatmap, Selected-scenario
Monte Carlo simulation, and Scenario export. It selects ARR explicitly in the
planning form and checks the actual backend 422 error in the stress section.

Evaluate Stress Scenario requests analytic results with simulation null. Run
simulation explicitly requests seed 42 and 10,000 replicates. Response matching
separates these requests from automatic analytic refreshes. Simulation assertions
check the current response timestamp, labeled result values, and both MCSEs in
percentage points with three decimal places. Every heatmap cell is checked against
the live response, including raw SVG values, coordinates, invalid masks, and
one-decimal table percentages.

Export starts as a disabled button and becomes the Download current scenario JSON
link after current design, seeded simulation, and grid results are available. The
suite downloads that link and compares complete captured responses, unwrapping
the API provenance envelope into the canonical field map for design/evaluation.
It validates the JSON with the backend ExportPayload contract, including canonical
inputs-hash verification, and attaches the JSON to the Playwright report. The
no-external-network workflow also downloads the export. Missing API or export
wiring must fail explicitly; no skips or expected failures are permitted.

The production build embeds NEXT_PUBLIC_API_BASE_URL and NEXT_PUBLIC_API_MODE;
changing only the startup environment does not rebuild those values. CI sets live
mode during both build and startup, uses the committed backend lock and full Git
history, and runs the configured list/HTML reporters. Missing HTML artifacts fail
upload. Failed tests retain screenshots and traces even with zero retries.

The suite checks Calculate, Evaluate, grid, stress changes, invalid ARR 422
visibility, frozen enrollment request bodies, fresh Monte Carlo response
metadata, and a provenance-bearing JSON download. API schemas used by these
checks are defined in `backend/app/schemas.py` and the design/scenario routers.

## Validated handoff

2026-10-11, integrated main 86e834e (final assembly #128): all eight Chromium
checks pass with the production frontend, real local FastAPI responses,
Python 3.12.13 and locked backend dependencies. The final run took 6.8 seconds
excluding installation/build. Backend egress self-check, targeted TypeScript,
production build and whitespace checks also pass. The HTML report contains the
actual downloaded JSON attachment validated by the backend export schema.
