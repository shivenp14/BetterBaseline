import assert from "node:assert/strict";
import { writeFileSync } from "node:fs";
import { calculateDesign, evaluateScenario, getStressGrid } from "../lib/api";
import { initializeWorkspaceState, workspaceReducer } from "../lib/workspace-state";
import { buildWorkspaceExport, downloadWorkspaceExport } from "../lib/workspace-export";

async function run() {
  process.env.NEXT_PUBLIC_API_MODE = "live";
  let state = initializeWorkspaceState("baseline-collapse-v1");
  assert.equal(state.frozenEnrollment, null, "live mode cannot evaluate preset enrollment before calculation");
  const planned = { ...state.plannedDraft, dropout: { control: 0.1, treatment: 0.1 } };
  state = workspaceReducer(state, {
    type: "UPDATE_PLANNED_FIELD", fieldPointer: "/planned_design/dropout/control", update: { dropout: planned.dropout },
  });
  const revision = state.requestRevision;
  state = workspaceReducer(state, { type: "START_CALCULATE", requestRevision: revision });
  const calculation = await calculateDesign({ ...planned, preset_id: state.presetId, provenance_ledger: state.provenanceLedger });
  assert.equal(calculation.enrolled_n.control, 1004);
  assert.equal(calculation.enrolled_n.treatment, 1004);
  assert.equal(calculation.mock, false);
  state = workspaceReducer(state, { type: "CALCULATE_SUCCESS", response: calculation, requestRevision: revision });
  const frozen = structuredClone(state.frozenEnrollment);
  assert.deepEqual(frozen, { control: 1004, treatment: 1004 }, "real calculation freezes enrollment from the backend response");

  state = workspaceReducer(state, { type: "UPDATE_STRESS_BASELINE", baseline: 0.2 });
  state = workspaceReducer(state, { type: "UPDATE_STRESS_DROPOUT", dropout: 0.25 });
  assert.deepEqual(state.frozenEnrollment, frozen, "stress edits preserve the frozen planned enrollment");
  const evaluationRevision = state.requestRevision + 1;
  state = workspaceReducer(state, { type: "START_EVALUATE", requestRevision: evaluationRevision });
  const result = await evaluateScenario({
    planned_design: planned,
    fixed_enrollment: state.frozenEnrollment!,
    stress_scenario: {
      control_event_rate: state.stressBaseline,
      dropout: { control: state.stressDropout, treatment: state.stressDropout },
      effect_override: null,
    },
    simulation: { replicates: 10000, seed: 42 },
    preset_id: state.presetId,
    provenance_ledger: state.provenanceLedger,
  });
  assert.equal(result.mock, false);
  assert.equal(result.monte_carlo?.method, "pooled_two_proportion_z_v1");
  assert.equal(result.monte_carlo?.replicates, 10000);
  assert.equal(result.monte_carlo?.seed, 42);
  assert.ok((result.monte_carlo?.significant_two_sided_fraction ?? -1) >= 0);
  assert.equal(result.analytic.assumed_evaluable_n.control, 753);
  assert.deepEqual(result.provenance.field_provenance, state.provenanceLedger);
  state = workspaceReducer(state, {
    type: "EVALUATE_SUCCESS", response: result, requestRevision: evaluationRevision,
  });
  assert.deepEqual(state.frozenEnrollment, frozen, "evaluation does not resize enrollment");

  const gridRevision = state.requestRevision + 1;
  state = workspaceReducer(state, { type: "START_GRID", requestRevision: gridRevision });
  const grid = await getStressGrid({
    planned_design: planned,
    fixed_enrollment: frozen!,
    x_baseline: [0.1, 0.2, 0.3],
    y_dropout: [0, 0.1, 0.2],
    selected_scenario: {
      control_event_rate: state.stressBaseline,
      dropout: { control: state.stressDropout, treatment: state.stressDropout },
      effect_override: null,
    },
    preset_id: state.presetId,
    provenance_ledger: state.provenanceLedger,
  });
  assert.equal(grid.mock, false);
  assert.equal(grid.grid_label, "expected_count_approximation");
  assert.ok(grid.fixed_enrollment, "canonical grid response includes frozen enrollment");
  assert.ok(grid.below_target, "canonical grid response includes target classification matrix");
  assert.ok(grid.software_versions, "canonical grid response includes calculation versions");
  assert.ok(grid.contour_segments);
  assert.ok(grid.power_curve);
  assert.equal(typeof grid.invalid_cell_count, "number");
  assert.deepEqual(grid.fixed_enrollment, frozen);
  assert.deepEqual(grid.x_baseline, [0.1, 0.2, 0.3]);
  assert.deepEqual(grid.y_dropout, [0, 0.1, 0.2]);
  assert.equal(grid.power.length, grid.y_dropout.length);
  assert.ok(grid.power.every((row) => row.length === grid.x_baseline.length));
  assert.equal(grid.invalid_mask.length, grid.y_dropout.length);
  assert.ok(grid.invalid_mask.every((row) => row.length === grid.x_baseline.length));
  assert.equal(grid.invalid_cell_count, grid.invalid_mask.flat().filter(Boolean).length);
  assert.equal(typeof grid.inputs_hash, "string");
  assert.ok(grid.inputs_hash.startsWith("sha256:"));
  assert.deepEqual(grid.provenance.field_provenance, state.provenanceLedger);
  assert.ok(Object.keys(grid.software_versions).includes("python"));
  state = workspaceReducer(state, { type: "GRID_SUCCESS", response: grid, requestRevision: gridRevision });

  const exportPayload = buildWorkspaceExport(state, "2026-10-11T16:00:00.000Z");
  assert.ok(exportPayload.design_result);
  assert.ok(exportPayload.evaluation_result);
  assert.ok(exportPayload.grid_result);
  assert.deepEqual(exportPayload.grid_result?.provenance, state.provenanceLedger);
  assert.deepEqual(exportPayload.software_versions, grid.software_versions);
  let downloadedBlob: Blob | undefined;
  let downloadClicked = false;
  const anchor = { href: "", download: "", click: () => { downloadClicked = true; } };
  const priorDocument = Object.getOwnPropertyDescriptor(globalThis, "document");
  const priorCreateObjectURL = URL.createObjectURL;
  const priorRevokeObjectURL = URL.revokeObjectURL;
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: { createElement: () => anchor },
  });
  URL.createObjectURL = (blob: Blob) => {
    downloadedBlob = blob;
    return "blob:backend-integration-export";
  };
  URL.revokeObjectURL = () => undefined;
  try {
    downloadWorkspaceExport(exportPayload);
  } finally {
    URL.createObjectURL = priorCreateObjectURL;
    URL.revokeObjectURL = priorRevokeObjectURL;
    if (priorDocument) Object.defineProperty(globalThis, "document", priorDocument);
    else delete (globalThis as { document?: unknown }).document;
  }
  assert.equal(downloadClicked, true);
  assert.ok(anchor.download.endsWith(".json"));
  const downloadedJson = await downloadedBlob!.text();
  const downloadedPayload = JSON.parse(downloadedJson) as typeof exportPayload;
  assert.ok(downloadedPayload.grid_result);
  assert.equal("baseline" in (downloadedPayload.grid_result!.planned_point as object), false,
    "download maps view-only baseline aliases back to canonical p_control");
  assert.deepEqual(downloadedPayload.grid_result!.provenance, state.provenanceLedger);
  if (process.env.WORKSPACE_EXPORT_PATH) writeFileSync(process.env.WORKSPACE_EXPORT_PATH, downloadedJson);

  console.log(JSON.stringify({
    calculated_enrollment: calculation.enrolled_n,
    stress_expected_evaluable: result.analytic.assumed_evaluable_n,
    monte_carlo: {
      method: result.monte_carlo?.method,
      replicates: result.monte_carlo?.replicates,
      seed: result.monte_carlo?.seed,
      significant_two_sided_fraction: result.monte_carlo?.significant_two_sided_fraction,
      significant_favorable_fraction: result.monte_carlo?.significant_favorable_fraction,
    },
    frozen_after_stress: state.frozenEnrollment,
    evaluation_provenance_fields: Object.keys(result.provenance.field_provenance ?? {}).length,
    grid: {
      status: "HTTP 200 canonical scenario grid",
      dimensions: [grid.y_dropout.length, grid.x_baseline.length],
      invalid_cell_count: grid.invalid_cell_count,
      provenance_fields: Object.keys(grid.provenance.field_provenance ?? {}).length,
    },
    downloaded_export: "actual anchor Blob JSON captured for canonical backend model validation",
  }, null, 2));
}

run().catch((error) => { console.error(error); process.exitCode = 1; });
