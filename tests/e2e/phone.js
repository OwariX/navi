// usage: node phone.js <base-url> <out-dir>
// NAVI on a phone (iPhone 13, 390 px): nothing scrolls sideways; Agents and Councils show their list first, an item
// opens with a way back; the session's top bar keeps the feed, New session and ⌘K on screen; the feed opens.
const { chromium, devices } = require('playwright');
const [base, out] = process.argv.slice(2);
const R = []; const check = (n, ok, x = '') => R.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  · ' + x : ''}`);
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const ctx = await browser.newContext({ ...devices['iPhone 13'] });
  await ctx.addInitScript(() => { try { localStorage.setItem('navi.tour', '1'); } catch {} });
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(e.message));
  const sideways = () => page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  const onScreen = sel => page.evaluate(s => { const e = document.querySelector(s); if (!e || !e.offsetParent) return false;
    const r = e.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth && r.width > 0; }, sel);
  try {
    await page.goto(base + '?skipboot'); await page.waitForSelector('#menu.show', { timeout: 8000 }); await page.waitForTimeout(500);
    check('home: nothing scrolls sideways', await sideways() <= 1, `${await sideways()} px`);
    await page.fill('#mTask', 'a page'); await page.click('#mStart'); await page.waitForSelector('#launchP.show'); await page.waitForTimeout(400);
    check('the launch sheet fits', await sideways() <= 1 && await onScreen('#lGo'), `${await sideways()} px`);
    await page.click('#lClose'); await page.waitForTimeout(300);

    await page.click('#tAgents'); await page.waitForTimeout(700);
    check('Agents on a phone: the list first (it used to open on one agent with no way to the others)',
      await page.isVisible('#agList') && !(await page.isVisible('#aTitle')) && await onScreen('#aListClose'));
    const second = await page.textContent('#agList .li:nth-child(2) b');
    await page.click('#agList .li >> nth=1'); await page.waitForTimeout(400);
    check('...an agent opens on its own, with a way back', await page.isVisible('#aTitle') && !(await page.isVisible('#agList'))
      && (await page.textContent('#aTitle')) === second && await onScreen('#aBack'), await page.textContent('#aTitle'));
    await page.click('#aBack'); await page.waitForTimeout(300);
    check('...back is the list again', await page.isVisible('#agList') && !(await page.isVisible('#aTitle')));
    await page.click('#aNew'); await page.waitForTimeout(300);
    check('...New opens the form for a new agent', await page.isVisible('#aName'));
    await page.click('#aClose'); await page.waitForTimeout(300);

    await page.click('#tCouncils'); await page.waitForTimeout(700);
    check('Councils on a phone: the list first', await page.isVisible('#coList') && !(await page.isVisible('#coTitleIn')));
    await page.click('#coList .li >> nth=0'); await page.waitForTimeout(400);
    check('...a council opens with a way back', await page.isVisible('#coTitleIn') && await onScreen('#coBack'));
    await page.click('#coBack'); await page.waitForTimeout(300);
    check('...and back', await page.isVisible('#coList'));
    await page.click('#coListClose'); await page.waitForTimeout(300);

    await page.goto(base + 'demo'); await page.waitForTimeout(6000);
    const bar = {}; for (const id of ['#modPill', '#bNew', '#bPal', '#bSide']) bar[id] = await onScreen(id);
    check('a session on a phone: the top bar keeps NAVI, New session, ⌘K and the feed on screen', Object.values(bar).every(Boolean), JSON.stringify(bar));
    check('...and nothing scrolls sideways', await sideways() <= 1, `${await sideways()} px`);
    await page.click('#bSide'); await page.waitForTimeout(600);
    check('...the feed opens', await page.isVisible('#side'));
    await page.screenshot({ path: `${out}/phone-session-feed.png` });
    check('no page errors', errs.length === 0, errs.join(' | '));
  } catch (e) {
    check('the run finished', false, e.message.split('\n')[0]);
  } finally { await browser.close(); }
  console.log(R.join('\n'));
  const failed = R.filter(x => x.startsWith('FAIL')).length;
  console.log(failed ? `PHONE SUITE FAILED: ${failed}` : 'PHONE SUITE PASSED');
  process.exit(failed ? 1 : 0);
})();
