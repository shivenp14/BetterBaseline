// Run from repository root after the setup in docs/DEMO_SCRIPT.md.
// Uses #118's locked Playwright package; no statistical response is mocked.
import { createRequire } from 'node:module';
import { spawn, execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
const root = process.cwd();
const require = createRequire(resolve(root, 'tests/e2e/package.json'));
const { chromium } = require('@playwright/test');
const offline = process.argv.includes('--offline');
const pace = process.argv.includes('--pace');
const output = resolve(root, process.env.DEMO_REPORT_DIR || 'scripts/demo/reports', offline ? 'offline' : 'online');
mkdirSync(output, { recursive: true });
const api = 'http://127.0.0.1:8001', ui = 'http://localhost:3001';
const env = { ...process.env, ALLOWED_ORIGINS: JSON.stringify([ui]) };
if (offline) {
  env.PYTHONPATH = resolve(root, 'tests/e2e/python_guard');
  execFileSync('python3', ['tests/e2e/check_backend_egress_guard.py'], { stdio: 'inherit' });
}
const servers = [
  spawn(resolve(root, 'backend/.venv/bin/python'), ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8001'], { cwd: resolve(root, 'backend'), env, stdio: 'inherit' }),
  spawn('npm', ['run', 'start', '--', '--port', '3001'], { cwd: resolve(root, 'frontend'), env, stdio: 'inherit', detached: true }),
];
let browser;
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function ready(url) {
  for (let i = 0; i < 120; i++) {
    try { if ((await fetch(url)).ok) return; } catch {}
    await sleep(500);
  }
  throw new Error(`Server not ready: ${url}`);
}
try {
  await Promise.all([ready(`${api}/healthz`), ready(ui)]);
  browser = await chromium.launch();
  const context = await browser.newContext({ serviceWorkers: 'block' });
  const external = [], errors = [], steps = [];
  const allowed = url => [api, ui].includes(new URL(url).origin);
  if (offline) {
    await context.route('**/*', route => allowed(route.request().url()) ? route.continue() : route.abort());
    await context.routeWebSocket(/.*/, socket => { if (allowed(socket.url().replace(/^ws/, 'http'))) socket.connectToServer(); else { external.push(socket.url()); socket.close(); } });
  }
  context.on('request', request => { if (!allowed(request.url())) external.push(request.url()); });
  const page = await context.newPage();
  page.on('pageerror', e => errors.push(String(e)));
  const start = performance.now();
  async function step(at, name, action) {
    if (pace) await sleep(Math.max(0, at * 1000 - (performance.now() - start)));
    await action();
    steps.push({ name, elapsed_seconds: +( (performance.now() - start) / 1000).toFixed(3) });
    console.log(name);
  }
  async function response(path, action, match = () => true) {
    const pending = page.waitForResponse(r => r.url() === api + path && r.request().method() === 'POST' && match(r.request().postDataJSON()));
    await action(); const r = await pending; assert.equal(r.status(), 200); return r.json();
  }
  let design, first, grid, evaluation;
  await step(0, 'Load synthetic baseline-collapse preset', async () => {
    await page.goto(ui); await page.getByLabel('Select Preset:').selectOption('baseline-collapse-v1');
    assert.match(await page.locator('main').innerText(), /LIVE/);
  });
  await step(15, 'Calculate and lock 903 per arm', async () => {
    design = await response('/api/v1/design/calculate', () => page.getByRole('button', { name: 'Calculate & Lock Design', exact: true }).click());
    assert.deepEqual(design.enrolled_n, { control: 903, treatment: 903 });
    first = await response('/api/v1/scenarios/evaluate', () => page.getByRole('button', { name: 'Evaluate Stress Scenario', exact: true }).click(), r => r.simulation === null);
    assert.ok(Math.abs(first.analytic.conditional_power_approx - .47) < .01);
  });
  await step(30, 'Fresh stress .12 risk / .13 dropout, frozen enrollment', async () => {
    await page.locator('#stress-baseline-num').fill('0.12');
    await page.locator('#stress-dropout-num').fill('0.13');
    evaluation = await response('/api/v1/scenarios/evaluate', () => page.getByRole('button', { name: 'Evaluate Stress Scenario', exact: true }).click(), r => r.simulation === null && r.stress_scenario.control_event_rate === .12 && r.stress_scenario.dropout.control === .13);
    assert.notEqual(evaluation.analytic.conditional_power_approx, first.analytic.conditional_power_approx);
  });
  await step(45, 'Load live grid and inspect heatmap/curve', async () => {
    grid = await response('/api/v1/scenarios/grid', () => page.getByRole('button', { name: 'Load grid response from backend', exact: true }).click());
    assert.ok(await page.getByRole('region', { name: 'Sensitivity heatmap', exact: true }).isVisible());
  });
  await step(60, 'Selected Monte Carlo seed 42 / 10000 replicates', async () => {
    await page.getByLabel('Simulation seed', { exact: true }).fill('42');
    await page.getByLabel('Simulation replicates', { exact: true }).fill('10000');
    evaluation = await response('/api/v1/scenarios/evaluate', () => page.getByRole('button', { name: 'Run simulation', exact: true }).click(), r => r.simulation?.seed === 42 && r.simulation?.replicates === 10000);
    assert.equal(evaluation.monte_carlo.seed, 42);
  });
  let exported;
  await step(75, 'Download complete JSON and validate backend schema', async () => {
    const pending = page.waitForEvent('download');
    await page.getByRole('link', { name: 'Download current scenario JSON', exact: true }).click();
    const path = resolve(output, 'scenario.json'); await (await pending).saveAs(path);
    exported = JSON.parse(readFileSync(path));
    assert.deepEqual(exported.fixed_enrollment, design.enrolled_n);
    const canonical = r => ({ ...r, provenance: r.provenance.field_provenance ?? r.provenance });
    assert.deepEqual(exported.design_result, canonical(design));
    assert.deepEqual(exported.evaluation_result, canonical(evaluation));
    assert.deepEqual(exported.grid_result, grid);
    execFileSync(resolve(root, 'backend/.venv/bin/python'), ['-c', 'import sys; from app.schemas import ExportPayload; ExportPayload.model_validate_json(open(sys.argv[1]).read())', path], { cwd: resolve(root, 'backend') });
  });
  await step(90, 'Reopen artifact and explain provenance / scientific boundary', async () => {
    await page.getByLabel('Reopen and validate scenario JSON', { exact: true }).setInputFiles(resolve(output, 'scenario.json'));
    await page.getByText(/Valid complete v1 scenario exported/).waitFor();
    await page.screenshot({ path: resolve(output, 'final.png'), fullPage: true });
  });
  if (pace) await sleep(Math.max(0, 105000 - (performance.now() - start)));
  assert.deepEqual(external, []); assert.deepEqual(errors, []);
  const report = { tested_commit: execFileSync('git', ['rev-parse', 'HEAD']).toString().trim(), date: new Date().toISOString(), offline, paced: pace, duration_seconds: +( (performance.now() - start) / 1000).toFixed(3), node: process.version, browser: browser.version(), steps, external_requests: external, page_errors: errors, baseline_power: first.analytic.conditional_power_approx, stressed_power: evaluation.analytic.conditional_power_approx, frozen_enrollment: exported.fixed_enrollment, export_sha256: createHash('sha256').update(readFileSync(resolve(output, 'scenario.json'))).digest('hex'), scope: offline ? 'Browser exact-origin routing and backend socket/DNS guard; host network remains available' : 'Network available; real local services, no external requests' };
  writeFileSync(resolve(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report));
} finally {
  await browser?.close();
  servers[0].kill('SIGTERM');
  try { process.kill(-servers[1].pid, 'SIGTERM'); } catch {}
}
