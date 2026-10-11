import assert from "node:assert";
import {
  initializeWorkspaceState,
  workspaceReducer,
} from "../lib/workspace-state";
import {
  evaluateScenario,
} from "../lib/api";
import type { CalculateResponse } from "../lib/contracts";

function testPresetLoading() {
  const state = initializeWorkspaceState("baseline-collapse-v1");
  assert.strictEqual(state.presetId, "baseline-collapse-v1");
  assert.strictEqual(state.frozenEnrollment?.control, 903);
  assert.strictEqual(state.frozenEnrollment?.treatment, 903);
  assert.strictEqual(state.stressBaseline, 0.1);
  assert.strictEqual(state.stressDropout, 0.0);
  assert.strictEqual(state.evaluateStatus, "idle");
  console.log("✔ Preset loading test passed");
}

function testStressAdjustmentPreservesFrozenEnrollment() {
  let state = initializeWorkspaceState("baseline-collapse-v1");
  const originalControlN = state.frozenEnrollment?.control;
  const originalTreatmentN = state.frozenEnrollment?.treatment;

  // Move stress slider to 0.15 baseline
  state = workspaceReducer(state, {
    type: "UPDATE_STRESS_BASELINE",
    baseline: 0.15,
  });

  // Fixed enrollment must NEVER change
  assert.strictEqual(state.frozenEnrollment?.control, originalControlN);
  assert.strictEqual(state.frozenEnrollment?.treatment, originalTreatmentN);
  assert.strictEqual(state.stressBaseline, 0.15);
  assert.strictEqual(state.evaluateStatus, "stale");
  assert.strictEqual(
    state.provenanceLedger["/stress_scenario/control_event_rate"]?.source,
    "manual_user"
  );

  // Move stress dropout to 0.25
  state = workspaceReducer(state, {
    type: "UPDATE_STRESS_DROPOUT",
    dropout: 0.25,
  });

  assert.strictEqual(state.frozenEnrollment?.control, originalControlN);
  assert.strictEqual(state.frozenEnrollment?.treatment, originalTreatmentN);
  assert.strictEqual(state.stressDropout, 0.25);
  assert.strictEqual(state.evaluateStatus, "stale");
  assert.strictEqual(
    state.provenanceLedger["/stress_scenario/dropout/control"]?.source,
    "manual_user"
  );
  console.log("✔ Stress adjustment preserves frozen enrollment test passed");
}

function testRecalculateLocksNewEnrollment() {
  let state = initializeWorkspaceState("baseline-collapse-v1");

  // Modify planned control event rate
  state = workspaceReducer(state, {
    type: "UPDATE_PLANNED_FIELD",
    fieldPointer: "/planned_design/control_event_rate",
    update: { control_event_rate: 0.3 },
  });

  assert.strictEqual(
    state.provenanceLedger["/planned_design/control_event_rate"]?.source,
    "manual_user"
  );
  assert.strictEqual(state.evaluateStatus, "stale");

  // Execute Calculate success with new counts
  const mockNewDesign: CalculateResponse = {
    model_version: "binary-v1",
    method: "cohen_h_normal_v1",
    p_treatment: 0.225,
    evaluable_n: { control: 560, treatment: 560 },
    enrolled_n: { control: 560, treatment: 560 },
    nominal_power_evaluable: 0.801,
    warnings: [],
    inputs_hash: "sha256:new-test-hash",
    provenance: state.calculatedDesign!.provenance,
    mock: true,
  };

  state = workspaceReducer(state, {
    type: "CALCULATE_SUCCESS",
    response: mockNewDesign,
    requestRevision: state.requestRevision,
  });

  assert.strictEqual(state.frozenEnrollment?.control, 560);
  assert.strictEqual(state.frozenEnrollment?.treatment, 560);
  assert.strictEqual(state.designStatus, "success");
  assert.strictEqual(state.displayedInputsHash, "sha256:new-test-hash");
  console.log("✔ Recalculate locks new enrollment test passed");
}

function testSwitchingPresetResetsStateAndProvenance() {
  let state = initializeWorkspaceState("baseline-collapse-v1");
  state = workspaceReducer(state, {
    type: "UPDATE_STRESS_BASELINE",
    baseline: 0.18,
  });
  assert.strictEqual(
    state.provenanceLedger["/stress_scenario/control_event_rate"]?.source,
    "manual_user"
  );

  // Switch to attrition-shock preset
  state = workspaceReducer(state, {
    type: "LOAD_PRESET",
    presetId: "attrition-shock-v1",
  });

  assert.strictEqual(state.presetId, "attrition-shock-v1");
  assert.strictEqual(state.frozenEnrollment?.control, 951);
  assert.strictEqual(state.stressDropout, 0.25);
  assert.strictEqual(
    state.provenanceLedger["/stress_scenario/control_event_rate"]?.source,
    "synthetic_preset"
  );
  console.log("✔ Switching preset resets state and provenance test passed");
}

function testRejectOutdatedLateResponses() {
  let state = initializeWorkspaceState("baseline-collapse-v1");
  const initialRevision = state.requestRevision;

  // Dispatch an async calculate start at initialRevision
  state = workspaceReducer(state, { type: "START_CALCULATE" });

  // User subsequently modifies stress baseline before calculation finishes
  state = workspaceReducer(state, {
    type: "UPDATE_STRESS_BASELINE",
    baseline: 0.30,
  });
  assert.strictEqual(state.requestRevision > initialRevision, true);

  // Now outdated response arrives with initialRevision
  const outdatedResponse: CalculateResponse = {
    model_version: "binary-v1",
    method: "cohen_h_normal_v1",
    p_treatment: 0.15,
    evaluable_n: { control: 903, treatment: 903 },
    enrolled_n: { control: 903, treatment: 903 },
    nominal_power_evaluable: 0.8,
    warnings: [],
    inputs_hash: "sha256:outdated",
    provenance: state.calculatedDesign!.provenance,
    mock: true,
  };

  const stateAfterLateArrival = workspaceReducer(state, {
    type: "CALCULATE_SUCCESS",
    response: outdatedResponse,
    requestRevision: initialRevision,
  });

  // Must reject: displayedInputsHash must NOT be overwritten by outdated hash
  assert.strictEqual(stateAfterLateArrival.displayedInputsHash, null);
  assert.strictEqual(stateAfterLateArrival.evaluateStatus, "stale");
  console.log("✔ Outdated late response rejected by revision guard");
}

async function testLiveEvaluationCalculatesDifferentAssumptions() {
  const state = initializeWorkspaceState("baseline-collapse-v1");
  // Preset has stress baseline 0.10, yielding approx 0.470 power
  const defaultEval = await evaluateScenario({
    planned_design: state.plannedDraft,
    fixed_enrollment: state.frozenEnrollment!,
    stress_scenario: {
      control_event_rate: 0.10,
      dropout: { control: 0.0, treatment: 0.0 },
      effect_override: null,
    },
    simulation: { replicates: 10000, seed: 42 },
    preset_id: state.presetId,
  });
  assert.strictEqual(defaultEval.analytic.conditional_power_approx, 0.47);

  // When user stresses baseline to 0.15, power must be computed live and different
  const stressedEval = await evaluateScenario({
    planned_design: state.plannedDraft,
    fixed_enrollment: state.frozenEnrollment!,
    stress_scenario: {
      control_event_rate: 0.15,
      dropout: { control: 0.0, treatment: 0.0 },
      effect_override: null,
    },
    simulation: { replicates: 10000, seed: 42 },
    preset_id: state.presetId,
  });
  assert.notStrictEqual(stressedEval.analytic.conditional_power_approx, 0.47);
  assert.strictEqual(typeof stressedEval.analytic.conditional_power_approx, "number");
  assert.strictEqual(stressedEval.analytic.conditional_power_approx! > 0.47, true);
  console.log("✔ Live evaluation recalculates dynamically for modified assumptions");
}

function testSingleAuthoritativeLedgerPreservesManualOrigin() {
  let state = initializeWorkspaceState("baseline-collapse-v1");
  // Edit planned control event rate
  state = workspaceReducer(state, {
    type: "UPDATE_PLANNED_FIELD",
    fieldPointer: "/planned_design/control_event_rate",
    update: { control_event_rate: 0.25 },
  });

  // Edit stress baseline
  state = workspaceReducer(state, {
    type: "UPDATE_STRESS_BASELINE",
    baseline: 0.12,
  });

  // In the single authoritative ledger, both must remain manual_user without being overwritten
  assert.strictEqual(
    state.provenanceLedger["/planned_design/control_event_rate"]?.source,
    "manual_user"
  );
  assert.strictEqual(
    state.provenanceLedger["/stress_scenario/control_event_rate"]?.source,
    "manual_user"
  );
  // Untouched field must still be synthetic_preset
  assert.strictEqual(
    state.provenanceLedger["/planned_design/alpha"]?.source,
    "synthetic_preset"
  );
  console.log("✔ Single authoritative ledger preserves manual origin across planned and stress fields");
}

async function testRolandReviewFixes() {
  const state = initializeWorkspaceState("baseline-collapse-v1");

  // 1. Changing effect kind/value triggers live evaluation, not preset mock
  const modifiedEffectEval = await evaluateScenario({
    planned_design: {
      ...state.plannedDraft,
      effect: { kind: "relative_risk", value: 0.9 },
    },
    fixed_enrollment: state.frozenEnrollment!,
    stress_scenario: {
      control_event_rate: 0.10,
      dropout: { control: 0.0, treatment: 0.0 },
      effect_override: null,
    },
    simulation: { replicates: 10000, seed: 42 },
    preset_id: state.presetId,
  });
  assert.strictEqual(modifiedEffectEval.monte_carlo, null);
  assert.notStrictEqual(modifiedEffectEval.analytic.conditional_power_approx, 0.47);
  assert.strictEqual(
    modifiedEffectEval.warnings.some((w) => w.includes("Monte Carlo simulation unavailable")),
    true
  );

  // 2. Effect override is honored in live evaluation
  const overrideEval = await evaluateScenario({
    planned_design: state.plannedDraft,
    fixed_enrollment: state.frozenEnrollment!,
    stress_scenario: {
      control_event_rate: 0.15,
      dropout: { control: 0.0, treatment: 0.0 },
      effect_override: { kind: "relative_risk", value: 0.99 },
    },
    simulation: { replicates: 10000, seed: 42 },
    preset_id: state.presetId,
  });
  // Without override, RR 0.75 at baseline 0.15 gives ~0.657 power; with RR 0.99 it should be near alpha (0.05)
  assert.notStrictEqual(overrideEval.analytic.conditional_power_approx, 0.657);
  assert.strictEqual(overrideEval.analytic.conditional_power_approx! < 0.1, true);

  // 3. Different simulation settings bypass preset fixture
  const customSimEval = await evaluateScenario({
    planned_design: state.plannedDraft,
    fixed_enrollment: state.frozenEnrollment!,
    stress_scenario: state.calculatedDesign ? {
      control_event_rate: 0.1,
      dropout: { control: 0.0, treatment: 0.0 },
      effect_override: null,
    } : {
      control_event_rate: 0.1,
      dropout: { control: 0.0, treatment: 0.0 },
      effect_override: null,
    },
    simulation: { replicates: 1234, seed: 123 },
    preset_id: state.presetId,
  });
  assert.strictEqual(customSimEval.monte_carlo, null);

  // 4. Infeasible solveMinimumN throws UNBOUNDED_OR_INFEASIBLE
  assert.throws(() => {
    // Weak effect RR 0.99999
    const { solveMinimumN } = require("../lib/statistical-engine");
    solveMinimumN(0.2, 0.2 * 0.99999, 0.8, 0.05);
  }, /UNBOUNDED_OR_INFEASIBLE/);

  // 5. Calculate does not get permanently stuck in calculating when stress edits arrive
  let stressMidCalcState = workspaceReducer(state, { type: "START_CALCULATE" });
  assert.strictEqual(stressMidCalcState.designStatus, "calculating");
  stressMidCalcState = workspaceReducer(stressMidCalcState, {
    type: "UPDATE_STRESS_BASELINE",
    baseline: 0.25,
  });
  // Outdated calculate response arrives
  stressMidCalcState = workspaceReducer(stressMidCalcState, {
    type: "CALCULATE_SUCCESS",
    response: state.calculatedDesign!,
    requestRevision: state.requestRevision,
  });
  assert.strictEqual(stressMidCalcState.designStatus, "idle");

  console.log("✔ Roland review fixes: null MC disclosure, effect matching, override, feasibility & revision verified");
}

async function runAll() {
  testPresetLoading();
  testStressAdjustmentPreservesFrozenEnrollment();
  testRecalculateLocksNewEnrollment();
  testSwitchingPresetResetsStateAndProvenance();
  testRejectOutdatedLateResponses();
  await testLiveEvaluationCalculatesDifferentAssumptions();
  testSingleAuthoritativeLedgerPreservesManualOrigin();
  await testRolandReviewFixes();
  console.log("\nALL WORKSPACE STATE INVARIANT TESTS PASSED!");
}

runAll().catch((err) => {
  console.error("Test failed:", err);
  process.exit(1);
});

