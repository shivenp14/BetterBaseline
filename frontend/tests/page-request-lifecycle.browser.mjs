// Mount the production workspace and hold independent API responses to exercise real
// evaluation/grid ownership and debounced input-generation behavior. Requires
// PLAYWRIGHT_MODULE and PAGE_URL; API replies are fulfilled by browser routes.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

const { chromium } = await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE).href);
const browser = await chromium.launch({ headless: true });

const calculateResponse = {
  model_version: "binary-v1",
  method: "cohen_h_normal_v1",
  p_treatment: 0.15,
  evaluable_n: { control: 903, treatment: 903 },
  enrolled_n: { control: 903, treatment: 903 },
  nominal_power_evaluable: 0.801,
  warnings: [],
  inputs_hash: "sha256:lifecycle-calculate",
};

const evaluateResponse = {
  model_version: "binary-v1",
  analytic: {
    method: "cohen_h_normal_v1",
    conditional_power_approx: 0.47,
    assumed_evaluable_n: { control: 903, treatment: 903 },
  },
  monte_carlo: null,
  warnings: [],
  metadata: { computed_at: "2026-10-11T12:00:00Z", inputs_hash: "sha256:lifecycle-evaluate" },
};

const gridResponse = {
  model_version: "binary-v1",
  method: "cohen_h_normal_v1",
  x_baseline: [0.05, 0.1, 0.15],
  y_dropout: [0, 0.1, 0.2],
  power: [[0.2, 0.4, 0.6], [0.18, 0.35, 0.54], [0.16, 0.31, 0.48]],
  invalid_mask: [[false, false, false], [false, false, false], [false, false, false]],
  target_power: 0.8,
  planned_point: { p_control: 0.2, dropout: 0, power: 0.801, is_safe: true, is_valid: true },
  selected_point: { p_control: 0.1, dropout: 0, power: 0.47, is_safe: false, is_valid: true },
  frontier_points: [],
  fixed_enrollment: { control: 903, treatment: 903 },
  warnings: [],
  computed_at: "2026-10-11T12:00:00Z",
  inputs_hash: "sha256:lifecycle-grid",
};

function deferred() {
  let settle;
  let timer;
  const promise = new Promise((res, reject) => {
    settle = res;
    timer = setTimeout(() => reject(new Error("Timed out waiting for a controlled browser request.")), 30000);
  });
  return {
    promise,
    resolve(value) {
      clearTimeout(timer);
      settle(value);
    },
  };
}

function statusSelector(kind) {
  return kind === "evaluation"
    ? 'section[aria-labelledby="stress-heading"] span strong'
    : 'section[aria-labelledby="grid-heading"] > span';
}

async function navigateTo(page, pathname) {
  if (new URL(page.url()).pathname === pathname) return;
  await page.locator(`a[href="${pathname}"]`).first().click();
  await page.waitForURL(url => url.pathname === pathname);
}

async function waitForStatus(page, kind, expected) {
  const selector = statusSelector(kind);
  await page.waitForFunction(({ selector: query, expectedText }) =>
    document.querySelector(query)?.textContent?.trim() === expectedText,
  { selector, expectedText: expected });
}

async function runCase({ startFirst, completeFirst, evaluationOutcome, gridOutcome }) {
  const page = await browser.newPage();
  const evaluateGate = deferred();
  const gridGate = deferred();
  const evaluateStarted = deferred();
  const gridStarted = deferred();

  await page.route("**/api/v1/design/calculate", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(calculateResponse),
  }));
  await page.route("**/api/v1/scenarios/evaluate", async (route) => {
    evaluateStarted.resolve();
    await evaluateGate.promise;
    await route.fulfill(evaluationOutcome === "success"
      ? { status: 200, contentType: "application/json", body: JSON.stringify(evaluateResponse) }
      : { status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Controlled evaluation failure" }) });
  });
  await page.route("**/api/v1/scenarios/grid", async (route) => {
    gridStarted.resolve();
    await gridGate.promise;
    await route.fulfill(gridOutcome === "success"
      ? { status: 200, contentType: "application/json", body: JSON.stringify(gridResponse) }
      : { status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Controlled grid failure" }) });
  });

  await page.goto(process.env.PAGE_URL);
  await page.getByRole("button", { name: "Calculate & Lock Design", exact: true }).click();
  await navigateTo(page, "/stress");
  await page.getByRole("button", { name: "Evaluate Stress Scenario", exact: true }).waitFor();

  const evaluateButton = page.getByRole("button", { name: "Evaluate Stress Scenario", exact: true });
  const gridButton = page.getByRole("button", { name: "Load analytic grid", exact: true });
  if (startFirst === "evaluation") {
    await evaluateButton.click();
    await gridButton.click();
  } else {
    await gridButton.click();
    await evaluateButton.click();
  }
  await Promise.all([evaluateStarted.promise, gridStarted.promise]);
  await waitForStatus(page, "evaluation", "EVALUATING");
  await waitForStatus(page, "grid", "Status: LOADING");

  const expectedEvaluation = evaluationOutcome === "success" ? "SUCCESS" : "ERROR";
  const expectedGrid = gridOutcome === "success" ? "Status: SUCCESS" : "Status: ERROR";
  if (completeFirst === "evaluation") evaluateGate.resolve();
  else gridGate.resolve();

  const firstKind = completeFirst;
  const secondKind = completeFirst === "evaluation" ? "grid" : "evaluation";
  const firstExpected = firstKind === "evaluation" ? expectedEvaluation : expectedGrid;
  const secondExpected = secondKind === "evaluation" ? expectedEvaluation : expectedGrid;
  await waitForStatus(page, firstKind, firstExpected);
  assert.equal(
    (await page.locator(statusSelector(secondKind)).textContent())?.trim(),
    secondKind === "evaluation" ? "EVALUATING" : "Status: LOADING",
    `${secondKind} must remain active when ${firstKind} settles first`,
  );

  if (completeFirst === "evaluation") gridGate.resolve();
  else evaluateGate.resolve();
  await waitForStatus(page, secondKind, secondExpected);
  assert.equal((await page.locator(statusSelector("evaluation")).textContent())?.trim(), expectedEvaluation);
  assert.equal((await page.locator(statusSelector("grid")).textContent())?.trim(), expectedGrid);
  await page.close();
}

async function mountLiveWorkspace(page, onEvaluation) {
  await page.route("**/api/v1/design/calculate", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(calculateResponse),
  }));
  await page.route("**/api/v1/scenarios/evaluate", async (route) => {
    await onEvaluation(route);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(evaluateResponse),
    });
  });
  await page.goto(process.env.PAGE_URL);
  await page.getByRole("button", { name: "Calculate & Lock Design", exact: true }).click();
  await navigateTo(page, "/stress");
  await page.waitForFunction(() => {
    const button = Array.from(document.querySelectorAll("button"))
      .find((candidate) => candidate.textContent?.trim() === "Evaluate Stress Scenario");
    return button instanceof HTMLButtonElement && !button.disabled;
  });
}

async function runLiveDebouncedStressEvaluation() {
  const page = await browser.newPage();
  const evaluationStarted = deferred();
  const requests = [];
  await mountLiveWorkspace(page, async (route) => {
    requests.push(route.request().postDataJSON());
    evaluationStarted.resolve();
  });

  await page.locator("#stress-baseline-num").fill("0.16");
  await evaluationStarted.promise;
  assert.equal(requests.length, 1, "one stress slider edit issues one debounced live evaluation");
  assert.deepEqual(requests[0].fixed_enrollment, { control: 903, treatment: 903 },
    "live stress evaluation uses the actual calculated fixed enrollment");
  assert.equal(requests[0].stress_scenario.control_event_rate, 0.16,
    "live stress evaluation uses the current slider value");
  assert.equal(requests[0].provenance["/stress_scenario/control_event_rate"].source, "manual_user",
    "live request carries current stress-input provenance");
  await waitForStatus(page, "evaluation", "SUCCESS");
  await page.waitForTimeout(400);
  assert.equal(requests.length, 1, "the settled debounce does not issue a duplicate request");
  await page.close();
}

async function runPendingDebounceInvalidation({ label, transition }) {
  const page = await browser.newPage();
  await captureStressTimers(page);
  const requests = [];
  await mountLiveWorkspace(page, async (route) => {
    requests.push(route.request().postDataJSON());
  });

  await page.locator("#stress-baseline-num").fill("0.16");
  await page.waitForFunction(() => document.querySelector("#stress-baseline-num")?.value === "0.16");
  await page.waitForTimeout(80);

  if (transition === "planned-edit") {
    await page.getByLabel("Relative risk (decimal ratio)").fill("0.8");
    await page.waitForFunction(() => Array.from(document.querySelectorAll("input"))
      .some((input) => input.getAttribute("name") === "relativeRisk" && input.value === "0.8"));
  } else if (transition === "preset") {
    await page.locator("#preset-select").selectOption("attrition-shock-v1");
    await page.waitForFunction(() => document.querySelector("#preset-select")?.value === "attrition-shock-v1");
  } else {
    await page.getByRole("button", { name: "Reset to Preset Defaults", exact: true }).click();
    await page.waitForFunction(() => document.querySelector("#stress-baseline-num")?.value === "0.1");
  }

  await page.evaluate(() => window.stressTimers.forEach((callback) => callback()));
  await page.waitForTimeout(450);
  assert.equal(requests.length, 0, `${label} invalidates a pending stress debounce before it reaches the API`);
  assert.notEqual(
    (await page.locator(statusSelector("evaluation")).textContent())?.trim(),
    "EVALUATING",
    `${label} cannot strand the evaluation status`,
  );
  await page.close();
}

async function captureStressTimers(page, pauseTimers = false) {
  // Retain canceled callbacks to exercise timers already queued for delivery.
  await page.addInitScript((pause) => {
    const originalSetTimeout = window.setTimeout.bind(window);
    window.stressTimers = [];
    window.setTimeout = (callback, delay, ...args) => {
      if (delay === 350 && typeof callback === "function") {
        window.stressTimers.push(callback);
        if (pause) delay = 10000;
      }
      return originalSetTimeout(callback, delay, ...args);
    };
  }, pauseTimers);
}

async function runManualEvaluationDuringDebounce({ delayResponse = false, deliverCancelledTimer = false } = {}) {
  const page = await browser.newPage();
  if (deliverCancelledTimer) await captureStressTimers(page);
  await mountLiveWorkspace(page, async () => {});
  await page.route("**/api/v1/scenarios/grid", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(gridResponse),
  }));
  await page.getByRole("button", { name: "Load analytic grid", exact: true }).click();
  await waitForStatus(page, "grid", "Status: SUCCESS");
  const requests = [];
  await page.route("**/api/v1/scenarios/evaluate", async (route) => {
    const requestNumber = requests.push(route.request().postDataJSON());
    if (delayResponse) await new Promise((resolve) => setTimeout(resolve, 450));
    await route.fulfill(requestNumber === 1
      ? { status: 200, contentType: "application/json", body: JSON.stringify({
        ...evaluateResponse,
        monte_carlo: {
          method: "pooled_two_proportion_z_v1",
          significant_two_sided_fraction: 0.47,
          significant_favorable_fraction: 0.47,
          mcse_two_sided: 0.005,
          mcse_favorable: 0.005,
          invalid_test_fraction: 0,
          replicates: 10000,
          seed: 2026,
        },
      }) }
      : { status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Late duplicate evaluation failure" }) });
  });

  await page.locator("#stress-baseline-num").fill("0.16");
  await page.waitForTimeout(80);
  await page.getByRole("button", { name: "Evaluate Stress Scenario", exact: true }).click();
  if (deliverCancelledTimer) {
    await page.evaluate(() => {
      if (window.stressTimers.length === 0) throw new Error("No stress debounce callback was captured");
      window.stressTimers.forEach((callback) => callback());
    });
  }
  await waitForStatus(page, "evaluation", "SUCCESS");
  await page.waitForTimeout(600);
  assert.equal(requests.length, 1, "manual evaluation consumes the pending stress debounce without a second request");
  assert.equal(requests[0].stress_scenario.control_event_rate, 0.16);
  assert.deepEqual(requests[0].fixed_enrollment, { control: 903, treatment: 903 });
  await waitForStatus(page, "evaluation", "SUCCESS");
  await navigateTo(page, "/simulation");
  assert.equal(await page.getByRole("link", { name: "Download current scenario JSON", exact: true }).isEnabled(), true,
    "successful manual evaluation remains exportable after the debounce window");
  const downloadStarted = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download current scenario JSON", exact: true }).click();
  const download = await downloadStarted;
  const exported = JSON.parse(await readFile(await download.path(), "utf8"));
  assert.equal(exported.evaluation_result.metadata.inputs_hash, evaluateResponse.metadata.inputs_hash,
    "download preserves the successful manual evaluation");
  assert.equal(exported.stress_scenario.control_event_rate, 0.16);
  await page.close();
}

async function runCancelledDebounceAfterCallbackChange() {
  const page = await browser.newPage();
  await captureStressTimers(page, true);
  const requests = [];
  await mountLiveWorkspace(page, async (route) => {
    requests.push(route.request().postDataJSON());
  });
  await page.route("**/api/v1/scenarios/grid", (route) => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(gridResponse),
  }));

  await page.locator("#stress-baseline-num").fill("0.16");
  await page.waitForFunction(() => window.stressTimers.length > 0);
  // Grid ownership changes page state and hence handleEvaluate's identity,
  // without invalidating the stress-input generation or its pending intent.
  await page.getByRole("button", { name: "Load analytic grid", exact: true }).click();
  await waitForStatus(page, "grid", "Status: SUCCESS");
  await page.waitForFunction(() => window.stressTimers.length > 1);
  await page.evaluate(() => window.stressTimers.slice(0, -1).forEach((callback) => callback()));
  await page.waitForTimeout(80);
  assert.equal(requests.length, 0, "obsolete callbacks cannot start work after callback identity changes");
  await page.evaluate(() => window.stressTimers.at(-1)());
  await waitForStatus(page, "evaluation", "SUCCESS");
  assert.equal(requests.length, 1, "the current pending automatic evaluation still runs once");
  await waitForStatus(page, "grid", "Status: SUCCESS");
  await page.close();
}

try {
  await runManualEvaluationDuringDebounce();
  await runManualEvaluationDuringDebounce({ delayResponse: true });
  await runManualEvaluationDuringDebounce({ deliverCancelledTimer: true });
  await runCancelledDebounceAfterCallbackChange();
  for (const evaluationOutcome of ["success", "error"]) {
    for (const gridOutcome of ["success", "error"]) {
      for (const startFirst of ["evaluation", "grid"]) {
        for (const completeFirst of ["evaluation", "grid"]) {
          await runCase({ startFirst, completeFirst, evaluationOutcome, gridOutcome });
        }
      }
    }
  }
  await runLiveDebouncedStressEvaluation();
  for (const invalidation of [
    { label: "planned/effect edit", transition: "planned-edit" },
    { label: "preset selection", transition: "preset" },
    { label: "preset reset", transition: "reset" },
  ]) {
    await runPendingDebounceInvalidation(invalidation);
  }
  console.log("PASS: the production workspace preserves manual success/export across route mounts, pending and canceled stress timers, evaluation/grid overlap, one automatic fixed-enrollment stress evaluation, and debounce invalidation across planned edits, presets, and reset.");
} finally {
  await browser.close();
}
