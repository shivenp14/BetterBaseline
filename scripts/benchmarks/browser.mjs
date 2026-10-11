import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import { createInterface } from 'node:readline';
const { chromium } = await import(pathToFileURL(process.env.D6_PLAYWRIGHT_MODULE).href);
const lines = createInterface({input:process.stdin})[Symbol.asyncIterator]();
async function control(command,clear=false) {
  console.log(JSON.stringify({command,clear}));
  const line = await lines.next(); assert.equal(line.done,false);
  return JSON.parse(line.value);
}
const browser = await chromium.launch({headless:true});
try {
  const page=await browser.newPage();const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto('http://localhost:3000');
  assert.match(await page.locator('header').textContent(),/LIVE/);
  const actions={design:'Calculate & Lock Design',grid:'Load grid response from backend','monte-carlo':'Evaluate Stress Scenario','grid-31x21':'Run 31×21 grid'};
  const routes={design:'/api/v1/design/calculate',grid:'/api/v1/scenarios/grid','monte-carlo':'/api/v1/scenarios/evaluate','grid-31x21':'/api/v1/scenarios/grid'};
  const measurements=[];
  const semantic=value=>{
    const copy=structuredClone(value);delete copy.computed_at;if(copy.metadata)delete copy.metadata.computed_at;
    const ordered=item=>Array.isArray(item)?item.map(ordered):item&&typeof item==='object'?Object.fromEntries(Object.entries(item).sort(([a],[b])=>a.localeCompare(b)).map(([key,entry])=>[key,ordered(entry)])):item;
    return JSON.stringify(ordered(copy));
  };
  for(const workload of Object.keys(actions)) {
    if(workload==='grid-31x21')await page.goto('http://localhost:3000/d6-grid');
    for(const condition of workload.startsWith('grid')?['uncached-grid']:['cache-cold','cache-warm']) {
      const durations=[],snapshots=[],timestamps=[];let reference,request;
      for(let i=0;i<34;i++) {
        await control('prepare',condition==='cache-cold'||i===0);
        const responsePromise=page.waitForResponse(response=>response.url().endsWith(routes[workload])&&response.request().method()==='POST');
        const timePromise=page.evaluate(({label})=>new Promise((resolve,reject)=>{
          const button=[...document.querySelectorAll('button')].find(element=>element.textContent===label);
          if(!button||button.disabled) {reject(new Error('Action unavailable: '+label));return;}
          let sawPending=false;
          const observer=new MutationObserver(()=>{
            const pending=button.disabled||button.closest('fieldset')?.disabled||button.textContent!==label;
            if(pending)sawPending=true;
            if(sawPending&&!pending) {
              observer.disconnect();clearTimeout(timeout);resolve(Math.round((performance.now()-start)*1e6));
            }
          });
          observer.observe(document.body,{subtree:true,childList:true,attributes:true,characterData:true});
          const timeout=setTimeout(()=>{observer.disconnect();reject(new Error('No result DOM commit'));},30000);
          const start=performance.now();button.click();
        }),{label:actions[workload]});
        const response=await responsePromise;
        assert.equal(response.status(),200);
        const result=await response.json();
        const elapsed=await timePromise;
        const snapshot=await control('snapshot');
        const payload=response.request().postDataJSON();
        assert.equal('preset_id' in payload,false);
        if(!reference){reference=result;request=payload;}
        assert.deepEqual(payload,request);assert.equal(semantic(result),semantic(reference));
        if(workload==='design') {
          const section=page.locator('[aria-labelledby="planned-heading"]');
          assert.match(await section.textContent(),/Calculated by the local backend service/);
          assert.match(await section.textContent(),/903 control and903 treatment|903 control and 903 treatment/);
        } else if(workload.startsWith('grid')) {
          assert.equal(await page.locator('[aria-labelledby="grid-heading"] tbody tr').count(),result.y_dropout.length);
          assert.equal(await page.locator('[aria-labelledby="grid-heading"] tbody td').count(),result.x_baseline.length*result.y_dropout.length);
          assert.match(await page.locator('[aria-labelledby="grid-heading"]').textContent(),/SUCCESS/);
          const cells=await page.locator('[aria-labelledby="grid-heading"] tbody td').allTextContents();
          assert.deepEqual(cells,result.power.flat().map(value=>value===null?'Invalid (power null)':`${(value*100).toFixed(0)}%`));
        } else {
          const text=await page.locator('[aria-labelledby="evaluate-heading"]').textContent();
          assert.match(text,/Calculated by the local backend service/);
          assert.match(text,/Replicates:10,000|Replicates: 10,000/);
          assert.match(text,/Seed:42|Seed: 42/);
          assert.ok(text.replace(/\s+/g,'').includes(`Two-sidedsignificanceMCSE:${(result.monte_carlo.mcse_two_sided*100).toFixed(1)}%`));
          assert.ok(text.replace(/\s+/g,'').includes(`Favorable-directionsignificanceMCSE:${(result.monte_carlo.mcse_favorable*100).toFixed(1)}%`));
        }
        if(i>=4) {
          durations.push(elapsed);snapshots.push(snapshot);
          timestamps.push(result.computed_at??result.metadata?.computed_at??null);
        }
      }
      const sorted=[...durations].sort((a,b)=>a-b);
      measurements.push({workload:workload==='grid-31x21'?'grid':workload,variant:workload,condition,measured_runs:30,excluded_warmups:3,excluded_priming_requests:1,
        raw_elapsed_ns:durations,median_ms:(sorted[14]+sorted[15])/2e6,p95_ms:sorted[28]/1e6,
        p95_definition:'nearest rank, ceil(0.95*runs), one-based',cache_observations:snapshots,
        computed_at_samples:timestamps,representative_result:reference,request,
        identical_semantic_results:true,browser:await browser.version(),frontend_mode:workload==='grid-31x21'?'next start; live shared API; isolated benchmark-owned 31x21 page':'next start production; live API; existing production workspace'});
    }
  }
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({command:'report',value:measurements}));
} finally {await browser.close();lines.return();process.stdin.destroy();}
