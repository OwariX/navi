// usage: node updates.js <base-url> <out-dir>
// Home's update line, against answers faked in the browser (nothing is updated for real; tests/update_test.py does
// that against a throwaway origin): a newer release in green with Update; Updating…, then "✔ Update installed" with
// Restart; Restart brings the page back; a refusal (a council is running) is said plainly; nothing shows when current.
const { chromium } = require('playwright');
const [base, out] = process.argv.slice(2);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const R = []; const check = (n, ok, x = '') => R.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x && !ok ? '  · ' + x : ''}`);
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 860 } });
  await ctx.addInitScript(() => { try { localStorage.setItem('navi.tour', '1'); } catch {} });
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(e.message));
  let upd = { version: '0.9.008', running: '0.9.008', latest: '0.9.009', available: true, installed: false, auto: false, git: true };
  let updateAnswer = { status: 200, body: { ok: true, job: 'jupd0001' } }, reloaded = 0;
  await page.route('**/status*', async route => {
    const r = await route.fetch(); const j = await r.json();
    route.fulfill({ response: r, json: { ...j, update: upd } });
  });
  await page.route('**/update', route => route.fulfill({ status: updateAnswer.status, json: updateAnswer.body }));
  await page.route('**/jobs?id=jupd0001', route => {
    upd = { ...upd, version: '0.9.009', available: false, installed: true };      // what the server says once it's installed
    route.fulfill({ json: { state: 'done', result: { ok: true, message: 'updated to 0.9.009', version: '0.9.009' } } });
  });
  await page.route('**/restart', route => route.fulfill({ json: { ok: true, restarting: true } }));
  await page.route('**/version', route => route.fulfill({ json: { version: '0.9.009', running: '0.9.009' } }));
  page.on('framenavigated', f => { if (f === page.mainFrame()) reloaded++; });
  const text = () => page.textContent('#mUpd').catch(() => '');
  try {
    await page.goto(base + '?skipboot'); await page.waitForSelector('#menu.show', { timeout: 8000 }); await sleep(600);
    check('a newer release: home says so in green, with Update', await page.isVisible('#mUpd') && /NAVI 0\.9\.009 is out/.test(await text())
      && /you have 0\.9\.008/.test(await text()) && await page.isVisible('#mUpd button:has-text("Update")'), await text());
    const color = await page.$eval('#mUpd', e => getComputedStyle(e).color), ok = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--ok').trim());
    check('...in the theme\'s green', color && ok && color.replace(/\s/g, '') !== '', `${color} / ${ok}`);
    await page.screenshot({ path: `${out}/update-available.png` });
    await page.click('#mUpd button:has-text("Update")');
    check('...Update: it says it\'s updating', await page.waitForFunction(() => /Updating…|installed/.test(document.querySelector('#mUpd').textContent), null, { timeout: 4000 }).then(() => true, () => false), await text());
    check('...then: ✔ Update installed · Restart to update, with Restart', await page.waitForFunction(() => /✔ Update installed/.test(document.querySelector('#mUpd').textContent), null, { timeout: 8000 }).then(() => true, () => false)
      && /Restart to update/.test(await text()) && await page.isVisible('#mUpd button:has-text("Restart")'), await text());
    await page.screenshot({ path: `${out}/update-installed.png` });
    const before = reloaded;
    await page.click('#mUpd button:has-text("Restart")');
    check('...Restart: the page comes back on the new version', await (async () => { for (let i = 0; i < 40; i++){ if (reloaded > before) return true; await sleep(200); } return false; })());

    // a council is running: Update says why it can't, plainly
    upd = { version: '0.9.008', running: '0.9.008', latest: '0.9.009', available: true, installed: false, auto: false, git: true };
    updateAnswer = { status: 409, body: { error: "a council is running: update when it's done (it would switch versions under it)" } };
    await page.goto(base + '?skipboot'); await page.waitForSelector('#menu.show', { timeout: 8000 }); await sleep(500);
    await page.click('#mUpd button:has-text("Update")'); await sleep(500);
    check('a council is running: Update says it can\'t, and why', /a council is running/.test(await text()), await text());

    upd = { version: '0.9.009', running: '0.9.009', latest: '0.9.009', available: false, installed: false, auto: true, git: true };
    await page.goto(base + '?skipboot'); await page.waitForSelector('#menu.show', { timeout: 8000 }); await sleep(500);
    check('up to date: no update line at all', !(await page.isVisible('#mUpd')));
    await page.click('#tSettings'); await page.waitForSelector('#setup.show'); await sleep(300);
    check('Settings has "Update NAVI automatically"', await page.isVisible('#updSec input[data-k="auto_update"]') && /Update NAVI automatically/.test(await page.textContent('#updSec')));
    check('no page errors', errs.length === 0, errs.join(' | '));
  } catch (e) {
    check('the run finished', false, e.message.split('\n')[0]);
  } finally { await browser.close(); }
  console.log(R.join('\n'));
  const failed = R.filter(x => x.startsWith('FAIL')).length;
  console.log(failed ? `UPDATES SUITE FAILED: ${failed}` : 'UPDATES SUITE PASSED');
  process.exit(failed ? 1 : 0);
})();
