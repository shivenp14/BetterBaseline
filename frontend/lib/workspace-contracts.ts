import type {
  TrialAssumptions,
  FixedEnrollment,
  CalculateResponse,
  EvaluateResponse,
  GridResponse,
  Effect,
} from "./contracts";

export interface FieldProvenance {
  source: "manual_user" | "synthetic_preset" | "protocol_curated" | "clinicaltrials_registry";
  description?: string | null;
  retrieved_at?: string | null;
  source_url?: string | null;
}

export type ProvenanceLedger = Record<string, FieldProvenance>;

export interface RawPresetData {
  preset_id: string;
  name: string;
  eyebrow: string;
  description: string;
  inputs_hash: string;
  planned_design: TrialAssumptions;
  fixed_enrollment: FixedEnrollment;
  stress_scenario: {
    control_event_rate: number;
    dropout: { control: number; treatment: number };
    effect_override: Effect | null;
  };
  simulation: {
    replicates: number;
    seed: number;
  };
  provenance: ProvenanceLedger;
  design_response: CalculateResponse;
  evaluate_response: EvaluateResponse;
  grid_response: GridResponse;
}

export interface WorkspaceState {
  presetId: string;
  plannedDraft: TrialAssumptions;
  calculatedDesign: CalculateResponse | null;
  frozenEnrollment: FixedEnrollment | null;
  designStatus: "idle" | "calculating" | "success" | "error";
  designError: string | null;
  /** Exact owner token for the currently active calculate request, if any. */
  activeCalculateRevision: number | null;
  stressBaseline: number;
  stressDropout: number;
  /** Single authoritative ledger tracking field provenance across all planned and stress inputs */
  provenanceLedger: ProvenanceLedger;
  evaluateResult: EvaluateResponse | null;
  evaluateStatus: "idle" | "evaluating" | "stale" | "success" | "error";
  evaluateError: string | null;
  /** Exact owner token for the currently active evaluation, if any. */
  activeEvaluateRevision: number | null;
  gridResult: GridResponse | null;
  gridStatus: "idle" | "loading" | "stale" | "success" | "error";
  gridError: string | null;
  /** Exact owner token for the currently active grid request, if any. */
  activeGridRevision: number | null;
  /** Input snapshot identity. Mutating inputs or starting a recalculation advances it. */
  inputGeneration: number;
  displayedInputsHash: string | null;
  /** Monotonic token allocator; operation ownership is tracked in the active fields above. */
  requestRevision: number;
}
