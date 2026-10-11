# Issue #85 verification preparation

Before screenshots captured with T3 preview before styling workers were released:
- `before-desktop-1440.png`: 1440 × 900 CSS viewport.
- `before-mobile-375.png`: 375 × 812 CSS viewport (PNG uses device pixel scaling).
- Both show the initial unstyled live-mode Baseline collapse page; no calculate workflow was run before capture.
- Release marker: `/private/tmp/issue-85-before-ready`.

Services left running:
- Frontend http://127.0.0.1:3085, exec session 97792; `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8085 NEXT_PUBLIC_API_MODE=live npm run dev -- --hostname 127.0.0.1 --port 3085`.
- Backend http://127.0.0.1:8085, exec session 71588, PID 92218; `ALLOWED_ORIGINS='["http://127.0.0.1:3085","http://localhost:3085"]' .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8085`.
- Installed frontend via npm ci and backend via uv sync --locked --extra dev. Local sockets required approved sandbox escalation. No regression results claimed yet.
- Next generated frontend/AGENTS.md was removed as instructed. next-env.d.ts is dev generated and should be restored by the final production build.

## Regression command plan

Run from the worktree root unless a directory change is shown. Keep production build/E2E sequential with frontend dev usage because both use `.next`; stop/restart dev around the final build if required.

```sh
cd backend
.venv/bin/python -m pytest -q
cd ..
backend/.venv/bin/python -m unittest discover -s tests/integration -p 'test_*.py' -v
cd frontend
npm run lint
npm run typecheck
BACKEND_PYTHON="$PWD/../backend/.venv/bin/python" npm run test:backend-integration
BETTERBASELINE_CURVE_API=http://127.0.0.1:8085 node tests/power-curve.test.cjs
BETTERBASELINE_HEATMAP_API=http://127.0.0.1:8085 node tests/heatmap.test.cjs
EXPORT_TEST_PYTHON="$PWD/../backend/.venv/bin/python" node tests/export.test.cjs
./node_modules/.bin/tsc --strict --target ES2020 --module commonjs --moduleResolution node --jsx react-jsx --esModuleInterop --skipLibCheck --rootDir . --outDir /private/tmp/issue-85-workspace-tests tests/workspace-state.test.ts tests/stress-debounce.test.ts tests/workspace-export.test.ts lib/api.ts lib/debounce.ts lib/workspace-export.ts lib/workspace-state.ts
NEXT_PUBLIC_API_MODE=demo node /private/tmp/issue-85-workspace-tests/tests/workspace-state.test.js
NEXT_PUBLIC_API_MODE=demo node /private/tmp/issue-85-workspace-tests/tests/stress-debounce.test.js
NEXT_PUBLIC_API_MODE=demo node /private/tmp/issue-85-workspace-tests/tests/workspace-export.test.js
./node_modules/.bin/tsc lib/validation.ts components/DesignForm.tsx components/DesignSummary.tsx --strict --target ES2020 --module commonjs --moduleResolution node --jsx react-jsx --esModuleInterop --skipLibCheck --outDir /private/tmp/issue-85-c2
C2_VALIDATION_MODULE=/private/tmp/issue-85-c2/lib/validation.js C2_RENDER_ROOT=/private/tmp/issue-85-c2 NODE_PATH="$PWD/node_modules" node --test tests/design-form.validation.mjs tests/design-form.render.mjs
./node_modules/.bin/tsc lib/simulation-client.ts components/MonteCarloPanel.tsx components/MethodDisclosures.tsx --strict --target ES2020 --module commonjs --moduleResolution node --jsx react-jsx --esModuleInterop --skipLibCheck --outDir /private/tmp/issue-85-c6
C6_RENDER_ROOT=/private/tmp/issue-85-c6 NODE_PATH="$PWD/node_modules" node --test tests/monte-carlo.test.mjs
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001 NEXT_PUBLIC_API_MODE=live npm run build
cd ../tests/e2e
npm ci
npx playwright install chromium
npm test
```

E2E owns ports 8001/3001, starts real production services with reuseExistingServer=false, and includes the egress guard plus eight browser checks. Build-time public environment must match those ports. Do not modify active E2E tests.

## Live three-preset/export acceptance

At desktop and 375px, select Baseline collapse, Attrition shock, and Stable design in turn. For each: Calculate & Lock Design; verify current backend counts and provenance; change stress baseline/dropout and verify enrollment stays frozen; evaluate/grid; inspect curve, heatmap and table; Run simulation with seed 42 and 10,000 replicates; download current scenario JSON and reopen it. Verify methods, warnings, sources, both MCSEs, complete live results and canonical hash, plus keyboard access and no horizontal overflow. Capture after screenshots for direct comparison. Also verify invalid ARR, stale/pending/error output and export disabling.

Existing broader production browser/export script (repository-authorized Playwright workflow, no source changes needed): install tests/integration dependencies/browser if needed, then from frontend:

```sh
PAGE_URL=http://127.0.0.1:3085 PLAYWRIGHT_MODULE="$PWD/../tests/integration/node_modules/playwright/index.mjs" EXPORT_TEST_PYTHON="$PWD/../backend/.venv/bin/python" EXPORT_BROWSER_OUTPUT="$PWD/verification/issue-85/export-browser" node tests/export.browser.mjs
```

This script covers seven downloads/reopens, synthetic/manual/ARR and switched-preset exports, request races, failure recovery and schema/hash rejection. It does not replace the explicit three-preset responsive check. Legacy README statements that grid returns 501 are stale relative to the current integrated E2E docs and backend implementation.

# Final verification (2026-10-11)

Status: **verified for the tested states**. No source or active E2E test edits made by verification worker; no commits. Waited for `/private/tmp/issue-85-implementation-ready` before builds/browser acceptance. Final production build includes the dark backing stroke beneath the amber frontier (confirmed in emitted CSS).

## Commands and results

Commands below use the worktree root unless noted. All frontend commands run in `frontend/`.

| Check | Actual command | Result |
|---|---|---|
| Backend | `backend/.venv/bin/python -m pytest -q backend` | 373 passed, 179 subtests passed; 15 deprecation warnings |
| Integration fixtures | `backend/.venv/bin/python -m unittest discover -s tests/integration -p 'test_*.py' -v` | 14 passed |
| Lint | `npm run lint` | Passed, no warnings after removing unused verification import |
| Types | `npm run typecheck` | Passed |
| Real API adapter/export | `BACKEND_PYTHON="$PWD/../backend/.venv/bin/python" npm run test:backend-integration` | Passed; canonical requests, live grid, downloaded export/backend hash validation |
| Curve | `BETTERBASELINE_CURVE_API=http://127.0.0.1:8085 node tests/power-curve.test.cjs` | 15 passed |
| Heatmap | `BETTERBASELINE_HEATMAP_API=http://127.0.0.1:8085 node tests/heatmap.test.cjs` | 13 passed |
| Export | `EXPORT_TEST_PYTHON="$PWD/../backend/.venv/bin/python" node tests/export.test.cjs` | 9 passed |
| Workspace | Exact tsc + three node commands in baseline above | 16 state assertions plus debounce and export scripts passed |
| Form/validation | Exact C2 tsc + node command in baseline above | 72 passed |
| Simulation/disclosures | Exact C6 tsc + node command in baseline above | 13 passed |
| Production for E2E | `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001 NEXT_PUBLIC_API_MODE=live npm run build` | Passed |
| Unchanged real E2E | `npm test` in `tests/e2e/` | Egress guard passed; 8 browser tests passed, 4.3s |
| Final production for manual/responsive | `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8085 NEXT_PUBLIC_API_MODE=live npm run build` | Passed |
| Existing export browser | `PAGE_URL=http://127.0.0.1:3085 PLAYWRIGHT_MODULE="$PWD/../tests/integration/node_modules/playwright/index.mjs" EXPORT_TEST_PYTHON="$PWD/../backend/.venv/bin/python" EXPORT_BROWSER_OUTPUT="$PWD/verification/issue-85/export-browser" node tests/export.browser.mjs` | Passed; seven downloaded/reopened exports, 34 numerical requests, 9 selected simulations, no page errors |
| Responsive real workflows | `PAGE_URL=http://127.0.0.1:3085 EXPORT_TEST_PYTHON="$PWD/../backend/.venv/bin/python" node verification/issue-85/responsive.mjs` | Six workflows passed; three presets at each width |

Preparatory component runs before integration failed because intermediate CSS module imports were unavailable; final suites passed after integration/unit worker updates. Sandbox initially blocked local socket binding; authorized escalated real integration/E2E/browser checks passed. First responsive script incorrectly asserted response.fixed_enrollment, which is absent in the response contract. Corrected own script to assert actual evaluate request.fixed_enrollment; all six rerun workflows passed. This was a verification harness error, not a product issue.

## Acceptance evidence

- Baseline collapse, Attrition shock, Stable design: calculate → lock → stress baseline 0.12/dropout 0.25 → analytic evaluate → seed 42/10,000 simulation → grid → actual JSON download → backend validation → reopen. Each ran at 1440×900 and 375×812.
- Enrollment stayed frozen at 903, 951, and 951 per arm respectively. Every downloaded design and evaluation matched the full captured response with canonical provenance unwrapping; grid matched the full captured response exactly. No numerical success was mocked.
- Six canonical hashes/results are retained in `responsive-results.json`; full downloaded scenario artifacts are alongside it.
- Document scrollWidth did not exceed innerWidth initially, after calculate, after current results/export, or after heatmap keyboard selection in any of the six workflows. T3 independently measured 1440/1440 and 375/375.
- Native heatmap buttons focus and Enter selection passed for every preset/width. Existing export-browser also passed mouse, Enter, and Space selection. Invalid planning ARR submit moved focus to the invalid field with aria-invalid/aria-describedby and exposed an alert.
- Curve numerical table, heatmap power matrix, comparison enrollment table and simulation expected/sampled-count table remain present. T3 inspected their captions directly.
- Unchanged E2E verified actual invalid stress ARR HTTP 422. Existing export-browser checked invalid seed/planning/ARR, stale real grid and MC races, explicit injected 503 failure followed by real recovery, disabled export, modified hash/schema rejection, and reopening downloaded JSON. Injected failure was used only to establish error handling; successful numerical/export evidence used the real backend.
- T3 manual mobile stale state showed stale summary and disabled export, no overflow. Invalid planning ARR (25 percentage points > 21% baseline) exposed alert, focused invalid input and no overflow.

## Screenshots

Full-page production screenshots:
- `after-initial-1440.png`, `after-initial-375.png`.
- `after-current-{baseline-collapse-v1,attrition-shock-v1,stable-design-v1}-{1440,375}.png` (six files; calculated, stressed, simulation/current export/reopen state).

T3 preview screenshots, copied into verification directory:
- `t3-after-curve-desktop.png`: final curve and numerical alternative area.
- `t3-after-heatmap-mobile.png`: final 375px heatmap with clearly visible dark-backed amber dashed frontier and disclosures.
- `t3-after-stale-mobile.png`: stale planned summary.
- `t3-after-invalid-arr-mobile.png`: invalid planning ARR, focused field.

## Integration/service state and limits

- Original `frontend/next-env.d.ts` content restored by final production build; no diff. No generated frontend AGENTS.md remains.
- Frontend restored on 3085 as final **production** service, exec session 44834, with public API 8085/live. Backend 8085 preserved. Stopped original dev listener PID 92216 before build.
- Dependency preparation: `npm ci` in `tests/e2e` and `tests/integration`; Chromium installed. `tests/integration/node_modules/` is an untracked dependency directory; do not stage it.
- No claim of every UI state/device/browser. Error and late-response behavior tested by existing browser script at its 1280px viewport, not repeated at both responsive widths. No dedicated error/pending screenshot; stale and invalid screenshots retained. Keyboard focus/activation verified; exhaustive keyboard traversal and screen-reader testing remain outside this run.
- Logs are transient evidence and should not be staged in the PR. Keep report, script, results/export JSON and representative screenshots selectively.
