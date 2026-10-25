// Production acceptance against a fresh local backend; numerical responses are
// never mocked. Routes only delay real responses or inject explicit failures.
// PAGE_URL, PLAYWRIGHT_MODULE, optional CHROMIUM_EXECUTABLE and EXPORT_TEST_PYTHON.
import assert from "node:assert/strict";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { pathToFileURL } from "node:url";
const { chromium } = await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE).href);
const browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {}) });
const output = process.env.EXPORT_BROWSER_OUTPUT || "/private/tmp/issue76-browser-acceptance";
await mkdir(output, { recursive: true });
const errors = [], requests = [], downloads = [];
const page = await browser.newPage({ acceptDownloads: true, viewport: { width: 1280, height: 900 } });
page.on("pageerror", error => errors.push(error.message));
page.on("request", request => { if (request.method() === "POST" && request.url().includes("/api/v1/")) requests.push({ url: request.url(), body: request.postDataJSON() }); });
const run = () => page.getByRole("button", { name: "Run simulation", exact: true });
const exportLink = () => page.getByRole("link", { name: "Download current scenario JSON", exact: true });
const disabledExport = () => page.getByRole("button", { name: "Download current scenario JSON", exact: true });
const mcCalls = () => requests.filter(r => r.url.endsWith("/evaluate") && r.body.simulation !== null);
async function go(pathname, label) {
  if (new URL(page.url()).pathname !== pathname) {
    await page.getByRole("link", { name: label, exact: true }).click();
    await page.waitForURL((url) => url.pathname === pathname);
  }
}
async function charts() {
  await page.waitForFunction(() => document.querySelector('section[aria-labelledby="grid-heading"] span')?.textContent.includes("SUCCESS"));
  const disclosure = page.getByText("Advanced: inspect range charts and grid data", { exact: true });
  if (!(await disclosure.evaluate((summary) => summary.parentElement?.hasAttribute("open")))) await disclosure.click();
  await page.locator("[data-cell]").first().waitFor();
}
async function calculate() {
  await go("/plan", "Plan");
  await page.getByRole("button", { name: "Calculate & Lock Design", exact: true }).click();
  await go("/stress-test", "Stress-test"); await charts();
}
async function simulate() {
  await go("/simulation", "Simulation");
  const before = mcCalls().length;
  await run().click(); await page.getByText("Current simulation.", { exact: false }).waitFor();
  assert.equal(mcCalls().length, before + 1, "Exactly one selected-point simulation per submit");
  await go("/methods", "Methods"); await exportLink().waitFor();
}
async function download(name) {
  await go("/methods", "Methods");
  const pending = page.waitForEvent("download"); await exportLink().click(); const file = await pending;
  const filename = path.join(output, `${name}.json`); await file.saveAs(filename);
  const data = JSON.parse(await readFile(filename, "utf8"));
  assert.match(data.inputs_hash, /^sha256:[a-f0-9]{64}$/);
  assert.ok(data.evaluation_result.monte_carlo.rng);
  assert.ok(data.evaluation_result.monte_carlo.software_versions.numpy);
  assert.ok(data.grid_result.contour_segments); assert.ok(data.grid_result.power_curve);
  const checked = spawnSync(process.env.EXPORT_TEST_PYTHON || "python3", ["-c", "import json,sys; from app.schemas import ExportPayload; from app.routers.scenarios import EvaluationResponse; p=json.load(open(sys.argv[1])); assert 'inputs_hash' in p; e=ExportPayload.model_validate(p); assert e.inputs_hash==p['inputs_hash']; assert EvaluationResponse.model_validate(p['evaluation_result']).model_dump(mode='json')==p['evaluation_result']", filename], { cwd: path.resolve("../backend"), encoding: "utf8" });
  assert.equal(checked.status, 0, checked.stderr);
  await page.getByLabel("Reopen and validate scenario JSON", { exact: true }).setInputFiles(filename);
  await page.getByText(/^Valid complete v1 scenario exported/).waitFor();
  downloads.push({ name, filename, hash: data.inputs_hash, enrollment: data.fixed_enrollment, seed: data.evaluation_result.monte_carlo.seed, replicates: data.evaluation_result.monte_carlo.replicates });
  return data;
}
try {
  await page.goto(process.env.PAGE_URL);
  assert.equal(new URL(page.url()).pathname, "/plan");
  for (const heading of ["Plan a trial", "Planning assumptions", "Enrollment estimate"]) assert.equal(await page.getByRole("heading", { name: heading, exact: true }).count(), 1);
  await page.getByLabel("Control group event rate (%)", { exact: true }).fill("20.");
  await go("/stress-test", "Stress-test");
  assert.equal(await page.getByRole("heading", { name: "Planning assumptions", exact: true }).count(), 0);
  await go("/plan", "Plan");
  assert.equal(await page.getByLabel("Control group event rate (%)", { exact: true }).inputValue(), "20.", "partially entered form draft survives route unmount/remount");
  await page.getByLabel("Control group event rate (%)", { exact: true }).fill("20");
  await go("/methods", "Methods");
  for (const heading of ["Methods and records", "Current results and export", "Assumption sources and audit trail", "Historical case study"]) assert.equal(await page.getByRole("heading", { name: heading, exact: true }).count(), 1);
  assert.equal(await disabledExport().isDisabled(), true);
  await calculate();
  assert.equal(mcCalls().length, 0, "Automatic stress refresh is analytic only");
  for (const heading of ["Stress-test the plan", "Planned design and selected analytic scenario", "Compare a range of assumptions"]) assert.equal(await page.getByRole("heading", { name: heading, exact: true }).count(), 1);
  assert.equal(await page.getByRole("heading", { name: "Planning assumptions", exact: true }).count(), 0, "stress-test route mounts only its relevant content");
  assert.ok(await page.locator('[data-curve-segment]').count());
  await page.goBack(); assert.equal(new URL(page.url()).pathname, "/plan", "browser Back restores the prior page URL");
  assert.equal(await page.getByLabel("Control group event rate (%)", { exact: true }).inputValue(), "20");
  await page.goForward(); assert.equal(new URL(page.url()).pathname, "/stress-test", "browser Forward restores the current page URL");
  await simulate(); const synthetic = await download("synthetic");
  assert.equal(synthetic.fixed_enrollment.control, 903);
  assert.equal(synthetic.provenance["/planned_design/control_event_rate"].source, "manual_user",
    "editing and restoring the displayed baseline records a manual draft edit");

  // Exact heatmap selection plus keyboard selection; enrollment remains frozen.
  await go("/stress-test", "Stress-test");
  await charts();
  const cell = page.locator('[data-cell="1-2"]');
  const baseline = Number(await cell.getAttribute("data-baseline")), dropout = Number(await cell.getAttribute("data-dropout"));
  const beforeSelection = mcCalls().length; await cell.click();
  await go("/methods", "Methods"); assert.equal(await disabledExport().isDisabled(), true);
  await go("/stress-test", "Stress-test"); await charts();
  assert.equal(mcCalls().length, beforeSelection);
  assert.equal(Number(await page.locator("#stress-baseline-num").inputValue()), baseline);
  assert.equal(Number(await page.locator("#stress-dropout-num").inputValue()), dropout);
  const keyboard = page.locator('[data-cell="0-1"]'); await keyboard.focus(); await keyboard.press("Enter"); await charts();
  const spaceCell = page.locator('[data-cell="2-3"]'), spaceDropout = Number(await spaceCell.getAttribute("data-dropout"));
  await spaceCell.focus(); await spaceCell.press("Space"); await charts();
  assert.equal(Number(await page.locator("#stress-dropout-num").inputValue()), spaceDropout);
  await go("/simulation", "Simulation");
  await page.getByLabel("Simulation seed", { exact: true }).fill("43");
  await page.getByLabel("Simulation replicates", { exact: true }).fill("1000");
  await go("/methods", "Methods");
  assert.equal(await disabledExport().isDisabled(), true);
  // Submit immediately, before the debounce expires: no analytic cancellation of MC.
  await simulate(); const manual = await download("manual-selected");
  assert.deepEqual(manual.fixed_enrollment, synthetic.fixed_enrollment);
  assert.equal(manual.evaluation_result.monte_carlo.seed, 43);
  assert.equal(manual.evaluation_result.monte_carlo.replicates, 1000);
  assert.equal(manual.provenance["/simulation/seed"].source, "manual_user");
  assert.equal(manual.provenance["/stress_scenario/dropout/control"].source, "manual_user");

  // Hash validation rejects a modified on-disk scenario.
  const tampered = { ...manual, inputs_hash: "sha256:" + "0".repeat(64) };
  const tamperedPath = path.join(output, "tampered.json"); await writeFile(tamperedPath, JSON.stringify(tampered));
  await page.getByLabel("Reopen and validate scenario JSON", { exact: true }).setInputFiles(tamperedPath);
  await page.getByRole("alert").filter({ hasText: "inputs_hash does not match" }).waitFor();
  await go("/simulation", "Simulation");
  await page.getByLabel("Simulation seed", { exact: true }).fill("invalid");
  assert.equal(await run().isDisabled(), true); await go("/methods", "Methods"); assert.equal(await disabledExport().isDisabled(), true);
  await go("/simulation", "Simulation");
  await page.getByLabel("Simulation seed", { exact: true }).fill("44"); await go("/stress-test", "Stress-test"); await charts();

  // Explicit simulation failure hides export; restoring the real transport recovers.
  await go("/simulation", "Simulation");
  await page.route("**/api/v1/scenarios/evaluate", async route => {
    if (route.request().postDataJSON().simulation) await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { code: "ACCEPTANCE_FAILURE", message: "Acceptance service failure" } }) });
    else await route.continue();
  });
  await run().click(); await page.getByRole("alert").filter({ hasText: "ACCEPTANCE_FAILURE" }).first().waitFor();
  await go("/methods", "Methods");
  assert.equal(await disabledExport().isDisabled(), true); await page.unroute("**/api/v1/scenarios/evaluate");
  await simulate(); await download("recovered");

  // Hold a real grid response, edit inputs, then release; the late reply cannot publish.
  await go("/stress-test", "Stress-test");
  let release, requested;
  const held = new Promise(resolve => { release = resolve; }), started = new Promise(resolve => { requested = resolve; });
  let once = true;
  await page.route("**/api/v1/scenarios/grid", async route => {
    if (!once) { await route.continue(); return; } once = false;
    const response = await route.fetch(); requested(); await held; try { await route.fulfill({ response }); } catch {}
  });
  await page.getByRole("button", { name: "Load range analysis", exact: true }).click(); await started;
  await go("/methods", "Methods");
  assert.equal(await disabledExport().isDisabled(), true);
  await go("/stress-test", "Stress-test"); await page.locator("#stress-baseline-num").fill("0.12"); release(); await charts();
  await go("/methods", "Methods"); assert.equal(await disabledExport().isDisabled(), true);
  await go("/stress-test", "Stress-test"); await charts();
  assert.equal(await page.locator('[data-marker="selected"][data-baseline="0.12"]').count(), 2);
  await page.unroute("**/api/v1/scenarios/grid");
  await simulate(); const current = await download("late-response-rejected"); assert.equal(current.stress_scenario.control_event_rate, .12);

  // Hold one real MC response, change options, and reject its late completion.
  await go("/simulation", "Simulation");
  let releaseSimulation, requestedSimulation;
  const heldSimulation = new Promise(resolve => { releaseSimulation = resolve; }), simulationStarted = new Promise(resolve => { requestedSimulation = resolve; });
  let holdSimulation = true;
  await page.route("**/api/v1/scenarios/evaluate", async route => {
    if (!holdSimulation || !route.request().postDataJSON().simulation) { await route.continue(); return; } holdSimulation = false;
    const response = await route.fetch(); requestedSimulation(); await heldSimulation; try { await route.fulfill({ response }); } catch {}
  });
  await run().click(); await simulationStarted;
  await go("/methods", "Methods"); await go("/simulation", "Simulation");
  assert.equal(await page.getByRole("button", { name: "Running simulation…", exact: true }).isDisabled(), true,
    "in-flight simulation remains active across route unmount/remount");
  await page.getByText("Running the selected seeded simulation.", { exact: true }).waitFor();
  await page.getByLabel("Simulation seed", { exact: true }).fill("45"); releaseSimulation(); await go("/stress-test", "Stress-test"); await charts();
  await go("/methods", "Methods");
  assert.equal(await disabledExport().isDisabled(), true); await page.unroute("**/api/v1/scenarios/evaluate");
  await simulate(); const latestSimulation = await download("late-simulation-rejected"); assert.equal(latestSimulation.evaluation_result.monte_carlo.seed, 45);

  // Planned invalid input prevents recalc, disables export and does not resize lock.
  await go("/plan", "Plan");
  const calculateCount = requests.filter(r => r.url.endsWith("/calculate")).length;
  await page.getByLabel("Control group event rate (%)", { exact: true }).fill("0");
  await page.getByRole("button", { name: "Calculate & Lock Design", exact: true }).click();
  assert.equal(requests.filter(r => r.url.endsWith("/calculate")).length, calculateCount);
  await go("/methods", "Methods");
  assert.equal(await disabledExport().isDisabled(), true);
  await go("/plan", "Plan");
  await page.getByLabel("Control group event rate (%)", { exact: true }).fill("20");
  await page.getByLabel("Assumed difference between groups", { exact: true }).selectOption("absolute_risk_reduction");
  await page.getByLabel("Absolute risk reduction (percentage points)", { exact: true }).fill("10");
  await go("/stress-test", "Stress-test"); await page.locator("#stress-baseline-num").fill("0.2"); await calculate();
  assert.ok(await page.locator('[data-cell][data-power="null"]').count());
  assert.ok(await page.locator('[data-invalid="true"]').count());
  const invalidButton = page.getByRole("button", { name: "Select baseline 5.0%, dropout 0.0%", exact: true });
  assert.equal(await invalidButton.isDisabled(), true);
  await simulate(); const arr = await download("arr-invalid-cells");
  assert.ok(arr.grid_result.invalid_cell_count); assert.equal(arr.grid_result.power[0][0], null); assert.equal(arr.grid_result.invalid_mask[0][0], true);
  await go("/stress-test", "Stress-test"); await page.locator("#stress-baseline-num").fill("0.05"); await charts();
  await go("/simulation", "Simulation"); assert.equal(await run().isDisabled(), true);
  await go("/methods", "Methods"); assert.equal(await disabledExport().isDisabled(), true);
  await go("/plan", "Plan");
  await page.getByLabel("Starting example:").selectOption("stable-design-v1");
  await go("/simulation", "Simulation"); assert.equal(await run().isDisabled(), true);
  await go("/methods", "Methods"); assert.equal(await disabledExport().isDisabled(), true);
  await calculate(); await simulate(); await download("stable-preset");
  await page.screenshot({ path: path.join(output, "complete-screen.png"), fullPage: true });
  const recovery = await browser.newPage();
  await recovery.goto(new URL("/simulation", process.env.PAGE_URL).toString());
  await recovery.getByRole("heading", { name: "Optional simulation", exact: true }).waitFor();
  await recovery.getByText("Calculate the current plan first.", { exact: false }).waitFor();
  assert.equal(await recovery.getByRole("heading", { name: "Planning assumptions", exact: true }).count(), 0,
    "direct simulation URL explains the calculate-first recovery without mounting planning content");
  await recovery.close();
  assert.deepEqual(errors, []);
  const report = { downloads, numericalRequests: requests.length, selectedSimulations: mcCalls().length, pageErrors: errors, checks: ["complete component assembly", "fresh calculate/freeze/stress/curve/grid", "mouse/Enter/Space selection", "one selected MC per submit", "synthetic/manual/ARR/preset exports", "actual download/reopen/backend hash validation", "invalid seed/planning/ARR", "failure recovery", "late real grid and MC response rejection", "frozen enrollment"] };
  await writeFile(path.join(output, "report.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
} finally { await browser.close(); }
