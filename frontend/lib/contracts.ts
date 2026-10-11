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

export interface CalculateRequest extends TrialAssumptions {
  preset_id: string;
}

export interface CalculateResponse {
  model_version: "binary-v1";
  method: "cohen_h_normal_v1";
  p_treatment: number;
  evaluable_n: FixedEnrollment;
  enrolled_n: FixedEnrollment;
  nominal_power_evaluable: number;
  warnings: string[];
  inputs_hash: string;
  provenance: Provenance;
  mock: true;
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
  metadata: { computed_at: string; inputs_hash: string };
  provenance: Provenance;
  mock: true;
}

export interface GridRequest {
  planned_design: TrialAssumptions;
  fixed_enrollment: FixedEnrollment;
  x_baseline: number[];
  y_dropout: number[];
  preset_id: string;
}

export interface GridPoint {
  baseline: number;
  dropout: number;
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
  selected_point: GridPoint;
  frontier_points: GridPoint[];
  warnings: string[];
  computed_at: string;
  inputs_hash: string;
  provenance: Provenance;
  mock: true;
}

export interface Provenance {
  scenario_id: string;
  scenario_kind: "synthetic";
  label: string;
  source: { type: "synthetic"; citation_url: null; source_location: null };
  endpoint_type: "binary_undesirable_event";
  follow_up_label: string;
  method_version: "binary-v1";
  generated_by: "local_fixture";
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
