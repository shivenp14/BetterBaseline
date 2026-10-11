import assert from "node:assert/strict";
import { scheduleDebounced } from "../lib/debounce";
import { buildStressEvaluationRequest, initializeWorkspaceState, workspaceReducer } from "../lib/workspace-state";

async function main() {
  const baseline = initializeWorkspaceState("baseline-collapse-v1");
  const calculationRevision = baseline.requestRevision + 1;
  let state = workspaceReducer(baseline, {
    type: "START_CALCULATE", requestRevision: calculationRevision,
    expectedInputGeneration: baseline.inputGeneration,
  });
  state = workspaceReducer(state, {
    type: "CALCULATE_SUCCESS",
    response: baseline.calculatedDesign!,
    requestRevision: calculationRevision,
  });
  const fixedEnrollment = { ...state.frozenEnrollment! };

  const priorWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      setTimeout: (callback: () => void, delay: number) => globalThis.setTimeout(callback, delay) as unknown as number,
      clearTimeout: (timer: number) => globalThis.clearTimeout(timer),
    },
  });
  try {
    let requested: ReturnType<typeof buildStressEvaluationRequest> | undefined;
    state = workspaceReducer(state, { type: "UPDATE_STRESS_BASELINE", baseline: 0.15 });
    assert.deepEqual(state.frozenEnrollment, fixedEnrollment, "stress edits preserve calculated fixed N");
    const cancelFirst = scheduleDebounced(() => { requested = buildStressEvaluationRequest(state); }, 20);
    state = workspaceReducer(state, { type: "UPDATE_STRESS_DROPOUT", dropout: 0.25 });
    assert.deepEqual(state.frozenEnrollment, fixedEnrollment, "dropout stress also preserves fixed N");
    cancelFirst();
    scheduleDebounced(() => { requested = buildStressEvaluationRequest(state); }, 20);
    await new Promise((resolve) => globalThis.setTimeout(resolve, 40));
    assert.ok(requested, "debounced stress change produces an evaluation request");
    assert.deepEqual(requested.fixed_enrollment, fixedEnrollment);
    assert.equal(requested.stress_scenario.control_event_rate, 0.15);
    assert.equal(requested.stress_scenario.dropout.control, 0.25);
    assert.equal(requested.provenance_ledger?.["/stress_scenario/control_event_rate"].source, "manual_user");
    console.log("Stress debounce regression checks passed (calculate → stress → fixed N → latest debounced request).");
  } finally {
    if (priorWindow) Object.defineProperty(globalThis, "window", priorWindow);
    else delete (globalThis as { window?: unknown }).window;
  }
}

void main();
