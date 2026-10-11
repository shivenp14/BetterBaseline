# E2E acceptance suite

This suite exercises the browser against the local production frontend and the
real FastAPI service. A passing result requires the UI to make actual API
requests. Fixture-only responses, intercepted success responses, skipped
exports, or expected failures do not satisfy acceptance.

## Local setup and run

From the repository root, install the backend and frontend dependencies and
build the production frontend:

```sh
cd backend && uv sync --extra dev
cd ../frontend && npm ci
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001 npm run build
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

At head `9adf3f6`, the page is explicitly a mock-only shell: `frontend/lib/api.ts`
returns local fixtures without network I/O, and no export control is present.
Consequently the acceptance suite is expected to fail with explicit
`[E2E integration pending #76]` errors until #76 connects the UI to the API and
assembles the export flow. These failures are intentional regression checks;
do not resolve them with skips or expected-failure annotations.

The suite checks Calculate, Evaluate, grid, stress changes, invalid ARR 422
visibility, frozen enrollment request bodies, fresh Monte Carlo response
metadata, and a provenance-bearing JSON download. API schemas used by these
checks are defined in `backend/app/schemas.py` and the design/scenario routers.
