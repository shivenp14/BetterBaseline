import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createRequire } from 'node:module';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { request, selection, alternative, nullFixture } from './monte-carlo.fixtures.mjs';
const load=createRequire(import.meta.url);
const { SimulationError, validateSimulationRequest, parseSimulationResult, parseSimulationOptions, simulationIdentity, createSimulationClient, createSharedSimulationTransport }=load(`${process.env.C6_RENDER_ROOT}/lib/simulation-client.js`);
const { MonteCarloPanel, MonteCarloResults }=load(`${process.env.C6_RENDER_ROOT}/components/MonteCarloPanel.js`);
const { MethodDisclosures }=load(`${process.env.C6_RENDER_ROOT}/components/MethodDisclosures.js`);
const render=(component,props)=>renderToStaticMarkup(React.createElement(component,props));
test('strict controls follow B3 bounds',()=>{
  assert.deepEqual(parseSimulationOptions('42','10000'),{seed:42,replicates:10000});
  assert.deepEqual(parseSimulationOptions('4294967295','100000'),{seed:4294967295,replicates:100000});
  for (const [seed,reps] of [['','1'],['-1','1'],['1','0'],['1','100001'],['4294967296','1'],['1.5','1'],['1','1e4']]) assert.throws(()=>parseSimulationOptions(seed,reps));
});
test('identity includes selection, effect, frozen N, options and source ledger',()=>{
  const identity=simulationIdentity(request);
  assert.equal(identity,simulationIdentity(Object.fromEntries(Object.entries(request).reverse())));
  for (const change of [r=>r.stress_scenario.control_event_rate=.15,r=>r.stress_scenario.dropout={control:.2,treatment:.2},r=>r.planned_design.effect.value=.7,
    r=>r.stress_scenario.effect_override={kind:'relative_risk',value:.5},r=>r.fixed_enrollment={control:900,treatment:900},r=>r.simulation.seed=43,r=>r.simulation.replicates=500,r=>r.provenance.control_event_rate.source='synthetic_preset']) {
    const copy=structuredClone(request);change(copy);assert.notEqual(simulationIdentity(copy),identity);
  }
});
test('one run sends one exact payload and preserves split metrics/provenance',async()=>{
  let calls=0;const run=createSimulationClient(async(sent,signal)=>{calls++;assert.deepEqual(sent,request);assert.equal(signal.aborted,false);return alternative;});
  assert.deepEqual(await run(request,new AbortController().signal),alternative);assert.equal(calls,1);
});
test('invalid selected ARR and asymmetric/frozen counts fail before transport',async()=>{
  let calls=0;const run=createSimulationClient(async()=>{calls++;return alternative;});
  for (const change of [r=>r.stress_scenario.effect_override={kind:'absolute_risk_reduction',value:.1},r=>r.fixed_enrollment.control=1005,r=>r.stress_scenario.dropout.treatment=.2,r=>r.simulation.replicates=100001]) {
    const copy=structuredClone(request);change(copy);await assert.rejects(run(copy,new AbortController().signal));
  }assert.equal(calls,0);
});
test('abort rejects late results even when transport ignores cancellation',async()=>{
  let resolve;const controller=new AbortController();const run=createSimulationClient(()=>new Promise(done=>{resolve=done;}));
  const result=run(request,controller.signal);controller.abort();resolve(alternative);
  await assert.rejects(result,{name:'AbortError'});await assert.rejects(run(request,controller.signal),{name:'AbortError'});
});
test('mismatched identity, missing split MCSE and unavailable simulation fail visibly',async()=>{
  for(const change of [r=>r.monte_carlo.seed=43,r=>r.metadata.fixed_enrollment={control:1,treatment:1},r=>delete r.monte_carlo.mcse_favorable,r=>r.monte_carlo=null,r=>r.monte_carlo.mcse_two_sided=NaN,r=>r.monte_carlo.significant_favorable_fraction=.9,r=>r.monte_carlo.mean_control_events=999]) {
    const copy=structuredClone(alternative);change(copy);await assert.rejects(createSimulationClient(async()=>copy)(request,new AbortController().signal));
  }
});
test('shared helper receives one selection/options payload and preserves backend metadata',async()=>{
  let calls=0;const controller=new AbortController();
  const transport=createSharedSimulationTransport(async(sent,signal)=>{
    calls++;assert.equal(signal,controller.signal);
    assert.deepEqual(sent,{planned_design:request.planned_design,fixed_enrollment:request.fixed_enrollment,
      stress_scenario:request.stress_scenario,simulation:request.simulation,preset_id:'selected-simulation',provenance_ledger:request.provenance});
    return {...alternative,mock:false,execution:{mode:'backend',label:'Backend'},provenance:{field_provenance:alternative.provenance}};
  });
  assert.deepEqual(await createSimulationClient(transport)(request,controller.signal),alternative);assert.equal(calls,1);
});
test('shared demo or unmarked execution is unavailable; server failures remain visible',async()=>{
  for(const flags of [{mock:true,execution:{mode:'demo'}},{mock:false},{mock:false,execution:{mode:'demo'}}]) {
    await assert.rejects(createSimulationClient(createSharedSimulationTransport(async()=>({...alternative,...flags,provenance:{field_provenance:alternative.provenance}})))(request,new AbortController().signal),/demo mode/);
  }
  await assert.rejects(createSimulationClient(createSharedSimulationTransport(async()=>{throw new Error('RESOURCE_SATURATED: Retry');}))(request,new AbortController().signal),/RESOURCE_SATURATED/);
});
test('null and alternative renders keep fractions, MCSEs and counts separate',()=>{
  for(const result of [alternative,nullFixture]){
    const html=render(MonteCarloResults,{result});
    for(const label of ['Two-sided significance fraction','Favorable-direction significance fraction','Two-sided MCSE','Favorable-direction MCSE','Invalid-test fraction','Mean actual retained','Floored expected evaluable','Frozen enrolled','PCG64','10000','manual_user','Synthetic test fixture warning'])assert.ok(html.includes(label));
  }
  const html=render(MonteCarloResults,{result:nullFixture});for(const n of ['5.000%','2.500%','0.218','0.156'])assert.ok(html.includes(n));
});
test('disclosures state conditional synthetic scope, distinct methods and null alpha/2',()=>{
  const html=render(MethodDisclosures,{});for(const label of ['synthetic and conditional','alpha/2','different approximations','nonrejections over all replicates','simulation sampling error'])assert.ok(html.includes(label));
});
test('native controls show defaults, empty/unavailable and invalid states honestly',()=>{
  const html=render(MonteCarloPanel,{selection,runSimulation:async()=>alternative});assert.ok(html.includes('value="42"')&&html.includes('value="10000"'));
  assert.ok(html.includes('Run simulation')&&html.includes('No simulation result yet'));
  assert.ok(render(MonteCarloPanel,{selection:null}).includes('Simulation unavailable'));
  const invalid=render(MonteCarloPanel,{selection:{...selection,stress_scenario:{...selection.stress_scenario,effect_override:{kind:'absolute_risk_reduction',value:.2}}},runSimulation:async()=>alternative});
  assert.ok(invalid.includes('role="alert"')&&invalid.includes('disabled='));
});

test('domain validation exposes actionable codes and affected fields',()=>{
  assert.throws(()=>parseSimulationOptions('42','0'),{name:'SimulationError',code:'INVALID_MODEL_INPUT',field:'simulation.replicates'});
  const invalid=structuredClone(request);invalid.stress_scenario.effect_override={kind:'absolute_risk_reduction',value:.2};
  assert.throws(()=>validateSimulationRequest(invalid),{code:'INVALID_MODEL_INPUT',field:'stress_scenario.effect_override'});
  const unsupported=structuredClone(request);unsupported.stress_scenario.dropout.treatment=.2;
  assert.throws(()=>validateSimulationRequest(unsupported),{code:'UNSUPPORTED_MODEL',field:'stress_scenario.dropout'});
  const malformed=structuredClone(alternative);delete malformed.monte_carlo.mcse_favorable;
  assert.throws(()=>parseSimulationResult(malformed,request),error=>error instanceof SimulationError&&error.code==='INVALID_RESPONSE');
  assert.throws(()=>parseSimulationResult({...alternative,monte_carlo:null},request),{code:'SIMULATION_UNAVAILABLE'});
});
test('disclosures accompany result metrics rather than the empty input form',()=>{
  const empty=render(MonteCarloPanel,{selection,runSimulation:async()=>alternative});
  assert.ok(!empty.includes('Simulation method disclosures'));
  for(const result of [alternative,nullFixture]){
    const html=render(MonteCarloResults,{result});
    assert.equal((html.match(/Simulation method disclosures/g)||[]).length,1);
    assert.ok(html.indexOf('Simulation method disclosures')<html.indexOf('Two-sided significance fraction'));
    assert.ok(html.includes('Conditional power estimates do not establish treatment efficacy or clinical benefit'));
  }
});
