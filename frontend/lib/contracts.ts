export type Effect =
  | { kind: "relative_risk"; value: number }
  | { kind: "absolute_risk_reduction"; value: number };

export interface TrialAssumptions {
  model_version: "binary-v1";
  control_event_rate: number;
  effect: Effect;
  alpha: number;
  target_power: number;
  allocation_ratio: 1;
  dropout: { control: number; treatment: number };
}

export interface FixedEnrollment {
  control: number;
  treatment: number;
}

/** Backend API v1 per-field attribution and optional audit metadata. */
export interface ApiFieldProvenance {
  source: "manual_user" | "synthetic_preset" | "protocol_curated" | "clinicaltrials_registry";
  description?: string | null;
  retrieved_at?: string | null;
  source_url?: string | null;
  source_location?: string | null;
  verified_by_user?: boolean | null;
  is_observed_registry_result?: boolean | null;
}

export type ApiProvenanceMap = Record<string, ApiFieldProvenance>;

export interface StatisticalDiagnostic {
  code: string;
  severity: "info" | "warning" | "error";
  field: string;
  method: string;
  message: string;
  arm?: "control" | "treatment" | null;
  outcome?: "events" | "non_events" | null;
  expected_count?: number | null;
  threshold?: number | null;
  count_basis?: "evaluable_count" | "expected_random_retention" | null;
  invalid_test_fraction?: number | null;
  replicates?: number | null;
  invalid_test_policy?: "nonrejection_over_all_replicates" | null;
}

export interface CalculateRequest extends TrialAssumptions {
  /** UI metadata only; stripped by the adapter before HTTP transport. */
  preset_id: string;
  /** Optional backend API v1 provenance; distinct from the UI-only ledger wrapper. */
  provenance?: ApiProvenanceMap;
}

/** Backend request schema without page-only preset metadata. */
export interface ApiDesignCalculateRequest extends TrialAssumptions {
  provenance?: ApiProvenanceMap;
}

/** Raw response from POST /api/v1/design/calculate before UI adapter metadata. */
export interface ApiDesignCalculateResponse {
  model_version: "binary-v1";
  method: "cohen_h_normal_v1";
  p_treatment: number;
  evaluable_n: FixedEnrollment;
  enrolled_n: FixedEnrollment;
  nominal_power_evaluable: number;
  warnings: string[];
  diagnostics: StatisticalDiagnostic[];
  provenance: ApiProvenanceMap;
  inputs_hash: string;
}

/** Raw API v1 evaluation response stored in the canonical export envelope. */
export interface ApiScenarioEvaluateResponse {
  model_version: "binary-v1";
  analytic: {
    method: "cohen_h_normal_v1";
    conditional_power_approx: number | null;
    assumed_evaluable_n: { control: number; treatment: number };
  };
  monte_carlo: {
    method: "pooled_two_proportion_z_v1";
    significant_two_sided_fraction: number;
    significant_favorable_fraction: number;
    mcse_two_sided: number;
    mcse_favorable: number;
    invalid_test_fraction: number;
    replicates: number;
    seed: number | null;
    invalid_test_policy?: "nonrejection_over_all_replicates" | null;
    mean_retained_control?: number | null;
    mean_retained_treatment?: number | null;
    mean_control_events?: number | null;
    mean_treatment_events?: number | null;
    rng?: string | null;
    software_versions?: Record<string, string>;
  } | null;
  warnings: string[];
  diagnostics: StatisticalDiagnostic[];
  metadata: {
    computed_at: string;
    inputs_hash: string;
    software_versions: Record<string, string>;
    fixed_enrollment: FixedEnrollment | null;
  };
  provenance: ApiProvenanceMap;
}

export interface ApiGridPoint {
  p_control: number;
  dropout: number;
  power?: number | null;
  is_safe?: boolean;
  is_valid?: boolean;
  invalid_reason?: string | null;
  expected_evaluable_n?: { control: number; treatment: number } | null;
}

/** Raw API v1 grid response; coordinates retain backend names before UI mapping. */
export interface ApiScenarioGridResponse {
  grid_label: "expected_count_approximation";
  fixed_enrollment?: FixedEnrollment | null;
  below_target: (boolean | null)[][];
  analytic_delta?: number | null;
  software_versions: Record<string, string>;
  provenance: ApiProvenanceMap;
  model_version: "binary-v1";
  method: "cohen_h_normal_v1";
  x_baseline: number[];
  y_dropout: number[];
  power: (number | null)[][];
  invalid_mask: boolean[][];
  target_power: number;
  planned_point: ApiGridPoint;
  selected_point?: ApiGridPoint | null;
  frontier_points: ApiGridPoint[];
  contour_segments: { start: { p_control: number; dropout: number }; end: { p_control: number; dropout: number } }[];
  power_curve: { p_control: number; power: number | null; is_valid: boolean }[];
  invalid_cell_count: number;
  worst_case_power?: number | null;
  warnings: string[];
  diagnostics: StatisticalDiagnostic[];
  computed_at: string;
  inputs_hash: string;
}

export interface ExecutionInfo {
  mode: "backend" | "demo";
  label: string;
}

export interface CalculateResponse {
  model_version: "binary-v1";
  method: "cohen_h_normal_v1";
  p_treatment: number;
  evaluable_n: FixedEnrollment;
  enrolled_n: FixedEnrollment;
  nominal_power_evaluable: number;
  warnings: string[];
  diagnostics?: StatisticalDiagnostic[];
  inputs_hash: string;
  provenance: Provenance;
  execution?: ExecutionInfo;
  mock: boolean;
}

export interface EvaluateRequest {
  planned_design: TrialAssumptions;
  fixed_enrollment: FixedEnrollment;
  stress_scenario: {
    control_event_rate: number;
    dropout: { control: number; treatment: number };
    effect_override: Effect | null;
  };
  simulation: { replicates: number; seed: number };
  preset_id: string;
  provenance?: ApiProvenanceMap;
  /** App ledger translated to the backend's top-level `provenance` field. */
  provenance_ledger?: Record<string, {
    source: "manual_user" | "synthetic_preset" | "protocol_curated" | "clinicaltrials_registry";
    description?: string | null;
    retrieved_at?: string | null;
    source_url?: string | null;
    source_location?: string | null;
    verified_by_user?: boolean | null;
    is_observed_registry_result?: boolean | null;
  }>;
}

export interface EvaluateResponse {
  model_version: "binary-v1";
  analytic: {
    method: "cohen_h_normal_v1";
    conditional_power_approx: number | null;
    assumed_evaluable_n: FixedEnrollment;
  };
  monte_carlo: {
    method: "pooled_two_proportion_z_v1";
    significant_two_sided_fraction: number;
    significant_favorable_fraction: number;
    mcse_two_sided: number;
    mcse_favorable: number;
    invalid_test_fraction: number;
    replicates: number;
    seed: number;
  } | null;
  warnings: string[];
  diagnostics?: StatisticalDiagnostic[];
  metadata: { computed_at: string; inputs_hash: string };
  provenance: Provenance;
  execution?: ExecutionInfo;
  mock: boolean;
}

export interface GridRequest {
  planned_design: TrialAssumptions;
  fixed_enrollment: FixedEnrollment;
  x_baseline: number[];
  y_dropout: number[];
  selected_scenario?: {
    control_event_rate: number;
    dropout: { control: number; treatment: number };
    effect_override: Effect | null;
  };
  preset_id: string;
}

export interface GridPoint {
  /** Canonical backend grid coordinate. */
  p_control?: number;
  /** UI alias added by the API adapter. */
  baseline: number;
  dropout: number;
  power?: number | null;
  is_safe?: boolean;
  is_valid?: boolean;
  expected_evaluable_n?: FixedEnrollment;
  invalid_reason?: string | null;
}

export interface GridResponse {
  model_version: "binary-v1";
  method: "cohen_h_normal_v1";
  grid_label: "expected_count_approximation";
  x_baseline: number[];
  y_dropout: number[];
  /** Rows are dropout values; columns are baseline values. */
  power: (number | null)[][];
  /** True cells have null power values. */
  invalid_mask: boolean[][];
  target_power: number;
  planned_point: GridPoint;
  selected_point: GridPoint | null;
  frontier_points: GridPoint[];
  /** Canonical backend fields used by exports and current-grid verification. */
  fixed_enrollment?: FixedEnrollment;
  below_target?: (boolean | null)[][];
  analytic_delta?: number | null;
  software_versions?: Record<string, string>;
  contour_segments?: { start: { p_control: number; dropout: number }; end: { p_control: number; dropout: number } }[];
  power_curve?: { p_control: number; power: number | null; is_valid: boolean }[];
  invalid_cell_count?: number;
  worst_case_power?: number | null;
  warnings: string[];
  diagnostics?: StatisticalDiagnostic[];
  computed_at: string;
  inputs_hash: string;
  provenance: Provenance;
  execution?: ExecutionInfo;
  mock: boolean;
}

export interface Provenance {
  scenario_id: string;
  scenario_kind: "synthetic";
  label: string;
  source: { type: "synthetic"; citation_url: null; source_location: null };
  endpoint_type: "binary_undesirable_event";
  follow_up_label: string;
  method_version: "binary-v1";
  generated_by: "local_fixture" | "backend_service";
  field_provenance?: Record<string, {
    source: "manual_user" | "synthetic_preset" | "protocol_curated" | "clinicaltrials_registry";
    description?: string | null;
    retrieved_at?: string | null;
    source_url?: string | null;
    source_location?: string | null;
    verified_by_user?: boolean | null;
    is_observed_registry_result?: boolean | null;
  }>;
}

/** Canonical backend export envelope; UI export assembly remains downstream. */
export interface ApiExportPayload {
  export_schema_version: number;
  model_version: "binary-v1";
  planned_design: TrialAssumptions;
  fixed_enrollment: FixedEnrollment;
  stress_scenario?: EvaluateRequest["stress_scenario"] | null;
  design_result?: ApiDesignCalculateResponse | null;
  evaluation_result?: ApiScenarioEvaluateResponse | null;
  grid_result?: ApiScenarioGridResponse | null;
  software_versions: Record<string, string>;
  provenance: ApiProvenanceMap;
  exported_at: string;
  inputs_hash: string;
}

export interface Preset {
  id: string;
  name: string;
  eyebrow: string;
  description: string;
  assumptions: TrialAssumptions;
  stress: { control_event_rate: number; dropout: number };
  effect_label: string;
  design_response: CalculateResponse;
  evaluate_response: EvaluateResponse;
  grid_response: GridResponse;
}
