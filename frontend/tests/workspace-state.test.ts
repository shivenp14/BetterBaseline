import assert from "node:assert";
import {
  initializeWorkspaceState,
  workspaceReducer,
} from "../lib/workspace-state";
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
    state.stressProvenance["/stress_scenario/control_event_rate"]?.source,
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
    state.stressProvenance["/stress_scenario/dropout/control"]?.source,
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
    state.plannedProvenance["/planned_design/control_event_rate"]?.source,
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
    state.stressProvenance["/stress_scenario/control_event_rate"]?.source,
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
    state.stressProvenance["/stress_scenario/control_event_rate"]?.source,
    "synthetic_preset"
  );
  console.log("✔ Switching preset resets state and provenance test passed");
}

try {
  testPresetLoading();
  testStressAdjustmentPreservesFrozenEnrollment();
  testRecalculateLocksNewEnrollment();
  testSwitchingPresetResetsStateAndProvenance();
  console.log("\nALL WORKSPACE STATE INVARIANT TESTS PASSED!");
} catch (err) {
  console.error("Test failed:", err);
  process.exit(1);
}
