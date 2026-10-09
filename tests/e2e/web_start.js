// usage: node web_start.js <menu-url> <shot-dir> <council> <task>
// The terminal hand-off: the home screen sees the waiting terminal, the launch sheet starts the council there.
const { chromium } = require('playwright');
const [url, out, council, task] = process.argv.slice(2);
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript(() => { try { localStorage.setItem('navi.tour', '1'); } catch {} });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  await page.goto(url + '?skipboot');
  await page.waitForSelector('#menu.show', { timeout: 8000 });
  await sleep(700);
  const status = await page.textContent('#mStatus');
  await page.fill('#mTask', task);
  await page.click('#mStart'); await sleep(400);
  const where = await page.textContent('#lWhere');
  await page.screenshot({ path: `${out}/web-launch-sheet.png` });
  await page.click('#lGo');
  await sleep(300);
  const msg = await page.textContent('#lWhere');
  await page.waitForURL(/\/s\/\d{8}-\d{6}/, { timeout: 10000 });
  await sleep(4500);
  const feed = await page.$$eval('#feed > *', els => els.map(e => e.innerText.replace(/\s+/g, ' ').slice(0, 110)));
  const pill = await page.textContent('#modPill').catch(() => '');
  await page.screenshot({ path: `${out}/web-session-live.png` });
  console.log(JSON.stringify({ status, where, msg, sessionUrl: page.url(), feed: feed.slice(-6), pill: pill.replace(/\s+/g, ' '), errs }, null, 1));
  await browser.close();
})().catch(e => { console.error('E2E FAIL', e.message); process.exit(1); });
