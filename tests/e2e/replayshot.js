const { chromium } = require('playwright');
const [base, out] = process.argv.slice(2);
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await chromium.launch({ channel: 'chrome', headless: true });
  const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(base + 's/20261006-144220?skipboot&replay=1'); await sleep(4000);
  const bar = await p.evaluate(() => ({ lbl: $('#viewlbl').textContent, spd: $('#spd').classList.contains('show'), link: $('#link').textContent }));
  await p.click('#spd button[data-x="4"]'); await sleep(2500);
  const n = await p.$$eval('#feed .ev', e => e.length);
  await p.click('#vPause'); await sleep(1500); const n2 = await p.$$eval('#feed .ev', e => e.length); await sleep(1500); const n3 = await p.$$eval('#feed .ev', e => e.length);
  await p.screenshot({ path: `${out}/replay-bar.png` });
  await p.hover('#stage', { position: { x: 720, y: 560 } }); await sleep(300);
  const hover = await p.evaluate(() => hoverId);
  console.log(JSON.stringify({ bar, eventsAt4x: n, pausedStable: n2 === n3, hover, errs }));
  await b.close();
  process.exit(bar.spd && n > 5 && n2 === n3 && !errs.length ? 0 : 1);
})();
