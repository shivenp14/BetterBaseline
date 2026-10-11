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
const { StressHeatmap, heatmapProblem, frontierEdgeAllowed, selectGridCell } = require("../components/StressHeatmap.tsx");
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
