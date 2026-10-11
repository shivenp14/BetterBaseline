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
  | { type: "CALCULATE_SUCCESS"; response: CalculateResponse }
  | { type: "CALCULATE_ERROR"; error: string }
  | { type: "UPDATE_STRESS_BASELINE"; baseline: number }
  | { type: "UPDATE_STRESS_DROPOUT"; dropout: number }
  | { type: "START_EVALUATE" }
  | { type: "EVALUATE_SUCCESS"; response: EvaluateResponse }
  | { type: "EVALUATE_ERROR"; error: string }
  | { type: "START_GRID" }
  | { type: "GRID_SUCCESS"; response: GridResponse }
  | { type: "GRID_ERROR"; error: string }
  | { type: "RESET_TO_PRESET" };

export function initializeWorkspaceState(presetId = "baseline-collapse-v1"): WorkspaceState {
  const preset = getPresetById(presetId);
  return {
    presetId: preset.preset_id,
    plannedDraft: JSON.parse(JSON.stringify(preset.planned_design)),
    plannedProvenance: JSON.parse(JSON.stringify(preset.provenance)),
    calculatedDesign: preset.design_response,
    frozenEnrollment: JSON.parse(JSON.stringify(preset.fixed_enrollment)),
    designStatus: "idle",
    designError: null,
    stressBaseline: preset.stress_scenario.control_event_rate,
    stressDropout: preset.stress_scenario.dropout.control,
    stressProvenance: JSON.parse(JSON.stringify(preset.provenance)),
    evaluateResult: preset.evaluate_response,
    evaluateStatus: "idle",
    evaluateError: null,
    gridResult: preset.grid_response,
    gridStatus: "idle",
    gridError: null,
    displayedInputsHash: preset.inputs_hash,
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
      const nextProvenance = markFieldManual(state.plannedProvenance, action.fieldPointer);
      return {
        ...state,
        plannedDraft: nextPlanned,
        plannedProvenance: nextProvenance,
        designStatus: "idle",
        evaluateStatus: "stale",
        gridStatus: "stale",
        displayedInputsHash: null,
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
      return {
        ...state,
        designStatus: "error",
        designError: action.error,
      };
    }

    case "UPDATE_STRESS_BASELINE": {
      const nextStressProv = markFieldManual(
        state.stressProvenance,
        "/stress_scenario/control_event_rate",
        "Stress baseline risk adjusted"
      );
      return {
        ...state,
        stressBaseline: action.baseline,
        stressProvenance: nextStressProv,
        evaluateStatus: "stale",
        gridStatus: "stale",
        displayedInputsHash: null,
      };
    }

    case "UPDATE_STRESS_DROPOUT": {
      let nextStressProv = markFieldManual(
        state.stressProvenance,
        "/stress_scenario/dropout/control",
        "Stress dropout adjusted"
      );
      nextStressProv = markFieldManual(
        nextStressProv,
        "/stress_scenario/dropout/treatment",
        "Stress dropout adjusted"
      );
      return {
        ...state,
        stressDropout: action.dropout,
        stressProvenance: nextStressProv,
        evaluateStatus: "stale",
        gridStatus: "stale",
        displayedInputsHash: null,
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
      return {
        ...state,
        evaluateResult: action.response,
        evaluateStatus: "success",
        evaluateError: null,
        displayedInputsHash: action.response.metadata.inputs_hash,
      };
    }

    case "EVALUATE_ERROR": {
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
      return {
        ...state,
        gridResult: action.response,
        gridStatus: "success",
        gridError: null,
        displayedInputsHash: action.response.inputs_hash,
      };
    }

    case "GRID_ERROR": {
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
