/**
 * E2E acceptance tests for the real baseline-collapse workflow (#78).
 *
 * Every calculation assertion is tied to an HTTP request made by a UI action
 * and the corresponding local FastAPI response. Missing API/export integration
 * fails explicitly; fixture-only success cannot satisfy acceptance.
 */

import { test, expect, Page, Response } from "@playwright/test";
import { spawnSync } from "node:child_process";
import path from "node:path";

const BACKEND_PORT = Number(process.env.BACKEND_PORT || 8001);
const FRONTEND_PORT = Number(process.env.FRONTEND_PORT || 3001);
const BACKEND_ORIGIN = `http://127.0.0.1:${BACKEND_PORT}`;
const FRONTEND_ORIGIN = `http://localhost:${FRONTEND_PORT}`;
const LOCAL_ORIGINS = new Set([BACKEND_ORIGIN, FRONTEND_ORIGIN]);
const PRESET_ID = "baseline-collapse-v1";
const REFERENCE_N = 903;
const RESPONSE_TIMEOUT_MS = 12_000;

const forbiddenRequests = new WeakMap<Page, string[]>();
const forbiddenWebSockets = new WeakMap<Page, string[]>();

function isLocalUrl(url: URL): boolean {
  const normalized = new URL(url.href);
  if (normalized.protocol === "ws:") normalized.protocol = "http:";
  if (normalized.protocol === "wss:") normalized.protocol = "https:";
  return LOCAL_ORIGINS.has(normalized.origin);
}

/**
 * Route every browser request, continue only requests to the two exact local
 * server origins, and retain violations for a deterministic afterEach check.
 * serviceWorkers: "block" in the Playwright config ensures page routing sees
 * requests that might otherwise be handled by a service worker.
 */
async function constrainBrowserNetwork(page: Page): Promise<void> {
  const forbidden: string[] = [];
  const forbiddenSockets: string[] = [];
  forbiddenRequests.set(page, forbidden);
  forbiddenWebSockets.set(page, forbiddenSockets);
  // page.route() does not intercept WebSocket handshakes. routeWebSocket()
  // installs before navigation and closes external sockets without connecting
  // to their destination.
  await page.routeWebSocket((url) => {
    if (isLocalUrl(url)) return false;
    forbiddenSockets.push(url.href);
    return true;
  }, (webSocket) => webSocket.close({ code: 1008, reason: "E2E external WebSocket blocked" }));
  await page.route("**/*", async (route) => {
    const requestUrl = route.request().url();
    let origin: string;
    try {
      origin = new URL(requestUrl).origin;
    } catch {
      forbidden.push(requestUrl);
      await route.abort();
      return;
    }

    if (!LOCAL_ORIGINS.has(origin)) {
      forbidden.push(requestUrl);
      await route.abort();
      return;
    }
    await route.continue();
  });
}

async function requireUiApiResponse(
  page: Page,
  endpoint: string,
  action: () => Promise<unknown>,
  matchesRequest: (body: Record<string, any>) => boolean = () => true,
): Promise<Response> {
  const pendingResponse = page.waitForResponse(
    (response) => {
      const url = new URL(response.url());
      return url.origin === BACKEND_ORIGIN && url.pathname === endpoint && response.request().method() === "POST" && matchesRequest(response.request().postDataJSON());
    },
    { timeout: RESPONSE_TIMEOUT_MS },
  );
  try {
    const [response] = await Promise.all([pendingResponse, action()]);
    return response;
  } catch (error) {
    throw new Error(
      `[E2E live integration] UI action did not receive ${endpoint} from ${BACKEND_ORIGIN}. ` +
        `Verify live API configuration and UI request wiring. Original error: ${String(error)}`,
    );
  }
}

async function selectPreset(page: Page, id = PRESET_ID): Promise<void> {
  await page.goto("/plan");
  await expect(page.getByRole("heading", { name: "Plan a trial", exact: true })).toBeVisible();
  await page.getByLabel("Starting example:").selectOption(id);
}

async function goToStep(page: Page, label: "Plan" | "Stress-test" | "Simulation" | "Methods"): Promise<void> {
  const link = page.getByRole("navigation", { name: "Workspace pages", exact: true })
    .getByRole("link", { name: label, exact: true });
  await link.click();
  await expect(link).toHaveAttribute("aria-current", "step");
}

async function calculateFromUi(page: Page): Promise<Record<string, any>> {
  const response = await requireUiApiResponse(
    page,
    "/api/v1/design/calculate",
    () => page.getByRole("button", { name: /calculate/i }).click(),
  );
  expect(response.status(), "design API response from the local backend").toBe(200);
  return response.json();
}

async function evaluateFromUi(page: Page): Promise<{ response: Response; body: Record<string, any> }> {
  const response = await requireUiApiResponse(
    page,
    "/api/v1/scenarios/evaluate",
    () => page.getByRole("button", { name: "Update estimate now", exact: true }).click(),
    (request) => request.simulation === null,
  );
  return { response, body: await response.json() };
}

function simulationRegion(page: Page) {
  return page.getByRole("region", { name: "Selected-scenario Monte Carlo simulation", exact: true });
}

function resultValue(page: Page, label: string) {
  return simulationRegion(page).locator("dt").filter({ hasText: new RegExp(`^${label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`) }).locator("+ dd");
}

async function simulateFromUi(page: Page): Promise<{ response: Response; body: Record<string, any> }> {
  await goToStep(page, "Simulation");
  const region = simulationRegion(page);
  await region.getByLabel("Simulation seed", { exact: true }).fill("42");
  await region.getByLabel("Simulation replicates", { exact: true }).fill("10000");
  const response = await requireUiApiResponse(page, "/api/v1/scenarios/evaluate",
    () => region.getByRole("button", { name: "Run simulation", exact: true }).click(),
    (request) => request.simulation?.seed === 42 && request.simulation?.replicates === 10000);
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.monte_carlo).not.toBeNull();
  await expect(resultValue(page, "Computed at")).toHaveText(body.metadata.computed_at);
  await expect(resultValue(page, "Seed")).toHaveText("42");
  await expect(resultValue(page, "Replicates")).toHaveText("10000");
  return { response, body };
}

// The app unwraps the API's provenance envelope before storing canonical results.
// Preserve every other returned field so export assertions remain full equality.
function canonicalResponse(body: Record<string, any>): Record<string, any> {
  return { ...body, provenance: body.provenance.field_provenance ?? body.provenance };
}

function exportLink(page: Page) {
  return page.getByRole("region", { name: "Scenario export", exact: true })
    .getByRole("link", { name: "Download current scenario JSON", exact: true });
}

test.describe("Offline baseline-collapse E2E workflow", () => {
  test.beforeEach(async ({ page }) => {
    await constrainBrowserNetwork(page);
  });

  test.afterEach(async ({ page }) => {
    const forbidden = forbiddenRequests.get(page) ?? [];
    expect(forbidden, "browser requests must use only the exact local frontend/backend origins").toEqual([]);
    expect(forbiddenWebSockets.get(page) ?? [], "unexpected WebSocket attempts must use exact local origins").toEqual([]);
  });

  test("Calculate calls the local API and displays its 903-per-arm design response", async ({ page }) => {
    await selectPreset(page);
    const design = await calculateFromUi(page);

    expect(design.evaluable_n).toEqual({ control: REFERENCE_N, treatment: REFERENCE_N });
    expect(design.enrolled_n).toEqual({ control: REFERENCE_N, treatment: REFERENCE_N });
    expect(design.method).toBe("cohen_h_normal_v1");
    expect(design).not.toHaveProperty("mock");
    const summary = page.locator("section").filter({ has: page.getByRole("heading", { name: "Enrollment estimate", exact: true }) });
    await expect(summary).toContainText("903");
    await expect(summary).toContainText(design.method);
  });

  test("Analytic Evaluate and explicit simulation send frozen enrollment and current stress", async ({ page }) => {
    await selectPreset(page);
    const design = await calculateFromUi(page);
    await goToStep(page, "Stress-test");
    await page.locator("#stress-baseline-num").fill("0.10");

    const analytic = await evaluateFromUi(page);
    expect(analytic.response.status()).toBe(200);
    expect(analytic.response.request().postDataJSON().simulation).toBeNull();
    expect(analytic.body.monte_carlo).toBeNull();
    const { response, body } = await simulateFromUi(page);
    expect(body.analytic).toEqual(analytic.body.analytic);
    expect(response.status()).toBe(200);
    const request = response.request().postDataJSON();
    expect(request.fixed_enrollment).toEqual(design.enrolled_n);
    expect(request.fixed_enrollment).toEqual({ control: REFERENCE_N, treatment: REFERENCE_N });
    expect(request.stress_scenario.control_event_rate).toBe(0.1);
    expect(request.planned_design.effect).toEqual({ kind: "relative_risk", value: 0.75 });
    expect(body.metadata.fixed_enrollment).toEqual(request.fixed_enrollment);
    expect(body.metadata.software_versions).toBeTruthy();
    expect(body.analytic.conditional_power_approx).toBeGreaterThan(0.42);
    expect(body.analytic.conditional_power_approx).toBeLessThan(0.52);
    expect(body.monte_carlo.replicates).toBe(request.simulation.replicates);
    expect(body.monte_carlo.seed).toBe(request.simulation.seed);
    expect(body).not.toHaveProperty("mock");

    await expect(resultValue(page, "Two-sided significance fraction")).toHaveText(
      `${(body.monte_carlo.significant_two_sided_fraction * 100).toFixed(3)}%`);

  });

  test("changed stress produces a fresh backend calculation and updated MC fields", async ({ page }) => {
    await selectPreset(page);
    const design = await calculateFromUi(page);
    await goToStep(page, "Stress-test");
    await page.locator("#stress-baseline-num").fill("0.10");
    const first = await simulateFromUi(page);
    expect(first.response.status()).toBe(200);
    const firstRequest = first.response.request().postDataJSON();
    expect(firstRequest.fixed_enrollment).toEqual(design.enrolled_n);
    expect(firstRequest.stress_scenario.control_event_rate).toBe(0.1);

    await goToStep(page, "Stress-test");
    await page.locator("#stress-baseline-num").fill("0.15");
    const changed = await simulateFromUi(page);
    expect(changed.response.status()).toBe(200);
    const changedRequest = changed.response.request().postDataJSON();
    expect(changedRequest.fixed_enrollment).toEqual(design.enrolled_n);
    expect(changedRequest.stress_scenario.control_event_rate).toBe(0.15);
    expect(changed.body.metadata.inputs_hash).not.toBe(first.body.metadata.inputs_hash);
    expect(changed.body.metadata.computed_at).not.toBe(first.body.metadata.computed_at);
    expect(changed.body.analytic.conditional_power_approx).not.toBe(first.body.analytic.conditional_power_approx);
    expect(changed.body.monte_carlo.significant_two_sided_fraction).not.toBe(first.body.monte_carlo.significant_two_sided_fraction);
    expect(changed.body.monte_carlo.mcse_two_sided).toBeGreaterThanOrEqual(0);
    expect(changed.body.monte_carlo.mcse_favorable).toBeGreaterThanOrEqual(0);
    expect(changed.body.monte_carlo.replicates).toBe(changedRequest.simulation.replicates);
    expect(changed.body.monte_carlo.seed).toBe(changedRequest.simulation.seed);

    await expect(resultValue(page, "Two-sided significance fraction")).toHaveText(
      `${(changed.body.monte_carlo.significant_two_sided_fraction * 100).toFixed(3)}%`);
    await expect(resultValue(page, "Two-sided MCSE (percentage points)")).toHaveText(
      (changed.body.monte_carlo.mcse_two_sided * 100).toFixed(3));
    await expect(resultValue(page, "Favorable-direction MCSE (percentage points)")).toHaveText(
      (changed.body.monte_carlo.mcse_favorable * 100).toFixed(3));

  });

  test("grid action calls the local API with frozen enrollment and displays its response", async ({ page }) => {
    await selectPreset(page);
    const design = await calculateFromUi(page);
    await goToStep(page, "Stress-test");
    await page.getByText("Advanced: inspect range charts and grid data", { exact: true }).click();
    const response = await requireUiApiResponse(
      page,
      "/api/v1/scenarios/grid",
      () => page.getByRole("button", { name: "Load range analysis", exact: true }).click(),
    );
    expect(response.status()).toBe(200);
    const request = response.request().postDataJSON();
    const body = await response.json();
    expect(request.fixed_enrollment).toEqual(design.enrolled_n);
    expect(request.fixed_enrollment).toEqual({ control: REFERENCE_N, treatment: REFERENCE_N });
    expect(body.method).toBe("cohen_h_normal_v1");
    expect(body.grid_label).toBe("expected_count_approximation");
    expect(body.y_dropout.length).toBeGreaterThan(0);
    expect(body.x_baseline.length).toBeGreaterThan(0);
    expect(body.power).toHaveLength(body.y_dropout.length);
    expect(body.invalid_mask).toHaveLength(body.y_dropout.length);
    for (const row of body.power) expect(row).toHaveLength(body.x_baseline.length);
    for (const row of body.invalid_mask) expect(row).toHaveLength(body.x_baseline.length);
    expect(body).not.toHaveProperty("mock");
    const gridSection = page.getByRole("region", { name: "Sensitivity heatmap", exact: true });
    await expect(gridSection).toContainText(body.method);
    await expect(gridSection.locator("table caption")).toContainText(/dropout.*baseline/i);
    await expect(gridSection.locator('thead th[scope="col"]').first()).toContainText(/dropout.*baseline/i);
    await expect(gridSection.locator('tbody th[scope="row"]').first()).toBeVisible();
    await expect(gridSection.locator("tbody tr")).toHaveCount(body.y_dropout.length);
    await expect(gridSection.locator("tbody td")).toHaveCount(body.x_baseline.length * body.y_dropout.length);
    for (let row = 0; row < body.y_dropout.length; row++) {
      for (let col = 0; col < body.x_baseline.length; col++) {
        const power = body.power[row][col];
        expect(body.invalid_mask[row][col]).toBe(power === null);
        const cell = gridSection.locator(`[data-cell="${row}-${col}"]`);
        await expect(cell).toHaveAttribute("data-power", power === null ? "null" : String(power));
        await expect(cell).toHaveAttribute("data-baseline", String(body.x_baseline[col]));
        await expect(cell).toHaveAttribute("data-dropout", String(body.y_dropout[row]));
        await expect(gridSection.locator("tbody tr").nth(row).locator("td").nth(col)).toContainText(
          power === null ? "Invalid scenario (null)" : `${(power * 100).toFixed(1)}% (${power} fraction)`);
      }
    }

  });

  test("invalid ARR reaches FastAPI and displays the actual 422 validation error", async ({ page }) => {
    await selectPreset(page);
    // All shipped presets use RR; select ARR explicitly in the planning form.
    await page.getByLabel("Assumed difference between groups").selectOption("absolute_risk_reduction");
    await page.locator('[name="reductionPoints"]').fill("5");
    const design = await calculateFromUi(page);
    await goToStep(page, "Stress-test");
    await page.locator("#stress-baseline-num").fill("0.05");

    const { response, body } = await evaluateFromUi(page);
    expect(response.status()).toBe(422);
    const request = response.request().postDataJSON();
    expect(request.fixed_enrollment).toEqual(design.enrolled_n);
    expect(request.planned_design.effect).toEqual({ kind: "absolute_risk_reduction", value: 0.05 });
    expect(request.stress_scenario.control_event_rate).toBe(0.05);
    expect(body.error.message).toMatch(/invalid arr|cannot equal or exceed/i);

    const errorSection = page.locator('section[aria-labelledby="stress-heading"]');
    await expect(errorSection, "the visible UI must expose the backend's invalid ARR 422").toContainText(body.error.message);
    await expect(errorSection.getByText(/Could not update this estimate:/)).toBeVisible();
    await expect(page.getByRole("heading", { name: "Stress-test the plan", exact: true })).toBeVisible();
  });

  test("export is available and downloads JSON containing provenance and real calculation metadata", async ({ page }, testInfo) => {
    await selectPreset(page);
    await goToStep(page, "Methods");
    await expect(page.getByRole("region", { name: "Scenario export", exact: true })
      .getByRole("button", { name: "Download current scenario JSON", exact: true })).toBeDisabled();
    await goToStep(page, "Plan");
    const design = await calculateFromUi(page);
    await goToStep(page, "Stress-test");
    await page.getByText("Advanced: inspect range charts and grid data", { exact: true }).click();
    const gridResponse = await requireUiApiResponse(page, "/api/v1/scenarios/grid",
      () => page.getByRole("button", { name: "Load range analysis", exact: true }).click());
    expect(gridResponse.status()).toBe(200);
    const grid = await gridResponse.json();
    const evaluation = await simulateFromUi(page);
    expect(evaluation.response.status()).toBe(200);
    await goToStep(page, "Methods");
    const exportButton = exportLink(page);
    await expect(exportButton).toBeEnabled();
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      exportButton.click(),
    ]);
    const stream = await download.createReadStream();
    expect(stream, "export action must create a downloadable file").not.toBeNull();
    const chunks: Buffer[] = [];
    for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
    const downloadedJson = Buffer.concat(chunks).toString("utf8");
    const exported = JSON.parse(downloadedJson);
    await testInfo.attach("downloaded-workspace-export", { body: downloadedJson, contentType: "application/json" });
    const backendDir = path.resolve(__dirname, "../../../backend");
    const python = process.platform === "win32"
      ? path.join(backendDir, ".venv", "Scripts", "python.exe")
      : path.join(backendDir, ".venv", "bin", "python");
    const validation = spawnSync(python, ["-c",
      "import sys; from app.schemas import ExportPayload; ExportPayload.model_validate_json(sys.stdin.read())"],
      { cwd: backendDir, input: downloadedJson, encoding: "utf8", timeout: 10_000 });
    expect(validation.error, "backend export validator must execute").toBeUndefined();
    expect(validation.status, validation.stderr).toBe(0);

    expect(exported.export_schema_version).toBe(1);
    expect(exported.exported_at).toBeTruthy();
    expect(Object.keys(exported.provenance ?? {})).not.toHaveLength(0);
    expect(exported.fixed_enrollment).toEqual(design.enrolled_n);
    expect(exported.design_result).toEqual(canonicalResponse(design));
    expect(exported.evaluation_result).toEqual(canonicalResponse(evaluation.body));
    expect(exported.grid_result).toEqual(grid);
    expect(exported.evaluation_result.metadata.inputs_hash).toMatch(/^(?:sha256:)?[a-f0-9]{64}$/);
    expect(exported.software_versions ?? exported.evaluation_result.metadata.software_versions).toBeTruthy();
  });

  test("complete workflow makes no requests outside the exact local server origins", async ({ page }) => {
    await selectPreset(page);
    await calculateFromUi(page);
    await goToStep(page, "Stress-test");
    await page.getByText("Advanced: inspect range charts and grid data", { exact: true }).click();
    await requireUiApiResponse(
      page,
      "/api/v1/scenarios/grid",
      () => page.getByRole("button", { name: "Load range analysis", exact: true }).click(),
    );
    await evaluateFromUi(page);
    await simulateFromUi(page);
    await goToStep(page, "Methods");
    const exportButton = exportLink(page);
    await expect(exportButton, "current seeded results must provide a download link").toBeVisible();
    await expect(exportButton).toBeEnabled();
    await Promise.all([page.waitForEvent("download"), exportButton.click()]);
  });

  test("external WebSockets are intercepted and closed before connecting", async ({ page }) => {
    await page.goto("/");
    const state = await page.evaluate(async () => await new Promise<number>((resolve, reject) => {
      const socket = new WebSocket("wss://example.invalid/e2e-guard-probe");
      const timeout = window.setTimeout(() => reject(new Error("routed WebSocket did not close")), 2_000);
      socket.addEventListener("close", () => {
        window.clearTimeout(timeout);
        resolve(socket.readyState);
      }, { once: true });
      socket.addEventListener("error", () => {
        // A routed close may emit error as the browser reports the handshake
        // termination; the close event below confirms interception completed.
      }, { once: true });
    }));

    expect(state).toBe(WebSocket.CLOSED);
    const captured = forbiddenWebSockets.get(page) ?? [];
    expect(captured).toEqual(["wss://example.invalid/e2e-guard-probe"]);
    // This one attempt is the subject of the test; clear it after proving the
    // guard caught it so afterEach can continue checking unexpected attempts.
    captured.length = 0;
  });
});
