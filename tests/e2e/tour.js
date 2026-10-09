// usage: node tour.js <base-url> <out-dir>  — the first-session tour shows once, steps through, and never again
const { chromium } = require('playwright');
const [base, out] = process.argv.slice(2);
const SID = '20261006-144220';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const R = []; const check = (n, ok, x = '') => R.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  · ' + x : ''}`);
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(e.message));
  // the suites before this one may have marked the tour seen (NAVI remembers it in the settings, not just the browser)
  await page.goto(`${base}?skipboot`); await page.waitForSelector('#menu.show', { timeout: 20000 });
  await page.evaluate(() => post('/settings', {guides_seen: []}));
  await page.goto(`${base}s/${SID}?skipboot`); await sleep(4000);
  const shown = () => page.$eval('#tour', e => e.classList.contains('show'));
  check('tour appears on the first session visit', await shown());
  const titles = [];
  for (let i = 0; i < 4; i++){
    titles.push(await page.textContent('#tourT'));
    const hi = await page.$$eval('.tour-hi', els => els.map(e => e.id));
    await page.screenshot({ path: `${out}/tour-${i + 1}.png` });
    if (i === 1) check('step 2 highlights the activity panel', hi.includes('side'), hi.join(','));
    if (i === 2) check('step 3 highlights the console', hi.includes('console'), hi.join(','));
    await page.click('#tourNext'); await sleep(400);
  }
  check('four steps', titles.length === 4 && new Set(titles).size === 4, titles.join(' → '));
  check('the tour speaks sentence case', titles.every(x => x !== x.toUpperCase()), titles.join(','));
  check('closes after the last step', !(await shown()));
  check('remembered', await page.evaluate(() => localStorage.getItem('navi.tour') === '1'));
  await page.reload(); await sleep(3500);
  check('does not show again', !(await shown()));
  // another browser, or the same one at another address (NAVI on another port after a restart): its memory is empty,
  // NAVI's isn't (the tour used to come back after every update)
  const ctxB = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const pb = await ctxB.newPage(); await pb.goto(`${base}s/${SID}?skipboot`); await sleep(3500);
  check('...not even in a fresh browser or at another port: NAVI remembers it, not just this browser',
    !(await pb.$eval('#tour', e => e.classList.contains('show'))) && (await pb.evaluate(() => fetch('/settings').then(r => r.json()))).guides_seen.includes('session'));
  await ctxB.close();
  const mono = await page.evaluate(() => [...nodes.keys()]);
  check('nodes present for monograms', mono.length >= 5, mono.join(','));
  await page.screenshot({ path: `${out}/monograms.png` });
  // skip path (from a NAVI that hasn't shown it yet)
  await page.evaluate(() => post('/settings', {guides_seen: []}));
  const ctx2 = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p2 = await ctx2.newPage(); await p2.goto(`${base}s/${SID}?skipboot`); await sleep(3500);
  await p2.click('#tourSkip'); await sleep(300);
  check('SKIP closes and remembers', !(await p2.$eval('#tour', e => e.classList.contains('show'))) && await p2.evaluate(() => localStorage.getItem('navi.tour') === '1'));
  // the guides for the other screens: home shows its own the first time (a real visit, no ?skipboot), once
  const ctx3 = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p3 = await ctx3.newPage(); p3.on('pageerror', e => errs.push(e.message));
  await p3.goto(base + '?skipboot'); await p3.waitForSelector('#menu.show', { timeout: 20000 });
  await p3.evaluate(() => post('/settings', {guides: true}));         // the suites turn guides off; this one needs them
  await p3.goto(base); await p3.waitForSelector('#menu.show', { timeout: 20000 });
  const homeGuide = await (async () => { for (let i = 0; i < 30; i++) { if (await p3.$eval('#tour', e => e.classList.contains('show'))) return true; await sleep(200); } return false; })();
  check('home: its guide shows the first time', homeGuide && (await p3.textContent('#tourT')) === 'Where you work', await p3.textContent('#tourT'));
  const n = +((await p3.textContent('#tourN')).match(/of (\d+)/) || [])[1];
  for (let i = 0; i < n; i++) { await p3.click('#tourNext'); await sleep(250); }
  check('home: Done closes it and remembers', !(await p3.$eval('#tour', e => e.classList.contains('show'))) && await p3.evaluate(() => localStorage.getItem('navi.guide.home') === '1'));
  await p3.reload(); await p3.waitForSelector('#menu.show', { timeout: 20000 }); await sleep(2500);
  check('home: not again after that', !(await p3.$eval('#tour', e => e.classList.contains('show'))));
  await p3.click('#tCouncils'); await p3.waitForSelector('#councilsP.show'); await sleep(1200);
  check('Councils: its guide shows the first time you open it', (await p3.textContent('#tourT')) === 'Your councils' && await p3.$eval('#tour', e => e.classList.contains('show')));
  await p3.click('#tourSkip'); await sleep(200);
  await p3.click('#councilsP .gq'); await sleep(300);
  check('the ? on a screen replays its guide', (await p3.textContent('#tourT')) === 'Your councils' && await p3.$eval('#tour', e => e.classList.contains('show')));
  await p3.keyboard.press('Escape'); await sleep(200); await p3.keyboard.press('Escape'); await sleep(300);
  await p3.click('#tSettings'); await p3.waitForSelector('#setup.show'); await sleep(1200);
  if (await p3.$eval('#tour', e => e.classList.contains('show'))) { await p3.click('#tourSkip'); await sleep(200); }
  await p3.click('#gReset'); await sleep(200);
  check('Settings > Guides: show every guide again', await p3.evaluate(() => ['home', 'councils', 'agents', 'settings'].every(n => !localStorage.getItem('navi.guide.' + n)) && !localStorage.getItem('navi.tour')));
  check('...in NAVI\'s memory too, not only this browser\'s', ((await p3.evaluate(() => fetch('/settings').then(r => r.json()))).guides_seen || []).length === 0);
  await p3.evaluate(() => post('/settings', {guides: false}));        // back off for the suites after this one
  console.log(R.join('\n')); console.log('page errors:', errs.length ? errs : 'none');
  await browser.close();
  process.exit(R.some(r => r.startsWith('FAIL')) || errs.length ? 1 : 0);
})().catch(e => { console.log(R.join('\n')); console.error('TOUR FAIL', e.message); process.exit(1); });
