import type { CalculateResponse, EvaluateResponse, GridResponse, TrialAssumptions } from "./contracts";
import type { ProvenanceLedger, WorkspaceState } from "./workspace-contracts";

/** Canonical backend ExportPayload (app-only execution/mock labels are omitted). */
export interface WorkspaceExportPayload {
  export_schema_version: 1;
  model_version: "binary-v1";
  planned_design: TrialAssumptions;
  fixed_enrollment: { control: number; treatment: number };
  stress_scenario: {
    control_event_rate: number;
    dropout: { control: number; treatment: number };
    effect_override: null;
  };
  design_result?: Omit<CalculateResponse, "provenance" | "mock" | "execution">;
  evaluation_result?: Omit<EvaluateResponse, "provenance" | "mock" | "execution"> & {
    monte_carlo: NonNullable<EvaluateResponse["monte_carlo"]>;
  };
  grid_result?: Record<string, unknown>;
  software_versions: Record<string, string>;
  provenance: ProvenanceLedger;
  exported_at: string;
}

function designForExport(result: CalculateResponse): WorkspaceExportPayload["design_result"] {
  const canonical = { ...result } as unknown as Record<string, unknown>;
  delete canonical.provenance;
  delete canonical.mock;
  delete canonical.execution;
  return canonical as WorkspaceExportPayload["design_result"];
}

function evaluationForExport(
  result: EvaluateResponse
): WorkspaceExportPayload["evaluation_result"] {
  if (!result.monte_carlo) return undefined;
  const canonical = { ...result } as unknown as Record<string, unknown>;
  delete canonical.provenance;
  delete canonical.mock;
  delete canonical.execution;
  return { ...canonical, monte_carlo: result.monte_carlo } as WorkspaceExportPayload["evaluation_result"];
}

function isCanonicalGridResult(result: GridResponse): boolean {
  const raw = result as unknown as Record<string, unknown>;
  return ["fixed_enrollment", "below_target", "software_versions", "analytic_delta", "contour_segments", "power_curve", "invalid_cell_count", "worst_case_power"].every(
    (key) => key in raw
  );
}

function gridForExport(result: GridResponse, provenance: ProvenanceLedger): Record<string, unknown> {
  const canonical = { ...result } as unknown as Record<string, unknown>;
  delete canonical.execution;
  delete canonical.mock;
  const canonicalPoint = (point: unknown) => {
    if (!point || typeof point !== "object") return point;
    const value = { ...(point as Record<string, unknown>) };
    delete value.baseline;
    return value;
  };
  canonical.planned_point = canonicalPoint(result.planned_point);
  canonical.selected_point = canonicalPoint(result.selected_point);
  canonical.frontier_points = result.frontier_points.map(canonicalPoint);
  canonical.provenance = provenance;
  return canonical;
}

export function buildWorkspaceExport(
  state: WorkspaceState,
  exportedAt = new Date().toISOString()
): WorkspaceExportPayload {
  if (!state.frozenEnrollment) throw new Error("Calculate a design before exporting results.");
  const payload: WorkspaceExportPayload = {
    export_schema_version: 1,
    model_version: "binary-v1",
    planned_design: state.plannedDraft,
    fixed_enrollment: state.frozenEnrollment,
    stress_scenario: {
      control_event_rate: state.stressBaseline,
      dropout: { control: state.stressDropout, treatment: state.stressDropout },
      effect_override: null,
    },
    software_versions: {},
    provenance: state.provenanceLedger,
    exported_at: exportedAt,
  };

  if (state.designStatus === "success" && state.calculatedDesign && !state.calculatedDesign.mock) {
    payload.design_result = designForExport(state.calculatedDesign)!;
  }
  if (state.evaluateStatus === "success" && state.evaluateResult && !state.evaluateResult.mock) {
    payload.evaluation_result = evaluationForExport(state.evaluateResult);
  }
  if (state.gridStatus === "success" && state.gridResult && !state.gridResult.mock && isCanonicalGridResult(state.gridResult)) {
    // The API grid response's provenance field is a field map in ExportPayload.
    // Carry the current workspace ledger so edits are reflected in the export.
    payload.grid_result = gridForExport(state.gridResult, state.provenanceLedger);
    const versions = (state.gridResult as unknown as { software_versions?: Record<string, string> }).software_versions;
    if (versions) payload.software_versions = versions;
  }
  return payload;
}

export function hasCurrentExportableResults(state: WorkspaceState): boolean {
  return Boolean(
    (state.designStatus === "success" && state.calculatedDesign && !state.calculatedDesign.mock) ||
    (state.evaluateStatus === "success" && state.evaluateResult && !state.evaluateResult.mock && state.evaluateResult.monte_carlo) ||
    (state.gridStatus === "success" && state.gridResult && !state.gridResult.mock && isCanonicalGridResult(state.gridResult))
  );
}

export function serializeWorkspaceExport(payload: WorkspaceExportPayload): string {
  return `${JSON.stringify(payload, null, 2)}\n`;
}

export function downloadWorkspaceExport(payload: WorkspaceExportPayload): void {
  const blob = new Blob([serializeWorkspaceExport(payload)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `better-baseline-export-${payload.exported_at.replace(/[:.]/g, "-")}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}
