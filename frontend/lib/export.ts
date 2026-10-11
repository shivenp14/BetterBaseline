import type { CalculateResponse, EvaluateRequest, StatisticalDiagnostic, TrialAssumptions } from "./contracts";
import type { WorkspaceState, ProvenanceLedger } from "./workspace-contracts";
import type { CurveApiResponse } from "../components/PowerCurve";
import type { HeatmapApiResponse } from "../components/StressHeatmap";
import { parseSimulationResult, validateSimulationRequest, type SimulationResult } from "./simulation-client";

/** Raw backend coordinates and all result metadata must survive the API adapter. */
export type ExportGridResult = CurveApiResponse & HeatmapApiResponse & {
  model_version: "binary-v1";
  computed_at: string;
  software_versions: Record<string, string>;
  provenance: ProvenanceLedger;
  below_target: (boolean | null)[][];
  invalid_cell_count: number;
  worst_case_power: number | null;
  frontier_points: unknown[];
};
export type ExportEvaluationResult = SimulationResult & { diagnostics?: StatisticalDiagnostic[] };
export type ExportDesignResult = Omit<CalculateResponse, "provenance" | "execution" | "mock">;

/** ExportPayload v1 field set from backend/app/schemas.py. Full evaluation
 * extensions from #65 are retained, including both MCSEs and sampled counts.
 * Each result hash describes its own endpoint request; these hashes differ.
 */
export interface ScenarioExportPayload {
  export_schema_version: 1;
  model_version: "binary-v1";
  planned_design: TrialAssumptions;
  fixed_enrollment: EvaluateRequest["fixed_enrollment"];
  stress_scenario: EvaluateRequest["stress_scenario"];
  design_result: ExportDesignResult;
  evaluation_result: ExportEvaluationResult;
  grid_result: ExportGridResult;
  software_versions: Record<string, string>;
  provenance: ProvenanceLedger;
  exported_at: string;
}
export interface CompletedExportRun<T> { requestState: WorkspaceState; response: T }
export interface ExportRuns {
  design: CompletedExportRun<ExportDesignResult> | null;
  evaluation: CompletedExportRun<ExportEvaluationResult> | null;
  grid: CompletedExportRun<ExportGridResult> | null;
}

export class ScenarioExportError extends Error {
  constructor(message: string) { super(message); this.name = "ScenarioExportError"; }
}
function requireValue(condition: unknown, message: string): asserts condition {
  if (!condition) throw new ScenarioExportError(message);
}
function record(value: unknown, field: string): Record<string, unknown> {
  requireValue(value && typeof value === "object" && !Array.isArray(value), `${field} must be an object.`);
  return value as Record<string, unknown>;
}
function text(value: unknown, field: string): asserts value is string {
  requireValue(typeof value === "string" && value.length > 0, `${field} is required.`);
}
function timestamp(value: unknown, field: string) {
  text(value, field);
  requireValue(/^\d{4}-\d\d-\d\dT/.test(value) && Number.isFinite(Date.parse(value)), `${field} must be an ISO timestamp.`);
}
function finite(value: unknown, field: string, min = 0, max = 1): asserts value is number {
  requireValue(typeof value === "number" && Number.isFinite(value) && value >= min && value <= max, `${field} is outside its allowed range.`);
}
function counts(value: unknown, field: string, min = 1) {
  const v = record(value, field);
  finite(v.control, field, min, 1_000_000); finite(v.treatment, field, min, 1_000_000);
  requireValue(Number.isInteger(v.control) && v.control === v.treatment, `${field} requires equal whole arm counts.`);
}
function same(a: unknown, b: unknown): boolean {
  function order(v: unknown): unknown {
    if (Array.isArray(v)) return v.map(order);
    if (v && typeof v === "object") return Object.fromEntries(Object.entries(v).sort(([a], [b]) => a.localeCompare(b)).map(([k, item]) => [k, order(item)]));
    return v;
  }
  return JSON.stringify(order(a)) === JSON.stringify(order(b));
}
function jsonValues(value: unknown): void {
  if (typeof value === "number") requireValue(Number.isFinite(value), "Export contains a nonfinite number.");
  else if (Array.isArray(value)) value.forEach(jsonValues);
  else if (value && typeof value === "object") Object.values(value).forEach(jsonValues);
  else requireValue(value === null || ["boolean", "string"].includes(typeof value), "Export contains a value JSON cannot preserve.");
}
function warnings(value: unknown, field: string) {
  requireValue(Array.isArray(value) && value.every(v => typeof v === "string"), `${field} must contain warning strings.`);
}
function versions(value: unknown, field: string, required = ["python", "numpy", "scipy", "statsmodels"]) {
  const v = record(value, field);
  for (const key of required) text(v[key], `${field}.${key}`);
  Object.values(v).forEach(v => text(v, field));
}
function sourceLedger(value: unknown): ProvenanceLedger {
  const ledger = record(value, "provenance");
  for (const [pointer, raw] of Object.entries(ledger)) {
    requireValue(pointer.startsWith("/"), "Provenance keys must be JSON field pointers.");
    const source = record(raw, `provenance.${pointer}`);
    requireValue(["manual_user", "synthetic_preset", "protocol_curated", "clinicaltrials_registry"].includes(String(source.source)), `Invalid provenance source for ${pointer}.`);
    for (const key of ["description", "retrieved_at", "source_url"]) requireValue(source[key] === undefined || source[key] === null || typeof source[key] === "string", `Invalid source metadata for ${pointer}.`);
  }
  return ledger as ProvenanceLedger;
}
function inputPointers(payload: ScenarioExportPayload): string[] {
  const paths: string[] = [];
  function walk(v: unknown, pointer: string) {
    if (v && typeof v === "object") Object.entries(v).forEach(([k, item]) => walk(item, `${pointer}/${k}`));
    else paths.push(pointer);
  }
  walk(payload.planned_design, "/planned_design"); walk(payload.fixed_enrollment, "/fixed_enrollment"); walk(payload.stress_scenario, "/stress_scenario");
  paths.push("/simulation/seed", "/simulation/replicates");
  return paths;
}
function point(value: unknown, field: string, dropout = true) {
  const p = record(value, field); finite(p.p_control, field);
  if (dropout) finite(p.dropout, field);
  requireValue(typeof p.is_valid === "boolean" && p.is_valid === (p.power !== null), `${field} has inconsistent validity.`);
  if (p.power !== null) finite(p.power, field);
  return p;
}

/** Reload validation is intentionally stricter than the backend's optional
 * v1 fields: a current export requires complete results and replay metadata.
 * Preserve the original JSON, including diagnostics and endpoint extensions.
 */
export function validateScenarioExport(value: unknown): ScenarioExportPayload {
  jsonValues(value);
  const v = record(value, "export");
  const keys = ["export_schema_version", "model_version", "planned_design", "fixed_enrollment", "stress_scenario", "design_result", "evaluation_result", "grid_result", "software_versions", "provenance", "exported_at"];
  requireValue(Object.keys(v).length === keys.length && keys.every(k => Object.hasOwn(v, k)), "Export must use the complete v1 field set.");
  requireValue(v.export_schema_version === 1 && v.model_version === "binary-v1", "Unsupported export schema or model version.");
  timestamp(v.exported_at, "exported_at"); versions(v.software_versions, "software_versions");
  const payload = v as unknown as ScenarioExportPayload;
  const evaluation = record(v.evaluation_result, "evaluation_result");
  const mc = record(evaluation.monte_carlo, "monte_carlo");
  const ledger = sourceLedger(v.provenance);
  inputPointers(payload).forEach(p => requireValue(ledger[p], `Missing field provenance: ${p}.`));
  const request = { planned_design: payload.planned_design, fixed_enrollment: payload.fixed_enrollment, stress_scenario: payload.stress_scenario,
    simulation: { seed: mc.seed as number, replicates: mc.replicates as number }, provenance: ledger };
  try { validateSimulationRequest(request); parseSimulationResult(evaluation, request); }
  catch (error) { throw new ScenarioExportError(error instanceof Error ? error.message : "Invalid evaluation result."); }
  requireValue(same(evaluation.provenance, ledger), "Evaluation provenance does not match exported inputs.");
  const metadata = record(evaluation.metadata, "evaluation metadata"); timestamp(metadata.computed_at, "evaluation computed_at");
  versions(metadata.software_versions, "evaluation software_versions"); versions(mc.software_versions, "Monte Carlo software_versions", ["python", "numpy", "scipy"]);
  const mcVersions = record(mc.software_versions, "Monte Carlo software_versions");
  requireValue(same(metadata.software_versions, v.software_versions) && Object.entries(mcVersions).every(([k, version]) => payload.software_versions[k] === version), "Recorded software versions disagree.");
  const design = record(v.design_result, "design_result");
  requireValue(design.model_version === "binary-v1" && design.method === "cohen_h_normal_v1", "Unsupported design method.");
  counts(design.evaluable_n, "evaluable_n"); counts(design.enrolled_n, "enrolled_n");
  requireValue(same(design.enrolled_n, v.fixed_enrollment), "Design enrollment does not match locked enrollment.");
  finite(design.p_treatment, "p_treatment"); finite(design.nominal_power_evaluable, "nominal power");
  const expectedTreatment = payload.planned_design.effect.kind === "relative_risk"
    ? payload.planned_design.control_event_rate * payload.planned_design.effect.value
    : payload.planned_design.control_event_rate - payload.planned_design.effect.value;
  requireValue(Math.abs(design.p_treatment - expectedTreatment) < 1e-12, "Design treatment risk disagrees with planned assumptions.");
  text(design.inputs_hash, "design inputs_hash"); warnings(design.warnings, "design warnings");
  const grid = record(v.grid_result, "grid_result");
  requireValue(grid.model_version === "binary-v1" && grid.method === "cohen_h_normal_v1" && grid.grid_label === "expected_count_approximation", "Unsupported grid method.");
  text(grid.inputs_hash, "grid inputs_hash"); timestamp(grid.computed_at, "grid computed_at"); warnings(grid.warnings, "grid warnings");
  versions(grid.software_versions, "grid software_versions");
  requireValue(same(grid.software_versions, v.software_versions) && same(grid.fixed_enrollment, v.fixed_enrollment) && same(grid.provenance, ledger), "Grid environment, enrollment or provenance disagrees with inputs.");
  requireValue(grid.target_power === payload.planned_design.target_power, "Grid target power disagrees with inputs.");
  const x = grid.x_baseline, y = grid.y_dropout;
  for (const [axis, name] of [[x, "baseline"], [y, "dropout"]] as const) {
    requireValue(Array.isArray(axis) && axis.length >= 2, `Missing ${name} domain.`);
    axis.forEach((n, i) => { finite(n, name); requireValue(i === 0 || n > axis[i - 1], `${name} domain must increase.`); });
  }
  requireValue(Array.isArray(x) && Array.isArray(y), "Missing grid domain.");
  const powers = grid.power, mask = grid.invalid_mask, below = grid.below_target;
  requireValue(Array.isArray(powers) && Array.isArray(mask) && Array.isArray(below) && [powers, mask, below].every(rows => rows.length === y.length), "Grid row dimensions disagree.");
  const valid: number[] = []; let invalid = 0;
  powers.forEach((row, r) => {
    requireValue(Array.isArray(row) && Array.isArray(mask[r]) && Array.isArray(below[r]) && [row, mask[r], below[r]].every(cols => cols.length === x.length), "Grid column dimensions disagree.");
    row.forEach((n, c) => {
      requireValue(typeof mask[r][c] === "boolean" && mask[r][c] === (n === null), "Grid null/mask mismatch.");
      if (n === null) { invalid++; requireValue(below[r][c] === null, "Invalid target mask must be null."); }
      else { finite(n, "grid power"); valid.push(n); requireValue(below[r][c] === (n < payload.planned_design.target_power), "Grid target mask disagrees with power."); }
    });
  });
  requireValue(grid.invalid_cell_count === invalid && grid.worst_case_power === (valid.length ? Math.min(...valid) : null), "Grid summary disagrees with matrix.");
  const selected = point(grid.selected_point, "selected point"), planned = point(grid.planned_point, "planned point");
  requireValue(selected.p_control === payload.stress_scenario.control_event_rate && selected.dropout === payload.stress_scenario.dropout.control && planned.p_control === payload.planned_design.control_event_rate && planned.dropout === payload.planned_design.dropout.control, "Grid points disagree with assumptions.");
  const analytic = record(evaluation.analytic, "analytic");
  const retained = Math.floor(payload.fixed_enrollment.control * (1 - payload.stress_scenario.dropout.control));
  requireValue(same(analytic.assumed_evaluable_n, { control: retained, treatment: retained }) && (retained === 0) === (analytic.conditional_power_approx === null), "Analytic counts disagree with expected retained enrollment.");
  requireValue(selected.power === analytic.conditional_power_approx, "Selected grid and evaluation powers disagree.");
  const curve = grid.power_curve;
  requireValue(Array.isArray(curve) && curve.length === x.length, "Complete selected-dropout curve is required.");
  curve.forEach((raw, i) => {
    const p = point(raw, "curve point", false);
    requireValue(p.p_control === x[i], "Curve baseline domain disagrees with grid.");
    const r = y.indexOf(selected.dropout);
    if (r >= 0) requireValue(p.power === powers[r][i], "Curve disagrees with the selected-dropout grid row.");
    if (p.p_control === selected.p_control) requireValue(p.power === selected.power, "Curve disagrees with selected-point power.");
  });
  requireValue(Array.isArray(grid.frontier_points) && Array.isArray(grid.contour_segments), "Raw frontier and segmented contour data are required.");
  grid.frontier_points.forEach(p => point(p, "frontier point"));
  grid.contour_segments.forEach(raw => { const edge = record(raw, "contour segment"); for (const key of ["start", "end"]) { const p = record(edge[key], "contour endpoint"); finite(p.p_control, "contour baseline"); finite(p.dropout, "contour dropout"); } });
  return structuredClone(payload);
}

function planningIdentity(state: WorkspaceState) { return [state.plannedDraft, state.calculatedDesign?.inputs_hash, state.frozenEnrollment]; }
export function exportWorkspaceIdentity(state: WorkspaceState): string {
  return JSON.stringify([state.requestRevision, ...planningIdentity(state), state.stressBaseline, state.stressDropout, state.provenanceLedger]);
}

export function buildScenarioExport(state: WorkspaceState, runs: ExportRuns, exportedAt = new Date().toISOString()): ScenarioExportPayload {
  requireValue(state.designStatus === "success" && state.evaluateStatus === "success" && state.gridStatus === "success", "Calculate, evaluate and load complete current charts before exporting.");
  requireValue(runs.design && runs.evaluation && runs.grid && state.frozenEnrollment, "Complete captured results are required for export.");
  requireValue(same(runs.design.requestState.plannedDraft, state.plannedDraft) && runs.design.response.inputs_hash === state.calculatedDesign?.inputs_hash, "The calculated design is stale.");
  for (const run of [runs.evaluation, runs.grid]) requireValue(exportWorkspaceIdentity(run.requestState) === exportWorkspaceIdentity(state), "Results do not match the displayed inputs and provenance.");
  requireValue(state.evaluateResult?.metadata.inputs_hash === runs.evaluation.response.metadata.inputs_hash && state.gridResult?.inputs_hash === runs.grid.response.inputs_hash, "Workspace result hashes do not match captured results.");
  return validateScenarioExport({ export_schema_version: 1, model_version: "binary-v1", planned_design: state.plannedDraft,
    fixed_enrollment: state.frozenEnrollment, stress_scenario: { control_event_rate: state.stressBaseline, dropout: { control: state.stressDropout, treatment: state.stressDropout }, effect_override: null },
    design_result: runs.design.response, evaluation_result: runs.evaluation.response, grid_result: runs.grid.response,
    software_versions: runs.evaluation.response.metadata.software_versions, provenance: state.provenanceLedger, exported_at: exportedAt });
}
export function serializeScenarioExport(payload: ScenarioExportPayload): string { return JSON.stringify(validateScenarioExport(payload), null, 2) + "\n"; }
export function parseScenarioExport(json: string): ScenarioExportPayload {
  try { return validateScenarioExport(JSON.parse(json)); }
  catch (error) { throw new ScenarioExportError(error instanceof Error ? error.message : "Invalid scenario JSON."); }
}
