import type {
  WorkspaceState,
  ProvenanceLedger,
} from "./workspace-contracts";
import type {
  CalculateResponse,
  EvaluateResponse,
  GridResponse,
  TrialAssumptions,
} from "./contracts";
import { getPresetById } from "./presets";
import { getApiMode } from "./api";

export type WorkspaceAction =
  | { type: "LOAD_PRESET"; presetId: string }
  | { type: "UPDATE_PLANNED_FIELD"; fieldPointer: string; fieldPointers?: string[]; update: Partial<TrialAssumptions> }
  | { type: "START_CALCULATE"; requestRevision: number }
  | { type: "CALCULATE_SUCCESS"; response: CalculateResponse; requestRevision: number }
  | { type: "CALCULATE_ERROR"; error: string; requestRevision: number }
  | { type: "UPDATE_STRESS_BASELINE"; baseline: number }
  | { type: "UPDATE_STRESS_DROPOUT"; dropout: number }
  | { type: "START_EVALUATE" }
  | { type: "EVALUATE_SUCCESS"; response: EvaluateResponse; requestRevision: number }
  | { type: "EVALUATE_ERROR"; error: string; requestRevision: number }
  | { type: "START_GRID" }
  | { type: "GRID_SUCCESS"; response: GridResponse; requestRevision: number }
  | { type: "GRID_ERROR"; error: string; requestRevision: number }
  | { type: "RESET_TO_PRESET" };

export function initializeWorkspaceState(presetId = "baseline-collapse-v1"): WorkspaceState {
  const preset = getPresetById(presetId);
  const apiMode = getApiMode();
  const initialExecution = apiMode === "demo"
    ? { mode: "demo" as const, label: "Demo fixture — not backend execution" }
    : { mode: "demo" as const, label: "Demo fixture — stale until a backend request succeeds" };
  const initialDesign = JSON.parse(JSON.stringify(preset.design_response));
  const initialEvaluate = JSON.parse(JSON.stringify(preset.evaluate_response));
  const initialGrid = JSON.parse(JSON.stringify(preset.grid_response));
  for (const result of [initialDesign, initialEvaluate, initialGrid]) {
    result.execution = initialExecution;
  }
  initialDesign.provenance.field_provenance = JSON.parse(JSON.stringify(preset.provenance));
  initialEvaluate.provenance.field_provenance = JSON.parse(JSON.stringify(preset.provenance));
  initialGrid.provenance.field_provenance = JSON.parse(JSON.stringify(preset.provenance));
  return {
    presetId: preset.preset_id,
    plannedDraft: JSON.parse(JSON.stringify(preset.planned_design)),
    calculatedDesign: initialDesign,
    frozenEnrollment: apiMode === "demo"
      ? JSON.parse(JSON.stringify(preset.fixed_enrollment))
      : null,
    designStatus: "idle",
    designError: null,
    activeCalculateRevision: null,
    stressBaseline: preset.stress_scenario.control_event_rate,
    stressDropout: preset.stress_scenario.dropout.control,
    provenanceLedger: JSON.parse(JSON.stringify(preset.provenance)),
    evaluateResult: initialEvaluate,
    evaluateStatus: "idle",
    evaluateError: null,
    gridResult: initialGrid,
    gridStatus: "idle",
    gridError: null,
    displayedInputsHash: preset.inputs_hash,
    requestRevision: 0,
  };
}

export function markFieldManual(
  ledger: ProvenanceLedger,
  pointer: string,
  description = "User edited value manually in workspace"
): ProvenanceLedger {
  return {
    ...ledger,
    [pointer]: {
      source: "manual_user",
      description,
      retrieved_at: new Date().toISOString(),
      source_url: null,
    },
  };
}

export function workspaceReducer(
  state: WorkspaceState,
  action: WorkspaceAction
): WorkspaceState {
  switch (action.type) {
    case "LOAD_PRESET": {
      return initializeWorkspaceState(action.presetId);
    }

    case "RESET_TO_PRESET": {
      return initializeWorkspaceState(state.presetId);
    }

    case "UPDATE_PLANNED_FIELD": {
      const nextPlanned = {
        ...state.plannedDraft,
        ...action.update,
      };
      const nextProvenance = (action.fieldPointers ?? [action.fieldPointer]).reduce(
        (ledger, pointer) => markFieldManual(ledger, pointer),
        state.provenanceLedger
      );
      return {
        ...state,
        plannedDraft: nextPlanned,
        provenanceLedger: nextProvenance,
        designStatus: "idle",
        activeCalculateRevision: null,
        evaluateStatus: "stale",
        gridStatus: "stale",
        displayedInputsHash: null,
        requestRevision: state.requestRevision + 1,
      };
    }

    case "START_CALCULATE": {
      return {
        ...state,
        // Calculation invalidates prior evaluation/grid requests even when the
        // assumptions did not change. Bump the shared revision so their late
        // completions cannot overwrite results for the newly locked design.
        requestRevision: action.requestRevision,
        designStatus: "calculating",
        designError: null,
        activeCalculateRevision: action.requestRevision,
        evaluateStatus: state.evaluateStatus === "evaluating" ? "stale" : state.evaluateStatus,
        evaluateError: null,
        gridStatus: state.gridStatus === "loading" ? "stale" : state.gridStatus,
        gridError: null,
      };
    }

    case "CALCULATE_SUCCESS": {
      // Reject stale late responses
      if (
        action.requestRevision !== state.requestRevision ||
        action.requestRevision !== state.activeCalculateRevision
      ) {
        return state;
      }
      return {
        ...state,
        // Results started against the previously locked enrollment must not
        // remain current after this calculation replaces that enrollment.
        requestRevision: action.requestRevision + 1,
        calculatedDesign: action.response,
        frozenEnrollment: action.response.enrolled_n,
        designStatus: "success",
        designError: null,
        activeCalculateRevision: null,
        displayedInputsHash: action.response.inputs_hash,
        evaluateStatus: "stale",
        gridStatus: "stale",
      };
    }

    case "CALCULATE_ERROR": {
      if (
        action.requestRevision !== state.requestRevision ||
        action.requestRevision !== state.activeCalculateRevision
      ) {
        return state;
      }
      return {
        ...state,
        designStatus: "error",
        designError: action.error,
        activeCalculateRevision: null,
      };
    }

    case "UPDATE_STRESS_BASELINE": {
      const nextProv = markFieldManual(
        state.provenanceLedger,
        "/stress_scenario/control_event_rate",
        "Stress baseline risk adjusted"
      );
      return {
        ...state,
        stressBaseline: action.baseline,
        provenanceLedger: nextProv,
        designStatus: state.designStatus === "calculating" ? "idle" : state.designStatus,
        activeCalculateRevision: null,
        evaluateStatus: "stale",
        gridStatus: "stale",
        displayedInputsHash: null,
        requestRevision: state.requestRevision + 1,
      };
    }

    case "UPDATE_STRESS_DROPOUT": {
      let nextProv = markFieldManual(
        state.provenanceLedger,
        "/stress_scenario/dropout/control",
        "Stress dropout adjusted"
      );
      nextProv = markFieldManual(
        nextProv,
        "/stress_scenario/dropout/treatment",
        "Stress dropout adjusted"
      );
      return {
        ...state,
        stressDropout: action.dropout,
        provenanceLedger: nextProv,
        designStatus: state.designStatus === "calculating" ? "idle" : state.designStatus,
        activeCalculateRevision: null,
        evaluateStatus: "stale",
        gridStatus: "stale",
        displayedInputsHash: null,
        requestRevision: state.requestRevision + 1,
      };
    }

    case "START_EVALUATE": {
      if (state.designStatus === "calculating") return state;
      return {
        ...state,
        evaluateStatus: "evaluating",
        evaluateError: null,
      };
    }

    case "EVALUATE_SUCCESS": {
      if (action.requestRevision < state.requestRevision) {
        return state;
      }
      return {
        ...state,
        evaluateResult: action.response,
        evaluateStatus: "success",
        evaluateError: null,
        displayedInputsHash: action.response.metadata.inputs_hash,
      };
    }

    case "EVALUATE_ERROR": {
      if (action.requestRevision < state.requestRevision) {
        return state;
      }
      return {
        ...state,
        evaluateStatus: "error",
        evaluateError: action.error,
      };
    }

    case "START_GRID": {
      if (state.designStatus === "calculating") return state;
      return {
        ...state,
        gridStatus: "loading",
        gridError: null,
      };
    }

    case "GRID_SUCCESS": {
      if (action.requestRevision < state.requestRevision) {
        return state;
      }
      return {
        ...state,
        gridResult: action.response,
        gridStatus: "success",
        gridError: null,
        displayedInputsHash: action.response.inputs_hash,
      };
    }

    case "GRID_ERROR": {
      if (action.requestRevision < state.requestRevision) {
        return state;
      }
      return {
        ...state,
        gridStatus: "error",
        gridError: action.error,
      };
    }

    default:
      return state;
  }
}
