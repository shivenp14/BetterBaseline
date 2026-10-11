# Planning form acceptance (#71)

The form uses explicit percent/percentage-point inputs and a decimal RR. The
parent receives the C1 `CalculateRequest` and draft-change notifications; #72
owns production API/state/page wiring and per-field provenance. Initial values
apply on mount; remount with a new key when changing presets. Summary props
accept the real #64 numerical response with optional parent-provided provenance
and an explicit mock flag for fixtures. Missing source metadata is disclosed.

From `frontend/` after `npm ci`, run:

```sh
./node_modules/.bin/tsc lib/validation.ts components/DesignForm.tsx components/DesignSummary.tsx --strict --target ES2020 --module commonjs --moduleResolution node --jsx react-jsx --esModuleInterop --skipLibCheck --outDir /private/tmp/c2-render
C2_VALIDATION_MODULE=/private/tmp/c2-render/lib/validation.js C2_RENDER_ROOT=/private/tmp/c2-render NODE_PATH="$PWD/node_modules" node --test tests/design-form.validation.mjs tests/design-form.render.mjs
npm run typecheck
npm run lint
npm run build
```

## Real browser/API acceptance

Use a disposable checkout of this branch. Start its backend on 127.0.0.1:8000
with its documented dependencies and `python -m uvicorn app.main:app`. In the
disposable frontend, add `app/c2-harness/page.tsx` containing only:

```tsx
export { default } from "../../tests/design-form.harness";
```

Run `npm run dev -- --hostname 127.0.0.1` on port 3000. Install Playwright and
Chromium separately, without changing this project's manifests/lockfile:

```sh
npm install --prefix /private/tmp/c2-browser playwright
PLAYWRIGHT_BROWSERS_PATH=/private/tmp/c2-browsers /private/tmp/c2-browser/node_modules/.bin/playwright install chromium
PLAYWRIGHT_BROWSERS_PATH=/private/tmp/c2-browsers C2_PLAYWRIGHT_MODULE=/private/tmp/c2-browser/node_modules/playwright/index.mjs node tests/design-form.browser.mjs
```

The harness removes C1's UI-only `preset_id` before sending the numeric API
request. It uses fresh network calculations; successful responses are never
mocked. Its state and adapter are acceptance scaffolding, not production wiring.
The browser script checks keyboard submission, first-invalid-field focus,
invalid ARR with no request, RR draft preservation, exact fraction payload,
903/1004 real counts, changed dropout, stale/failure states, and pending duplicate
blocking. Remove the temporary page before the final production build.

Verified 11 October 2026 against main `da6986e`: 69 parser/render tests and the
Chromium acceptance script passed. The real endpoint returned 903 evaluable and
1004 enrolled per arm at 10% dropout, and 903/903 at zero dropout. Source metadata
was absent in the live response and was displayed as unavailable. No production
page/API/contracts/package changes are part of #71.
