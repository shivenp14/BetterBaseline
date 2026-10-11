# Deployment draft (#81)

This configuration is preparation, not a working live deployment. #68 must
supply the registered FastAPI app, dependency manifest, health endpoint and
CORS settings; #76 must replace the frontend fixture adapter with live calls.
The prerequisite check fails on the current branch. It is a source heuristic,
not a substitute for the browser acceptance below. No hosting account or
outbound deployment identity is configured in the current execution environment;
no public URL has been deployed or verified.

## Build and local startup after the handoffs

From the repository root:

```sh
python3 infra/deploy/check_prerequisites.py
cp .env.example .env
docker compose config
docker compose build
docker compose up -d --wait
curl --fail http://localhost:8000/healthz
```

Open http://localhost:3000 on the judging device. Both published ports bind
loopback. The browser URL is localhost:8000, not Compose's internal backend DNS.
For a different browser device or hosted UI, supply the publicly reachable
HTTPS API origin at build time and allow that UI origin in backend CORS.
`NEXT_PUBLIC_API_BASE_URL` is baked into Next.js bundles: changing a running
container's environment does not change it; rebuild the frontend.
Confirm `CORS_ORIGINS` and its string/list encoding against #68's final settings
before running. No wildcard origin is proposed.

The frontend uses the existing npm lockfile. The backend installs the package
owned by #64, without defining a second dependency list here. Before freezing
this draft, verify that the package installs uvicorn and all runtime numerical
libraries, commits a dependency lock and runs on Python 3.12. Pin both base
images to the tested digest before acceptance. The current major/minor image
tags are provisional. The frontend copies the current app/lib/components files
explicitly to exclude host dependencies; add public assets if later handoffs
introduce them. No standalone Next.js configuration is assumed.

Both runtimes use non-root users and service health checks. A single backend
worker avoids duplicating a process-local cache; #68 remains responsible for
bounded compute/concurrency and readiness semantics. A successful health check
alone does not prove that calculations or CORS work.

## Proxy builds in the managed environment

Preserve Docker's configured proxy settings. When its CA is required, build
images with a BuildKit secret (a combined system CA bundle for pip):

```sh
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -f infra/docker/backend.Dockerfile -t betterbaseline-backend .
docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" --build-arg NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 -f infra/docker/frontend.Dockerfile -t betterbaseline-frontend .
```

These optional mounts exist only during dependency installation. Keep TLS
verification enabled; do not bake session credentials or proxy CA into images.
Compose's ordinary build is intended for a device with standard public trust.

## Required fresh calculation and offline evidence

After #68/#76 merge, record commit, image digests, Python/NumPy/SciPy/statsmodels
versions, browser version, date and actual requests/results. The current
hand-authored presets are illustrative and are not measured acceptance output.

1. In the real browser, calculate the .20/.75 RR design. Confirm 903 evaluable
   per arm and 1,004 enrolled with 10% planned dropout.
2. Change stress baseline to .10 at frozen 903 enrolled/no dropout. Confirm
   analytic power approximately .470 without changing the enrollment.
3. Run selected-point simulation with seed 42. Confirm separate MCSE fields,
   method/software/RNG metadata, actual retained means and finite JSON.
4. Exercise grid baseline/dropout axes and an invalid ARR cell. Confirm null
   masking and agreement with the selected point at exactly the same dropout.
5. Export and inspect assumptions, fixed counts, seed/method metadata and
   per-field provenance. Inspect browser network requests to confirm real API
   responses with an allowlisted Origin, rather than fixture output.
6. Preinstall/build all dependencies and images, then disconnect external
   internet while keeping loopback networking. Start with
   `docker compose up -d --no-build --pull never --wait`. Change inputs to a new
   value and repeat calculate/stress/grid/simulate/export through the local API.
   Registry lookup may fail; manual inputs and synthetic presets must still work.
   Do not rebuild or pull during this test. Cached results alone do not pass.

Record failures explicitly. Do not mark #81 complete until container startup,
real browser requests and fresh offline calculations pass. Hosted verification
requires both publicly reachable services and a browser CORS smoke; absent a
hosting account, record the exact limitation and demonstrate the complete local
fallback. UI fixture mode is a labeled degraded supplement only.

Stop services with `docker compose down`. No volumes or database are required.
