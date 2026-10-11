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

export type WorkspaceAction =
  | { type: "LOAD_PRESET"; presetId: string }
  | { type: "UPDATE_PLANNED_FIELD"; fieldPointer: string; update: Partial<TrialAssumptions> }
  | { type: "START_CALCULATE" }
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
  return {
    presetId: preset.preset_id,
    plannedDraft: JSON.parse(JSON.stringify(preset.planned_design)),
    calculatedDesign: preset.design_response,
    frozenEnrollment: JSON.parse(JSON.stringify(preset.fixed_enrollment)),
    designStatus: "idle",
    designError: null,
    stressBaseline: preset.stress_scenario.control_event_rate,
    stressDropout: preset.stress_scenario.dropout.control,
    provenanceLedger: JSON.parse(JSON.stringify(preset.provenance)),
    evaluateResult: preset.evaluate_response,
    evaluateStatus: "idle",
    evaluateError: null,
    gridResult: preset.grid_response,
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
      const nextProvenance = markFieldManual(state.provenanceLedger, action.fieldPointer);
      return {
        ...state,
        plannedDraft: nextPlanned,
        provenanceLedger: nextProvenance,
        designStatus: "idle",
        evaluateStatus: "stale",
        gridStatus: "stale",
        displayedInputsHash: null,
        requestRevision: state.requestRevision + 1,
      };
    }

    case "START_CALCULATE": {
      return {
        ...state,
        designStatus: "calculating",
        designError: null,
      };
    }

    case "CALCULATE_SUCCESS": {
      // Reject stale late responses
      if (action.requestRevision < state.requestRevision) {
        return state;
      }
      return {
        ...state,
        calculatedDesign: action.response,
        frozenEnrollment: action.response.enrolled_n,
        designStatus: "success",
        designError: null,
        displayedInputsHash: action.response.inputs_hash,
        evaluateStatus: "stale",
        gridStatus: "stale",
      };
    }

    case "CALCULATE_ERROR": {
      if (action.requestRevision < state.requestRevision) {
        return state;
      }
      return {
        ...state,
        designStatus: "error",
        designError: action.error,
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
        evaluateStatus: "stale",
        gridStatus: "stale",
        displayedInputsHash: null,
        requestRevision: state.requestRevision + 1,
      };
    }

    case "START_EVALUATE": {
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
