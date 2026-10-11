// Verify the explicitly labeled fallback without starting or accessing a backend. Requires npm ci.
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import assert from 'node:assert/strict';
const root = process.cwd();
const { chromium } = createRequire(resolve(root, 'tests/e2e/package.json'))('@playwright/test');
const ui = 'http://localhost:3002';
const server = spawn('npm', ['run', 'dev', '--', '--port', '3002'], { cwd: resolve(root, 'frontend'), env: { ...process.env, NEXT_PUBLIC_API_MODE: 'demo' }, detached: true, stdio: 'inherit' });
let browser;
try {
  let ready = false;
  for (let i = 0; i < 120; i++) {
    try { if ((await fetch(ui)).ok) { ready = true; break; } } catch {}
    await new Promise(r => setTimeout(r, 500));
  }
  assert.ok(ready, 'Frontend starts');
  browser = await chromium.launch();
  const context = await browser.newContext({ serviceWorkers: 'block' });
  const forbidden = [];
  await context.route('**/*', route => new URL(route.request().url()).origin === ui ? route.continue() : (forbidden.push(route.request().url()), route.abort()));
  await context.routeWebSocket(/.*/, socket => new URL(socket.url().replace(/^ws/, 'http')).origin === ui ? socket.connectToServer() : (forbidden.push(socket.url()), socket.close()));
  const page = await context.newPage();
  await page.goto(ui);
  await page.getByLabel('Select Preset:').selectOption('baseline-collapse-v1');
  await page.getByRole('button', { name: 'Calculate & Lock Design', exact: true }).click();
  assert.match(await page.locator('main').innerText(), /DEMO — fixtures and client calculations; no backend execution/);
  assert.match(await page.getByRole('region', { name: 'Planned design summary', exact: true }).innerText(), /903/);
  assert.ok(await page.getByRole('button', { name: 'Download current scenario JSON', exact: true }).isDisabled());
  assert.match(await page.getByRole('region', { name: 'Selected-scenario Monte Carlo simulation', exact: true }).innerText(), /Live simulation is unavailable in demo mode/);
  assert.deepEqual(forbidden, []);
  const output = resolve(root, process.env.DEMO_REPORT_DIR || 'scripts/demo/reports', 'fixture');
  mkdirSync(output, { recursive: true });
  await page.screenshot({ path: resolve(output, 'fallback.png'), fullPage: true });
  writeFileSync(resolve(output, 'report.json'), JSON.stringify({ date: new Date().toISOString(), mode: 'demo', backend_started: false, forbidden_requests: forbidden, visible_fixture_design: 903, complete_export_disabled: true, live_simulation_unavailable: true }, null, 2) + '\n');
  console.log('Fixture recovery passed: labeled DEMO, 903/arm visible, no backend/registry requests, complete export disabled.');
} finally {
  await browser?.close();
  try { process.kill(-server.pid, 'SIGTERM'); } catch {}
}
