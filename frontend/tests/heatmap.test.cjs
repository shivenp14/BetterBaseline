/* eslint-disable @typescript-eslint/no-require-imports -- Node CJS test loads owned TSX via an in-memory compiler. */
// Run: node tests/heatmap.test.cjs
// Uses the existing React/TypeScript dependencies; no package or lockfile edits.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const ts = require("typescript");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");

// Compile only these owned TSX modules in memory; production typecheck remains
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
const { StressHeatmap, heatmapProblem, frontierEdgeAllowed, selectGridCell, workspaceHeatmapProps } = require("../components/StressHeatmap.tsx");
const { GridDataTable, gridCsv } = require("../components/GridDataTable.tsx");
function props() {
 const current = { inputsHash: "fixture", designHash: "design", fixedEnrollment: {control:100,treatment:100}, effectKind:"absolute_risk_reduction", effectValue:.1,targetPower:.8,selectedPoint:{baseline:.2,dropout:.4} };
 return {current,status:"ready",result:{...structuredClone(current),method:"cohen_h_normal_v1",gridLabel:"expected_count_approximation",xBaseline:[.05,.2,.4],yDropout:[0,.4],power:[[null,0,.9],[null,.5,.8]],invalidMask:[[true,false,false],[true,false,false]],frontierSegments:[[{baseline:.2,dropout:0},{baseline:.3,dropout:.1}],[{baseline:.35,dropout:.3},{baseline:.4,dropout:.4}]],illustrative:true,warnings:["Fixture only"]}};
}
const render = p => renderToStaticMarkup(React.createElement(StressHeatmap,p));
test("2×3 orientation, nonuniform spacing and selected coordinates",()=>{
 const html=render(props()); assert.equal((html.match(/data-cell=/g)||[]).length,6);
 assert.match(html,/data-cell="1-1" data-baseline="0.2" data-dropout="0.4" data-power="0.5"/);
 assert.match(html,/data-cell="0-2" data-baseline="0.4" data-dropout="0" data-power="0.9"/);
 assert.match(html,/data-marker="selected" data-baseline="0.2" data-dropout="0.4" cx="299.28571428571433" cy="35"/);
 for(const label of ["Control baseline event risk (%)","Symmetric dropout (%)","floor-based expected retained counts","sampled actual retained counts","Illustrative synthetic fixture","Fixture only"]) assert.ok(html.includes(label));
});
test("invalid gray cross differs from power zero; accessible table and CSV preserve null",()=>{
 const p=props(),html=render(p); assert.equal((html.match(/data-invalid="true"/g)||[]).length,2);
 assert.match(html,/data-power="null"[^]*?fill="#bdbdbd"/);
 assert.match(html,/data-power="0"[^]*?fill="#2166ac" fill-opacity="0.12"/);
 assert.ok(html.includes("0.0% (0 fraction)")); assert.match(html,/scope="row"/);assert.match(html,/scope="col"/);
 const csv=gridCsv(p.result); assert.ok(csv.includes('0.05,0,null,true,false,0.8,"fixture","design"'));
 assert.ok(csv.includes('0.2,0,0,false,false,0.8'));assert.ok(csv.includes('0.2,0.4,0.5,false,true,0.8'));
 assert.equal(decodeURIComponent(html.match(/href="data:text\/csv;charset=utf-8,([^"]+)"/)[1]),csv);
});
test("native buttons emit exact baseline/dropout pairs and invalid handlers cannot emit",()=>{
 const p=props(),calls=[],buttons=[];
 const element=GridDataTable({result:p.result,onSelectPoint:point=>calls.push(point)});
 function walk(n){if(Array.isArray(n))return n.forEach(walk);if(!n||typeof n!=="object")return;if(n.type==="button")buttons.push(n);walk(n.props?.children);}walk(element);
 assert.equal(buttons.length,6);buttons.forEach(b=>b.props.onClick());assert.equal(buttons.filter(b=>b.props.disabled).length,2);
 assert.deepEqual(calls,[{baseline:.2,dropout:0},{baseline:.4,dropout:0},{baseline:.2,dropout:.4},{baseline:.4,dropout:.4}]);
 for(const [r,c] of [[-1,0],[0,9],[.5,1]])selectGridCell(p.result,r,c,point=>calls.push(point));assert.equal(calls.length,4);
 assert.match(render({...p,onSelectPoint:()=>{}}),/disabled="" aria-pressed="false">Select baseline 5.0%, dropout 0.0%/);
});
test("frontier segments never join and invalid crossing edges are suppressed",()=>{
 const p=props(),a={baseline:.05,dropout:0},b={baseline:.4,dropout:.4};assert.equal(frontierEdgeAllowed(p.result,a,b),false);
 p.result.frontierSegments.push([a,b]); const html=render(p);assert.equal((html.match(/data-frontier-segment=/g)||[]).length,2);assert.match(html,/data-target-power="0.8"/);
 p.current.selectedPoint=p.result.selectedPoint=a;assert.ok(!render(p).includes('data-marker="selected"'));assert.ok(render(p).includes("Selected scenario is invalid"));
});
test("every identity change hides stale chart, table and download",()=>{
 for(const change of [{inputsHash:"new"},{designHash:"new"},{fixedEnrollment:{control:101,treatment:101}},{effectKind:"relative_risk"},{effectValue:.05},{targetPower:.9},{selectedPoint:{baseline:.4,dropout:0}}]){
 const p=props();Object.assign(p.current,change);assert.match(heatmapProblem(p.current,p.result),/Stale/);const html=render(p);assert.ok(!html.includes("<svg"));assert.ok(!html.includes("<table"));assert.ok(!html.includes("download="));}
});
test("loading, error and idle have no numeric output",()=>{
 for(const status of ["loading","error","idle"]){const html=render({...props(),status,error:"Grid unavailable"});assert.ok(!html.includes("<svg"));assert.ok(!html.includes("<table"));if(status==="loading")assert.match(html,/aria-busy="true"/);if(status==="error")assert.match(html,/role="alert">Grid unavailable/);}
});
test("reject malformed masks, shape, powers, ARR, domain and counts",()=>{
 for(const mutate of [p=>p.result.power.pop(),p=>p.result.invalidMask[0].pop(),p=>p.result.power[0][0]=0,p=>p.result.power[0][1]=null,p=>p.result.power[0][1]=NaN,p=>p.result.power[0][1]=1.1,p=>p.result.xBaseline[1]=.05,p=>p.result.yDropout[1]=1,p=>p.current.fixedEnrollment.treatment=p.result.fixedEnrollment.treatment=99,p=>p.current.selectedPoint=p.result.selectedPoint={baseline:.8,dropout:0},p=>p.result.frontierSegments[0][0].baseline=.01,p=>{p.result.invalidMask[0][0]=false;p.result.power[0][0]=.5;}]){
 const p=props();mutate(p);assert.ok(heatmapProblem(p.current,p.result));assert.ok(!render(p).includes("<svg"));}
});
test("CSV escapes metadata and render-only components contain no CSS or requests",()=>{
 const p=props();p.result.inputsHash='fixture,"quoted"';const before=structuredClone(p.result);assert.ok(gridCsv(p.result).includes('"fixture,""quoted"""'));assert.deepEqual(p.result,before);
 for(const name of ["StressHeatmap.tsx","GridDataTable.tsx"]){const source=fs.readFileSync(path.join(__dirname,"../components",name),"utf8");assert.doesNotMatch(source,/className=|style=|fetch\(|axios|Math\.asin/);}
});

function handoff() {
 const state=initializeWorkspaceState("baseline-collapse-v1");
 state.plannedDraft.effect={kind:"absolute_risk_reduction",value:.1};
 state.calculatedDesign={inputs_hash:"design",enrolled_n:{control:100,treatment:100}};
 state.frozenEnrollment={control:100,treatment:100};state.designStatus="success";state.gridStatus="success";
 state.stressBaseline=.2;state.stressDropout=.4;
 const p=props().result,point=p=>({p_control:p.baseline,dropout:p.dropout});
 const response={method:p.method,grid_label:p.gridLabel,inputs_hash:p.inputsHash,
 fixed_enrollment:p.fixedEnrollment,target_power:p.targetPower,x_baseline:p.xBaseline,y_dropout:p.yDropout,
 power:p.power,invalid_mask:p.invalidMask,selected_point:{...point(p.selectedPoint),power:.5,is_valid:true},
 contour_segments:p.frontierSegments.map(([a,b])=>({start:point(a),end:point(b)})),
 frontier_points:[{p_control:.05,dropout:0},{p_control:.4,dropout:.4}],warnings:p.warnings,
 diagnostics:[{code:"SPARSE_COUNTS",severity:"warning",field:"selected_point",method:p.method,message:"Expected counts are sparse."}]};
 return {state,completed:{requestState:structuredClone(state),response}};
}
test("merged workspace preserves matrix, mask, independent contours and diagnostics",()=>{
 const {state,completed}=handoff(),before=structuredClone(completed),p=workspaceHeatmapProps(state,completed);
 assert.equal(heatmapProblem(p.current,p.result),null);assert.deepEqual(p.result.power,completed.response.power);
 assert.deepEqual(p.result.invalidMask,completed.response.invalid_mask);assert.deepEqual(p.result.frontierSegments,props().result.frontierSegments);
 const html=render(p);assert.equal((html.match(/data-frontier-segment=/g)||[]).length,2);assert.match(html,/Expected counts are sparse/);
 assert.deepEqual(completed,before);
});
test("workspace edits, revisions, provenance and statuses suppress late grids and downloads",()=>{
 for(const mutate of [s=>s.requestRevision++,s=>s.plannedDraft.alpha=.01,s=>s.plannedDraft.effect.value=.05,
 s=>s.stressBaseline=.3,s=>s.stressDropout=.2,s=>s.provenanceLedger.changed={source:"manual_user"},
 s=>s.frozenEnrollment.control++,s=>s.calculatedDesign.inputs_hash="new",s=>s.gridStatus="stale",s=>s.designStatus="idle"]){
 const {state,completed}=handoff();mutate(state);const html=render(workspaceHeatmapProps(state,completed));
 assert.ok(!html.includes("<svg"));assert.ok(!html.includes("download="));}
 for(const status of ["loading","error"]){const {state,completed}=handoff();state.gridStatus=status;state.gridError="Backend failed";
 const p=workspaceHeatmapProps(state,completed);assert.equal(p.status,status);assert.ok(!render(p).includes("<table"));}
 assert.equal(workspaceHeatmapProps(handoff().state,null).status,"idle");
});
test("requires raw segmented contours and selected-point contract; flat frontier is never connected",()=>{
 for(const mutate of [r=>delete r.contour_segments,r=>delete r.selected_point.power,r=>r.selected_point.is_valid=false,
 r=>r.selected_point.dropout=.2,r=>r.fixed_enrollment.control++,r=>r.target_power=.9]){
 const {state,completed}=handoff();mutate(completed.response);assert.equal(workspaceHeatmapProps(state,completed).status,"error");}
 const {state,completed}=handoff();completed.response.contour_segments=[];
 assert.ok(!render(workspaceHeatmapProps(state,completed)).includes("data-frontier-segment="));
 completed.response.selected_point.power=null;completed.response.selected_point.is_valid=false;
 assert.ok(!render(workspaceHeatmapProps(state,completed)).includes('data-marker="selected"'));
});

// Explicit live gate: fresh HTTP calculation failures fail without a fixture fallback.
if(process.env.BETTERBASELINE_HEATMAP_API){
 test("fresh real API RR and ARR grids render through merged workspace handoff",async()=>{
 const post=async(route,body)=>{const r=await fetch(process.env.BETTERBASELINE_HEATMAP_API+route,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});const t=await r.text();assert.equal(r.status,200,t);return JSON.parse(t);};
 for(const effect of [{kind:"relative_risk",value:.75},{kind:"absolute_risk_reduction",value:.1}]){
 const {state}=handoff();state.plannedDraft.effect=effect;state.stressBaseline=.2;state.stressDropout=.13;
 state.calculatedDesign=await post("/api/v1/design/calculate",state.plannedDraft);state.frozenEnrollment=state.calculatedDesign.enrolled_n;
 const requestState=structuredClone(state),response=await post("/api/v1/scenarios/grid",{
 planned_design:state.plannedDraft,fixed_enrollment:state.frozenEnrollment,x_baseline:{min:.05,max:.35,steps:3},
 y_dropout:{min:0,max:.4,steps:2},selected_scenario:{control_event_rate:.2,dropout:{control:.13,treatment:.13},effect_override:null}});
 const p=workspaceHeatmapProps(state,{requestState,response});assert.equal(heatmapProblem(p.current,p.result),null);
 assert.deepEqual(p.result.power,response.power);assert.deepEqual(p.result.invalidMask,response.invalid_mask);
 assert.equal(p.result.frontierSegments.length,response.contour_segments.length);
 const html=render(p);assert.equal((html.match(/data-cell=/g)||[]).length,6);
 assert.match(html,/data-marker="selected" data-baseline="0.2" data-dropout="0.13"/);
 const calls=[];selectGridCell(p.result,0,1,q=>calls.push(q));assert.deepEqual(calls,[{baseline:response.x_baseline[1],dropout:0}]);
 if(effect.kind==="absolute_risk_reduction"){assert.equal(response.power[0][0],null);assert.match(gridCsv(p.result),/0.05,0,null,true/);}
 const edited=structuredClone(state);edited.stressDropout=.2;assert.ok(!render(workspaceHeatmapProps(edited,{requestState,response})).includes("<svg"));
 console.log(JSON.stringify({scope:"live_heatmap_handoff",effect,hash:response.inputs_hash,power:response.power,contours:response.contour_segments.length,frozen:state.frozenEnrollment}));
 }
 });
}

test("exact selected API power controls off-grid marker validity and rejects inconsistent powers",()=>{
 const {state,completed}=handoff();
 state.stressBaseline=completed.requestState.stressBaseline=.11;
 completed.response.selected_point={p_control:.11,dropout:.4,power:.2,is_valid:true};
 const p=workspaceHeatmapProps(state,completed);assert.equal(heatmapProblem(p.current,p.result),null);
 assert.match(render(p),/data-marker="selected" data-baseline="0.11"/);
 for(const power of [NaN,1.1,-.1]){p.result.selectedPower=power;assert.ok(heatmapProblem(p.current,p.result));}
 const exact=handoff();exact.completed.response.selected_point.power=.7;
 const bad=workspaceHeatmapProps(exact.state,exact.completed);assert.match(heatmapProblem(bad.current,bad.result),/disagrees/);
});
