// Compile the owned TSX modules to C2_RENDER_ROOT; no new test dependency.
import assert from "node:assert/strict";
import { test } from "node:test";
import path from "node:path";
import { createRequire } from "node:module";
const loadModule = createRequire(import.meta.url);
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
const { DesignForm } = loadModule(path.join(process.env.C2_RENDER_ROOT, "components/DesignForm.js"));
const { DesignSummary } = loadModule(path.join(process.env.C2_RENDER_ROOT, "components/DesignSummary.js"));
const assumptions = {
  model_version: "binary-v1", control_event_rate: .2, effect: { kind: "relative_risk", value: .75 },
  alpha: .05, target_power: .8, allocation_ratio: 1, dropout: { control: .1, treatment: .1 },
};
const result = {
  model_version: "binary-v1", method: "cohen_h_normal_v1", p_treatment: .15,
  evaluable_n: { control: 903, treatment: 903 }, enrolled_n: { control: 1004, treatment: 1004 },
  nominal_power_evaluable: .8001, warnings: ["Example warning"], inputs_hash: "fixture-hash", mock: true,
  provenance: { label: "Synthetic fixture", scenario_kind: "synthetic", source: { type: "synthetic" },
    scenario_id: "test", follow_up_label: "12 months", generated_by: "local_fixture", method_version: "binary-v1" },
};
const form = (props = {}) => renderToStaticMarkup(React.createElement(DesignForm, {
  initialAssumptions: assumptions, presetId: "test", onCalculate: () => {}, ...props,
}));
const summary = (props = {}) => renderToStaticMarkup(React.createElement(DesignSummary, { result, ...props }));

test("form has explicit units, baseline definition, and associated native controls", () => {
  const html = form();
  for (const text of ["Control group event rate (%)", "eligible people in the control group", "decimal ratio", "0.75 means", "equally sized groups", "shared estimate applies", "Calculate design"]) assert.ok(html.includes(text));
  assert.match(html, /name="controlPercent"[^>]*value="20"/);
  assert.match(html, /name="relativeRisk"[^>]*value="0.75"/);
  assert.ok(html.includes("aria-describedby="));
  for (const label of html.matchAll(/<label\b[^>]*\bfor="([^"]+)"/g)) {
    assert.ok(html.includes(`id="${label[1]}"`));
  }
});

test("ARR form displays percentage points without reusing RR", () => {
  const html = form({ initialAssumptions: { ...assumptions, effect: { kind: "absolute_risk_reduction", value: .05 } } });
  assert.ok(html.includes("percentage points"));
  assert.match(html, /name="reductionPoints"[^>]*value="5"/);
  assert.ok(!html.includes('name="relativeRisk"'));
});

test("pending form disables controls and exposes error/status", () => {
  const html = form({ isCalculating: true, error: "Service unavailable" });
  assert.ok(html.includes("disabled="));
  assert.ok(html.includes('aria-busy="true"'));
  assert.ok(html.includes('role="status"'));
  assert.ok(html.includes("Service unavailable"));
});

test("summary separates counts and preserves method, source, and warnings", () => {
  const html = summary();
  for (const text of ["Needed with outcome data", "Planned to enroll", "903", "1004", "80.01%", "15.00%", "cohen_h_normal_v1", "binary-v1", "Synthetic fixture", "Example warning", "Illustrative mock", "cannot guarantee"]) assert.ok(html.includes(text));
  const changed = summary({ result: { ...result, evaluable_n: { control: 120, treatment: 120 }, enrolled_n: { control: 150, treatment: 150 } } });
  assert.ok(changed.includes("120") && changed.includes("150"));
  assert.ok(!changed.includes("903"));
});

test("stale, failed, pending, and empty summaries stay honest", () => {
  assert.ok(summary({ isStale: true }).includes("Stale result"));
  assert.ok(summary({ error: "Calculation failed" }).includes("Stale result"));
  assert.ok(summary({ isCalculating: true }).includes("Stale result"));
  assert.ok(summary({ result: null }).includes("No calculated design"));
  assert.ok(!summary({ result: { ...result, mock: false } }).includes("Illustrative mock"));
});

test("live API fields render without invented fixture provenance", () => {
  const { mock, provenance, ...live } = result;
  void mock; void provenance;
  const html = summary({ result: live });
  assert.ok(html.includes("903") && html.includes("1004"));
  assert.ok(html.includes("Source metadata was not supplied"));
  assert.ok(!html.includes("Illustrative mock") && !html.includes("Synthetic fixture"));
});

test("unsupported initial assumptions render an error instead of crashing", () => {
  for (const initialAssumptions of [
    { ...assumptions, dropout: { control: .1, treatment: .2 } },
    { ...assumptions, allocation_ratio: 2 },
    { ...assumptions, control_event_rate: 20 },
    { ...assumptions, effect: { kind: "relative_risk", value: 1 } },
  ]) {
    const html = form({ initialAssumptions });
    assert.ok(html.includes('role="alert"'));
    assert.ok(html.includes("Cannot initialize this planned design"));
    assert.ok(!html.includes('<form'));
  }
});
