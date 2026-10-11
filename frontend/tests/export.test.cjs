/* eslint-disable @typescript-eslint/no-require-imports -- Compile owned TS in memory for Node tests. */
// EXPORT_TEST_PYTHON=/path/to/backend/.venv/bin/python node tests/export.test.cjs
// Starts a fresh local backend; no mock responses or cached fixtures.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const net = require("node:net");
const { spawn, spawnSync } = require("node:child_process");
const { test, before, after } = require("node:test");
const ts = require("typescript");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
require.extensions[".ts"] = require.extensions[".tsx"] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, "utf8"), {
  fileName: filename, compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
}).outputText, filename);
const { validateScenarioExport, serializeScenarioExport, parseScenarioExport, buildScenarioExport, normalizeExportProvenance } = require("../lib/export.ts");
const { computeWorkspaceExportInputsHash } = require("../lib/workspace-export.ts");
const { ScenarioExport } = require("../components/ScenarioExport.tsx");
const { initializeWorkspaceState, workspaceReducer } = require("../lib/workspace-state.ts");
const python = process.env.EXPORT_TEST_PYTHON || "python3";
const backend = path.resolve(__dirname, "../../backend");
let server, origin, log = "", fixture, manualFixture, arrFixture;
async function post(route, payload) {
  const response = await fetch(`${origin}/api/v1/${route}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  const body = await response.json(); assert.equal(response.status, 200, JSON.stringify(body)); return body;
}
function provenance(planned, stress, manual) {
  const result = {};
  function walk(value, pointer) {
    if (value && typeof value === "object") Object.entries(value).forEach(([key, item]) => walk(item, `${pointer}/${key}`));
    else result[pointer] = { source: manual ? "manual_user" : "synthetic_preset", description: manual ? "Manual review fixture" : "Synthetic test assumption", retrieved_at: "2026-10-11T00:00:00Z", source_url: null };
  }
  walk(planned, "/planned_design"); walk(stress, "/stress_scenario");
  for (const p of ["/fixed_enrollment/control", "/fixed_enrollment/treatment", "/simulation/seed", "/simulation/replicates"]) result[p] = { source: manual ? "manual_user" : "synthetic_preset", description: "Test configuration", retrieved_at: null, source_url: null };
  return result;
}
async function calculateFixture(manual = false, arr = false) {
  const planned = { model_version: "binary-v1", control_event_rate: .2, effect: { kind: arr ? "absolute_risk_reduction" : "relative_risk", value: arr ? .1 : .75 }, alpha: .05, target_power: .8, allocation_ratio: 1, dropout: { control: 0, treatment: 0 } };
  const stress = { control_event_rate: arr ? .2 : .1, dropout: { control: .1, treatment: .1 }, effect_override: null };
  const ledger = provenance(planned, stress, manual);
  if (manual) {
    Object.assign(ledger["/planned_design/alpha"], { source: "protocol_curated", source_location: "Protocol §3 — α", verified_by_user: true, is_observed_registry_result: false });
    Object.assign(ledger["/stress_scenario/control_event_rate"], { source: "clinicaltrials_registry", source_url: "https://clinicaltrials.gov/study/NCT00000000", source_location: "Observed result table", description: "Observed registry result used for hypothetical sensitivity", verified_by_user: false, is_observed_registry_result: true });
  }
  const design = await post("design/calculate", { ...planned, provenance: ledger });
  const inputs = { planned_design: planned, fixed_enrollment: design.enrolled_n, stress_scenario: stress, simulation: { seed: 42, replicates: 1000 }, provenance: ledger };
  const evaluation = await post("scenarios/evaluate", inputs);
  const grid = await post("scenarios/grid", { planned_design: planned, fixed_enrollment: design.enrolled_n, selected_scenario: stress, x_baseline: { min: .05, max: .35, steps: 3 }, y_dropout: { min: 0, max: .4, steps: 2 }, provenance: ledger });
  const canonicalLedger = normalizeExportProvenance(evaluation.provenance);
  return { export_schema_version: 1, model_version: "binary-v1", planned_design: planned, fixed_enrollment: design.enrolled_n, stress_scenario: stress, design_result: design, evaluation_result: evaluation, grid_result: grid, software_versions: evaluation.metadata.software_versions, provenance: canonicalLedger, exported_at: "2026-10-11T00:00:00Z", inputs_hash: computeWorkspaceExportInputsHash(planned, design.enrolled_n, stress, canonicalLedger) };
}
before(async () => {
  const listener = net.createServer(); await new Promise(resolve => listener.listen(0, "127.0.0.1", resolve));
  const port = listener.address().port; await new Promise(resolve => listener.close(resolve)); origin = `http://127.0.0.1:${port}`;
  server = spawn(python, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(port)], { cwd: backend, stdio: ["ignore", "pipe", "pipe"] });
  server.stdout.on("data", data => { log += data; }); server.stderr.on("data", data => { log += data; });
  for (let i = 0; i < 100; i++) {
    if (server.exitCode !== null) throw new Error(log);
    try { if ((await fetch(`${origin}/healthz`)).ok) break; } catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  fixture = await calculateFixture(); manualFixture = await calculateFixture(true); arrFixture = await calculateFixture(true, true);
  if (process.env.EXPORT_TEST_OUTPUT) {
    fs.mkdirSync(process.env.EXPORT_TEST_OUTPUT, { recursive: true });
    for (const [name, data] of [["synthetic", fixture], ["manual", manualFixture], ["arr", arrFixture]]) fs.writeFileSync(path.join(process.env.EXPORT_TEST_OUTPUT, `${name}.json`), serializeScenarioExport(data));
  }
});
after(async () => { if (server && server.exitCode === null) { server.kill(); await new Promise(resolve => server.once("exit", resolve)); } });
test("fresh synthetic and manual HTTP runs round-trip without losing any input/result/source metadata", () => {
  for (const data of [fixture, manualFixture, arrFixture]) {
    assert.deepEqual(parseScenarioExport(serializeScenarioExport(data)), data);
    assert.deepEqual(validateScenarioExport(data), data);
    assert.notEqual(data.design_result.inputs_hash, data.evaluation_result.metadata.inputs_hash);
    assert.notEqual(data.grid_result.inputs_hash, data.evaluation_result.metadata.inputs_hash);
    assert.ok(data.evaluation_result.monte_carlo.rng);
    assert.ok(data.evaluation_result.diagnostics.length);
    assert.deepEqual(data.grid_result.provenance, data.provenance);
  }
  assert.equal(fixture.provenance["/planned_design/control_event_rate"].source, "synthetic_preset");
  assert.equal(manualFixture.provenance["/planned_design/control_event_rate"].source, "manual_user");
  assert.equal(manualFixture.provenance["/planned_design/alpha"].source_location, "Protocol §3 — α");
  assert.equal(manualFixture.provenance["/planned_design/alpha"].verified_by_user, true);
  assert.equal(manualFixture.provenance["/stress_scenario/control_event_rate"].verified_by_user, false);
  assert.equal(manualFixture.provenance["/stress_scenario/control_event_rate"].is_observed_registry_result, true);
  assert.equal(arrFixture.grid_result.invalid_cell_count, 2);
  assert.equal(arrFixture.grid_result.power[0][0], null);
});
test("downloads reopen as complete JSON; unavailable/invalid snapshots have no download link", () => {
  const html = renderToStaticMarkup(React.createElement(ScenarioExport, { payload: fixture }));
  const url = html.match(/href="data:application\/json;charset=utf-8,([^"]+)"/)[1].replaceAll("&#x27;", "'").replaceAll("&amp;", "&");
  assert.deepEqual(parseScenarioExport(decodeURIComponent(url)), fixture);
  assert.match(JSON.parse(decodeURIComponent(url)).inputs_hash, /^sha256:[a-f0-9]{64}$/);
  assert.match(html, /download="better-baseline-scenario-v1.json"/);
  for (const payload of [null, { ...fixture, grid_result: null }]) {
    const disabled = renderToStaticMarkup(React.createElement(ScenarioExport, { payload }));
    assert.match(disabled, /disabled=""/); assert.ok(!disabled.includes("data:application/json"));
  }
});
test("complete artifacts validate through backend ExportPayload plus full #65 evaluation extension", () => {
  const result = spawnSync(python, ["-c", "import sys,json; from app.schemas import ExportPayload; from app.routers.scenarios import EvaluationResponse; p=json.load(sys.stdin); assert 'inputs_hash' in p; parsed=ExportPayload.model_validate(p); assert parsed.inputs_hash==p['inputs_hash']; e=EvaluationResponse.model_validate(p['evaluation_result']); assert e.model_dump(mode='json')==p['evaluation_result']; print('validated')"], { cwd: backend, input: JSON.stringify(manualFixture), encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr); assert.match(result.stdout, /validated/);
});
function currentRuns() {
  const state = initializeWorkspaceState();
  Object.assign(state, structuredClone({ plannedDraft: fixture.planned_design, frozenEnrollment: fixture.fixed_enrollment, stressBaseline: fixture.stress_scenario.control_event_rate, stressDropout: fixture.stress_scenario.dropout.control, provenanceLedger: fixture.provenance,
    calculatedDesign: fixture.design_result, evaluateResult: fixture.evaluation_result, gridResult: fixture.grid_result, designStatus: "success", evaluateStatus: "success", gridStatus: "success", requestRevision: 4 }));
  const capture = response => ({ requestState: structuredClone(state), response: structuredClone(response) });
  return { state, runs: { design: capture(fixture.design_result), evaluation: capture(fixture.evaluation_result), grid: capture(fixture.grid_result) } };
}
test("current export binds endpoint hashes to detached requests; edits and pending/errors disable it", () => {
  const { state, runs } = currentRuns();
  assert.deepEqual(buildScenarioExport(state, runs, fixture.exported_at), fixture);
  for (const mutate of [s => s.inputGeneration++, s => s.stressBaseline = .12, s => s.stressDropout = .2, s => s.plannedDraft.alpha = .01, s => s.frozenEnrollment.control++, s => s.provenanceLedger["/planned_design/alpha"].source = "manual_user", s => s.gridResult.inputs_hash = "different", s => s.evaluateResult.metadata.inputs_hash = "different"]) {
    const next = structuredClone(state); mutate(next); assert.throws(() => buildScenarioExport(next, runs));
  }
  for (const [field, statuses] of [["designStatus", ["idle", "calculating", "error"]], ["evaluateStatus", ["idle", "stale", "evaluating", "error"]], ["gridStatus", ["idle", "stale", "loading", "error"]]]) {
    statuses.forEach(status => assert.throws(() => buildScenarioExport({ ...state, [field]: status }, runs)));
  }
  assert.throws(() => buildScenarioExport(state, { ...runs, grid: null }));
});
test("independent evaluate/grid tokens do not stale current input snapshots", () => {
  const { state, runs } = currentRuns();
  let next = workspaceReducer(state, { type: "START_EVALUATE", requestRevision: 20, expectedInputGeneration: state.inputGeneration });
  next = workspaceReducer(next, { type: "START_GRID", requestRevision: 21, expectedInputGeneration: state.inputGeneration });
  assert.throws(() => buildScenarioExport(next, runs));
  next = workspaceReducer(next, { type: "EVALUATE_SUCCESS", requestRevision: 20, response: state.evaluateResult });
  next = workspaceReducer(next, { type: "GRID_SUCCESS", requestRevision: 21, response: state.gridResult });
  assert.deepEqual(buildScenarioExport(next, runs, fixture.exported_at), fixture);
  assert.strictEqual(workspaceReducer(next, { type: "GRID_SUCCESS", requestRevision: 19, response: state.gridResult }), next);
  const edited = workspaceReducer(next, { type: "UPDATE_SIMULATION_PROVENANCE", pointers: ["/simulation/seed"] });
  assert.throws(() => buildScenarioExport(edited, runs));
});
test("omitted audit fields equal null, preserve full audit records, and reject tampered canonical hashes", () => {
  const { state, runs } = currentRuns();
  for (const source of Object.values(state.provenanceLedger)) for (const key of Object.keys(source)) if (source[key] === null) delete source[key];
  assert.deepEqual(buildScenarioExport(state, runs, fixture.exported_at), fixture);
  const data = structuredClone(manualFixture);
  for (const source of Object.values(data.provenance)) for (const key of Object.keys(source)) if (source[key] === null) delete source[key];
  assert.deepEqual(parseScenarioExport(JSON.stringify(data)), data);
  for (const mutate of [p => delete p.inputs_hash, p => p.inputs_hash = "sha256:" + "0".repeat(64), p => p.provenance["/simulation/seed"].description = "tampered", p => p.evaluation_result.provenance["/planned_design/alpha"].verified_by_user = false, p => p.provenance["/planned_design/alpha"].verified_by_user = "yes", p => p.provenance["/planned_design/alpha"].is_observed_registry_result = true]) {
    const bad = structuredClone(manualFixture); mutate(bad); assert.throws(() => parseScenarioExport(JSON.stringify(bad)));
  }
});
test("reload rejects missing replay metadata, contradictory grids, versions, sources and malformed JSON", () => {
  const mutations = [p => p.export_schema_version = 2, p => p.extra = true, p => delete p.grid_result, p => delete p.evaluation_result.monte_carlo.rng, p => delete p.evaluation_result.monte_carlo.mcse_favorable,
    p => delete p.provenance["/simulation/seed"], p => p.provenance["/planned_design/alpha"].source = "unknown", p => p.grid_result.selected_point.p_control = .3,
    p => p.grid_result.power[0][0] = null, p => p.grid_result.below_target[0][0] = null, p => p.grid_result.power_curve.pop(), p => delete p.grid_result.contour_segments,
    p => p.grid_result.software_versions.numpy = "other", p => p.evaluation_result.monte_carlo.seed = -1, p => p.exported_at = "yesterday", p => p.design_result.enrolled_n.control++,
    p => p.grid_result.invalid_cell_count++, p => p.evaluation_result.analytic.conditional_power_approx = .999];
  for (const mutate of mutations) { const data = structuredClone(fixture); mutate(data); assert.throws(() => validateScenarioExport(data)); }
  const nonfinite = structuredClone(fixture); nonfinite.grid_result.power[0][0] = NaN; assert.throws(() => serializeScenarioExport(nonfinite));
  assert.throws(() => parseScenarioExport("{bad JSON"));
});
