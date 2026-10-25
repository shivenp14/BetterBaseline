# Deployment and offline fallback (#81)

The assembled LIVE application has been built and verified against the local
backend, including fresh inputs, seeded simulation and independently downloaded
JSON exports. No public hosting account/project or target is configured in this
task, so no public URL is claimed. The verified judge-device fallback uses
preinstalled container images and bundled synthetic presets.

## Local startup

From a clean checkout with Docker installed:

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

## Verified complete offline rehearsal

The product source is main `86e834efd50aba6ba1951c5bb0f052c463846867`.
[Recorded evidence](../infra/deploy/offline-report.json) contains the exact image
IDs, browser version, counts, seeds, request totals and export hashes. Backend
and frontend images build successfully, run as app (UID 10001) and node (UID
1000), and report healthy. The frontend production build includes TypeScript.

The two prebuilt containers ran on a Docker internal network with no external
route. A backend socket probe to 1.1.1.1:443 failed with ENETUNREACH (101).
Loopback TCP relays exposed their internal API/UI ports for Chromium; these
relays only carry local connections. Browser HTTP and WebSocket routing allowed
only the exact local frontend/backend origins and blocked service workers.

Eight real browser POST responses succeeded. Calculate locked 903 enrolled per
arm; the baseline-collapse analytic power was approximately .470. Fresh stress
inputs (.12 risk, .13 dropout), seed 43 and 1,000 replicates preserved enrollment
and recorded manual provenance. Repeating that seed produced identical complete
Monte Carlo aggregates. Three real JSON downloads passed the committed schemas,
complete response/provenance checks and the UI reopen validator. There were zero
page errors or external browser requests. This verifies fresh local calculations,
not cached illustrative output. Separate HTTP checks passed 1,004 enrollment
inflation, nonsquare 2×3 grid/point agreement, exact .13 dropout curves and two
invalid ARR cells. Backend software: Python 3.12.15, NumPy 2.5.4, SciPy 1.18.1,
statsmodels 0.15.0. Compose configuration and source prerequisites pass.

## Judge-device rehearsal

Build and install dependencies while online using the local startup above. Then
disconnect external connectivity, preserving loopback, and start without a pull
or rebuild:

```sh
docker compose up -d --no-build --pull never --wait
```

Open http://localhost:3000. Calculate & Lock Design, change stress baseline and
dropout, inspect the heatmap/curve, select seed/replicates and click Run simulation.
Download current scenario JSON and reopen it through the file control. Verify
that fresh values change results, enrollment stays frozen, MCSE fields remain
separate and field provenance survives. Manual input and presets require no
registry service. Stop with `docker compose down`.

PR #100 adds an independently repeatable production-browser capture runner under
`tests/integration/`, with real HTTP/download validation and an offline socket
guard. It owns the CI version of this acceptance flow. Its recorded artifacts
retain raw requests, responses and downloaded files; this deployment report
records the separate container build and isolation evidence.
