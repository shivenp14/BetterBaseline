# Better Baseline judge runbook (#83)

Prepare the device before the judge arrives. The 105-second walkthrough measures
an already installed, running application; installation and cold startup are
separate prerequisites. Use only synthetic assumptions. No patient data, NCT
lookup, registry access, or hosted service is required.

## Setup and readiness

Follow [README clean setup](../README.md#getting-started) with Python 3.12,
Node 24.15.0, npm and uv 0.9.26. Start the backend on 8000 and frontend on 3000.
Check `curl --fail http://127.0.0.1:8000/healthz`, open http://localhost:3000,
and confirm **LIVE**. A bundled preset shown before calculation is fixture
content, not evidence of a successful backend request. Keep an export directory
and a browser available. Do not start a package install during the walkthrough.

For production/offline startup use [#94 deployment instructions](DEPLOYMENT.md).
The frontend's API URL/mode are build-time settings. Changing an environment
variable on an already built server does not change the browser bundle.

## Narration and actions (105 seconds)

| Time | Action and narration |
| --- | --- |
| 0–15 s | Select **baseline-collapse-v1** under **Select Preset:**. “Better Baseline stress-tests a hypothetical two-arm trial with a binary adverse endpoint. Baseline risk is endpoint risk in the eligible control population, not population disease prevalence.” |
| 15–30 s | Click **Calculate & Lock Design**, then **Evaluate Stress Scenario**. “The plan uses control risk .20, RR .75, alpha .05 and target power .80: 903 participants per arm. At stress risk .10, conditional analytic power is about 47%. This is conditional on assumptions and test method, not a prediction that a treatment works.” |
| 30–45 s | Set stress baseline number to **0.12**, symmetric dropout to **0.13**, click **Evaluate Stress Scenario** and wait for SUCCESS. “Enrollment stays 903 per arm. Retained analytic counts are floored expected counts: 785 per arm. We change uncertainty, not the planned sample size.” |
| 45–60 s | Click **Load grid response from backend**. Inspect **Sensitivity heatmap** and power curve. “Columns are baseline risk; rows are dropout. The boundary uses our selected target. Invalid cells are null/masked, not zero power, and contours must not cross them. The curve is a slice at selected dropout.” |
| 60–75 s | Set **Simulation seed** to **42**, **Simulation replicates** to **10000**; click **Run simulation** and wait for results. “This simulates only the selected scenario at frozen enrollment. Analytic power is an approximation; Monte Carlo samples actual retention and uses its recorded test. Two-sided and favorable-direction fractions have separate MCSEs. Undefined tests count as nonrejections.” |
| 75–90 s | Click **Download current scenario JSON**. “This records complete assumptions, frozen enrollment, live design/evaluation/grid, separate MCSEs, seed, methods, hashes, software versions and per-field provenance. Synthetic origin does not mean clinically verified evidence.” |
| 90–105 s | Use **Reopen and validate scenario JSON** on that file; show **Valid complete v1**. “Reopening validates a detached artifact; it does not overwrite or replay the workspace. Reproduction needs the recorded environment. This is a planning demo, not clinical advice or a regulatory design tool; qualified statisticians must independently review real study decisions.” |

If a stress edit or seed change invalidates export, wait for the current analytic
result, reload the grid, then run the displayed simulation before downloading.
Do not present stale or fixture output as a completed live calculation.

## Recovery before presentation

1. **Cold backend:** check health, start the README backend command, wait for
   readiness, reload the page and repeat Calculate → Evaluate → Grid → Simulation.
   Connection errors or retryable 429 responses require waiting/retry, not a
   fabricated success. Plan startup time outside the 105-second narration.
2. **Registry or hosted service unavailable:** keep LIVE mode, choose the bundled
   synthetic preset and use the local backend. No trial lookup is necessary.
   A public deployment is optional; none is configured or tested here.
3. **External network unavailable:** use dependencies already installed and the
   local commands, or prebuilt Docker images with
   `docker compose up -d --no-build --pull never --wait`. Preserve loopback.
   See Deployment for image/build prerequisites; cold image pulls cannot work
   offline. The local live calculation/export is the acceptance fallback.
4. **Backend cannot be restored:** change `NEXT_PUBLIC_API_MODE=demo` in
   `frontend/.env.local`, restart `npm run dev` (or rebuild production), reload,
   select baseline-collapse-v1 and show the visible **DEMO** warning. This is a
   fixture-backed exploration with client analytic calculations; live simulation
   and complete current export are unavailable. It supports an honest visual
   fallback, but does not satisfy real offline calculation/export acceptance.
   Restore `live` and restart/rebuild when the backend recovers.

## Repeatable validation

The validation checkout must contain merged #94 and #118 prerequisites as well as
#83. Keep #118's tests/workflow unmodified. #94 merged into main at `53f7fd1`
after refreshing its head to `1a4af92`; #118 merged at `f07092f`. The #83 PR
now targets main and contains only README.md, this runbook, and `scripts/demo/**`.
Recheck the combined source after main updates before final acceptance or a release tag.

After clean backend/frontend installation, in that checkout:

```bash
cd tests/e2e
npm ci
npx playwright install chromium
cd ../../frontend
NEXT_PUBLIC_API_MODE=live NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001 npm run build
cd ../tests/e2e
npm test
cd ../..
node scripts/demo/rehearse.mjs --pace
node scripts/demo/rehearse.mjs --offline --pace
node scripts/demo/fixture-recovery.mjs
```

Free ports 8001/3001 first, and 3002 for fixture recovery. Run these commands sequentially. Fixture recovery starts a separate development frontend in DEMO mode, allows only its own origin, and verifies the labeled preset while complete export and live simulation remain unavailable. The runner owns and stops its local services; it uses
#118's locked Playwright package and backend guard. Reports, downloaded JSON and
screenshots go to ignored `scripts/demo/reports/{online,offline}/`. Optional
`DEMO_REPORT_DIR` changes the artifact directory. `--pace` places actions at the
narrated times and ends at 105 seconds; without it the runner is a fast diagnostic.
It checks fresh changed stress power, 903/arm enrollment, full export equality
with received responses, backend ExportPayload validation and successful UI
reopen. It never intercepts statistical success responses.

Offline mode blocks browser HTTP/WebSockets outside exact local origins and
uses #118's backend socket/DNS guard plus its self-check. The host network is
still available: this is scoped process isolation, not a device-wide air gap.
#94 separately records real Docker internal-network isolation and image IDs in
[its report](../infra/deploy/offline-report.json). Docker is not available in
this #83 environment; that container experiment is dependency evidence, not a
new #83 container run.

## Measured evidence and acceptance gates

On 2026-10-11, clean installation succeeded with Python 3.12.13, Node 24.15.0
and uv 0.9.26. Production build, frontend lint/typecheck and 368 backend/fixture
tests (plus 212 subtests) passed. The unmodified #118 E2E suite also passed
all 8 tests in 4.3 seconds against the combined production build. See [setup identities](../scripts/demo/evidence/setup.json).
The temporary assembly commit was `912b9eeb9186ba3beb2eb15ae607723cd291e747`
(ca6dc37 + 4322bd0). These temporary commits are local validation identities;
reconstruct the assembly from the recorded dependency heads and scoped sources.

| Rehearsal | Tested temporary commit | Time | Outcome |
| --- | --- | --- | --- |
| Network available | 82b9fb6b904e6751c7e68281df3b5dc8836dcac9 | 105.017 s | Real seeded local export validated and reopened |
| Scoped offline | 80216ea7a8260d0b5547c457219a7705f8e46937 | 105.008 s | Same live flow; browser and backend egress blocked |

Both runs retained 903 per arm, measured initial stress power .46999657396642885
and fresh .12/.13 stress power .4934706317083697, and recorded zero page errors
or external browser requests. Exact action times, Chromium identity and export
hashes are in the [online report](../scripts/demo/evidence/online-report.json)
and [offline report](../scripts/demo/evidence/offline-report.json). The actual
[offline downloaded JSON](../scripts/demo/evidence/offline-scenario.json) is retained
for inspection; its hash matches the report. The [fixture recovery report](../scripts/demo/evidence/fixture-report.json)
records a visible 903/arm DEMO calculation with only the frontend origin allowed,
complete export disabled and live simulation unavailable.

Dependency outcomes checked during this run: #82/#117 merged at bf327a8;
#76/#128 merged at 86e834e; #78/#118 merged at f07092f (handoff 4322bd0 had three
passing checks). These are the original rehearsal's dependency identities.
Subsequently, #94 refreshed to `1a4af92` and merged into main at `53f7fd1`;
#83 incorporated that parent and retargeted main. Later main UI/narrative updates
are incorporated normally; the recorded rehearsals above do not establish
acceptance of those updates. The independent teammate must test the final head.
No end-to-end hosted backend rehearsal is claimed.

A timed automated browser rehearsal demonstrates the actions fit the narration budget;
it is not an independent teammate usability test. Do not mark that human
acceptance or a demo-ready tag complete without the actual handoff and CI/core
acceptance. #85 remains reserved for the user.
