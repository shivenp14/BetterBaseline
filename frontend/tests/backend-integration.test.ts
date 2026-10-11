import assert from "node:assert/strict";
import { writeFileSync } from "node:fs";
import { calculateDesign, evaluateScenario, getStressGrid } from "../lib/api";
import { initializeWorkspaceState, workspaceReducer } from "../lib/workspace-state";
import { buildWorkspaceExport, downloadWorkspaceExport } from "../lib/workspace-export";

async function run() {
  process.env.NEXT_PUBLIC_API_MODE = "live";
  let state = initializeWorkspaceState("baseline-collapse-v1");
  const manuallyVerifiedBaseline = {
    source: "manual_user" as const,
    description: "Manually transcribed and checked against the protocol",
    source_url: "https://example.org/protocol.pdf",
    source_location: "Page 14, Table 2 — β",
    retrieved_at: "2026-10-11T12:00:00Z",
    verified_by_user: true,
  };
  const bmpUnicodeRecord = {
    source: "manual_user" as const,
    description: "BMP key with Unicode value β and 😀",
    source_location: "Appendix – table α",
    verified_by_user: true,
  };
  const nonBmpUnicodeRecord = {
    source: "synthetic_preset" as const,
    description: "Non-BMP key; retained verbatim",
    source_location: "Fixture manifest",
    verified_by_user: false,
  };
  state.provenanceLedger = {
    ...state.provenanceLedger,
    "/planned_design/control_event_rate": manuallyVerifiedBaseline,
    "\uE000": bmpUnicodeRecord,
    "\u{1F600}": nonBmpUnicodeRecord,
  };
  assert.equal(state.frozenEnrollment, null, "live mode cannot evaluate preset enrollment before calculation");
  const planned = { ...state.plannedDraft, dropout: { control: 0.1, treatment: 0.1 } };
  state = workspaceReducer(state, {
    type: "UPDATE_PLANNED_FIELD", fieldPointer: "/planned_design/dropout/control", update: { dropout: planned.dropout },
  });
  const revision = state.requestRevision;
  state = workspaceReducer(state, {
    type: "START_CALCULATE", requestRevision: revision,
    expectedInputGeneration: state.inputGeneration,
  });
  const calculation = await calculateDesign({ ...planned, preset_id: state.presetId, provenance_ledger: state.provenanceLedger });
  assert.equal(calculation.enrolled_n.control, 1004);
  assert.equal(calculation.enrolled_n.treatment, 1004);
  assert.equal(calculation.mock, false);
  assert.equal(calculation.provenance.field_provenance?.["/planned_design/control_event_rate"].source, "manual_user");
  assert.equal(calculation.provenance.field_provenance?.["/planned_design/control_event_rate"].source_location, "Page 14, Table 2 — β");
  assert.equal(calculation.provenance.field_provenance?.["/planned_design/control_event_rate"].verified_by_user, true);
  state = workspaceReducer(state, { type: "CALCULATE_SUCCESS", response: calculation, requestRevision: revision });
  const frozen = structuredClone(state.frozenEnrollment);
  assert.deepEqual(frozen, { control: 1004, treatment: 1004 }, "real calculation freezes enrollment from the backend response");

  state = workspaceReducer(state, { type: "UPDATE_STRESS_BASELINE", baseline: 0.2 });
  state = workspaceReducer(state, { type: "UPDATE_STRESS_DROPOUT", dropout: 0.25 });
  assert.deepEqual(state.frozenEnrollment, frozen, "stress edits preserve the frozen planned enrollment");
  const evaluationRevision = state.requestRevision + 1;
  state = workspaceReducer(state, {
    type: "START_EVALUATE", requestRevision: evaluationRevision,
    expectedInputGeneration: state.inputGeneration,
  });
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
  assert.equal(Object.keys(result.provenance.field_provenance ?? {}).length, Object.keys(state.provenanceLedger).length);
  assert.equal(result.provenance.field_provenance?.["/planned_design/control_event_rate"].source_location, "Page 14, Table 2 — β");
  assert.equal(result.provenance.field_provenance?.["/planned_design/control_event_rate"].verified_by_user, true);
  state = workspaceReducer(state, {
    type: "EVALUATE_SUCCESS", response: result, requestRevision: evaluationRevision,
  });
  assert.deepEqual(state.frozenEnrollment, frozen, "evaluation does not resize enrollment");

  const gridRevision = state.requestRevision + 1;
  state = workspaceReducer(state, {
    type: "START_GRID", requestRevision: gridRevision,
    expectedInputGeneration: state.inputGeneration,
  });
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
  assert.equal(Object.keys(grid.provenance.field_provenance ?? {}).length, Object.keys(state.provenanceLedger).length);
  assert.equal(grid.provenance.field_provenance?.["/planned_design/control_event_rate"].source_location, "Page 14, Table 2 — β");
  assert.equal(grid.provenance.field_provenance?.["/planned_design/control_event_rate"].verified_by_user, true);
  assert.ok(Object.keys(grid.software_versions).includes("python"));
  state = workspaceReducer(state, { type: "GRID_SUCCESS", response: grid, requestRevision: gridRevision });

  const exportPayload = buildWorkspaceExport(state, "2026-10-11T16:00:00.000Z");
  assert.ok(exportPayload.design_result);
  assert.ok(exportPayload.evaluation_result);
  assert.ok(exportPayload.grid_result);
  assert.ok(exportPayload.inputs_hash.startsWith("sha256:"));
  assert.equal(exportPayload.design_result?.method, "cohen_h_normal_v1");
  assert.equal(exportPayload.evaluation_result?.monte_carlo?.method, "pooled_two_proportion_z_v1");
  assert.equal(exportPayload.design_result?.inputs_hash, calculation.inputs_hash);
  assert.equal(exportPayload.evaluation_result?.metadata.inputs_hash, result.metadata.inputs_hash);
  assert.equal(exportPayload.grid_result?.inputs_hash, grid.inputs_hash);
  assert.deepEqual(exportPayload.design_result?.warnings, calculation.warnings);
  assert.deepEqual(exportPayload.design_result?.diagnostics, calculation.diagnostics);
  assert.deepEqual(exportPayload.evaluation_result?.warnings, result.warnings);
  assert.deepEqual(exportPayload.evaluation_result?.diagnostics, result.diagnostics);
  assert.deepEqual(exportPayload.grid_result?.warnings, grid.warnings);
  assert.deepEqual(exportPayload.grid_result?.diagnostics, grid.diagnostics);
  assert.deepEqual(exportPayload.design_result?.provenance["/planned_design/control_event_rate"],
    calculation.provenance.field_provenance?.["/planned_design/control_event_rate"]);
  assert.deepEqual(exportPayload.evaluation_result?.provenance["/planned_design/control_event_rate"],
    result.provenance.field_provenance?.["/planned_design/control_event_rate"]);
  assert.deepEqual(exportPayload.grid_result?.provenance["/planned_design/control_event_rate"],
    grid.provenance.field_provenance?.["/planned_design/control_event_rate"]);
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
  assert.equal(downloadedPayload.inputs_hash, exportPayload.inputs_hash);
  assert.equal(downloadedPayload.provenance["/planned_design/control_event_rate"].source_location, "Page 14, Table 2 — β");
  assert.equal(downloadedPayload.provenance["/planned_design/control_event_rate"].verified_by_user, true);
  assert.equal(downloadedPayload.provenance["\uE000"].description, "BMP key with Unicode value β and 😀");
  assert.equal(downloadedPayload.provenance["\u{1F600}"].description, "Non-BMP key; retained verbatim");
  assert.equal(downloadedPayload.grid_result!.provenance["/planned_design/control_event_rate"].source_location, "Page 14, Table 2 — β");
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
