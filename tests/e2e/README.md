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

Current main includes live Calculate/Evaluate/grid wiring. The suite uses the
current preset selector and decimal-fraction stress fields, selects ARR
explicitly in the planning form, checks the actual backend error in the visible
stress section, and compares every rendered grid cell with the live response.
The shipped presets use RR; attrition-shock is not an ARR preset.

Main now includes the export/provenance handoff from PRs #126/#127. The export
check uses the current Download current results (JSON) control and requires an
actual download with the captured design, evaluation, grid and frozen enrollment,
plus provenance and software metadata. It validates the downloaded JSON with the
backend ExportPayload contract, including canonical inputs-hash verification,
and attaches the JSON to the Playwright report. Evaluation hashes allow the
canonical sha256: prefix. The no-external-network workflow also downloads the
export. Missing API or export wiring must fail explicitly; no skips or expected
failures are permitted.

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

2026-10-11, integrated main a2b3f2a (including #97/#115/#117/#126/#127): all eight
Chromium checks pass with the production frontend, real local FastAPI responses,
Python 3.12.13 and locked backend dependencies. The final run took 5.2 seconds
excluding installation/build. Backend egress self-check, targeted TypeScript,
production build and whitespace checks also pass. The HTML report contains the
actual downloaded JSON attachment. Earlier missing-export runs failed both
export-dependent checks and retained HTML/screenshots/traces, confirming that
absent wiring cannot satisfy acceptance. Final product assembly remains #76's
responsibility; this evidence covers the tested acceptance flow.
