import type { RawPresetData, ProvenanceLedger, FieldProvenance } from "./workspace-contracts";
import { presets as mockPresets } from "./mocks";

function syntheticProvenance(field: string, basis: string): FieldProvenance {
  return {
    source: "synthetic_preset",
    description: basis,
    retrieved_at: null,
    source_url: null,
  };
}

function buildDefaultProvenance(fields: string[]): ProvenanceLedger {
  const ledger: ProvenanceLedger = {};
  for (const f of fields) {
    ledger[f] = syntheticProvenance(f, "Hand-authored synthetic assumption from playbook; no clinical source");
  }
  return ledger;
}

const commonFields = [
  "/planned_design/model_version",
  "/planned_design/control_event_rate",
  "/planned_design/effect/kind",
  "/planned_design/effect/value",
  "/planned_design/alpha",
  "/planned_design/target_power",
  "/planned_design/allocation_ratio",
  "/planned_design/dropout/control",
  "/planned_design/dropout/treatment",
  "/fixed_enrollment/control",
  "/fixed_enrollment/treatment",
  "/stress_scenario/control_event_rate",
  "/stress_scenario/dropout/control",
  "/stress_scenario/dropout/treatment",
  "/stress_scenario/effect_override",
  "/simulation/replicates",
  "/simulation/seed",
];

export const rawPresets: RawPresetData[] = [
  {
    preset_id: "baseline-collapse-v1",
    name: "Baseline collapse",
    eyebrow: "Control rate drop",
    description: "Planned 20% control risk collapses to 10% under fixed enrollment (N=903/arm, 0% dropout). Illustrates dramatic loss of statistical power.",
    inputs_hash: "sha256:d4dfd5525e9b355437d458dd211996674bd3b263509125fdceaf1b3bf8643380",
    planned_design: {
      model_version: "binary-v1",
      control_event_rate: 0.2,
      effect: { kind: "relative_risk", value: 0.75 },
      alpha: 0.05,
      target_power: 0.8,
      allocation_ratio: 1.0,
      dropout: { control: 0.0, treatment: 0.0 },
    },
    fixed_enrollment: { control: 903, treatment: 903 },
    stress_scenario: {
      control_event_rate: 0.1,
      dropout: { control: 0.0, treatment: 0.0 },
      effect_override: null,
    },
    simulation: { replicates: 10000, seed: 42 },
    provenance: buildDefaultProvenance(commonFields),
    design_response: {
      model_version: "binary-v1",
      method: "cohen_h_normal_v1",
      p_treatment: 0.15,
      evaluable_n: { control: 903, treatment: 903 },
      enrolled_n: { control: 903, treatment: 903 },
      nominal_power_evaluable: 0.801,
      warnings: ["Hand-authored illustrative preset mock."],
      inputs_hash: "sha256:d4dfd5525e9b355437d458dd211996674bd3b263509125fdceaf1b3bf8643380",
      provenance: mockPresets[1].design_response.provenance,
      mock: true,
    },
    evaluate_response: {
      model_version: "binary-v1",
      analytic: {
        method: "cohen_h_normal_v1",
        conditional_power_approx: 0.47,
        assumed_evaluable_n: { control: 903, treatment: 903 },
      },
      monte_carlo: {
        method: "pooled_two_proportion_z_v1",
        significant_two_sided_fraction: 0.47,
        significant_favorable_fraction: 0.47,
        mcse_two_sided: 0.005,
        mcse_favorable: 0.005,
        invalid_test_fraction: 0.0,
        replicates: 10000,
        seed: 42,
      },
      warnings: [
        "Hand-authored illustrative mock; not measured engine output or clinical evidence.",
        "Analytic and pooled-z simulation use distinct approximations.",
      ],
      metadata: {
        computed_at: "2026-10-10T12:00:00Z",
        inputs_hash: "sha256:d4dfd5525e9b355437d458dd211996674bd3b263509125fdceaf1b3bf8643380",
      },
      provenance: mockPresets[1].evaluate_response.provenance,
      mock: true,
    },
    grid_response: mockPresets[1].grid_response,
  },
  {
    preset_id: "attrition-shock-v1",
    name: "Attrition shock",
    eyebrow: "Severe dropout spike",
    description: "Planned 5% dropout increases to 25% under fixed enrollment (N=951/arm), shrinking evaluable sample size and eroding power.",
    inputs_hash: "sha256:5f0dc91f3a976ea707db2016da1fe009949d0df545b736b42b918641b691d575",
    planned_design: {
      model_version: "binary-v1",
      control_event_rate: 0.2,
      effect: { kind: "relative_risk", value: 0.75 },
      alpha: 0.05,
      target_power: 0.8,
      allocation_ratio: 1.0,
      dropout: { control: 0.05, treatment: 0.05 },
    },
    fixed_enrollment: { control: 951, treatment: 951 },
    stress_scenario: {
      control_event_rate: 0.2,
      dropout: { control: 0.25, treatment: 0.25 },
      effect_override: null,
    },
    simulation: { replicates: 10000, seed: 42 },
    provenance: buildDefaultProvenance(commonFields),
    design_response: {
      model_version: "binary-v1",
      method: "cohen_h_normal_v1",
      p_treatment: 0.15,
      evaluable_n: { control: 903, treatment: 903 },
      enrolled_n: { control: 951, treatment: 951 },
      nominal_power_evaluable: 0.801,
      warnings: ["Hand-authored illustrative preset mock."],
      inputs_hash: "sha256:5f0dc91f3a976ea707db2016da1fe009949d0df545b736b42b918641b691d575",
      provenance: mockPresets[2].design_response.provenance,
      mock: true,
    },
    evaluate_response: {
      model_version: "binary-v1",
      analytic: {
        method: "cohen_h_normal_v1",
        conditional_power_approx: 0.50,
        assumed_evaluable_n: { control: 713, treatment: 713 },
      },
      monte_carlo: {
        method: "pooled_two_proportion_z_v1",
        significant_two_sided_fraction: 0.50,
        significant_favorable_fraction: 0.495,
        mcse_two_sided: 0.005,
        mcse_favorable: 0.004,
        invalid_test_fraction: 0.0,
        replicates: 10000,
        seed: 42,
      },
      warnings: [
        "Hand-authored illustrative mock; not measured engine output or clinical evidence.",
        "Analytic and pooled-z simulation use distinct approximations.",
      ],
      metadata: {
        computed_at: "2026-10-10T12:00:00Z",
        inputs_hash: "sha256:5f0dc91f3a976ea707db2016da1fe009949d0df545b736b42b918641b691d575",
      },
      provenance: mockPresets[2].evaluate_response.provenance,
      mock: true,
    },
    grid_response: mockPresets[2].grid_response,
  },
  {
    preset_id: "stable-design-v1",
    name: "Stable design",
    eyebrow: "Robust operating point",
    description: "Planned 20% control risk shifts slightly to 19% with 6% dropout (N=951/arm), preserving acceptable power.",
    inputs_hash: "sha256:f9ec599b821415139097e882a1df6714a9ecae70377464010a3e813f835b5a7a",
    planned_design: {
      model_version: "binary-v1",
      control_event_rate: 0.2,
      effect: { kind: "relative_risk", value: 0.75 },
      alpha: 0.05,
      target_power: 0.8,
      allocation_ratio: 1.0,
      dropout: { control: 0.05, treatment: 0.05 },
    },
    fixed_enrollment: { control: 951, treatment: 951 },
    stress_scenario: {
      control_event_rate: 0.19,
      dropout: { control: 0.06, treatment: 0.06 },
      effect_override: null,
    },
    simulation: { replicates: 10000, seed: 42 },
    provenance: buildDefaultProvenance(commonFields),
    design_response: {
      model_version: "binary-v1",
      method: "cohen_h_normal_v1",
      p_treatment: 0.15,
      evaluable_n: { control: 903, treatment: 903 },
      enrolled_n: { control: 951, treatment: 951 },
      nominal_power_evaluable: 0.801,
      warnings: ["Hand-authored illustrative preset mock."],
      inputs_hash: "sha256:f9ec599b821415139097e882a1df6714a9ecae70377464010a3e813f835b5a7a",
      provenance: mockPresets[0].design_response.provenance,
      mock: true,
    },
    evaluate_response: {
      model_version: "binary-v1",
      analytic: {
        method: "cohen_h_normal_v1",
        conditional_power_approx: 0.78,
        assumed_evaluable_n: { control: 893, treatment: 893 },
      },
      monte_carlo: {
        method: "pooled_two_proportion_z_v1",
        significant_two_sided_fraction: 0.78,
        significant_favorable_fraction: 0.78,
        mcse_two_sided: 0.004,
        mcse_favorable: 0.004,
        invalid_test_fraction: 0.0,
        replicates: 10000,
        seed: 42,
      },
      warnings: [
        "Hand-authored illustrative mock; not measured engine output or clinical evidence.",
        "Analytic and pooled-z simulation use distinct approximations.",
      ],
      metadata: {
        computed_at: "2026-10-10T12:00:00Z",
        inputs_hash: "sha256:f9ec599b821415139097e882a1df6714a9ecae70377464010a3e813f835b5a7a",
      },
      provenance: mockPresets[0].evaluate_response.provenance,
      mock: true,
    },
    grid_response: mockPresets[0].grid_response,
  },
];

export function getPresetById(id: string): RawPresetData {
  return rawPresets.find((p) => p.preset_id === id) ?? rawPresets[0];
}
