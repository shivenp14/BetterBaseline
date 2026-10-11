// Mount the production page and hold independent API responses to exercise real
// overlapping evaluation/grid lifecycle behavior. Requires PLAYWRIGHT_MODULE and
// PAGE_URL; API replies are fulfilled by the browser route handlers below.
import assert from "node:assert/strict";
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
  let resolve;
  const promise = new Promise((res) => { resolve = res; });
  return { promise, resolve };
}

function statusSelector(kind) {
  return kind === "evaluation"
    ? 'section[aria-labelledby="stress-heading"] span strong'
    : 'section[aria-labelledby="grid-heading"] > span';
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
  await page.getByRole("button", { name: "Evaluate Stress Scenario", exact: true }).waitFor();

  const evaluateButton = page.getByRole("button", { name: "Evaluate Stress Scenario", exact: true });
  const gridButton = page.getByRole("button", { name: "Load grid response from backend", exact: true });
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

try {
  for (const evaluationOutcome of ["success", "error"]) {
    for (const gridOutcome of ["success", "error"]) {
      for (const startFirst of ["evaluation", "grid"]) {
        for (const completeFirst of ["evaluation", "grid"]) {
          await runCase({ startFirst, completeFirst, evaluationOutcome, gridOutcome });
        }
      }
    }
  }
  console.log("PASS: mounted production page settles overlapping evaluation/grid success and error responses in both start and completion orders.");
} finally {
  await browser.close();
}
