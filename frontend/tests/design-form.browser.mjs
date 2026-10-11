// Run against the isolated harness and a fresh real backend, never mock success.
// C2_PLAYWRIGHT_MODULE points at a separately installed Playwright module.
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";
const { chromium } = await import(pathToFileURL(process.env.C2_PLAYWRIGHT_MODULE).href);
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const failures = [];
  page.on("pageerror", (error) => failures.push(error.message));
  await page.goto(process.env.C2_HARNESS_URL || "http://127.0.0.1:3000/c2-harness");
  const field = (label) => page.getByLabel(label, { exact: true });
  const calls = () => page.getByLabel("Calculation calls").textContent();
  await field("Control endpoint risk (%)").fill("");
  await field("Target power (%)").fill("2");
  await field("Dropout in each arm (%)").press("Enter");
  await page.getByText("Correct the marked planning inputs before calculating.").waitFor();
  assert.equal(await calls(), "0");
  assert.equal(await field("Control endpoint risk (%)").evaluate((el) => el === document.activeElement), true);
  await field("Control endpoint risk (%)").fill("20");
  await field("Target power (%)").fill("80");
  await field("Hypothetical treatment effect").selectOption("absolute_risk_reduction");
  await field("Absolute risk reduction (percentage points)").fill("20");
  await field("Dropout in each arm (%)").press("Enter");
  await page.getByText("Absolute risk reduction must be smaller than the control endpoint risk.").waitFor();
  assert.equal(await calls(), "0");
  assert.equal(await field("Absolute risk reduction (percentage points)").evaluate((el) => el === document.activeElement), true);
  await field("Hypothetical treatment effect").selectOption("relative_risk");
  assert.equal(await field("Relative risk (decimal ratio)").inputValue(), "0.75");
  await field("Dropout in each arm (%)").press("Enter");
  await page.getByRole("cell", { name: "1004", exact: true }).first().waitFor();
  assert.equal(await calls(), "1");
  const payload = JSON.parse(await page.getByLabel("Submitted payload").textContent());
  assert.equal(payload.control_event_rate, .2);
  assert.equal(payload.effect.value, .75);
  assert.equal(payload.alpha, .05);
  assert.equal(payload.target_power, .8);
  assert.deepEqual(payload.dropout, { control: .1, treatment: .1 });
  assert.equal(await page.getByRole("cell", { name: "903", exact: true }).count(), 2);
  assert.equal(await page.getByText("Illustrative mock response.").count(), 0);
  await page.getByText("cohen_h_normal_v1", { exact: false }).waitFor();
  await page.getByText("Source metadata was not supplied with this result.").waitFor();
  await field("Dropout in each arm (%)").fill("0");
  await page.getByText("Stale result.", { exact: true }).waitFor();
  await field("Dropout in each arm (%)").press("Enter");
  await page.waitForFunction(() => document.querySelector('[aria-label="Calculation calls"]').textContent === "2");
  await page.getByRole("button", { name: "Calculate design", exact: true }).waitFor();
  assert.equal(await page.getByRole("cell", { name: "1004", exact: true }).count(), 0);
  assert.equal(await page.getByRole("cell", { name: "903", exact: true }).count(), 4);
  // Hold one real request to prove pending blocks duplicate submission.
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  await page.route("**/api/v1/design/calculate", async (route) => { await gate; await route.continue(); });
  await field("Dropout in each arm (%)").press("Enter");
  await page.getByRole("button", { name: "Calculating design…", exact: true }).waitFor();
  assert.equal(await page.getByRole("button", { name: "Calculating design…", exact: true }).isDisabled(), true);
  await page.locator("form").evaluate((form) => {
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
  assert.equal(await calls(), "3");
  release();
  await page.getByRole("button", { name: "Calculate design", exact: true }).waitFor();
  await page.unroute("**/api/v1/design/calculate");
  // Transport failure keeps the last real result visibly stale.
  await page.route("**/api/v1/design/calculate", (route) => route.abort());
  await field("Dropout in each arm (%)").press("Enter");
  await page.getByText("Stale result.", { exact: true }).waitFor();
  await page.getByRole("button", { name: "Calculate design", exact: true }).waitFor();
  assert.equal(await page.getByRole("cell", { name: "903", exact: true }).count(), 4);
  assert.ok(await page.getByRole("alert").count() > 0);
  assert.deepEqual(failures, []);
  console.log("PASS: keyboard validation/focus, ARR rejection, unit payload, fresh 903/1004, changed dropout, stale/failure states, pending duplicate guard.");
} finally { await browser.close(); }
