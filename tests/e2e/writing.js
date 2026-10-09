// usage: node writing.js <base-url> <out-dir> <scratch-dir>
// Room to write, and attachments in plain sight: home's box says files, images and links are welcome, grows, and has a
// big writing view; a text file attaches on home (that upload crashed before a session existed); the start window
// shows the whole task; NAVI's open question ("what should the council work on?") gets a roomy box with Attach in
// plain sight; the session's task opens in full from its header.
const { chromium } = require('playwright');
const { execFileSync } = require('child_process');
const fs = require('fs');
const [base, out, sp] = process.argv.slice(2);
const waitFor = async (fn, ms) => { const end = Date.now() + ms; while (Date.now() < end) { if (await fn()) return true; await new Promise(r => setTimeout(r, 200)); } return false; };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const R = []; const check = (n, ok, x = '') => R.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x && !ok ? '  · ' + x : ''}`);
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await ctx.addInitScript(() => { try { localStorage.setItem('navi.tour', '1'); } catch {} });
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(e.message));
  const uploads = []; page.on('response', r => { if (r.url().includes('/upload?') && r.request().method() === 'POST') uploads.push(r.status()); });
  try {
    await page.goto(base + '?skipboot'); await page.waitForSelector('#menu.show', { timeout: 8000 }); await sleep(400);
    check('home says files, images and links are welcome', /files, images and links/.test(await page.getAttribute('#mTask', 'placeholder')));
    const long = 'writing e2e: a long task. ' + 'Each section needs a heading, a short paragraph and a link to the docs. '.repeat(9) + 'Done when every link answers.';
    await page.fill('#mTask', long); await page.dispatchEvent('#mTask', 'input'); await sleep(200);
    const h1 = await page.$eval('#mTask', e => e.getBoundingClientRect().height);
    check('the box grows with a long task', h1 > 120, `${h1}px`);
    await page.click('#mBig'); await sleep(250);
    const h2 = await page.$eval('#mTask', e => e.getBoundingClientRect().height);
    check('⤢ gives it a big writing view (half the screen)', h2 >= 900 * 0.45, `${h2}px`);
    await page.screenshot({ path: `${out}/writing-big.png` });
    await page.click('#mBig'); await sleep(150);
    const note = `${sp}/writing-note.md`; fs.writeFileSync(note, '# a note\nfor the council\n');
    const [chooser] = await Promise.all([page.waitForEvent('filechooser'), page.click('#mClip')]);
    await chooser.setFiles(note); await sleep(300);
    check('a text file attaches on home: a chip', /writing-note\.md/.test(await page.textContent('#mChips')));
    await page.click('#mStart'); await page.waitForSelector('#launchP.show'); await sleep(400);
    const shown = await page.textContent('#lTask');
    check('the start window shows the whole task, not the first 220 characters', shown.includes('Done when every link answers.'), shown.slice(-80));
    await page.click('#lGo');
    await page.waitForURL(/\/s\/\d{8}-\d{6}/, { timeout: 15000 }); await sleep(1500);
    check('...and the text file uploads before the session exists (it used to fail)', uploads.length > 0 && uploads.every(s => s === 200), JSON.stringify(uploads));
    const sid = page.url().match(/\/s\/([\d-]+)/)[1];
    await page.click('#task'); await sleep(300);
    check('the session\'s task opens in full from the header', await page.isVisible('#modal.show') && (await page.textContent('#mbody')).includes('Done when every link answers.'));
    await page.keyboard.press('Escape'); await sleep(200);

    // NAVI's open question: room to write, Attach in plain sight
    execFileSync('navi', ['ask', '--from', 'navi', '--question', 'What should the council work on?', '--no-wait'],
                 { env: { ...process.env, NAVI_DIR: `${sp}/proj/.navi`, NAVI_SESSION: sid } });
    await page.waitForSelector('#askbar.show', { timeout: 10000 }).catch(() => {});
    await page.click('#askbar').catch(() => {}); await sleep(400);
    if (!(await page.isVisible('#askm.show'))) await page.evaluate(() => { const id = [...pending.keys()].pop(); if (id) openAsk(id); });
    await sleep(300);
    const box = await page.$eval('#askText', e => e.getBoundingClientRect().height).catch(() => 0);
    check('an open question gets a roomy answer box', await page.isVisible('#askm.free') && box >= 180, `${box}px`);
    check('...that says files, images and links can come along, with Attach in plain sight',
      /Paste or drop files, images and links/.test(await page.textContent('#askm')) && await page.isVisible('#askClip:has-text("Attach files or images")'));
    await page.screenshot({ path: `${out}/writing-ask.png` });
    await page.keyboard.press('Escape'); await sleep(200);

    // an agent's long question, written the way moderators write (one line, \n, Markdown): it reads as written
    const longQ = 'Given the plan, which way?\\n\\n**A) Reuse:** extend the `auth` module\\n**B) New:** a separate service\\n'
      + Array.from({length: 30}, (_, i) => `- point ${i} of the plan`).join('\\n');
    execFileSync('navi', ['ask', '--from', 'architect', '--question', longQ, '--option', 'A) reuse', '--option', 'B) new', '--no-wait'],
                 { env: { ...process.env, NAVI_DIR: `${sp}/proj/.navi`, NAVI_SESSION: sid } });
    await waitFor(() => page.evaluate(() => [...pending.values()].some(e => /Given the plan/.test(e.body || ''))), 10000);
    await page.evaluate(() => { const ev = [...pending.values()].find(e => /Given the plan/.test(e.body || '')); openAsk(ev.id); });
    await sleep(300);
    const q = await page.evaluate(() => ({lis: document.querySelectorAll('#askQ li').length, strong: document.querySelectorAll('#askQ strong').length,
      code: document.querySelectorAll('#askQ code').length, raw: /\\n|\*\*/.test($('#askQ').textContent), long: $('#askm').classList.contains('long'),
      w: $('#askm .sheet').getBoundingClientRect().width, scrolls: $('#askQ').scrollHeight > $('#askQ').clientHeight}));
    check('a long question reads as written: a list, bold and code shown as such, no \\n or **', q.lis === 30 && q.strong === 2 && q.code === 1 && !q.raw, JSON.stringify(q));
    check('...in a wider window, and it scrolls instead of running off', q.long && q.w > 700 && q.scrolls, JSON.stringify(q));
    await page.screenshot({ path: `${out}/writing-long-question.png` });
    check('no page errors', errs.length === 0, errs.join(' | '));
  } catch (e) {
    check('the run finished', false, e.message.split('\n')[0]);
  } finally { await browser.close(); }
  console.log(R.join('\n'));
  const failed = R.filter(x => x.startsWith('FAIL')).length;
  console.log(failed ? `WRITING SUITE FAILED: ${failed}` : 'WRITING SUITE PASSED');
  process.exit(failed ? 1 : 0);
})();
