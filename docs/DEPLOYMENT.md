# Deployment draft (#81)

The backend builds and serves real calculate/evaluate requests from the committed
dependency lock. The merged workspace now makes live calculate/evaluate/grid calls. Export and
fresh offline acceptance await #76; this draft does not close #81.
No public deployment has been verified.

## Local startup

From the repository root, once the frontend live adapter is available:

```sh
python3 infra/deploy/check_prerequisites.py
cp .env.example .env
docker compose config
docker compose build
docker compose up -d --wait
curl --fail http://localhost:8000/healthz
```

The prerequisite checker passes with the merged live adapter. It checks source
presence only; passing it does not replace browser or offline acceptance.
Both ports bind loopback. Open http://localhost:3000; the browser API address is
localhost:8000, not Compose's internal backend DNS. For another device or hosted
UI, provide a reachable HTTPS API origin and allow that UI origin through
ALLOWED_ORIGINS (comma-separated or JSON list). No wildcard origin is configured.
NEXT_PUBLIC_API_BASE_URL is embedded at build time: rebuild the frontend when
changing it.

The backend uses Python 3.12, pinned uv 0.9.26 and `uv sync --locked --no-dev`.
Its base image is pinned to the tested digest. The frontend uses npm's committed
lockfile and a tested, pinned Node 24 image digest.
Both runtimes run as non-root users with health checks. One backend worker avoids
duplicating process-local caches; #68 owns bounded concurrency and readiness.
The frontend explicitly copies app/lib/components; include public assets if a
later handoff adds them.

## Managed proxy builds

Preserve Docker's configured proxy settings. Pass the required CA as an optional
BuildKit secret while keeping TLS verification enabled:

```sh
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -f infra/docker/backend.Dockerfile -t betterbaseline-backend .
docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" --build-arg NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 -f infra/docker/frontend.Dockerfile -t betterbaseline-frontend .
```

Secrets are mounted only during dependency installation and are not copied into
images. Ordinary Compose builds target devices with standard public CA trust.

## Verified local evidence (2026-10-11 UTC)

- The committed lock installs; 292 backend/fixture tests and 183 subtests pass.
- Docker 28.4.0 builds the backend from Python base digest
  `sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258`.
  Tested local image ID:
  `sha256:d21482240c4baea55044b86c45c4c9954a3620a2cb4b7b333c737bf1176eede9`.
  Container UID 10001; built-in health check healthy.
- Real HTTP calculate/evaluate checks pass: 903 evaluable per arm, 1,004 enrolled
  with planned dropout .10, and stressed analytic power 0.46999657396642797.
  Repeated seed 42 results match; changed dropout preserves enrolled counts and
  changes the input hash. Responses validate against the running app's OpenAPI.
  Software: Python 3.12.15, NumPy 2.5.4, SciPy 1.18.1, statsmodels 0.15.0.
- CORS preflight allows http://localhost:3000 (HTTP 200 with that exact origin)
  and rejects https://not-allowed.example (HTTP 400).
- Earlier frontend preparation built image
  `sha256:488bdc479ac8568051aee20d8d660aa8af28023093fe277ded11d0a7c3a42f72`
  from Node base digest
  `sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20`.
  UID 1000, healthy, GET / HTTP 200; Chromium rendered the fixture shell.
  This was not live UI or offline acceptance.

Run the point checker against a locally running backend:

```sh
uv run --project backend --locked --extra dev python tests/integration/run_point_checks.py --base-url http://127.0.0.1:8000
```

## Remaining acceptance

Record commit, image digests, software/browser versions, date and actual requests
and results. Hand-authored presets are inputs, not measured output.

1. In the real browser, calculate .20/RR=.75: 903 evaluable per arm and 1,004
   enrolled with planned dropout .10. Stress .10 at frozen 903/no dropout: ~.470.
2. Simulate with seed 42; inspect separate MCSE fields, retained means,
   method/software/RNG metadata and finite JSON.
3. Exercise nonsquare grid axes and an invalid ARR cell; verify null masking
   and agreement with the selected point at the same dropout.
4. Independently download the UI export; inspect assumptions, fixed counts,
   seed/method metadata and per-field provenance. Confirm real API network calls.
5. Prebuild dependencies/images, disconnect external internet but preserve
   loopback, then run `docker compose up -d --no-build --pull never --wait`.
   Change to fresh inputs and repeat calculate/stress/grid/simulate/export.
   Registry lookup may fail; manual inputs and synthetic presets must work.
   Cached results alone do not pass. Do not rebuild or pull during this check.

Record failures explicitly. Hosted acceptance needs reachable services and a
browser CORS smoke. A complete local fallback still needs the live UI and fresh
offline flow. Stop services with `docker compose down`; no database is required.


## Live workspace verification after #72/#68 (2026-10-11 UTC)

Source base: main `9bedacc16fd8deb23b6f7ea5a9613518d6ff0818` plus this
PR's scoped container files. Both frontend build/runtime stages now pin the
Node digest recorded above. No external preset JSON is imported by the frontend;
its typed synthetic preset data are included in the bundle.

- Backend image: `sha256:8468a215586d729a99f81ac66b178cde4f93f05226adf645c4ca4b9390228698`.
- Frontend image: `sha256:580636b64db4bc94864b45178b8811aeb2b3e259c58c40db12da3000290137a2`.
  This smoke build embeds `NEXT_PUBLIC_API_BASE_URL=http://localhost:8104`;
  tested UI origin is http://localhost:3104 and backend ALLOWED_ORIGINS matches it.
  Compose defaults remain the standard 3000/8000 ports.
- Both health checks report healthy; runtime users are app (UID 10001) and
  node (UID 1000). Headless Chromium 154.0.8037.57 opens the built LIVE workspace.
- Click Calculate & Lock Design: real POST returns HTTP 200 and locks 903/arm.
  Set stress risk .12 and dropout .13, then Evaluate Stress: HTTP 200, enrollment
  stays 903/arm, expected retained counts are 785/arm, analytic power is
  0.4934706317083679, and 10,000 Monte Carlo replicates use seed 42.
  Load grid response from backend: HTTP 200, selected risk/dropout .12/.13 and
  the same frozen counts. No browser page errors occur.
- Real calculate/evaluate/grid HTTP integration also passes against this backend
  image, including the canonical ~.470 case, 2×3 cell/point agreement, exact .13
  dropout curves and two invalid ARR cells. Software is Python 3.12.15 / NumPy
  2.5.4 / SciPy 1.18.1 / statsmodels 0.15.0.
- Refreshed locked host environment: 320 backend/fixture tests, 201 subtests and
  14 invariant regressions pass. Compose configuration and prerequisites pass.

This verifies live container/browser calculations and seeded simulation, not
final chart assembly, independently downloaded exports, public hosting or a
complete fresh offline rehearsal. The earlier fixture-shell evidence is
historical; the LIVE browser checks above establish the current tested scope.
