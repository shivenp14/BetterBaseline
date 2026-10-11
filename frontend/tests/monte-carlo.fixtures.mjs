export const selection = {
  planned_design: { model_version: 'binary-v1', allocation_ratio: 1, control_event_rate: .2, effect: { kind: 'relative_risk', value: .75 }, alpha: .05, target_power: .8, dropout: { control: .1, treatment: .1 } },
  fixed_enrollment: { control: 1004, treatment: 1004 }, stress_scenario: { control_event_rate: .1, dropout: { control: .1, treatment: .1 }, effect_override: null },
  provenance: { control_event_rate: { source: 'manual_user', description: 'Entered assumption' } },
};
export const request = { ...selection, simulation: { seed: 42, replicates: 10000 } };
export const alternative = {
  model_version: 'binary-v1', analytic: { method: 'cohen_h_normal_v1', conditional_power_approx: .47, assumed_evaluable_n: { control: 903, treatment: 903 } },
  monte_carlo: { method: 'pooled_two_proportion_z_v1', invalid_test_policy: 'nonrejection_over_all_replicates', significant_two_sided_fraction: .46, significant_favorable_fraction: .45,
    mcse_two_sided: .0049839743, mcse_favorable: .0049749372, invalid_test_fraction: .01, mean_retained_control: 903.65, mean_retained_treatment: 903.55,
    mean_control_events: 90.3, mean_treatment_events: 67.7, seed: 42, replicates: 10000, rng: 'PCG64', software_versions: { numpy: 'fixture-version' } },
  metadata: { computed_at: '2026-10-11T00:00:00+00:00', inputs_hash: 'fixture-only', fixed_enrollment: selection.fixed_enrollment, software_versions: { python: 'fixture-version' } },
  provenance: selection.provenance, warnings: ['Synthetic test fixture warning'],
};
export const nullFixture = { ...alternative, monte_carlo: { ...alternative.monte_carlo, significant_two_sided_fraction: .05, significant_favorable_fraction: .025, mcse_two_sided: .0021794495, mcse_favorable: .0015612495 } };
