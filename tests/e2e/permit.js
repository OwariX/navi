// usage: node permit.js <base-url> <out-dir> <fake-log> <navi-dir>
// Permission cards. The background moderator (the fake claude, FAKE_PERMIT=1) runs three commands nothing allowed; like
// the real CLI in -p, each goes to NAVI's PermissionRequest hook and waits for you. "For this session" on the first
// (Claude Code gets a session rule, NAVI remembers it for a restart), "Deny" in the full card on the second, and nobody
// answers the third (NAVI_PERMIT_WAIT), so it doesn't run.
const { chromium } = require('playwright');
const fs = require('fs');
const [base, out, fakeLog, naviDir] = process.argv.slice(2);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const waitFor = async (fn, ms) => { const end = Date.now() + ms; while (Date.now() < end) { if (await fn()) return true; await sleep(250); } return false; };
const R = []; const check = (n, ok, x = '') => R.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  · ' + x : ''}`);
const said = s => fs.existsSync(fakeLog) && fs.readFileSync(fakeLog, 'utf8').includes(s);
const text = async (page, sel) => ((await page.textContent(sel).catch(() => '')) || '').replace(/\s+/g, ' ').trim();
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript(() => { try { localStorage.setItem('navi.tour', '1'); } catch {} });
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(e.message));
  await page.goto(base + '?skipboot'); await page.waitForSelector('#menu.show', { timeout: 8000 }); await sleep(500);
  await page.fill('#mTask', 'permission cards');
  await page.click('#mStart'); await sleep(400);
  await page.click('#lPace .opt:has-text("Quick")'); await sleep(150);
  await page.click('#lGo');
  await page.waitForURL(/\/s\/\d{8}-\d{6}/, { timeout: 10000 });
  const sid = page.url().match(/\/s\/([\d-]+)/)[1];

  // 1. the card: above the console, in the feed, and "needs you" in the top bar
  const waiting = cmd => page.evaluate(c => [...pending.values()].some(e => e.type === 'permit' && e.body === c), cmd);
  const up = await waitFor(async () => await page.isVisible('#askbar') && await waiting('npm install left-pad'), 30000);
  const bar = await text(page, '#askbar');
  check('a command nothing allowed waits as a card: who, and what it wants in words (the agent\'s own)', up && /wants to run/.test(bar) && /fake: this needs your OK/.test(bar)
    && !/npm install left-pad/.test(bar), bar);
  const btns = await page.$$eval('#askbarOpts button', els => els.map(e => e.textContent.trim()));
  check('three answers: Allow once, For this session, Deny', btns.join('|') === 'Allow once|For this session|Deny', btns.join(' | '));
  check('the feed shows it in words: what the agent says, and what the command does (worked out by NAVI)',
    (await text(page, '#feed .ev.permit .pwhy')) === 'fake: this needs your OK' && (await text(page, '#feed .ev.permit .pplain')) === 'It runs: Use npm',
    `${await text(page, '#feed .ev.permit .pwhy')} | ${await text(page, '#feed .ev.permit .pplain')}`);
  check('...the command itself one click away', !(await page.isVisible('#feed .ev.permit .pcmd')));
  await page.click('#feed .ev.permit .praw summary'); await sleep(150);
  check('...Show the command shows it', await page.isVisible('#feed .ev.permit .pcmd') && (await text(page, '#feed .ev.permit .pcmd')) === 'npm install left-pad');
  check('the top bar says it needs you', /needs you/.test(await text(page, '#needPill')), await text(page, '#needPill'));
  await page.screenshot({ path: `${out}/permit-card.png` });

  // 2. "For this session"
  await page.click('#askbarOpts button:has-text("For this session")');
  check('"For this session": the hook allows it and gives Claude Code a session rule', await waitFor(() => said('permit npm install left-pad: allow +session-rule'), 10000));
  let rem = {}; try { rem = JSON.parse(fs.readFileSync(`${naviDir}/sessions/${sid}/permits.json`, 'utf8')); } catch {}
  check('NAVI remembers the rule for a restarted moderator', (rem.always || []).includes('Bash(npm install:*)'), JSON.stringify(rem));
  const done1 = await text(page, '#feed .ev.permit.answered');
  check('the card says what you decided', /You allowed it for this session/.test(done1) && /Bash\(npm install:\*\)/.test(done1), done1);

  // 3. the full card from the bar: the command, why, nothing runs until you answer; then Deny
  await waitFor(async () => !(await waiting('npm install left-pad')) && await waiting('curl -s https://example.com'), 10000);
  await page.click('#askbarQ'); await sleep(300);
  const sheet = await text(page, '#askm');
  check('the full card: why in words, what it does, nothing runs until you answer',
    /fake: this needs your OK/.test(sheet) && /It runs: Fetch from the web/.test(sheet) && /Nothing runs until you answer/.test(sheet) && !(await page.isVisible('#askm .pcmd')), sheet.slice(0, 200));
  await page.click('#askm .praw summary'); await sleep(150);
  check('...and the command on Show the command', await page.isVisible('#askm .pcmd') && /curl -s https:\/\/example\.com/.test(await text(page, '#askm .pcmd')));
  check('a permission card has no answer box', !(await page.isVisible('#askText')) && !(await page.isVisible('#askSend')));
  await page.screenshot({ path: `${out}/permit-sheet.png` });
  await page.click('#askOpts button:has-text("Deny")');
  check('Deny: the hook denies it', await waitFor(() => said('permit curl -s https://example.com: deny'), 10000));

  // 4. nobody answers the third: it doesn't run, the card says so, nothing waits any more
  check('no answer in time: denied, nothing ran', await waitFor(() => said('permit wget https://example.com/x: deny'), 30000));
  check('the card says nobody answered', await waitFor(async () => /Nobody answered/.test(await text(page, '#feed')), 5000));
  check('the bar goes away once nothing waits', await waitFor(async () => !(await page.isVisible('#askbar')), 5000));

  // 5. a reload replays the log: nothing waits
  await page.reload(); await sleep(2500);
  check('after a reload nothing waits', !(await page.isVisible('#askbar')) && (await page.evaluate(() => pending.size)) === 0);
  check('no page errors', !errs.length, errs.join(' | '));
  await browser.close();
  console.log(R.join('\n'));
  process.exit(R.some(r => r.startsWith('FAIL')) ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
