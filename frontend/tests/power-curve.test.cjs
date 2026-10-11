/* eslint-disable @typescript-eslint/no-require-imports -- Node CJS test loads owned TSX via an in-memory compiler. */
// Run: node tests/power-curve.test.cjs
// Uses the existing React/TypeScript dependencies; no package or lockfile edits.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const ts = require("typescript");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");

// Compile owned components and read-only workspace dependencies in memory; production typecheck remains
// the normal tsc --noEmit command and this does not emulate a React renderer.
require.extensions[".tsx"] = (module, filename) => {
  const source = fs.readFileSync(filename, "utf8");
  const result = ts.transpileModule(source, {
    fileName: filename,
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
      target: ts.ScriptTarget.ES2020, esModuleInterop: true },
  });
  module._compile(result.outputText, filename);
};
require.extensions[".ts"] = require.extensions[".tsx"];
const { initializeWorkspaceState } = require("../lib/workspace-state.ts");
const { PowerCurve, curveProblem, workspaceCurveProps } = require("../components/PowerCurve.tsx");
const { DesignComparison, workspaceComparisonProps } = require("../components/DesignComparison.tsx");

function props() {
  const current = {
    inputsHash: "synthetic-curve-illustration-v1", designHash: "synthetic-plan-v1", fixedEnrollment: { control: 903, treatment: 903 },
    dropout: .25, effectKind: "relative_risk", targetPower: .75,
    plannedBaseline: .20, selectedBaseline: .10,
  };
  return { current, status: "ready", result: {
    ...structuredClone(current), method: "cohen_h_normal_v1", illustrative: true,
    powerCurve: [{ baseline: .05, power: .30 }, { baseline: .10, power: .47 },
      { baseline: .15, power: null }, { baseline: .20, power: .80 }, { baseline: .25, power: .90 }],
    plannedPoint: { baseline: .20, power: .80 }, selectedPoint: { baseline: .10, power: .47 },
  } };
}
const render = (Component, input) => renderToStaticMarkup(React.createElement(Component, input));

test("axis labels, method, target and exact supplied marker coordinates", () => {
  const html = render(PowerCurve, props());
  for (const label of ["Control baseline event risk (%)", "Conditional power (%)", "Target 75.0%",
    "cohen_h_normal_v1", "25.0%", "903 control / 903 treatment", "Illustrative synthetic fixture"]) {
    assert.ok(html.includes(label), label);
  }
  const selected = html.match(/data-marker="selected" data-baseline="0.1" data-power="0.47" cx="([^"]+)" cy="([^"]+)"/);
  assert.ok(selected);
  assert.ok(Math.abs(Number(selected[1]) - 200) < 1e-9);
  assert.ok(Math.abs(Number(selected[2]) - 146.6) < 1e-9);
  assert.match(html, /data-marker="planned" data-baseline="0.2" data-power="0.8"/);
  assert.match(html, /data-target-power="0.75"[^>]*y1="85"/);
  assert.match(html, /role="img" aria-labelledby=/);
  assert.ok(html.includes("<caption>Analytic curve at symmetric dropout 25.0%"));
  assert.ok(html.includes("0.1 fraction"));
  assert.ok(html.includes("47.0%"));
});

test("null values break the trace and remain explicit in the table", () => {
  const html = render(PowerCurve, props());
  assert.equal((html.match(/data-curve-segment=/g) || []).length, 2);
  assert.ok(html.includes("Invalid scenario (null)"));
  const input = props();
  input.current.selectedBaseline = .15;
  input.result.selectedBaseline = .15;
  input.result.selectedPoint = { baseline: .15, power: null };
  const selected = render(PowerCurve, input);
  assert.ok(!selected.includes('data-marker="selected"'));
  const comparison = render(DesignComparison, { ...input, plannedPower: .80, plannedDropout: 0, plannedDesignHash: "synthetic-plan-v1" });
  assert.ok(comparison.includes("Power change is unavailable"));
  assert.ok(!comparison.includes("-80.0 percentage points"));
});

test("changing any design identity field suppresses stale results in both components", () => {
  for (const change of [{ inputsHash: "new" }, { dropout: .20 }, { targetPower: .80 },
    { effectKind: "absolute_risk_reduction" }, { selectedBaseline: .15 },
    { plannedBaseline: .19 }, { fixedEnrollment: { control: 1004, treatment: 1004 } }]) {
    const input = props();
    Object.assign(input.current, change);
    assert.match(curveProblem(input.current, input.result), /Stale/);
    const html = render(PowerCurve, input);
    assert.ok(html.includes("Stale analytic curve"));
    assert.ok(!html.includes("<svg"));
    const comparison = render(DesignComparison, { ...input, plannedPower: .80, plannedDropout: 0, plannedDesignHash: "synthetic-plan-v1" });
    assert.ok(comparison.includes("Stale analytic curve"));
    assert.ok(!comparison.includes("percentage points"));
  }
});

test("loading, errors and idle states expose no prior numeric chart", () => {
  for (const status of ["loading", "error", "idle"]) {
    const input = { ...props(), status, error: "API unavailable" };
    const html = render(PowerCurve, input);
    assert.ok(!html.includes("<svg"));
    if (status === "loading") assert.match(html, /aria-busy="true"/);
    if (status === "error") assert.ok(html.includes('role="alert">API unavailable'));
    const comparison = render(DesignComparison, { ...input, plannedPower: .80, plannedDropout: 0, plannedDesignHash: "synthetic-plan-v1" });
    assert.ok(!comparison.includes("<table"));
  }
});

test("comparison shows supplied planned power and selected power with percentage-point change", () => {
  const html = render(DesignComparison, { ...props(), plannedPower: .80, plannedDropout: 0, plannedDesignHash: "synthetic-plan-v1" });
  assert.ok(html.includes("-33.0 percentage points"));
  assert.ok(html.includes("Original planned design"));
  assert.ok(html.includes("Selected stress scenario"));
  assert.ok(html.includes("80.0%"));
  assert.ok(html.includes("47.0%"));
  assert.equal((html.match(/903 \/ 903/g) || []).length, 2);
  assert.ok(html.includes("planned baseline evaluated at the selected dropout"));
});

test("comparison refuses planned power from another calculated design", () => {
  const html = render(DesignComparison, { ...props(), plannedPower: .80, plannedDropout: 0,
    plannedDesignHash: "previous-plan" });
  assert.ok(html.includes("Stale planned design"));
  assert.ok(!html.includes("percentage points"));
});

test("RR/ARR labels and target follow supplied context without power calculations", () => {
  const input = props();
  input.current.effectKind = input.result.effectKind = "absolute_risk_reduction";
  input.current.targetPower = input.result.targetPower = .90;
  const html = render(PowerCurve, input);
  assert.ok(html.includes("Effect: ARR"));
  assert.ok(html.includes("Target 90.0%"));
  assert.ok(html.includes("47.0%"));
});

test("selection uses native accessible buttons and invalid values cannot be selected", () => {
  const input = { ...props(), onSelectBaseline: () => {} };
  const html = render(PowerCurve, input);
  assert.equal((html.match(/<button/g) || []).length, 5);
  assert.match(html, /<button type="button" disabled="">Select baseline 15.0%<\/button>/);
  assert.match(html, /<button type="button">Select baseline 10.0%<\/button>/);
});

test("malformed probabilities, ordering, markers and allocation cannot become chart data", () => {
  const mutations = [
    (p) => { p.result.powerCurve[1].power = NaN; },
    (p) => { p.result.powerCurve[1].power = 1.1; },
    (p) => { p.result.powerCurve[1].baseline = .05; },
    (p) => { p.result.selectedPoint.power = .70; },
    (p) => { p.result.selectedPoint.baseline = .15; },
    (p) => { p.result.powerCurve = []; },
    (p) => { p.result.dropout = p.current.dropout = 1; },
    (p) => { p.result.fixedEnrollment.treatment = p.current.fixedEnrollment.treatment = 902; },
  ];
  for (const mutate of mutations) {
    const input = props();
    mutate(input);
    assert.ok(curveProblem(input.current, input.result));
    assert.ok(!render(PowerCurve, input).includes("<svg"));
  }
});

test("components contain no CSS or network/statistical calculation path", () => {
  for (const name of ["PowerCurve.tsx", "DesignComparison.tsx"]) {
    const source = fs.readFileSync(path.join(__dirname, "../components", name), "utf8");
    assert.doesNotMatch(source, /className=|style=|fetch\(|axios|monte_carlo|Math\.asin/);
  }
});


function handoff() {
  const state = initializeWorkspaceState('baseline-collapse-v1');
  state.calculatedDesign = { inputs_hash: 'calculated-plan', enrolled_n: {control:903,treatment:903} };
  state.frozenEnrollment = {control:903,treatment:903};
  state.designStatus = 'success'; state.gridStatus = 'success';
  state.stressBaseline = .1; state.stressDropout = .13;
  const response = { method:'cohen_h_normal_v1',inputs_hash:'measured-grid',
    fixed_enrollment:{control:903,treatment:903},target_power:.8,
    power_curve:[{p_control:.1,power:.4,is_valid:true},{p_control:.2,power:.7,is_valid:true}],
    planned_point:{p_control:.2,dropout:0,power:.8},
    selected_point:{p_control:.1,dropout:.13,power:.4} };
  return {state, completed:{requestState:structuredClone(state), response}};
}

test('merged workspace handoff preserves original-plan and exact-dropout API values',()=>{
  const {state,completed}=handoff();
  const input=workspaceCurveProps(state,completed);
  assert.equal(curveProblem(input.current,input.result),null);
  const html=render(PowerCurve,input);
  assert.match(html,/data-marker="planned" data-baseline="0.2" data-power="0.8"/);
  assert.match(html,/original planned scenario at 0.0% dropout/);
  assert.match(html,/measured-grid/);
  const comparison=render(DesignComparison,workspaceComparisonProps(state,completed));
  assert.match(comparison,/-40.0 percentage points/);
  assert.deepEqual(input.result.powerCurve,[{baseline:.1,power:.4},{baseline:.2,power:.7}]);
});

test('workspace revisions, effect values, alpha and provenance invalidate late curves',()=>{
  for(const mutate of [s=>s.requestRevision++,s=>s.plannedDraft.effect.value=.5,
    s=>s.plannedDraft.alpha=.01,s=>s.stressDropout=.2,s=>s.stressBaseline=.12,
    s=>s.provenanceLedger.changed={source:'manual_user'},s=>s.designStatus='idle']){
    const {state,completed}=handoff();mutate(state);
    assert.ok(!render(PowerCurve,workspaceCurveProps(state,completed)).includes('<svg'));
    assert.ok(!render(DesignComparison,workspaceComparisonProps(state,completed)).includes('<table'));
  }
});

test('workspace loading/errors and coordinate-only or mismatched API responses fail explicitly',()=>{
  for(const status of ['loading','error']){
    const {state,completed}=handoff();state.gridStatus=status;state.gridError='Unavailable API';
    const result=workspaceCurveProps(state,completed);assert.equal(result.status,status);
    assert.ok(!render(PowerCurve,result).includes('<svg'));
  }
  for(const mutate of [r=>delete r.power_curve,r=>delete r.selected_point.power,
    r=>r.selected_point.dropout=.2,r=>r.fixed_enrollment.control=904,
    r=>r.target_power=.9,r=>r.power_curve[0].is_valid=false]){
    const {state,completed}=handoff();mutate(completed.response);
    assert.equal(workspaceCurveProps(state,completed).status,'error');
  }
});

test('original planned null power remains unavailable in comparison',()=>{
  const {state,completed}=handoff();completed.response.planned_point.power=null;
  const html=render(DesignComparison,workspaceComparisonProps(state,completed));
  assert.match(html,/Unavailable \(null\)/);assert.match(html,/Power change is unavailable/);
  assert.ok(!html.includes('percentage points'));
});

// Required when explicitly requested: errors fail this test, with no fixture
// substitution. Normal offline component tests do not claim live acceptance.
if(process.env.BETTERBASELINE_CURVE_API){
  test('actual calculate/grid HTTP data render through merged workspace handoff',async()=>{
    const base=process.env.BETTERBASELINE_CURVE_API;
    const post=async(route,body)=>{const r=await fetch(base+route,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const text=await r.text();assert.equal(r.status,200,text);return JSON.parse(text);};
    const {state}=handoff();
    state.stressBaseline=.12;
    state.calculatedDesign=await post('/api/v1/design/calculate',state.plannedDraft);
    state.frozenEnrollment=state.calculatedDesign.enrolled_n;
    const requestState=structuredClone(state);
    const response=await post('/api/v1/scenarios/grid',{planned_design:state.plannedDraft,
      fixed_enrollment:state.frozenEnrollment,x_baseline:{min:.1,max:.3,steps:3},
      y_dropout:{min:0,max:.2,steps:2},selected_scenario:{control_event_rate:state.stressBaseline,
        dropout:{control:.13,treatment:.13},effect_override:null}});
    const completed={requestState,response};
    const adapted=workspaceCurveProps(state,completed);
    assert.equal(curveProblem(adapted.current,adapted.result),null);
    assert.equal(adapted.result.selectedPoint.power,response.selected_point.power);
    assert.equal(adapted.result.plannedPoint.power,response.planned_point.power);
    assert.match(render(PowerCurve,adapted),/Calculated from the supplied API response/);
    assert.match(render(DesignComparison,workspaceComparisonProps(state,completed)),/Current comparison/);
    console.log(JSON.stringify({scope:'live_curve_handoff',gridHash:response.inputs_hash,
      selectedDropout:response.selected_point.dropout,plannedPower:response.planned_point.power,
      selectedPower:response.selected_point.power,curve:response.power_curve}));
  });
}
