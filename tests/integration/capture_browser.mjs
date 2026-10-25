// Real production UI -> local HTTP -> independently downloaded JSON.
import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { pathToFileURL } from "node:url";

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE
  ? pathToFileURL(process.env.PLAYWRIGHT_MODULE).href : "playwright");
const ui = process.env.PAGE_URL || "http://localhost:3000";
const api = process.env.API_URL || "http://127.0.0.1:8000";
const output = process.env.CAPTURE_OUTPUT || "/tmp/betterbaseline-integration";
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true,
  ...(process.env.CHROMIUM_EXECUTABLE ? { executablePath: process.env.CHROMIUM_EXECUTABLE } : {}) });
const context = await browser.newContext({ acceptDownloads: true, serviceWorkers: "block" });
const page = await context.newPage();
const violations = [], errors = [], calls = [], captures = [];
const allowed = new Set([new URL(ui).origin, new URL(api).origin]);
await context.route("**/*", async route => {
  if (!allowed.has(new URL(route.request().url()).origin)) {
    violations.push(route.request().url()); await route.abort();
  } else await route.continue();
});
await page.routeWebSocket(url => {
  const normalized = new URL(url); normalized.protocol = normalized.protocol === "wss:" ? "https:" : "http:";
  return !allowed.has(normalized.origin);
}, socket => { violations.push(socket.url()); socket.close(); });
page.on("pageerror", error => errors.push(error.message));
const pending = new Set();
page.on("response", response => {
  if (!response.url().startsWith(api) || response.request().method() !== "POST") return;
  const task = (async () => calls.push({ url: response.url(), status: response.status(),
    request: response.request().postDataJSON(), response: await response.json() }))();
  pending.add(task); task.finally(() => pending.delete(task));
});
const downloadLink = () => page.getByRole("link", { name: "Download current scenario JSON", exact: true });
async function charts() {
  await page.waitForFunction(() => document.querySelector('section[aria-labelledby="grid-heading"] span')?.textContent.includes("SUCCESS"));
  await page.locator("[data-cell]").first().waitFor();
}
async function capture(name) {
  await charts();
  const response = page.waitForResponse(r => r.url() === `${api}/api/v1/scenarios/evaluate`
    && r.request().postDataJSON()?.simulation != null);
  await page.getByRole("button", { name: "Run simulation", exact: true }).click();
  assert.equal((await response).status(), 200);
  await downloadLink().waitFor();
  const download = page.waitForEvent("download"); await downloadLink().click();
  const file = path.join(output, `${name}-download.json`); await (await download).saveAs(file);
  const exported = JSON.parse(await readFile(file, "utf8"));
  await Promise.all([...pending]);
  const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const evaluation = [...calls].reverse().find(c => c.request.simulation
    && c.response.metadata?.inputs_hash === exported.evaluation_result.metadata.inputs_hash);
  const design = [...calls].reverse().find(c => c.url.endsWith("/calculate")
    && c.response.inputs_hash === exported.design_result.inputs_hash);
  const grid = [...calls].reverse().find(c => c.url.endsWith("/grid")
    && equal(c.response, exported.grid_result));
  assert.ok(evaluation && design && grid, "Export must correspond to captured real HTTP responses");
  const bundle = { source: "real_api_and_ui_export", engine_commit: execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
    captured_at: new Date().toISOString(), request: evaluation.request, design_request: design.request,
    grid_request: grid.request, design_response: design.response, evaluation_response: evaluation.response,
    grid_response: grid.response, expected_provenance: evaluation.request.provenance, export: exported };
  const filename = path.join(output, `${name}-capture.json`);
  await writeFile(filename, JSON.stringify(bundle, null, 2) + "\n");
  execFileSync(process.env.CAPTURE_PYTHON || "python3", ["tests/integration/check_capture.py", filename], { stdio: "inherit" });
  await page.getByLabel("Reopen and validate scenario JSON", { exact: true }).setInputFiles(file);
  await page.getByText(/^Valid complete v1 scenario exported/).waitFor();
  captures.push({ name, enrollment: exported.fixed_enrollment, inputs_hash: exported.inputs_hash,
    seed: exported.evaluation_result.monte_carlo.seed, replicates: exported.evaluation_result.monte_carlo.replicates });
  return exported;
}
try {
  await page.goto(ui);
  await page.getByLabel("Select Preset:").selectOption("baseline-collapse-v1");
  await page.getByRole("button", { name: "Calculate & Lock Design", exact: true }).click();
  const first = await capture("preset");
  assert.deepEqual(first.fixed_enrollment, { control: 903, treatment: 903 });
  assert.ok(Math.abs(first.evaluation_result.analytic.conditional_power_approx - .46999657396642797) < 1e-10);
  await page.locator("#stress-baseline-num").fill("0.12");
  await page.locator("#stress-dropout-num").fill("0.13");
  await page.getByLabel("Simulation seed", { exact: true }).fill("43");
  await page.getByLabel("Simulation replicates", { exact: true }).fill("1000");
  await page.waitForTimeout(500);
  const changed = await capture("fresh-manual");
  assert.deepEqual(changed.fixed_enrollment, first.fixed_enrollment);
  assert.notEqual(changed.inputs_hash, first.inputs_hash);
  assert.equal(changed.provenance["/stress_scenario/control_event_rate"].source, "manual_user");
  assert.equal(changed.provenance["/simulation/seed"].source, "manual_user");
  const repeated = await capture("same-seed-repeat");
  assert.deepEqual(repeated.evaluation_result.monte_carlo, changed.evaluation_result.monte_carlo);
  assert.deepEqual(violations, []); assert.deepEqual(errors, []);
  await writeFile(path.join(output, "browser-report.json"), JSON.stringify({ captured_at: new Date().toISOString(),
    browser: browser.version(), page_url: ui, api_url: api, engine_commit: execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
    captures, post_requests: calls.length, statuses: calls.map(c => c.status), external_attempts: violations, page_errors: errors,
    isolation: "Browser HTTP/WebSocket allowlist; backend egress isolation is supplied and recorded by the runner." }, null, 2) + "\n");
  console.log(`Passed: ${captures.length} independent downloads, ${calls.length} real POST responses, no page errors or external requests.`);
} finally { await browser.close(); }
