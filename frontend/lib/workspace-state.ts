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
import type { ExtendedEvaluateRequest } from "./api";

export type WorkspaceAction =
  | { type: "LOAD_PRESET"; presetId: string }
  | { type: "UPDATE_PLANNED_FIELD"; fieldPointer: string; fieldPointers?: string[]; update: Partial<TrialAssumptions> }
  | { type: "START_CALCULATE"; requestRevision: number; expectedInputGeneration: number }
  | { type: "CALCULATE_SUCCESS"; response: CalculateResponse; requestRevision: number }
  | { type: "CALCULATE_ERROR"; error: string; requestRevision: number }
  | { type: "UPDATE_STRESS_BASELINE"; baseline: number }
  | { type: "UPDATE_STRESS_DROPOUT"; dropout: number }
  | { type: "SELECT_STRESS_POINT"; baseline: number; dropout: number }
  | { type: "UPDATE_SIMULATION_PROVENANCE"; pointers: string[] }
  | { type: "START_EVALUATE"; requestRevision?: number; expectedInputGeneration: number }
  | { type: "EVALUATE_SUCCESS"; response: EvaluateResponse; requestRevision: number }
  | { type: "EVALUATE_ERROR"; error: string; requestRevision: number }
  | { type: "START_GRID"; requestRevision?: number; expectedInputGeneration: number }
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
    activeEvaluateRevision: null,
    gridResult: initialGrid,
    gridStatus: "idle",
    gridError: null,
    activeGridRevision: null,
    inputGeneration: 0,
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

/** Build the real stress request from the current draft and immutable enrollment lock. */
export function buildStressEvaluationRequest(state: WorkspaceState): ExtendedEvaluateRequest {
  if (!state.frozenEnrollment) throw new Error("Calculate a design before evaluating stress.");
  return {
    planned_design: state.plannedDraft,
    fixed_enrollment: state.frozenEnrollment,
    stress_scenario: {
      control_event_rate: state.stressBaseline,
      dropout: { control: state.stressDropout, treatment: state.stressDropout },
      effect_override: null,
    },
    simulation: { replicates: 10000, seed: 42 },
    preset_id: state.presetId,
    provenance_ledger: state.provenanceLedger,
  };
}

export function workspaceReducer(
  state: WorkspaceState,
  action: WorkspaceAction
): WorkspaceState {
  switch (action.type) {
    case "LOAD_PRESET": {
      return {
        ...initializeWorkspaceState(action.presetId),
        // Preset changes invalidate every in-flight request. Keep the revision
        // monotonic so an already-resolving old request can never own the new
        // preset, even when no request is started after the switch.
        requestRevision: state.requestRevision + 1,
        inputGeneration: state.inputGeneration + 1,
      };
    }

    case "RESET_TO_PRESET": {
      return {
        ...initializeWorkspaceState(state.presetId),
        requestRevision: state.requestRevision + 1,
        inputGeneration: state.inputGeneration + 1,
      };
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
        activeEvaluateRevision: null,
        activeGridRevision: null,
        evaluateStatus: "stale",
        gridStatus: "stale",
        displayedInputsHash: null,
        requestRevision: state.requestRevision + 1,
        inputGeneration: state.inputGeneration + 1,
      };
    }

    case "START_CALCULATE": {
      if (action.expectedInputGeneration !== state.inputGeneration) return state;
      return {
        ...state,
        // Calculation replaces the enrollment lock, so evaluation and grid
        // requests owned by the previous lock can no longer publish results.
        requestRevision: action.requestRevision,
        inputGeneration: state.inputGeneration + 1,
        designStatus: "calculating",
        designError: null,
        activeCalculateRevision: action.requestRevision,
        activeEvaluateRevision: null,
        evaluateStatus: state.evaluateStatus === "evaluating" ? "stale" : state.evaluateStatus,
        evaluateError: null,
        activeGridRevision: null,
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
        activeEvaluateRevision: null,
        activeGridRevision: null,
        displayedInputsHash: action.response.inputs_hash,
        evaluateStatus: "stale",
        gridStatus: "stale",
        provenanceLedger: {
          ...state.provenanceLedger,
          ...Object.fromEntries(["control", "treatment"].map(arm => [`/fixed_enrollment/${arm}`, {
            source: Object.entries(state.provenanceLedger).some(([key, value]) => key.startsWith("/planned_design/") && value.source === "manual_user") ? "manual_user" as const : "synthetic_preset" as const,
            description: `Enrollment derived from calculated design ${action.response.inputs_hash}`,
            retrieved_at: new Date().toISOString(), source_url: null,
          }])),
        },
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

    case "SELECT_STRESS_POINT": {
      const baseline = workspaceReducer(state, { type: "UPDATE_STRESS_BASELINE", baseline: action.baseline });
      const both = workspaceReducer(baseline, { type: "UPDATE_STRESS_DROPOUT", dropout: action.dropout });
      return { ...both, requestRevision: state.requestRevision + 1, inputGeneration: state.inputGeneration + 1 };
    }
    case "UPDATE_SIMULATION_PROVENANCE": {
      return { ...state, provenanceLedger: action.pointers.reduce((ledger, pointer) => markFieldManual(ledger, pointer, "Selected simulation configuration edited"), state.provenanceLedger),
        activeCalculateRevision: null, designStatus: state.designStatus === "calculating" ? "idle" : state.designStatus,
        activeEvaluateRevision: null, activeGridRevision: null, evaluateStatus: "stale", gridStatus: "stale", displayedInputsHash: null,
        requestRevision: state.requestRevision + 1, inputGeneration: state.inputGeneration + 1 };
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
        activeEvaluateRevision: null,
        activeGridRevision: null,
        evaluateStatus: "stale",
        gridStatus: "stale",
        displayedInputsHash: null,
        requestRevision: state.requestRevision + 1,
        inputGeneration: state.inputGeneration + 1,
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
        activeEvaluateRevision: null,
        activeGridRevision: null,
        evaluateStatus: "stale",
        gridStatus: "stale",
        displayedInputsHash: null,
        requestRevision: state.requestRevision + 1,
        inputGeneration: state.inputGeneration + 1,
      };
    }

    case "START_EVALUATE": {
      if (action.expectedInputGeneration !== state.inputGeneration) return state;
      if (state.designStatus === "calculating") return state;
      const requestRevision = action.requestRevision ?? state.requestRevision + 1;
      return {
        ...state,
        // Keep the operation token separate from other request kinds: evaluation
        // and grid are valid concurrently for the same frozen inputs.
        requestRevision,
        activeEvaluateRevision: requestRevision,
        evaluateStatus: "evaluating",
        evaluateError: null,
      };
    }

    case "EVALUATE_SUCCESS": {
      if (
        action.requestRevision !== state.activeEvaluateRevision ||
        state.evaluateStatus !== "evaluating"
      ) {
        return state;
      }
      return {
        ...state,
        activeEvaluateRevision: null,
        evaluateResult: action.response,
        evaluateStatus: "success",
        evaluateError: null,
        displayedInputsHash: action.response.metadata.inputs_hash,
      };
    }

    case "EVALUATE_ERROR": {
      if (
        action.requestRevision !== state.activeEvaluateRevision ||
        state.evaluateStatus !== "evaluating"
      ) {
        return state;
      }
      return {
        ...state,
        activeEvaluateRevision: null,
        evaluateStatus: "error",
        evaluateError: action.error,
      };
    }

    case "START_GRID": {
      if (action.expectedInputGeneration !== state.inputGeneration) return state;
      if (state.designStatus === "calculating") return state;
      const requestRevision = action.requestRevision ?? state.requestRevision + 1;
      return {
        ...state,
        requestRevision,
        activeGridRevision: requestRevision,
        gridStatus: "loading",
        gridError: null,
      };
    }

    case "GRID_SUCCESS": {
      if (
        action.requestRevision !== state.activeGridRevision ||
        state.gridStatus !== "loading"
      ) {
        return state;
      }
      return {
        ...state,
        activeGridRevision: null,
        gridResult: action.response,
        gridStatus: "success",
        gridError: null,
        displayedInputsHash: action.response.inputs_hash,
      };
    }

    case "GRID_ERROR": {
      if (
        action.requestRevision !== state.activeGridRevision ||
        state.gridStatus !== "loading"
      ) {
        return state;
      }
      return {
        ...state,
        activeGridRevision: null,
        gridStatus: "error",
        gridError: action.error,
      };
    }

    default:
      return state;
  }
}
