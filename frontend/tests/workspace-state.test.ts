import assert from "node:assert";
import {
  initializeWorkspaceState,
  markFieldManual,
  workspaceReducer,
} from "../lib/workspace-state";
import {
  evaluateScenario,
  calculateDesign,
} from "../lib/api";
import { solveMinimumN } from "../lib/statistical-engine";
import type { CalculateResponse } from "../lib/contracts";
import { planningValuesToRequest, validatePlanningDraft } from "../lib/validation";
import { plannedFieldUpdateAction } from "../lib/workspace-planning";

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

  const requestRevision = state.requestRevision;
  state = workspaceReducer(state, { type: "START_CALCULATE", requestRevision });
  state = workspaceReducer(state, {
    type: "CALCULATE_SUCCESS",
    response: mockNewDesign,
    requestRevision,
  });

  assert.strictEqual(state.frozenEnrollment?.control, 560);
  assert.strictEqual(state.frozenEnrollment?.treatment, 560);
  assert.strictEqual(state.designStatus, "success");
  assert.strictEqual(state.displayedInputsHash, "sha256:new-test-hash");
  console.log("✔ Recalculate locks new enrollment test passed");
}

async function testPlanningFormEditsUpdateDraftAndLockOnCalculate() {
  let state = initializeWorkspaceState("baseline-collapse-v1");
  const originalEnrollment = state.frozenEnrollment;
  const draft = {
    controlPercent: "25", effectKind: "absolute_risk_reduction" as const,
    relativeRisk: "0.75", reductionPoints: "4", targetPercent: "90",
    alphaPercent: "2.5", dropoutPercent: "15",
  };
  const invalidState = workspaceReducer(state, plannedFieldUpdateAction(
    { ...draft, controlPercent: "not a number" }, "controlPercent", state.presetId
  ));
  assert.equal(invalidState.plannedDraft.control_event_rate, state.plannedDraft.control_event_rate,
    "invalid form text does not enter the numeric workspace draft");
  assert.equal(invalidState.provenanceLedger["/planned_design/control_event_rate"]?.source, "manual_user");
  assert.equal(invalidState.displayedInputsHash, null, "invalid edits still mark displayed results stale");

  const validation = validatePlanningDraft(draft);
  assert.equal(validation.valid, true, "valid form entries pass the same validation used on submit");
  if (!validation.valid) throw new Error("Expected valid planning draft");
  const plannedRequest = planningValuesToRequest(validation.values, state.presetId);

  for (const field of ["controlPercent", "effectKind", "targetPercent", "alphaPercent", "dropoutPercent"] as const) {
    state = workspaceReducer(state, plannedFieldUpdateAction(draft, field, state.presetId));
  }

  assert.deepEqual(state.plannedDraft, {
    model_version: plannedRequest.model_version,
    allocation_ratio: plannedRequest.allocation_ratio,
    control_event_rate: 0.25,
    effect: { kind: "absolute_risk_reduction", value: 0.04 },
    alpha: 0.025,
    target_power: 0.9,
    dropout: { control: 0.15, treatment: 0.15 },
  });
  assert.equal(state.evaluateStatus, "stale");
  assert.equal(state.gridStatus, "stale");
  for (const pointer of [
    "/planned_design/control_event_rate", "/planned_design/effect/kind", "/planned_design/effect/value",
    "/planned_design/target_power", "/planned_design/alpha",
    "/planned_design/dropout/control", "/planned_design/dropout/treatment",
  ]) assert.equal(state.provenanceLedger[pointer]?.source, "manual_user", `${pointer} is recorded as a manual edit`);
  assert.deepEqual(state.frozenEnrollment, originalEnrollment, "editing assumptions does not silently change locked enrollment");

  const calculated = await calculateDesign({ ...plannedRequest, provenance_ledger: state.provenanceLedger });
  const calculationRevision = state.requestRevision + 1;
  state = workspaceReducer(state, { type: "START_CALCULATE", requestRevision: calculationRevision });
  state = workspaceReducer(state, { type: "CALCULATE_SUCCESS", response: calculated, requestRevision: calculationRevision });
  assert.equal(state.designStatus, "success");
  assert.deepEqual(state.frozenEnrollment, calculated.enrolled_n, "explicit Calculate locks the newly computed enrollment");
  assert.notDeepEqual(state.frozenEnrollment, originalEnrollment, "changed planning entries produce a new enrollment lock");
}

function testRecalculationInvalidatesPendingEvaluationAndGrid() {
  let state = initializeWorkspaceState("baseline-collapse-v1");
  const oldRevision = state.requestRevision;
  state = workspaceReducer(state, { type: "START_EVALUATE" });
  state = workspaceReducer(state, { type: "START_GRID" });
  assert.equal(state.evaluateStatus, "evaluating");
  assert.equal(state.gridStatus, "loading");

  const calculationRevision = oldRevision + 1;
  state = workspaceReducer(state, { type: "START_CALCULATE", requestRevision: calculationRevision });
  assert.equal(state.evaluateStatus, "stale", "aborted evaluation is retryable after recalculation starts");
  assert.equal(state.gridStatus, "stale", "aborted grid is retryable after recalculation starts");
  state = workspaceReducer(state, {
    type: "CALCULATE_ERROR", error: "calculation failed", requestRevision: calculationRevision,
  });
  assert.equal(state.designStatus, "error");
  assert.equal(state.evaluateStatus, "stale", "failed recalculation leaves evaluation retryable");
  assert.equal(state.gridStatus, "stale", "failed recalculation leaves grid retryable");

  state = workspaceReducer(state, { type: "START_EVALUATE" });
  state = workspaceReducer(state, { type: "START_GRID" });
  assert.equal(state.evaluateStatus, "evaluating", "evaluation can retry after calculation failure");
  assert.equal(state.gridStatus, "loading", "grid can retry after calculation failure");

  const afterStart = state;
  const oldEvaluation = initializeWorkspaceState().evaluateResult!;
  const oldGrid = initializeWorkspaceState().gridResult!;
  state = workspaceReducer(state, { type: "EVALUATE_SUCCESS", response: oldEvaluation, requestRevision: oldRevision });
  state = workspaceReducer(state, { type: "GRID_SUCCESS", response: oldGrid, requestRevision: oldRevision });
  state = workspaceReducer(state, { type: "EVALUATE_ERROR", error: "late eval", requestRevision: oldRevision });
  state = workspaceReducer(state, { type: "GRID_ERROR", error: "late grid", requestRevision: oldRevision });
  assert.equal(state, afterStart, "late same-input evaluation/grid completions cannot overwrite the recalculation state");

  let successful = initializeWorkspaceState("baseline-collapse-v1");
  successful = workspaceReducer(successful, { type: "START_EVALUATE" });
  successful = workspaceReducer(successful, { type: "START_GRID" });
  const successfulRevision = successful.requestRevision + 1;
  successful = workspaceReducer(successful, { type: "START_CALCULATE", requestRevision: successfulRevision });
  // A direct/stale callback cannot start new work against the old enrollment
  // while the calculation is pending.
  const calculatingState = successful;
  successful = workspaceReducer(successful, { type: "START_EVALUATE" });
  successful = workspaceReducer(successful, { type: "START_GRID" });
  assert.equal(successful, calculatingState, "evaluation and grid starts are ignored during calculation");
  const pendingRevision = successful.requestRevision;
  successful = workspaceReducer(successful, {
    type: "CALCULATE_SUCCESS", response: initializeWorkspaceState().calculatedDesign!,
    requestRevision: successfulRevision,
  });
  const lockedDesignState = successful;
  successful = workspaceReducer(successful, {
    type: "EVALUATE_SUCCESS", response: oldEvaluation, requestRevision: pendingRevision,
  });
  successful = workspaceReducer(successful, {
    type: "GRID_SUCCESS", response: oldGrid, requestRevision: pendingRevision,
  });
  assert.equal(successful, lockedDesignState, "pending calculation results cannot replace results after the new design locks");

  successful = workspaceReducer(successful, { type: "START_EVALUATE" });
  successful = workspaceReducer(successful, { type: "START_GRID" });
  assert.equal(successful.evaluateStatus, "evaluating", "evaluation can retry after calculation success");
  assert.equal(successful.gridStatus, "loading", "grid can retry after calculation success");
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
  state = workspaceReducer(state, {
    type: "START_CALCULATE",
    requestRevision: state.requestRevision,
  });

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
    stress_scenario: {
      control_event_rate: 0.1,
      dropout: { control: 0.0, treatment: 0.0 },
      effect_override: null,
    },
    simulation: { replicates: 1234, seed: 123 },
    preset_id: state.presetId,
  });
  assert.strictEqual(customSimEval.monte_carlo, null);

  const customReplicatesEval = await evaluateScenario({
    planned_design: state.plannedDraft,
    fixed_enrollment: state.frozenEnrollment!,
    stress_scenario: {
      control_event_rate: 0.1,
      dropout: { control: 0.0, treatment: 0.0 },
      effect_override: null,
    },
    simulation: { replicates: 1234, seed: 42 },
    preset_id: state.presetId,
  });
  assert.strictEqual(customReplicatesEval.monte_carlo, null);

  const customSeedEval = await evaluateScenario({
    planned_design: state.plannedDraft,
    fixed_enrollment: state.frozenEnrollment!,
    stress_scenario: {
      control_event_rate: 0.1,
      dropout: { control: 0.0, treatment: 0.0 },
      effect_override: null,
    },
    simulation: { replicates: 10000, seed: 123 },
    preset_id: state.presetId,
  });
  assert.strictEqual(customSeedEval.monte_carlo, null);

  // 4. Infeasible solveMinimumN throws UNBOUNDED_OR_INFEASIBLE
  assert.throws(() => {
    // Weak effect RR 0.99999
    solveMinimumN(0.2, 0.2 * 0.99999, 0.8, 0.05);
  }, /UNBOUNDED_OR_INFEASIBLE/);
  assert.throws(() => solveMinimumN(0.2, 0.2, 0.8, 0.05), /UNBOUNDED_OR_INFEASIBLE/);

  // 5. Calculate does not get permanently stuck in calculating when stress edits arrive
  let stressMidCalcState = workspaceReducer(state, {
    type: "START_CALCULATE",
    requestRevision: state.requestRevision,
  });
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

async function testFieldProvenanceRoundTripsThroughLiveAndFixtureResults() {
  const state = initializeWorkspaceState("baseline-collapse-v1");
  const ledger = markFieldManual(
    state.provenanceLedger,
    "/planned_design/control_event_rate"
  );

  const fixtureCalculate = await calculateDesign({
    ...state.plannedDraft,
    preset_id: state.presetId,
    provenance_ledger: ledger,
  });
  assert.deepStrictEqual(fixtureCalculate.provenance.field_provenance, ledger);

  const liveCalculate = await calculateDesign({
    ...state.plannedDraft,
    control_event_rate: 0.21,
    preset_id: state.presetId,
    provenance_ledger: ledger,
  });
  assert.deepStrictEqual(liveCalculate.provenance.field_provenance, ledger);

  const fixtureEvaluate = await evaluateScenario({
    planned_design: state.plannedDraft,
    fixed_enrollment: state.frozenEnrollment!,
    stress_scenario: {
      control_event_rate: state.stressBaseline,
      dropout: { control: state.stressDropout, treatment: state.stressDropout },
      effect_override: null,
    },
    simulation: { replicates: 10000, seed: 42 },
    preset_id: state.presetId,
    provenance_ledger: ledger,
  });
  assert.deepStrictEqual(fixtureEvaluate.provenance.field_provenance, ledger);

  const liveEvaluate = await evaluateScenario({
    planned_design: state.plannedDraft,
    fixed_enrollment: state.frozenEnrollment!,
    stress_scenario: {
      control_event_rate: 0.15,
      dropout: { control: 0.0, treatment: 0.0 },
      effect_override: null,
    },
    simulation: { replicates: 10000, seed: 42 },
    preset_id: state.presetId,
    provenance_ledger: ledger,
  });
  assert.deepStrictEqual(liveEvaluate.provenance.field_provenance, ledger);
  console.log("✔ Field provenance round-trips through live and preset fixture results");
}

function testCalculateInvalidationDoesNotClearNewerRequest() {
  let state = initializeWorkspaceState("baseline-collapse-v1");
  const oldRevision = state.requestRevision;
  state = workspaceReducer(state, {
    type: "START_CALCULATE",
    requestRevision: oldRevision,
  });
  assert.strictEqual(state.designStatus, "calculating");

  state = workspaceReducer(state, {
    type: "UPDATE_STRESS_BASELINE",
    baseline: 0.25,
  });
  assert.strictEqual(state.designStatus, "idle");
  assert.strictEqual(state.activeCalculateRevision, null);

  const currentRevision = state.requestRevision;
  state = workspaceReducer(state, {
    type: "START_CALCULATE",
    requestRevision: currentRevision,
  });
  const newerActiveState = state;
  state = workspaceReducer(state, {
    type: "CALCULATE_SUCCESS",
    response: initializeWorkspaceState().calculatedDesign!,
    requestRevision: oldRevision,
  });
  assert.strictEqual(state, newerActiveState);
  assert.strictEqual(state.designStatus, "calculating");
  assert.strictEqual(state.activeCalculateRevision, currentRevision);
  console.log("✔ Stress edits clear pending calculation and old completions preserve newer requests");
}

function testSupersededEvaluationRevisionIsRejected() {
  let state = initializeWorkspaceState("baseline-collapse-v1");
  state = workspaceReducer(state, { type: "START_EVALUATE" });
  const firstRevision = state.requestRevision;
  state = workspaceReducer(state, { type: "START_EVALUATE" });
  const newerRequestState = state;
  assert.ok(state.requestRevision > firstRevision, "each evaluation receives a distinct revision");
  state = workspaceReducer(state, {
    type: "EVALUATE_SUCCESS",
    response: initializeWorkspaceState("baseline-collapse-v1").evaluateResult!,
    requestRevision: firstRevision,
  });
  assert.strictEqual(state, newerRequestState, "late result cannot replace a newer evaluation for the same inputs");
  console.log("✔ Superseded same-input evaluation response is rejected by revision guard");
}

async function runAll() {
  testPresetLoading();
  testStressAdjustmentPreservesFrozenEnrollment();
  testRecalculateLocksNewEnrollment();
  await testPlanningFormEditsUpdateDraftAndLockOnCalculate();
  testRecalculationInvalidatesPendingEvaluationAndGrid();
  testSwitchingPresetResetsStateAndProvenance();
  testRejectOutdatedLateResponses();
  await testLiveEvaluationCalculatesDifferentAssumptions();
  testSingleAuthoritativeLedgerPreservesManualOrigin();
  await testRolandReviewFixes();
  await testFieldProvenanceRoundTripsThroughLiveAndFixtureResults();
  testCalculateInvalidationDoesNotClearNewerRequest();
  testSupersededEvaluationRevisionIsRejected();
  console.log("\nALL WORKSPACE STATE INVARIANT TESTS PASSED!");
}

runAll().catch((err) => {
  console.error("Test failed:", err);
  process.exit(1);
});

