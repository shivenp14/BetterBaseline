# #75 isolated simulation panel handoff

This is preparation for #75, not completed #72/#76 integration. Only
MonteCarloPanel.tsx, MethodDisclosures.tsx, simulation-client.ts and
monte-carlo.* tests are delivered. Shared page/API/contracts/package files are
unchanged. The panel is unstyled semantic HTML.

## Interface and pending gate

`MonteCarloPanel` takes an immutable `SimulationSelection` (planned design,
frozen enrollment, exact selected baseline/dropout/effect, optional field
provenance), an injected `runSimulation(request, signal)`, optional
`unavailableReason`, and optional `onResult(result, request)`. Only the current
successful run reaches onResult, allowing parent export state to retain the
complete validated result. Keep the adapter reference stable across equivalent
parent rerenders. Pass a null selection or unavailable reason whenever the
parent's design/selection is stale, missing or invalid.

`createSimulationClient(transport)` wraps the eventual shared request helper,
checks cancellation before/after transport, validates runtime response fields,
and preserves both MCSEs, warnings, count aggregates, provenance and metadata.
The request uses the real #65 wire names (`provenance`, not `provenance_ledger`;
no UI-only `preset_id`). Selection/options identity includes both effects,
frozen N, dropout, alpha, target, seed, replicates and field sources.

At the last check, #72/#105 is unmerged. Its proposed API helper supplies
fixtures/local computations and does not yet expose the real simulation fetch
seam. C1's published EvaluateResponse also lacks the live optional simulation,
count aggregates, RNG/software and field-provenance shape. Local types here
mirror the merged #65 endpoint and must be reconciled with #72's final shared
contracts before readiness. Do not feed fixture-only evaluateScenario outputs
into this client as live simulations. #76 owns production assembly and export.

`createHttpSimulationTransport(baseUrl)` exists only as the isolated HTTP
acceptance seam until the final #72 helper is available. No competing production
page wiring or shared API changes are made. Final #75 acceptance still needs
that handoff and selected-state integration.

## Behavior

Seed/replicate defaults are 42/10,000. Bounds match merged #65: seed
0..2^32-1, replicates 1..100,000, equal enrollment at most 1,000,000 per arm.
Explicit Run submits one selected scenario. Edits immediately mark an existing
result stale and invalidate/abort active work. A monotonic generation counter
also rejects late responses from adapters that ignore cancellation. Unmount
aborts work; obsolete results never notify the parent. Requests cannot duplicate
while active, and an aborted identity can be selected and run again.

Two-sided and favorable fractions and MCSEs have separate labels. MCSE display
uses percentage points. Expected analytical counts, frozen enrollment and mean
actual retained/event counts are distinct. Null fixtures explain alpha versus
alpha/2; simulations are synthetic/conditional and do not predict efficacy.

## Reproduction

From frontend/ with installed existing dependencies:

```sh
./node_modules/.bin/tsc lib/simulation-client.ts components/MonteCarloPanel.tsx components/MethodDisclosures.tsx --strict --target ES2020 --module commonjs --moduleResolution node --jsx react-jsx --esModuleInterop --skipLibCheck --outDir /private/tmp/c6-render
C6_RENDER_ROOT=/private/tmp/c6-render NODE_PATH="$PWD/node_modules" node --test tests/monte-carlo.test.mjs
npm run typecheck
npm run lint
npm run build
```

In a disposable checkout, serve the real backend on 127.0.0.1:8000. Add a
temporary app/c6-harness/page.tsx containing:

```tsx
export { default } from "../../tests/monte-carlo.harness";
```

Run the frontend on 127.0.0.1:3000. Install Playwright/Chromium separately
without changing manifests and run:

```sh
PLAYWRIGHT_BROWSERS_PATH=/private/tmp/c6-browsers C6_PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs node tests/monte-carlo.browser.mjs
```

Remove the temporary page before the production build. The browser harness
uses fresh real backend responses, including its explicit delayed adapter that
ignores cancellation. Fixture objects are used only in the standalone unit and
server-render suite. Browser checks cover a fresh 10k seeded response, native
keyboard controls and bounds, one call per run, pending duplicate rejection,
out-of-order completion, effect/selection changes, failure/invalid/unavailable
states, and unmount abort. No final production workspace integration is claimed.
