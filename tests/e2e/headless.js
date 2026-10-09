// usage: node headless.js <base-url> <out-dir> <fake-log>
// A real launch through the launch sheet with a background (headless) moderator, played by the fake claude:
// pace Quick -> effort low on the command line, the live trace on the NAVI node, slash commands, cost on CONSENSUS.
const { chromium } = require('playwright');
const fs = require('fs');
const [base, out, fakeLog] = process.argv.slice(2);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const waitFor = async (fn, ms) => { const end = Date.now() + ms; while (Date.now() < end) { if (await fn()) return true; await sleep(300); } return false; };
const R = []; const check = (n, ok, x = '') => R.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  · ' + x : ''}`);
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  // which button NAVI focuses when CONSENSUS opens (the test's own clicks race the session's end, so read what it did)
  await ctx.addInitScript(() => {
    const f = HTMLElement.prototype.focus;
    HTMLElement.prototype.focus = function (...a) { if (this.id === 'stay' || this.id === 'openDemo') window.__consFocus = this.id; return f.apply(this, a); };
  });
  await ctx.addInitScript(() => { try { localStorage.setItem('navi.tour', '1'); } catch {} });
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(e.message));
  await page.goto(base + '?skipboot'); await page.waitForSelector('#menu.show', { timeout: 8000 }); await sleep(500);
  await page.fill('#mTask', 'a test html page');
  await page.click('#mStart'); await sleep(400);
  await page.click('#lPace .opt:has-text("Quick")'); await page.click('#lModels .opt:has-text("Sonnet")'); await page.click('#lBranch button:has-text("New branch")'); await sleep(150);
  check('the launch sheet asks for the permission mode (Ask me by default)', (await page.$$eval('#lPerms .opt', els => els.map(e => e.querySelector('b').textContent))).join(',') === 'Ask me,Auto,Allow all,Skip permissions'
    && /Ask me/.test(await page.textContent('#lPerms .opt.on')));
  await page.click('#lPerms .opt:has-text("Allow all")'); await sleep(100);
  const byHand = async (kind, value) => {     // Add a source of truth → Enter it by hand → one row → Add it
    await page.click('#lSources .srcopen'); await page.click('#lSources .srcbox .btn.ghost');
    await page.selectOption('#lSources .srow select', kind); await page.fill('#lSources .srow .in.v', value);
    await page.click('#lSources .srcgo'); await sleep(400);
  };
  await byHand('mcp', 'obsidian');
  check('Sources of truth: an MCP server added in the launch sheet shows as a chip', /MCP server\s*obsidian/.test(await page.textContent('#lSources .srcs')), await page.textContent('#lSources'));
  await byHand('folder', '/no/such/folder');
  check('...a folder that does not exist: NAVI says so before it adds it', /Nothing there on this machine/.test(await page.textContent('#lSources .srcbox')), await page.textContent('#lSources'));
  await page.keyboard.press('Escape'); await sleep(150);
  check('...Esc closes the box, the launch sheet stays', !(await page.isVisible('#lSources .srcbox')) && await page.isVisible('#launchP'));
  await page.click('#lGo');
  await page.waitForURL(/\/s\/\d{8}-\d{6}/, { timeout: 10000 });
  const firstSid = page.url().match(/\/s\/([\d-]+)/)[1];

  await sleep(1500);
  const early = await page.evaluate(() => hub.status && hub.status.text);
  check('the hub shows the moderator starting', /connecting|council seated/.test(early || ''), early);
  await sleep(5000);
  const argv = fs.existsSync(fakeLog) ? fs.readFileSync(fakeLog, 'utf8').split('hid=')[0] : '';
  check('launched with --effort low (Quick) and --model sonnet', /\[--effort\]\n  \[low\]/.test(argv) && /\[--model\]\n  \[sonnet\]/.test(argv));
  check('"Allow all" launches with --permission-mode bypassPermissions, WARDEN still on', /\[--permission-mode\]\n  \[bypassPermissions\]/.test(argv) && /PreToolUse/.test(argv));
  check('the session header says Allow all', /Allow all/.test(await page.textContent('#meta')), await page.textContent('#meta'));
  const brEv = await page.$$eval('#feed .ev.alert', els => els.map(e => e.innerText.replace(/\s+/g, ' ')).filter(t => /branch/i.test(t)));
  check('"New branch for this session" made navi/<name> and the feed says so', brEv.some(t => /New branch/.test(t) && /navi\/test-html-page/.test(t) && /from main/.test(t)), brEv.join(' | '));
  check('the top bar follows the new branch', /^navi\//.test(await page.textContent('#wsTopBr')), await page.textContent('#wsTopBr'));
  const pill = await page.textContent('#modPill');
  check('the top bar shows the live moderator', /Sonnet/.test(pill) && /Low/.test(pill), pill);
  const chips = await page.textContent('#meta');
  check('the header shows the pace', /Quick/.test(chips), chips);
  const trace = await page.evaluate(() => traceLog.length);
  check('trace events stream in', trace >= 2, String(trace));
  const agentsFile = (argv.match(/\[--agents\]\n  \[([^\]]+)\]/) || [])[1];
  let defs = {}; try { defs = JSON.parse(fs.readFileSync(agentsFile, 'utf8')); } catch {}
  check('every member is registered as a subagent type: its instructions, its model, the session effort',
    defs.adversary?.model === 'sonnet' && defs.scribe?.model === 'haiku' && defs.architect?.model === 'inherit'
    && Object.values(defs).every(d => d.effort === 'low' && /NAVI rules/.test(d.prompt) && /MCP server obsidian/.test(d.prompt)) && Object.keys(defs).length === 5,
    JSON.stringify(Object.fromEntries(Object.entries(defs).map(([k, v]) => [k, `${v.model}/${v.effort}`]))));
  check('tokens show in the session header while it runs', await waitFor(async () => /tokens/.test(await page.textContent('#meta')), 10000), await page.textContent('#meta'));
  await page.click('#modPill'); await sleep(700);
  const rows = await page.$$eval('#tracelist .t', els => els.map(e => e.textContent.slice(0, 40)));
  check('the NAVI card shows what Claude is doing', rows.length >= 2, rows.join(' | '));
  await page.screenshot({ path: `${out}/headless-card.png` });
  await page.keyboard.press('Escape');
  await page.waitForSelector('#consensus.show', { timeout: 60000 });
  const cost = await waitFor(async () => /\$0\.42/.test(await page.textContent('#sumCost')), 15000);
  const sumCost = await page.textContent('#sumCost');
  check('CONSENSUS shows how long it took, turns and cost', cost && /Done in \d+:\d\d/.test(sumCost), sumCost);
  check('...and the tokens, per model as Claude Code counted them', /70k tokens/.test(sumCost) && /Opus 5: .*cached.*\$0\.30/.test(await page.getAttribute('#sumCost', 'title')) && /Sonnet 5\.5/.test(await page.getAttribute('#sumCost', 'title')),
    `${sumCost} | ${await page.getAttribute('#sumCost', 'title')}`);
  check('the idle background moderator is told to leave after the end', /stop now/.test(fs.readFileSync(fakeLog, 'utf8')));
  const fin = await waitFor(async () => (await page.evaluate(() => hub.status && hub.status.text)) === 'finished', 8000);
  check('once it leaves, the hub says finished (not connecting)', fin, await page.evaluate(() => JSON.stringify({hub: hub.status?.text, mod: MOD?.mode})));
  const cbtn = await page.$$eval('#consensus .next button', els => els.filter(e => e.offsetParent !== null).map(e => e.textContent));
  check('CONSENSUS offers going back to the chat or running the council again', cbtn.includes('Back to chat') && cbtn.includes('Run the council again'), cbtn.join(' | '));
  await waitFor(() => page.evaluate(() => !!window.__consFocus), 5000);       // NAVI focuses it a moment after CONSENSUS opens
  check('Back to chat is the default (NAVI focuses it when CONSENSUS opens; it is the primary)', await page.evaluate(() => window.__consFocus === 'stay' && $('#stay').classList.contains('pri')),
    await page.evaluate(() => `focused: ${window.__consFocus} · stay: ${$('#stay').className}`));
  await page.fill('#nextTask', 'add a footer'); await page.click('#newTask');
  const read = () => fs.readFileSync(fakeLog, 'utf8');
  const woke = await waitFor(() => /wrote to you in the interface/.test(read()) && /add a footer/.test(read()) && /followup handled/.test(read()), 20000);
  check('writing after the end wakes NAVI on the same conversation (--resume)', woke && /\[--resume\]/.test(read().split('add a footer')[0]));
  await sleep(3500);
  check('the council shows offline, the console is a chat with NAVI', /Council offline/.test(await page.textContent('#meta')) && /Chat with NAVI/.test(await page.getAttribute('#cin', 'placeholder')), await page.textContent('#meta'));
  const offline = await page.evaluate(() => [...nodes.values()].filter(n => n !== hub && n.id !== 'user').every(n => n.status?.state === 'offline'));
  check('every council node is offline', offline);
  // the console, in chat mode (typed here, after CONSENSUS: during the run it would race the end for the focus)
  await page.click('#cin'); await page.type('#cin', '/he'); await sleep(150);
  check('typing / shows command hints', /\/help/.test(await page.textContent('#cmsg')));
  await page.fill('#cin', '/help'); await page.keyboard.press('Enter'); await sleep(150);
  check('/help lists the commands', /\/end/.test(await page.textContent('#cmsg')));
  await page.fill('#cin', ''); await page.keyboard.press('ArrowUp'); await sleep(100);
  check('↑ brings back what you typed', (await page.inputValue('#cin')) === '/help');
  await page.fill('#cin', 'make the title bigger'); await page.keyboard.press('Enter'); await sleep(400);
  check('the console says NAVI is resuming', /resuming|Sent to NAVI/.test(await page.textContent('#cmsg')), await page.textContent('#cmsg'));
  const chat = await waitFor(async () => (await page.$$eval('#feed .ev.chat', els => els.map(e => e.innerText).join(' '))).includes('the title is bigger'), 25000);
  check('chat: NAVI answers you right in the feed', chat);
  check('chat: the answer shows in full, no click needed', await page.$eval('#feed .ev.chat .eb', e => getComputedStyle(e).maxHeight === 'none' && !e.onclick));
  await page.screenshot({ path: `${out}/headless-chat.png` });
  await page.click('#crumbs a'); await sleep(900);
  const meta = await page.$$eval('#sessList .scard .meta', els => els.map(e => e.textContent));
  check('the switchboard card shows the cost', meta.some(m => /\$0\.4\d/.test(m)), meta.join(' | '));
  // a second council, with every agent on the moderator's model
  await page.goto(base + '?skipboot'); await page.waitForSelector('#menu.show', { timeout: 8000 }); await sleep(500);
  await page.fill('#mTask', 'agents on one model'); await page.click('#mStart'); await sleep(400);
  await page.click('#lPace .opt:has-text("Standard")'); await page.click('#lModels .opt:has-text("Sonnet")'); await sleep(150);
  const agOpts = await page.$$eval('#lAgents button', els => els.map(e => e.textContent));
  check("the launch sheet offers the council's models, NAVI picking per task, or everyone on the moderator's", agOpts.join('|') === 'The council’s models|NAVI picks per task|Everyone on Sonnet', agOpts.join('|'));
  await page.click('#lAgents button:has-text("Everyone on Sonnet")'); await page.click('#lGo');
  await page.waitForURL(u => /\/s\/\d{8}-\d{6}/.test(u.toString()) && !u.toString().includes(firstSid), { timeout: 10000 }); await sleep(1500);
  const mdl = await page.evaluate(async () => (await (await fetch(api('/log'))).json()).filter(e => e.type === 'model').map(e => e.agent + ':' + (e.model || 'inherit')));
  check('"Everyone on Sonnet" puts every agent on the moderator\'s model', ['adversary', 'ledger', 'scribe', 'warden'].every(a => mdl.includes(a + ':inherit')), mdl.join(','));
  console.log(R.join('\n')); console.log('page errors:', errs.length ? errs : 'none');
  await browser.close();
  process.exit(R.some(r => r.startsWith('FAIL')) || errs.length ? 1 : 0);
})().catch(e => { console.log(R.join('\n')); console.error('HEADLESS FAIL', e.message); process.exit(1); });
