import { chromium } from '../../../tests/e2e/node_modules/playwright/index.mjs';
import assert from 'node:assert/strict';
import {writeFile,readFile} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
const out=new URL('.',import.meta.url).pathname; const browser=await chromium.launch({headless:true}); const results=[];
const canon=b=>({...b,provenance:b.provenance.field_provenance??b.provenance});
try { for(const width of [1440,375]) { const page=await browser.newPage({viewport:{width,height:width===375?812:900},acceptDownloads:true}); const errors=[];page.on('pageerror',e=>errors.push(e.message));
const overflow=async()=>assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`overflow ${width}`);
const call=async(endpoint,action,match=()=>true)=>{const pending=page.waitForResponse(r=>r.url().endsWith(endpoint)&&r.request().method()==='POST'&&match(r.request().postDataJSON()));await action();const r=await pending;assert.equal(r.status(),200);return r.json();};
await page.goto(process.env.PAGE_URL);await overflow();await page.screenshot({path:`${out}after-initial-${width}.png`,fullPage:true});
for(const preset of ['baseline-collapse-v1','attrition-shock-v1','stable-design-v1']) {
await page.getByLabel('Select Preset:').selectOption(preset);
const design=await call('/calculate',()=>page.getByRole('button',{name:'Calculate & Lock Design',exact:true}).click());
await page.locator('[data-cell]').first().waitFor();await overflow();
await page.locator('#stress-baseline-num').fill('0.12');await page.locator('#stress-dropout-num').fill('0.25');
let analyticRequest; page.on('request',r=>{if(r.url().endsWith('/evaluate')&&r.method()==='POST'&&r.postDataJSON().simulation===null)analyticRequest=r.postDataJSON();});
await call('/evaluate',()=>page.getByRole('button',{name:'Evaluate Stress Scenario',exact:true}).click(),b=>b.simulation===null);assert.deepEqual(analyticRequest.fixed_enrollment,design.enrolled_n);
await page.getByLabel('Simulation seed',{exact:true}).fill('42');await page.getByLabel('Simulation replicates',{exact:true}).fill('10000');
const evaluation=await call('/evaluate',()=>page.getByRole('button',{name:'Run simulation',exact:true}).click(),b=>b.simulation?.seed===42);
const grid=await call('/grid',()=>page.getByRole('button',{name:'Load grid response from backend',exact:true}).click());
const link=page.getByRole('link',{name:'Download current scenario JSON',exact:true});await link.waitFor();
const pending=page.waitForEvent('download');await link.click();const download=await pending;const filename=`${out}${preset}-${width}.json`;await download.saveAs(filename);const data=JSON.parse(await readFile(filename,'utf8'));
assert.deepEqual(data.design_result,canon(design));assert.deepEqual(data.evaluation_result,canon(evaluation));assert.deepEqual(data.grid_result,grid);assert.deepEqual(data.fixed_enrollment,design.enrolled_n);
const check=spawnSync(process.env.EXPORT_TEST_PYTHON,['-c','import sys; from app.schemas import ExportPayload; ExportPayload.model_validate_json(open(sys.argv[1]).read())',filename],{cwd:new URL('../../../backend',import.meta.url).pathname,encoding:'utf8'});assert.equal(check.status,0,check.stderr);
await page.getByLabel('Reopen and validate scenario JSON',{exact:true}).setInputFiles(filename);await page.getByText(/^Valid complete v1 scenario exported/).waitFor();
await overflow();await page.screenshot({path:`${out}after-current-${preset}-${width}.png`,fullPage:true});
assert.ok(await page.locator('table').count()); const cell=page.locator('[data-cell="1-2"]');await cell.focus();assert.equal(await cell.evaluate(e=>e===document.activeElement),true);await cell.press('Enter');await page.locator('section[aria-labelledby="grid-heading"]').getByText(/SUCCESS/).waitFor();await overflow();
results.push({width,preset,enrollment:data.fixed_enrollment,hash:data.inputs_hash,identity:'full design/evaluate/grid equality',keyboard:'heatmap Enter',overflow:false});
}assert.deepEqual(errors,[]);await page.close(); } await writeFile(`${out}responsive-results.json`,JSON.stringify(results,null,2));console.log(JSON.stringify(results,null,2)); }finally{await browser.close();}
