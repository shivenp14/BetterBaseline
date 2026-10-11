// Standalone tests until C1 supplies the frontend test runner and contracts.
// Compile validation.ts to a temporary directory, then pass its .js path as
// C2_VALIDATION_MODULE when running this file with node --test.
import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
const loadModule = createRequire(import.meta.url);
const { validatePlanningDraft, planningValuesToDraft, planningValuesToRequest, assumptionsToDraft } = loadModule(process.env.C2_VALIDATION_MODULE);

const fixture = {
  controlPercent: "20", effectKind: "relative_risk", relativeRisk: ".75",
  reductionPoints: "5", targetPercent: "80", alphaPercent: "5", dropoutPercent: "10",
};

test("explicit percent fields become fractions and RR stays a ratio", () => {
  const result = validatePlanningDraft(fixture);
  assert.equal(result.valid, true);
  assert.deepEqual(result.values, {
    controlRisk: .2, effect: { kind: "relative_risk", value: .75 },
    targetPower: .8, alpha: .05, dropout: .1,
  });
});

test("ARR uses percentage points and rejects impossible reductions", () => {
  const draft = { ...fixture, effectKind: "absolute_risk_reduction" };
  assert.equal(validatePlanningDraft(draft).values.effect.value, .05);
  for (const controlPercent of ["4", "5"]) {
    const result = validatePlanningDraft({ ...draft, controlPercent });
    assert.equal(result.valid, false);
    assert.ok(result.errors.reductionPoints);
    assert.equal(result.values, undefined);
  }
});

test("no unit inference or percentage-style RR", () => {
  assert.equal(validatePlanningDraft({ ...fixture, controlPercent: ".20" }).values.controlRisk, .002);
  assert.equal(validatePlanningDraft({ ...fixture, relativeRisk: "75" }).valid, false);
});

for (const field of ["controlPercent", "targetPercent", "alphaPercent", "dropoutPercent", "relativeRisk"]) {
  for (const value of ["", " ", "NaN", "Infinity", "20%", "20abc", "0x10", "1e999"]) {
    test(`${field} rejects ${JSON.stringify(value)}`, () => {
      const result = validatePlanningDraft({ ...fixture, [field]: value });
      assert.equal(result.valid, false);
      assert.ok(result.errors[field]);
    });
  }
}

for (const [field, values] of Object.entries({
  controlPercent: ["0", "100", "-1"], targetPercent: ["0", "100", "-1"],
  alphaPercent: ["0", "100", "-1"], dropoutPercent: ["100", "-1"], relativeRisk: ["0", "1", "-1"],
})) {
  for (const value of values) {
    test(`${field} rejects boundary ${value}`, () => {
      assert.equal(validatePlanningDraft({ ...fixture, [field]: value }).valid, false);
    });
  }
}

test("zero dropout is allowed; target must exceed alpha", () => {
  assert.equal(validatePlanningDraft({ ...fixture, dropoutPercent: "0" }).valid, true);
  for (const targetPercent of ["4", "5"]) {
    assert.ok(validatePlanningDraft({ ...fixture, targetPercent }).errors.targetPercent);
  }
});

test("unknown effect kind is invalid", () => {
  assert.ok(validatePlanningDraft({ ...fixture, effectKind: "odds_ratio" }).errors.effectKind);
});

test("inactive effect drafts are ignored rather than reinterpreted", () => {
  assert.equal(validatePlanningDraft({ ...fixture, reductionPoints: "junk" }).valid, true);
  assert.equal(validatePlanningDraft({ ...fixture, effectKind: "absolute_risk_reduction", relativeRisk: "junk" }).valid, true);
});

test("fraction drafts round-trip without display rounding", () => {
  for (const effect of [{ kind: "relative_risk", value: .7534567 }, { kind: "absolute_risk_reduction", value: .0234567 }]) {
    const original = { controlRisk: .23456789, effect, targetPower: .81234567, alpha: .0434567, dropout: .1234567 };
    const draft = planningValuesToDraft(original);
    const result = validatePlanningDraft(draft);
    assert.equal(result.valid, true);
    for (const field of ["controlRisk", "targetPower", "alpha", "dropout"]) {
      assert.ok(Math.abs(original[field] - result.values[field]) < 1e-14);
    }
    assert.ok(Math.abs(effect.value - result.values.effect.value) < 1e-14);
    assert.equal(effect.kind === "relative_risk" ? draft.reductionPoints : draft.relativeRisk, "");
  }
});

test("invalid initial assumptions are rejected", () => {
  assert.throws(() => planningValuesToDraft({ controlRisk: 20, effect: { kind: "relative_risk", value: .75 }, targetPower: .8, alpha: .05, dropout: 0 }), RangeError);
});

test("C1 request preserves explicit fractional values and symmetric scope", () => {
  const result = validatePlanningDraft(fixture);
  const request = planningValuesToRequest(result.values, "synthetic-test");
  assert.deepEqual(request, {
    model_version: "binary-v1", allocation_ratio: 1, preset_id: "synthetic-test",
    control_event_rate: .2, effect: { kind: "relative_risk", value: .75 },
    target_power: .8, alpha: .05, dropout: { control: .1, treatment: .1 },
  });
  assert.equal(assumptionsToDraft(request).controlPercent, "20");
  assert.throws(() => assumptionsToDraft({ ...request, dropout: { control: .1, treatment: .2 } }), RangeError);
  assert.throws(() => assumptionsToDraft({ ...request, allocation_ratio: 2 }), RangeError);
});
