# Deployment draft (#81)

The backend builds and serves real calculate/evaluate requests from the committed
dependency lock. The frontend still uses fixtures. Full browser, grid, export and
fresh offline acceptance await #66/#68/#76; this draft does not close #81.
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

The prerequisite checker currently fails on the missing frontend fetch seam.
It is a source heuristic; passing it does not replace browser acceptance.
Both ports bind loopback. Open http://localhost:3000; the browser API address is
localhost:8000, not Compose's internal backend DNS. For another device or hosted
UI, provide a reachable HTTPS API origin and allow that UI origin through
ALLOWED_ORIGINS (comma-separated or JSON list). No wildcard origin is configured.
NEXT_PUBLIC_API_BASE_URL is embedded at build time: rebuild the frontend when
changing it.

The backend uses Python 3.12, pinned uv 0.9.26 and `uv sync --locked --no-dev`.
Its base image is pinned to the tested digest. The frontend uses npm's committed
lockfile; its Node image tag still needs pinning before final acceptance.
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
