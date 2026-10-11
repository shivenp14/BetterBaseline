import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
const { chromium }=await import(pathToFileURL(process.env.C6_PLAYWRIGHT_MODULE).href);
const browser=await chromium.launch({headless:true});
try {
  const page=await browser.newPage();const errors=[],requests=[];
  page.on('request',request=>{if(request.method()==='POST'&&request.url().endsWith('/api/v1/scenarios/evaluate'))requests.push(request.postDataJSON());});page.on('pageerror',error=>errors.push(error.message));
  await page.goto('http://localhost:3000/c6-harness');
  const field=name=>page.getByLabel(name,{exact:true});
  const run=()=>page.getByRole('button',{name:'Run simulation',exact:true});
  const value=label=>page.locator('dt').filter({hasText: new RegExp(`^${label}$`)}).locator('xpath=following-sibling::dd[1]').textContent();
  assert.equal(await page.getByRole('complementary',{name:'Simulation method disclosures'}).count(),0);
  assert.equal(await field('Simulation seed').inputValue(),'42');assert.equal(await field('Simulation replicates').inputValue(),'10000');
  // Standalone panel cleanup must clear only the aborted request's pending ID.
  // Returning to A must permit a replacement run, and A's late finally must not
  // clear that replacement while it is still pending.
  const regression=await browser.newPage();
  try {
    await regression.goto('http://localhost:3000/c6-harness');
    const runRegression=()=>regression.getByRole('button',{name:'Run simulation',exact:true});
    await regression.getByRole('button',{name:'Hold runs',exact:true}).click();
    await runRegression().click();
    await regression.getByRole('button',{name:'Running simulation…',exact:true}).waitFor();
    await regression.getByRole('button',{name:'Select new baseline',exact:true}).click();
    await regression.waitForFunction(()=>document.querySelector('button[type="submit"]')?.disabled===false);
    await regression.getByRole('button',{name:'Return to original baseline',exact:true}).click();
    await regression.waitForFunction(()=>document.querySelector('button[type="submit"]')?.disabled===false);
    await runRegression().click();
    await regression.getByRole('button',{name:'Running simulation…',exact:true}).waitFor();
    await regression.waitForFunction(()=>document.querySelector('[aria-label="Held runs"]')?.textContent==='2');
    assert.equal(await regression.getByLabel('Held runs',{exact:true}).textContent(),'2');
    await regression.getByRole('button',{name:'Release oldest held run',exact:true}).click();
    await regression.waitForFunction(()=>document.querySelector('[aria-label="Settled held runs"]')?.textContent==='1');
    assert.equal(await regression.getByRole('button',{name:'Running simulation…',exact:true}).count(),1,
      'the aborted A run must not clear the replacement A run pending state');
    await regression.getByRole('button',{name:'Release oldest held run',exact:true}).click();
    await regression.waitForFunction(()=>document.querySelector('[aria-label="Settled held runs"]')?.textContent==='2');
    await regression.waitForFunction(()=>document.querySelector('button[type="submit"]')?.disabled===false);
    assert.equal(await runRegression().isDisabled(),false);
    assert.equal(await regression.getByLabel('Accepted seeds',{exact:true}).textContent(),'[42]');
  } finally { await regression.close(); }
  await field('Simulation replicates').fill('100001');
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('button')).some(button=>button.textContent==='Run simulation'&&button.disabled));
  assert.equal(await run().isDisabled(),true);
  await field('Simulation replicates').fill('10000');
  await field('Simulation seed').press('Enter');
  await page.getByText('Mean actual retained participants (simulation)',{exact:true}).waitFor();
  assert.equal(await page.getByRole('complementary',{name:'Simulation method disclosures'}).count(),1);
  assert.equal(await field('Run calls').textContent(),'1');assert.equal(await value('Seed'),'42');assert.equal(await value('Replicates'),'10000');
  assert.match(await value('Inputs hash'),/^sha256:/);
  assert.equal(requests.length,1);assert.equal(requests[0].simulation.replicates,10000);assert.equal(requests[0].simulation.seed,42);
  assert.deepEqual(requests[0].provenance,{control_event_rate:{source:'manual_user'}});
  assert.equal('preset_id' in requests[0],false);assert.equal('provenance_ledger' in requests[0],false);
  assert.ok((await page.locator('body').textContent()).includes('manual_user'));
  assert.equal(await value('Simulation method'),'pooled_two_proportion_z_v1');
  assert.equal(await page.getByText('Two-sided MCSE (percentage points)',{exact:true}).count(),1);
  assert.equal(await page.getByText('Favorable-direction MCSE (percentage points)',{exact:true}).count(),1);
  await page.getByRole('button',{name:'Select new baseline',exact:true}).click();
  await page.getByText('Stale simulation.',{exact:true}).waitFor();
  assert.equal(await field('Run calls').textContent(),'1');
  await page.getByRole('button',{name:'Ignore cancellation',exact:true}).click();
  await run().click();await page.getByRole('button',{name:'Running simulation…',exact:true}).waitFor();
  await page.locator('form').evaluate(form=>{form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));});
  assert.equal(await field('Run calls').textContent(),'2');
  await field('Simulation seed').fill('43');await run().click();
  await page.waitForFunction(()=>JSON.parse(document.querySelector('[aria-label="Finished seeds"]').textContent).includes(43));
  await page.waitForFunction(()=>JSON.parse(document.querySelector('[aria-label="Finished seeds"]').textContent).includes(42));
  assert.equal(await value('Seed'),'43');assert.equal(await page.getByText('Stale simulation.',{exact:true}).count(),0);
  assert.deepEqual(JSON.parse(await field('Accepted seeds').textContent()),[42,43]);
  assert.equal(await field('Run calls').textContent(),'3');
  await page.getByRole('button',{name:'Change effect',exact:true}).click();await page.getByText('Stale simulation.',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Fail adapter',exact:true}).click();await run().click();await page.getByText('Acceptance transport failure',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Invalid ARR',exact:true}).click();assert.equal(await run().isDisabled(),true);
  await page.getByRole('button',{name:'Clear selection',exact:true}).click();await page.getByText('Simulation unavailable:',{exact:false}).waitFor();
  await page.getByRole('button',{name:'Restore selection',exact:true}).click();await page.getByRole('button',{name:'Ignore cancellation',exact:true}).click();
  await field('Simulation seed').fill('42');await run().click();
  await page.getByRole('button',{name:'Running simulation…',exact:true}).waitFor();
  await page.getByRole('button',{name:'Toggle panel',exact:true}).click();
  await page.waitForFunction(()=>Number(document.querySelector('[aria-label="Abort calls"]').textContent)>0);
  assert.deepEqual(errors,[]);
  console.log('PASS: fresh 10k seeded API, keyboard/bounds, one call per run, late responses, effect/selection stale states, errors/invalid/unavailable states, unmount abort, standalone A→B→A held-run cleanup and stale-finally ownership.');
} finally {await browser.close();}
