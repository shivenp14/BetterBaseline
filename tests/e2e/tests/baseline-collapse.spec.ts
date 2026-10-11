/**
 * E2E acceptance tests for the real baseline-collapse workflow (#78).
 *
 * Every calculation assertion is tied to an HTTP request made by a UI action
 * and the corresponding local FastAPI response. The current mock shell does
 * not satisfy these tests; its missing integration is reported as pending #76.
 */

import { test, expect, Page, Response } from "@playwright/test";

const BACKEND_PORT = Number(process.env.BACKEND_PORT || 8001);
const FRONTEND_PORT = Number(process.env.FRONTEND_PORT || 3001);
const BACKEND_ORIGIN = `http://127.0.0.1:${BACKEND_PORT}`;
const FRONTEND_ORIGIN = `http://localhost:${FRONTEND_PORT}`;
const LOCAL_ORIGINS = new Set([BACKEND_ORIGIN, FRONTEND_ORIGIN]);
const PRESET_ID = "baseline-collapse-v1";
const ATTRITION_PRESET_ID = "attrition-shock-v1";
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
): Promise<Response> {
  const pendingResponse = page.waitForResponse(
    (response) => {
      const url = new URL(response.url());
      return url.origin === BACKEND_ORIGIN && url.pathname === endpoint && response.request().method() === "POST";
    },
    { timeout: RESPONSE_TIMEOUT_MS },
  );
  await action();
  try {
    return await pendingResponse;
  } catch (error) {
    throw new Error(
      `[E2E integration pending #76] UI action did not receive ${endpoint} from ${BACKEND_ORIGIN}. ` +
        `The current mock-only shell performs no API I/O. Original error: ${String(error)}`,
    );
  }
}

async function selectPreset(page: Page, id = PRESET_ID): Promise<void> {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /better baseline/i })).toBeVisible();
  await page.getByLabel("Synthetic scenario").selectOption(id);
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
    () => page.getByRole("button", { name: /evaluate/i }).click(),
  );
  return { response, body: await response.json() };
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
    await expect(page.locator('section[aria-labelledby="planned-heading"]')).toContainText("903");
    await expect(page.locator('section[aria-labelledby="planned-heading"]')).toContainText(design.method);
  });

  test("Evaluate sends the frozen enrollment and current stress input to the local API", async ({ page }) => {
    await selectPreset(page);
    const design = await calculateFromUi(page);
    await page.locator("#baseline").fill("10");

    const { response, body } = await evaluateFromUi(page);
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

    const evaluateSection = page.locator('section[aria-labelledby="evaluate-heading"]');
    await expect(evaluateSection).toContainText(`${(body.analytic.conditional_power_approx * 100).toFixed(0)}%`);
    await expect(evaluateSection).toContainText(String(body.monte_carlo.replicates));
  });

  test("changed stress produces a fresh backend calculation and updated MC fields", async ({ page }) => {
    await selectPreset(page);
    const design = await calculateFromUi(page);
    await page.locator("#baseline").fill("10");
    const first = await evaluateFromUi(page);
    expect(first.response.status()).toBe(200);
    const firstRequest = first.response.request().postDataJSON();
    expect(firstRequest.fixed_enrollment).toEqual(design.enrolled_n);
    expect(firstRequest.stress_scenario.control_event_rate).toBe(0.1);

    await page.locator("#baseline").fill("15");
    const changed = await evaluateFromUi(page);
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

    const evaluateSection = page.locator('section[aria-labelledby="evaluate-heading"]');
    await expect(evaluateSection).toContainText(`${(changed.body.analytic.conditional_power_approx * 100).toFixed(0)}%`);
    const twoSidedMcse = evaluateSection.locator("li").filter({ hasText: /two-sided significance MCSE/i });
    const favorableMcse = evaluateSection.locator("li").filter({ hasText: /favorable-direction significance MCSE/i });
    await expect(twoSidedMcse, "two-sided MCSE must have its own visible label").toBeVisible();
    await expect(favorableMcse, "favorable-direction MCSE must have its own visible label").toBeVisible();
    await expect(twoSidedMcse).toContainText(`${(changed.body.monte_carlo.mcse_two_sided * 100).toFixed(1)}%`);
    await expect(favorableMcse).toContainText(`${(changed.body.monte_carlo.mcse_favorable * 100).toFixed(1)}%`);
  });

  test("grid action calls the local API with frozen enrollment and displays its response", async ({ page }) => {
    await selectPreset(page);
    const design = await calculateFromUi(page);
    const response = await requireUiApiResponse(
      page,
      "/api/v1/scenarios/grid",
      () => page.getByRole("button", { name: /grid/i }).click(),
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
    const gridSection = page.locator('section[aria-labelledby="grid-heading"]');
    await expect(gridSection).toContainText(body.grid_label);
    await expect(gridSection).toContainText("Cell indexing follows [dropout][baseline]");
    await expect(gridSection.locator("table caption")).toContainText(/dropout.*baseline/i);
    await expect(gridSection.locator('thead th[scope="col"]').first()).toContainText(/dropout.*baseline/i);
    await expect(gridSection.locator('tbody th[scope="row"]').first()).toBeVisible();
  });

  test("invalid ARR reaches FastAPI and displays the actual 422 validation error", async ({ page }) => {
    await selectPreset(page, ATTRITION_PRESET_ID);
    const design = await calculateFromUi(page);
    await page.locator("#baseline").fill("5");

    const { response, body } = await evaluateFromUi(page);
    expect(response.status()).toBe(422);
    const request = response.request().postDataJSON();
    expect(request.fixed_enrollment).toEqual(design.enrolled_n);
    expect(request.planned_design.effect).toEqual({ kind: "absolute_risk_reduction", value: 0.05 });
    expect(request.stress_scenario.control_event_rate).toBe(0.05);
    expect(body.error.message).toMatch(/invalid arr|cannot equal or exceed/i);

    const alert = page.getByRole("alert");
    await expect(alert, "the visible UI must expose the backend's invalid ARR 422").toBeVisible();
    await expect(alert).toContainText(/arr/i);
    await expect(page.getByRole("heading", { name: /better baseline/i })).toBeVisible();
  });

  test("export is available and downloads JSON containing provenance and real calculation metadata", async ({ page }) => {
    await selectPreset(page);
    const exportButton = page.getByRole("button", { name: /export/i });
    await expect(
      exportButton,
      "[E2E integration pending #76] export button is missing; export assembly is not integrated",
    ).toBeVisible();

    await calculateFromUi(page);
    await evaluateFromUi(page);
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      exportButton.click(),
    ]);
    const stream = await download.createReadStream();
    expect(stream, "export action must create a downloadable file").not.toBeNull();
    const chunks: Buffer[] = [];
    for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
    const exported = JSON.parse(Buffer.concat(chunks).toString("utf8"));

    expect(exported.export_schema_version).toBe(1);
    expect(exported.exported_at).toBeTruthy();
    expect(Object.keys(exported.provenance ?? {})).not.toHaveLength(0);
    expect(exported.evaluation_result.metadata.inputs_hash).toMatch(/^[a-f0-9]{64}$/);
    expect(exported.software_versions ?? exported.evaluation_result.metadata.software_versions).toBeTruthy();
  });

  test("complete workflow makes no requests outside the exact local server origins", async ({ page }) => {
    await selectPreset(page);
    await calculateFromUi(page);
    await evaluateFromUi(page);
    await requireUiApiResponse(
      page,
      "/api/v1/scenarios/grid",
      () => page.getByRole("button", { name: /grid/i }).click(),
    );
    const exportButton = page.getByRole("button", { name: /export/i });
    await expect(exportButton, "[E2E integration pending #76] export action is missing").toBeVisible();
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
