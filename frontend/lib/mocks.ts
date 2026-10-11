import type {
  CalculateResponse,
  EvaluateResponse,
  GridResponse,
  Preset,
  Provenance,
} from "./contracts";

const generatedAt = "2026-10-10T12:00:00Z";

function provenance(id: string, label: string, followUp: string): Provenance {
  return {
    scenario_id: id,
    scenario_kind: "synthetic",
    label,
    source: { type: "synthetic", citation_url: null, source_location: null },
    endpoint_type: "binary_undesirable_event",
    follow_up_label: followUp,
    method_version: "binary-v1",
    generated_by: "local_fixture",
  };
}

function design(
  pTreatment: number,
  evaluablePerArm: number,
  enrolledPerArm: number,
  nominalPower: number,
  hash: string,
  source: Provenance,
): CalculateResponse {
  return {
    model_version: "binary-v1",
    method: "cohen_h_normal_v1",
    p_treatment: pTreatment,
    evaluable_n: { control: evaluablePerArm, treatment: evaluablePerArm },
    enrolled_n: { control: enrolledPerArm, treatment: enrolledPerArm },
    nominal_power_evaluable: nominalPower,
    warnings: [
      "Dropout inflation represents expected retention, not guaranteed evaluable counts.",
      "Illustrative local fixture; this is not a calculation.",
    ],
    inputs_hash: `sha256:mock-${hash}`,
    provenance: source,
    mock: true,
  };
}

function evaluate(
  power: number,
  twoSided: number,
  favorable: number,
  mcse: number,
  invalidFraction: number,
  hash: string,
  source: Provenance,
): EvaluateResponse {
  return {
    model_version: "binary-v1",
    analytic: {
      method: "cohen_h_normal_v1",
      conditional_power_approx: power,
      assumed_evaluable_n: { control: 903, treatment: 903 },
    },
    monte_carlo: {
      method: "pooled_two_proportion_z_v1",
      significant_two_sided_fraction: twoSided,
      significant_favorable_fraction: favorable,
      mcse,
      invalid_test_fraction: invalidFraction,
      replicates: 10000,
      seed: 42,
    },
    warnings: [
      "Independent, symmetric dropout is an illustrative assumption.",
      "Analytic and Monte Carlo examples use distinct approximations.",
      "Values are a fixed mock snapshot, not a simulation run.",
    ],
    metadata: { computed_at: generatedAt, inputs_hash: `sha256:mock-${hash}` },
    provenance: source,
    mock: true,
  };
}

function grid(
  x: number[],
  y: number[],
  power: (number | null)[][],
  invalidMask: boolean[][],
  planned: { baseline: number; dropout: number },
  selected: { baseline: number; dropout: number },
  frontier: { baseline: number; dropout: number }[],
  hash: string,
  source: Provenance,
): GridResponse {
  return {
    model_version: "binary-v1",
    method: "cohen_h_normal_v1",
    grid_label: "expected_count_approximation",
    x_baseline: x,
    y_dropout: y,
    power,
    invalid_mask: invalidMask,
    target_power: 0.8,
    planned_point: planned,
    selected_point: selected,
    frontier_points: frontier,
    warnings: [
      "Heatmap and target contour are illustrative fixture values.",
      "Grid cells use an expected-count approximation in this contract example.",
      "Masked cells have null power and are excluded from the contour.",
    ],
    computed_at: generatedAt,
    inputs_hash: `sha256:mock-${hash}`,
    provenance: source,
    mock: true,
  };
}

const stableSource = provenance("stable-v1", "Stable plan", "12 months (illustrative)");
const collapseSource = provenance(
  "baseline-collapse-v1",
  "Baseline collapse",
  "12 months (illustrative)",
);
const attritionSource = provenance(
  "attrition-shock-v1",
  "Attrition shock · ARR example",
  "12 months (illustrative)",
);

export const presets: Preset[] = [
  {
    id: "stable-v1",
    name: "Stable plan",
    eyebrow: "SYNTHETIC CASE 01",
    description: "A steady control risk with the planned retention assumption.",
    assumptions: {
      model_version: "binary-v1",
      control_event_rate: 0.2,
      effect: { kind: "relative_risk", value: 0.75 },
      alpha: 0.05,
      target_power: 0.8,
      allocation_ratio: 1,
      dropout: { control: 0, treatment: 0 },
    },
    stress: { control_event_rate: 0.2, dropout: 0 },
    effect_label: "RR 0.75",
    design_response: design(0.15, 903, 903, 0.801, "stable-design", stableSource),
    evaluate_response: evaluate(0.801, 0.803, 0.803, 0.004, 0, "stable-eval", stableSource),
    grid_response: grid(
      [0.05, 0.1, 0.15, 0.2, 0.25, 0.3],
      [0, 0.1, 0.2, 0.3],
      [
      [0.16, 0.47, 0.65, 0.801, 0.88, 0.93],
      [0.15, 0.44, 0.62, 0.77, 0.85, 0.91],
      [0.13, 0.4, 0.57, 0.72, 0.82, 0.88],
      [0.11, 0.36, 0.53, 0.67, 0.78, 0.85],
      ],
      [
        [false, false, false, false, false, false],
        [false, false, false, false, false, false],
        [false, false, false, false, false, false],
        [false, false, false, false, false, false],
      ],
      { baseline: 0.2, dropout: 0 },
      { baseline: 0.2, dropout: 0 },
      [
        { baseline: 0.2, dropout: 0 },
        { baseline: 0.24, dropout: 0.1 },
        { baseline: 0.29, dropout: 0.3 },
      ],
      "stable-grid",
      stableSource,
    ),
  },
  {
    id: "baseline-collapse-v1",
    name: "Baseline collapse",
    eyebrow: "SYNTHETIC CASE 02",
    description: "The event rate falls while planned enrollment stays frozen.",
    assumptions: {
      model_version: "binary-v1",
      control_event_rate: 0.2,
      effect: { kind: "relative_risk", value: 0.75 },
      alpha: 0.05,
      target_power: 0.8,
      allocation_ratio: 1,
      dropout: { control: 0, treatment: 0 },
    },
    stress: { control_event_rate: 0.1, dropout: 0 },
    effect_label: "RR 0.75",
    design_response: design(0.15, 903, 903, 0.801, "collapse-design", collapseSource),
    evaluate_response: evaluate(0.47, 0.468, 0.466, 0.005, 0.001, "collapse-eval", collapseSource),
    grid_response: grid(
      [0.05, 0.1, 0.15, 0.2, 0.25, 0.3],
      [0, 0.1, 0.2, 0.3],
      [
      [0.16, 0.47, 0.65, 0.801, 0.88, 0.93],
      [0.15, 0.44, 0.62, 0.77, 0.85, 0.91],
      [0.13, 0.4, 0.57, 0.72, 0.82, 0.88],
      [0.11, 0.36, 0.53, 0.67, 0.78, 0.85],
      ],
      [
        [false, false, false, false, false, false],
        [false, false, false, false, false, false],
        [false, false, false, false, false, false],
        [false, false, false, false, false, false],
      ],
      { baseline: 0.2, dropout: 0 },
      { baseline: 0.1, dropout: 0 },
      [
        { baseline: 0.2, dropout: 0 },
        { baseline: 0.24, dropout: 0.1 },
        { baseline: 0.29, dropout: 0.3 },
      ],
      "collapse-grid",
      collapseSource,
    ),
  },
  {
    id: "attrition-shock-v1",
    name: "Attrition shock · ARR",
    eyebrow: "SYNTHETIC CASE 03",
    description: "A fixed absolute risk reduction becomes invalid below its baseline.",
    assumptions: {
      model_version: "binary-v1",
      control_event_rate: 0.2,
      effect: { kind: "absolute_risk_reduction", value: 0.05 },
      alpha: 0.05,
      target_power: 0.8,
      allocation_ratio: 1,
      dropout: { control: 0.1, treatment: 0.1 },
    },
    stress: { control_event_rate: 0.13, dropout: 0.2 },
    effect_label: "ARR 5 pp",
    design_response: design(0.15, 903, 1004, 0.801, "attrition-design", attritionSource),
    evaluate_response: evaluate(0.5, 0.497, 0.495, 0.005, 0.002, "attrition-eval", attritionSource),
    grid_response: grid(
      [0.03, 0.08, 0.13, 0.18, 0.23, 0.28],
      [0, 0.1, 0.2, 0.3],
      [
        [null, 0.38, 0.61, 0.77, 0.88, 0.94],
        [null, 0.34, 0.56, 0.72, 0.84, 0.91],
        [null, 0.29, 0.5, 0.67, 0.8, 0.88],
        [null, 0.25, 0.45, 0.62, 0.75, 0.84],
      ],
      [
        [true, false, false, false, false, false],
        [true, false, false, false, false, false],
        [true, false, false, false, false, false],
        [true, false, false, false, false, false],
      ],
      { baseline: 0.2, dropout: 0.1 },
      { baseline: 0.13, dropout: 0.2 },
      [
        { baseline: 0.18, dropout: 0 },
        { baseline: 0.23, dropout: 0.2 },
        { baseline: 0.25, dropout: 0.3 },
      ],
      "attrition-grid",
      attritionSource,
    ),
  },
];
