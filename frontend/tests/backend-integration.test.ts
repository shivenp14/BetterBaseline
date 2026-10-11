import assert from "node:assert/strict";
import { calculateDesign, evaluateScenario, getStressGrid } from "../lib/api";
import { initializeWorkspaceState, workspaceReducer } from "../lib/workspace-state";

async function run() {
  process.env.NEXT_PUBLIC_API_MODE = "live";
  let state = initializeWorkspaceState("baseline-collapse-v1");
  assert.equal(state.frozenEnrollment, null, "live mode cannot evaluate preset enrollment before calculation");
  const planned = { ...state.plannedDraft, dropout: { control: 0.1, treatment: 0.1 } };
  state = workspaceReducer(state, {
    type: "UPDATE_PLANNED_FIELD", fieldPointer: "/planned_design/dropout/control", update: { dropout: planned.dropout },
  });
  const revision = state.requestRevision;
  state = workspaceReducer(state, { type: "START_CALCULATE", requestRevision: revision });
  const calculation = await calculateDesign({ ...planned, preset_id: state.presetId, provenance_ledger: state.provenanceLedger });
  assert.equal(calculation.enrolled_n.control, 1004);
  assert.equal(calculation.enrolled_n.treatment, 1004);
  assert.equal(calculation.mock, false);
  state = workspaceReducer(state, { type: "CALCULATE_SUCCESS", response: calculation, requestRevision: revision });
  const frozen = structuredClone(state.frozenEnrollment);
  assert.deepEqual(frozen, { control: 1004, treatment: 1004 }, "real calculation freezes enrollment from the backend response");

  state = workspaceReducer(state, { type: "UPDATE_STRESS_BASELINE", baseline: 0.2 });
  state = workspaceReducer(state, { type: "UPDATE_STRESS_DROPOUT", dropout: 0.25 });
  assert.deepEqual(state.frozenEnrollment, frozen, "stress edits preserve the frozen planned enrollment");
  const result = await evaluateScenario({
    planned_design: planned,
    fixed_enrollment: state.frozenEnrollment!,
    stress_scenario: {
      control_event_rate: state.stressBaseline,
      dropout: { control: state.stressDropout, treatment: state.stressDropout },
      effect_override: null,
    },
    simulation: { replicates: 10000, seed: 42 },
    preset_id: state.presetId,
    provenance_ledger: state.provenanceLedger,
  });
  assert.equal(result.mock, false);
  assert.equal(result.monte_carlo?.method, "pooled_two_proportion_z_v1");
  assert.equal(result.monte_carlo?.replicates, 10000);
  assert.equal(result.monte_carlo?.seed, 42);
  assert.ok((result.monte_carlo?.significant_two_sided_fraction ?? -1) >= 0);
  assert.equal(result.analytic.assumed_evaluable_n.control, 753);
  assert.deepEqual(result.provenance.field_provenance, state.provenanceLedger);
  assert.deepEqual(state.frozenEnrollment, frozen, "evaluation does not resize enrollment");
  await assert.rejects(getStressGrid({
    planned_design: planned, fixed_enrollment: frozen!, x_baseline: [0.1, 0.2], y_dropout: [0, 0.2],
    preset_id: state.presetId, provenance_ledger: state.provenanceLedger,
  }), /Scenario grid endpoint implementation owned by Issue #66/);
  console.log(JSON.stringify({
    calculated_enrollment: calculation.enrolled_n,
    stress_expected_evaluable: result.analytic.assumed_evaluable_n,
    monte_carlo: {
      method: result.monte_carlo?.method,
      replicates: result.monte_carlo?.replicates,
      seed: result.monte_carlo?.seed,
      significant_two_sided_fraction: result.monte_carlo?.significant_two_sided_fraction,
      significant_favorable_fraction: result.monte_carlo?.significant_favorable_fraction,
    },
    frozen_after_stress: state.frozenEnrollment,
    provenance_fields: Object.keys(result.provenance.field_provenance ?? {}).length,
    grid: "backend returned its owned-by-#66 HTTP 501 scaffold; no client formula fallback",
  }, null, 2));
}

run().catch((error) => { console.error(error); process.exitCode = 1; });
