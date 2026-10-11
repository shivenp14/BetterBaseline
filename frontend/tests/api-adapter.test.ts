import assert from "node:assert/strict";
import { calculateDesign, evaluateScenario, getApiMode, getStressGrid } from "../lib/api";
import type { ExtendedCalculateRequest, ExtendedEvaluateRequest, ExtendedGridRequest } from "../lib/api";
import { initializeWorkspaceState, workspaceReducer } from "../lib/workspace-state";

const ledger = {
  "/planned_design/control_event_rate": {
    source: "manual_user" as const, description: "Edited one field", source_url: "https://example.org/protocol.pdf",
    source_location: "Page 14, Table 2", retrieved_at: "2026-10-11T12:00:00Z", verified_by_user: true,
  },
  "/stress_scenario/dropout/control": { source: "synthetic_preset" as const, description: "seed" },
};
const assumptions = {
  model_version: "binary-v1" as const, control_event_rate: 0.2,
  effect: { kind: "relative_risk" as const, value: 0.75 }, alpha: 0.05,
  target_power: 0.8, allocation_ratio: 1 as const,
  dropout: { control: 0.1, treatment: 0.1 },
};

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

async function run() {
  process.env.NEXT_PUBLIC_API_MODE = "live";
  assert.equal(getApiMode(), "live");
  let liveState = initializeWorkspaceState("baseline-collapse-v1");
  assert.equal(liveState.frozenEnrollment, null, "live preset data does not lock enrollment before calculation");
  assert.equal(liveState.evaluateResult !== null, true, "preset fixture may remain visible while live enrollment is unfrozen");
  liveState = workspaceReducer(liveState, { type: "LOAD_PRESET", presetId: "attrition-shock-v1" });
  assert.equal(liveState.frozenEnrollment, null, "loading a preset keeps live enrollment unfrozen");
  liveState = workspaceReducer(liveState, { type: "RESET_TO_PRESET" });
  assert.equal(liveState.frozenEnrollment, null, "resetting a preset keeps live enrollment unfrozen");
  let captured: { url: string; body: Record<string, unknown>; signal?: AbortSignal } | undefined;
  let gridAvailable = false;
  globalThis.fetch = (async (input, init) => {
    captured = { url: String(input), body: JSON.parse(String(init?.body)), signal: init?.signal as AbortSignal };
    if (String(input).endsWith("/design/calculate")) return response({
      model_version: "binary-v1", method: "cohen_h_normal_v1", p_treatment: 0.15,
      evaluable_n: { control: 903, treatment: 903 }, enrolled_n: { control: 1004, treatment: 1004 },
      nominal_power_evaluable: 0.8, warnings: ["backend-calculation-warning"], diagnostics: [{
        code: "CALC_DIAGNOSTIC", severity: "warning", field: "control_event_rate", method: "cohen_h_normal_v1", message: "Backend diagnostic",
      }], inputs_hash: "sha256:calc", provenance: ledger,
    });
    if (String(input).endsWith("/scenarios/evaluate")) return response({
      model_version: "binary-v1", analytic: { method: "cohen_h_normal_v1", conditional_power_approx: 0.47,
        assumed_evaluable_n: { control: 713, treatment: 713 } },
      monte_carlo: { method: "pooled_two_proportion_z_v1", significant_two_sided_fraction: 0.2,
        significant_favorable_fraction: 0.18, mcse_two_sided: 0.004, mcse_favorable: 0.004,
        invalid_test_fraction: 0, replicates: 10000, seed: 42 }, warnings: ["backend-evaluation-warning"],
      diagnostics: [{ code: "EVAL_DIAGNOSTIC", severity: "info", field: "simulation", method: "pooled_two_proportion_z_v1", message: "Backend evaluation diagnostic" }],
      metadata: { computed_at: "now", inputs_hash: "sha256:eval", software_versions: { python: "3.12" }, fixed_enrollment: { control: 1004, treatment: 1004 } }, provenance: ledger,
    });
    if (!gridAvailable) return response({ detail: "Scenario grid endpoint implementation owned by Issue #66." }, 501);
    return response({
      model_version: "binary-v1", method: "cohen_h_normal_v1", x_baseline: [0.1, 0.2, 0.3],
      y_dropout: [0, 0.15, 0.3], power: [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3], [0.1, 0.2, 0.3]],
      invalid_mask: [[false, false, false], [false, false, false], [false, false, false]], target_power: 0.8,
      planned_point: { p_control: 0.2, dropout: 0.1, power: 0.8, is_safe: true, is_valid: true },
      selected_point: null, frontier_points: [{ p_control: 0.2, dropout: 0.15 }],
      warnings: ["backend-grid-warning"], diagnostics: [{ code: "GRID_DIAGNOSTIC", severity: "warning", field: "grid", method: "cohen_h_normal_v1", message: "Backend grid diagnostic" }], computed_at: "now", inputs_hash: "sha256:grid",
      fixed_enrollment: { control: 1004, treatment: 1004 }, below_target: [[false]], analytic_delta: 0.1,
      software_versions: { python: "3.12" }, contour_segments: [], power_curve: [], invalid_cell_count: 0,
      worst_case_power: 0.2, provenance: ledger,
    });
  }) as typeof fetch;

  const calcRequest: ExtendedCalculateRequest = { ...assumptions, preset_id: "fixture-id", provenance_ledger: ledger };
  const calculated = await calculateDesign(calcRequest);
  assert.equal(captured?.url, `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"}/api/v1/design/calculate`);
  assert.deepEqual(captured?.body, { ...assumptions, provenance: ledger }, "calculate sends canonical assumptions and the actual API provenance map");
  assert.equal(calculated.mock, false);
  assert.equal(calculated.execution?.mode, "backend");
  assert.deepEqual(calculated.provenance.field_provenance, ledger);
  assert.equal(calculated.warnings[0], "backend-calculation-warning");
  assert.equal(calculated.diagnostics?.[0].message, "Backend diagnostic");
  assert.equal(calculated.provenance.field_provenance?.["/planned_design/control_event_rate"].source_location, "Page 14, Table 2");
  assert.equal(calculated.provenance.field_provenance?.["/planned_design/control_event_rate"].verified_by_user, true);
  const calculateRevision = liveState.requestRevision;
  liveState = workspaceReducer(liveState, {
    type: "START_CALCULATE", requestRevision: calculateRevision,
    expectedInputGeneration: liveState.inputGeneration,
  });
  liveState = workspaceReducer(liveState, {
    type: "CALCULATE_SUCCESS", response: calculated, requestRevision: calculateRevision,
  });
  assert.deepEqual(liveState.frozenEnrollment, calculated.enrolled_n, "successful live calculation freezes backend enrollment");
  liveState = workspaceReducer(liveState, { type: "UPDATE_STRESS_BASELINE", baseline: 0.18 });
  liveState = workspaceReducer(liveState, { type: "UPDATE_STRESS_DROPOUT", dropout: 0.25 });
  assert.deepEqual(liveState.frozenEnrollment, calculated.enrolled_n, "stress changes retain calculated enrollment");

  const evalRequest: ExtendedEvaluateRequest = {
    planned_design: assumptions, fixed_enrollment: liveState.frozenEnrollment!,
    stress_scenario: { control_event_rate: liveState.stressBaseline, dropout: { control: liveState.stressDropout, treatment: liveState.stressDropout }, effect_override: null },
    simulation: { replicates: 10000, seed: 42 }, preset_id: "fixture-id", provenance_ledger: ledger,
  };
  const evaluated = await evaluateScenario(evalRequest);
  assert.equal(captured?.url, `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"}/api/v1/scenarios/evaluate`);
  assert.deepEqual(captured?.body, {
    planned_design: assumptions, fixed_enrollment: { control: 1004, treatment: 1004 },
    stress_scenario: evalRequest.stress_scenario, simulation: { replicates: 10000, seed: 42 }, provenance: ledger,
  }, "evaluate maps the ledger into the backend's accepted provenance field and strips UI metadata");
  assert.deepEqual(evaluated.provenance.field_provenance, ledger);
  assert.equal(evaluated.warnings[0], "backend-evaluation-warning");
  assert.equal(evaluated.diagnostics?.[0].message, "Backend evaluation diagnostic");
  assert.equal(evaluated.mock, false);

  const gridRequest: ExtendedGridRequest = {
    planned_design: assumptions, fixed_enrollment: { control: 1004, treatment: 1004 },
    x_baseline: [0.1, 0.2, 0.3], y_dropout: [0, 0.15, 0.3],
    selected_scenario: { control_event_rate: 0.18, dropout: { control: 0.2, treatment: 0.2 }, effect_override: null },
    preset_id: "fixture-id", provenance_ledger: ledger,
  };
  await assert.rejects(getStressGrid(gridRequest), /Scenario grid endpoint implementation owned by Issue #66/);
  const gridBody = captured?.body as Record<string, unknown>;
  assert.deepEqual(gridBody.x_baseline, { min: 0.1, max: 0.3, steps: 3 });
  assert.deepEqual(gridBody.y_dropout, { min: 0, max: 0.3, steps: 3 });
  assert.deepEqual(gridBody.selected_scenario, gridRequest.selected_scenario);
  assert.equal(gridBody.preset_id, undefined);
  gridAvailable = true;
  const liveGrid = await getStressGrid(gridRequest);
  assert.equal(liveGrid.planned_point.baseline, 0.2);
  assert.equal((liveGrid.planned_point as unknown as { p_control: number }).p_control, 0.2,
    "grid adapter retains canonical point coordinates for export");
  assert.equal((liveGrid.planned_point as unknown as { power: number }).power, 0.8,
    "grid adapter retains canonical point results for export");
  assert.equal((liveGrid.frontier_points[0] as unknown as { p_control: number }).p_control, 0.2);
  assert.equal(liveGrid.selected_point, null, "missing backend selected point remains unavailable instead of falling back to planned point");
  assert.deepEqual(liveGrid.provenance.field_provenance, ledger, "successful live grid response keeps the full request ledger for result/export consumers");
  assert.equal(liveGrid.warnings[0], "backend-grid-warning");
  assert.equal(liveGrid.diagnostics?.[0].message, "Backend grid diagnostic");
  gridAvailable = false;

  globalThis.fetch = (async () => response({ error: { code: "INVALID_MODEL_INPUT", message: "ARR cannot exceed risk", field: "effect", recoverable: true } }, 422)) as typeof fetch;
  await assert.rejects(calculateDesign(calcRequest), /INVALID_MODEL_INPUT: ARR cannot exceed risk/);
  let fetchCalls = 0;
  globalThis.fetch = (async () => { fetchCalls++; return response({}); }) as typeof fetch;
  const preAborted = new AbortController(); preAborted.abort();
  await assert.rejects(calculateDesign(calcRequest, preAborted.signal), (error: Error) => error.name === "AbortError");
  assert.equal(fetchCalls, 0, "pre-aborted request must not reach fetch");
  globalThis.fetch = (async () => ({
    ok: true,
    status: 200,
    json: () => Promise.reject(new DOMException("Body read aborted", "AbortError")),
  } as Response)) as typeof fetch;
  await assert.rejects(calculateDesign(calcRequest), (error: Error) => error.name === "AbortError",
    "an abort while consuming a response body remains a cancellation");
  globalThis.fetch = (async () => ({
    ok: true,
    status: 200,
    json: () => Promise.reject(new SyntaxError("Malformed JSON")),
  } as Response)) as typeof fetch;
  await assert.rejects(calculateDesign(calcRequest), /empty or invalid JSON response/,
    "malformed JSON retains the normal invalid-response error");
  globalThis.fetch = ((_input, init) => new Promise((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
  })) as typeof fetch;
  const inFlight = new AbortController();
  const pending = evaluateScenario(evalRequest, inFlight.signal);
  inFlight.abort();
  await assert.rejects(pending, (error: Error) => error.name === "AbortError");

  process.env.NEXT_PUBLIC_API_MODE = "demo";
  const state = initializeWorkspaceState();
  assert.equal(state.calculatedDesign?.execution?.mode, "demo");
  assert.deepEqual(state.gridResult?.provenance.field_provenance, state.provenanceLedger);
  const demoFixtureGrid = await getStressGrid({
    planned_design: state.plannedDraft, fixed_enrollment: state.frozenEnrollment!,
    x_baseline: state.gridResult!.x_baseline, y_dropout: state.gridResult!.y_dropout,
    preset_id: state.presetId,
  });
  assert.deepEqual(demoFixtureGrid.provenance.field_provenance, state.provenanceLedger);
  const demoCustomGrid = await getStressGrid({
    planned_design: { ...state.plannedDraft, control_event_rate: 0.21 }, fixed_enrollment: state.frozenEnrollment!,
    x_baseline: [0.08, 0.16, 0.24], y_dropout: [0, 0.2],
    preset_id: state.presetId, provenance_ledger: ledger,
  });
  assert.deepEqual(demoCustomGrid.provenance.field_provenance, ledger);
  assert.equal(demoCustomGrid.execution?.mode, "demo");
  console.log("API adapter regression checks passed (canonical payloads, errors, aborts, grid axes, provenance and demo paths).");
}

run().catch((error) => { console.error(error); process.exitCode = 1; });
