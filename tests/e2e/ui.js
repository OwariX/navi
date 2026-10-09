// usage: node ui.js <base-url> <out-dir>
// The whole interface with real clicks: home, the launch sheet, panels, navigation, the switchboard, the palette, files.
// Expects the fixture project: an ended session 20261006-144220 and (optionally) more sessions next to it.
const { chromium } = require('playwright');
const [base, out, sp] = process.argv.slice(2);
const SID = '20261006-144220';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const R = []; const check = (n, ok, x = '') => R.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  · ' + x : ''}`);
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript(() => { try { localStorage.setItem('navi.tour', '1'); } catch {} });
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(e.message));
  page.on('dialog', d => d.accept(d.type() === 'prompt' ? 'renamed-by-test' : undefined));
  const shown = sel => page.$eval(sel, e => e.classList.contains('show')).catch(() => false);
  const home = async () => { await page.goto(base + '?skipboot'); await page.waitForSelector('#menu.show', { timeout: 8000 }); await sleep(600); };

  // ---- home
  await home();
  check('home opens on /', await shown('#menu'));
  check('home status line says how the council runs', (await page.textContent('#mStatus')).length > 10, await page.textContent('#mStatus'));
  const recent = await page.$$eval('#recentList .rrow', els => els.length);
  check('home lists sessions to continue', recent >= 1, String(recent));
  check('session-only buttons are hidden on home', !(await page.isVisible('#bNew')) && !(await page.isVisible('#cog')));
  await page.click('#mCouncil'); await sleep(300);
  const councils = await page.$$eval('#cPop .li', els => els.map(e => e.textContent.trim()));
  check('council picker lists councils + create/edit', councils.length >= 3, councils.join(' | '));
  await page.keyboard.press('Escape'); await sleep(200);
  check('Esc closes the council picker', !(await shown('#cPop')));

  // ---- where you are: folder, branch, git state; switch branch; switch folder and back
  const wsPath = await page.textContent('#wsPath'), wsBr = await page.textContent('#wsBr'), wsState = await page.textContent('#wsState');
  check('home says which folder and branch you work in', /proj$/.test(wsPath) && wsBr === 'main', `${wsPath} · ${wsBr}`);
  check('home says what is uncommitted, pushed or not', /1 uncommitted change/.test(wsState) && /Local only, no remote/.test(wsState) && /Last commit .*first page/.test(wsState), wsState);
  await page.click('#wsBranch'); await sleep(500);
  const brs = await page.$$eval('#brList .li b', els => els.map(e => e.textContent));
  check('the branch picker lists the branches', brs.includes('main') && brs.includes('feature/demo'), brs.join(','));
  await page.click('#brList .li:has-text("feature/demo")'); await sleep(900);
  check('switching branch updates the home line', (await page.textContent('#wsBr')) === 'feature/demo');
  await page.click('#wsBranch'); await sleep(400); await page.fill('#brIn', 'try/ui-test'); await sleep(200);
  check('typing a new name offers to create it', /Create “try\/ui-test”/.test(await page.textContent('#brList')));
  await page.keyboard.press('Enter'); await sleep(900);
  check('Enter creates and switches to it', (await page.textContent('#wsBr')) === 'try/ui-test');
  await page.click('#wsBranch'); await sleep(400); await page.click('#brList .li:has-text("main")'); await sleep(900);
  await page.screenshot({ path: `${out}/ui-home-ws.png` });
  // HALLOWEEN 2026: delete at the start of November (with the pumpkin itself)
  const pk = await page.evaluate(() => ({hidden: $('#pumpkin').hidden, october: new Date().getMonth() === 9}));
  check('the Halloween pumpkin shows in October only', pk.hidden === !pk.october, JSON.stringify(pk));
  if (pk.october){
    await page.click('#pumpkin'); await sleep(250);
    check('...and says boo when you click it', await page.evaluate(() => $('#pumpkin').classList.contains('boo')));
    await page.screenshot({ path: `${out}/ui-pumpkin.png`, clip: { x: 300, y: 0, width: 840, height: 260 } });
  }
  await page.click('#wsFolder'); await sleep(700);
  check('the folder picker shows recent folders and the folder browser', /Recent/.test(await page.textContent('#fsPop')) && (await page.$$eval('#fsPop .li', e => e.length)) >= 2);
  await page.fill('#fsPop .fsin input', sp + '/other'); await page.keyboard.press('Enter'); await sleep(600);
  await page.click('#fsPop .fsfoot .btn'); await page.waitForURL(base, { timeout: 8000 }); await sleep(1500);
  check('working in another folder: same tab, new folder', /other$/.test(await page.textContent('#wsPath')) && !(await page.isVisible('#wsBranch')), await page.textContent('#wsState'));
  await page.click('#wsFolder'); await sleep(700);
  await page.click('#fsPop .li:has-text("proj")'); await page.waitForURL(base, { timeout: 8000 }); await sleep(1500);
  check('and back again from Recent', /proj$/.test(await page.textContent('#wsPath')) && (await page.textContent('#wsBr')) === 'main');

  // ---- launch sheet: model, effort, pace, data, every time
  await page.fill('#mTask', 'a test html page');
  await page.click('#mStart'); await sleep(500);
  check('Start opens the launch sheet', await shown('#launchP'));
  const models = await page.$$eval('#lModels .opt b', els => els.map(e => e.textContent));
  check('launch sheet: five model choices, Codex nowhere', models.join(',') === 'Default,Fable,Opus,Sonnet,Haiku', models.join(','));
  const efforts = await page.$$eval('#lEffort button', els => els.map(e => e.textContent));
  check('launch sheet: effort, defaulting to the pace', efforts.length === 6 && /By pace/.test(efforts[0]), efforts.join(','));
  await page.click('#lPace .opt:nth-child(2)'); await sleep(150);
  const eff2 = await page.textContent('#lEffort button:first-child');
  check('picking Quick makes the pace effort Low', /Low/.test(eff2), eff2);
  check('in Quick the agents choice explains that NAVI plays every seat', (await page.$$eval('#lAgents button', els => els.every(e => e.disabled))) && /Quick: NAVI plays every seat itself/.test(await page.textContent('#lAgentsHint')), await page.textContent('#lAgentsHint'));
  const paces = await page.$$eval('#lPace .opt b', els => els.map(e => e.textContent));
  check('launch sheet: four paces', paces.join(',') === 'Auto,Quick,Standard,Thorough', paces.join(','));
  const where = await page.textContent('#lBranchSec');
  check('launch sheet: where it runs, and a new-branch option', /proj/.test(where) && /Stay on main/.test(where) && /New branch for this session/.test(where), where.replace(/\s+/g, ' '));
  await page.screenshot({ path: `${out}/ui-launch.png` });
  await page.keyboard.press('Escape'); await sleep(300);
  check('Esc closes the launch sheet back to home', !(await shown('#launchP')) && await shown('#menu'));
  check('the launch sheet offers every engine that is installed (Codex and Gemini are engines now)',
    (await page.$$eval('#lEngines .opt b', els => els.map(e => e.textContent))).join('|') === 'Claude|Local (Ollama)|Codex|Local (Ollama) via Codex|Gemini');

  // ---- panels from home: open, close with Esc, back to home
  for (const [btn, panel] of [['#tAgents', '#agentsP'], ['#tCouncils', '#councilsP'], ['#tSettings', '#setup'], ['#tSessions', '#sessionsP']]) {
    await home(); await page.click(btn); await sleep(700);
    check(`${btn} opens ${panel}`, await shown(panel));
    await page.keyboard.press('Escape'); await sleep(500);
    check(`${panel} closes with Esc, back to home`, !(await shown(panel)) && await shown('#menu'));
  }

  // ---- agents: built-in read-only, new agent form, score
  await home(); await page.click('#tAgents'); await sleep(700);
  const agents = await page.$$eval('#agList .li', els => els.length);
  check('agents list shows the five Knights', agents === 5, String(agents));
  check('a built-in shows a grade', /Grade A/.test(await page.textContent('#aScore')), await page.textContent('#aScore'));
  check('a built-in is read-only (no Save, describe box hidden)', !(await page.isVisible('#aSave')) && !(await page.isVisible('#aGenSec')));
  await page.click('#aNew'); await sleep(300);
  check('New agent: name, role and describe box', await page.isVisible('#aName') && await page.isVisible('#aHelp') && await page.isVisible('#aGenerate'));
  await page.fill('#aName', 'k8s'); await page.fill('#aRole', 'kubernetes reviewer'); await page.click('#aTemplate'); await sleep(600);
  const grade = await page.textContent('#aScore');
  check('template fills instructions and scores them', /Grade/.test(grade), grade);
  // with instructions there, the box changes them instead of writing them again
  const gen = () => page.evaluate(() => ({lbl: $('#aGenLbl').textContent, btn: $('#aGenTxt').textContent, again: !$('#aRewrite').hidden, tpl: !$('#aTemplate').hidden}));
  let g = await gen();
  check('once it has instructions, the box offers a change (only that), and still a fresh start', /Change something/.test(g.lbl) && g.btn === 'Make the change' && g.again && !g.tpl, JSON.stringify(g));
  const before = await page.inputValue('#aDirective');
  await page.fill('#aHelp', 'Also check that every pod sets resource limits');
  await page.click('#aGenerate');
  await page.waitForFunction(() => /Changed/.test($('#aJob').textContent) || $('#aErr').textContent, null, { timeout: 20000 }).catch(() => {});
  const changed = await page.inputValue('#aDirective');
  const diff = await page.evaluate(() => ({shown: !$('#aDiff').hidden, adds: [...document.querySelectorAll('#aDiff .dl.add')].map(e => e.textContent),
    dels: document.querySelectorAll('#aDiff .dl.del').length, head: $('#aDiff .dh')?.textContent || '', job: $('#aJob').textContent, err: $('#aErr').textContent}));
  check('Make the change: the rest stays word for word, the new line is added', changed.startsWith(before.split('\n').slice(0, 3).join('\n')) && /resource limits/.test(changed)
    && changed.split('\n').length === before.split('\n').length + 1, JSON.stringify(diff));
  check('...and the change is shown line by line: what was added, nothing removed', diff.shown && diff.adds.length === 1 && /\+ .*resource limits/.test(diff.adds[0]) && diff.dels === 0
    && /1 line added/.test(diff.head), JSON.stringify(diff));
  check('...the box is empty for the next change', (await page.inputValue('#aHelp')) === '');
  await page.screenshot({ path: `${out}/ui-agent-change.png` });
  await page.click('#aDiff .btn:has-text("Undo the change")'); await sleep(200);
  check('Undo puts it back as it was, and the words back in the box to try again', (await page.inputValue('#aDirective')) === before && (await page.isHidden('#aDiff'))
    && /resource limits/.test(await page.inputValue('#aHelp')));
  await page.fill('#aDirective', ''); await page.dispatchEvent('#aDirective', 'input');
  g = await gen();
  check('with no instructions, it writes them again (Write it for me)', g.btn === 'Write it for me' && !g.again && g.tpl, JSON.stringify(g));
  await page.keyboard.press('Escape'); await sleep(300);

  // ---- councils: read-only built-in, duplicate into a roster, add/remove, roles, flow sentence
  await home(); await page.click('#tCouncils'); await sleep(800);
  check('built-in council is read-only with a duplicate offer', await page.isVisible('#coRo') && !(await page.isVisible('#coSave')));
  const mem = await page.$$eval('#coRoster .mem', els => els.length);
  check('the roster shows its 5 members', mem === 5, String(mem));
  check('the flow sentence explains the council', /proposes and builds/.test(await page.textContent('#coFlow')));
  await page.click('#coRoDup'); await sleep(400);
  check('Duplicate makes it editable', await page.isVisible('#coSave') && await page.isVisible('#coAdd'));
  // remove two members: a council of 3
  await page.click('#coRoster .mem:nth-child(3) .ib'); await sleep(150);
  await page.click('#coRoster .mem:nth-child(3) .ib'); await sleep(150);
  const left = await page.$$eval('#coRoster .mem', els => els.map(e => e.querySelector('.n b').textContent));
  check('members can be removed (any size)', left.length === 3, left.join(','));
  // make the second member the lead: the old lead becomes a reviewer
  await page.selectOption('#coRoster .mem:nth-child(2) select:first-of-type', 'lead'); await sleep(200);
  const seats = await page.$$eval('#coRoster .mem', els => els.map(e => e.querySelector('.n b').textContent + ':' + e.querySelector('select').value));
  check('one lead at a time: the old lead steps down', seats.filter(s => s.endsWith(':lead')).length === 1, seats.join(','));
  // add a brand-new agent inline
  await page.click('#coAdd'); await sleep(300);
  check('Add agent opens the picker', await shown('#addPop'));
  await page.click('#addNewBtn'); await page.fill('#naName', 'gdpr'); await page.fill('#naRole', 'privacy'); await page.fill('#naBrief', 'checks personal data handling'); await page.click('#naAdd'); await sleep(300);
  const after = await page.$$eval('#coRoster .mem', els => els.map(e => e.querySelector('.n b').textContent));
  check('a new agent joins the roster, marked new', after.length === 4 && await page.isVisible('#coRoster .mem.new'), after.join(','));
  await page.screenshot({ path: `${out}/ui-council-roster.png` });
  await page.keyboard.press('Escape'); await sleep(300);

  // ---- a session page: crumbs, switcher, tabs, filter, files, palette
  await page.goto(`${base}s/${SID}?skipboot`); await sleep(3500);
  check('the top bar shows the folder and branch on a session page', (await page.isVisible('#wsTop')) && (await page.textContent('#wsTopBr')) === 'main');
  check('breadcrumb shows Sessions / name', /Sessions/.test(await page.textContent('#crumbs')) && (await page.textContent('#crumbs .cur')).length > 2, await page.textContent('#crumbs'));
  await page.click('#crumbs .cur'); await sleep(300);
  const sw = await page.$$eval('#swPop .li', els => els.length);
  check('the session switcher lists sessions and actions', sw >= 4, String(sw));
  await page.keyboard.press('Escape'); await sleep(200);
  check('the stepper shows the phases', (await page.$$eval('#steps .s', els => els.length)) >= 4);
  const metaTxt = await page.textContent('#meta');
  check('a finished session ends on Done and says how long it took', await page.$('#steps .s.fin') !== null && /took \d+:\d\d/.test(metaTxt), metaTxt);
  check('system chatter is folded into lines', (await page.$$eval('#feed .sysg', els => els.length)) >= 1);
  await page.click('#fBtn'); await sleep(200); await page.click('#fpop button[data-f="think"]'); await sleep(300);
  const vis = await page.$$eval('#feed > *', els => els.filter(e => !e.hidden).map(e => e.dataset.cat || e.className));
  check('filter: thoughts only', vis.length > 0 && vis.every(c => c === 'think'), `${vis.length} visible`);
  await page.click('#fBtn'); await sleep(200); await page.click('#fpop button[data-f="all"]'); await sleep(200);
  await page.click('#tabs button[data-tab="files"]'); await sleep(300);
  const files = await page.$$eval('#artlist .frow', els => els.length);
  check('Files tab lists the deliverables', files >= 1, String(files));
  await page.click('#artlist .frow'); await sleep(600);
  check('a Markdown deliverable renders as a document', await page.$eval('#mdoc', e => e.classList.contains('show') && !!e.querySelector('h1, h2')));
  await page.keyboard.press('Escape'); await sleep(200);
  await page.click('#tabs button[data-tab="council"]'); await sleep(300);
  check('Council tab lists the agents', (await page.$$eval('#clist .crow', els => els.length)) >= 4);
  await page.keyboard.press('Meta+k'); await sleep(300);
  check('⌘K opens the palette', await shown('#pal'));
  await page.type('#palIn', 'export'); await sleep(150);
  check('the palette filters commands', (await page.$$eval('#palList .it', els => els.length)) === 1);
  await page.keyboard.press('Escape'); await sleep(200);
  await page.click('#crumbs .cur'); await sleep(200);
  await page.click('#swPop .li:has-text("Rename this session")'); await sleep(800);
  check('rename from the switcher', (await page.textContent('#crumbs .cur')).includes('renamed-by-test'), await page.textContent('#crumbs .cur'));
  await page.evaluate(sid => fetch('/sessions/rename', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Navi-Token': TOKEN }, body: JSON.stringify({ id: sid, name: 'flappy-bird-clone' }) }), SID);

  // ---- the switchboard and new session from a session page
  await page.click('#crumbs a'); await sleep(800);
  check('Sessions in the breadcrumb opens the switchboard', await shown('#sessionsP'));
  const cards = await page.$$eval('#sessList .scard:not(.new)', els => els.length);
  check('one card per session', cards >= 1, String(cards));
  await page.click('#sessFilters button[data-sf="ended"]'); await sleep(200);
  const ended = await page.$$eval('#sessList .scard:not(.new) .tag', els => els.map(e => e.textContent));
  check('filter: ended', ended.length >= 1 && ended.every(t => /Ended/.test(t)), ended.join(','));
  await page.keyboard.press('Escape'); await sleep(200);
  await page.click('#bNew'); await sleep(1500);
  check('New session from a session page goes home, task box focused', await shown('#menu') && await page.evaluate(() => document.activeElement?.id === 'mTask'));
  const quickSid = await page.evaluate(async () => (await (await fetch('/sessions')).json()).find(s => s.task === 'a quick landing page')?.id);
  await page.goto(`${base}s/${quickSid}?skipboot`); await sleep(2500);
  check('a session page shows the branch it works on', /main/.test(await page.textContent('#meta')), await page.textContent('#meta'));
  check('the console shows where commands run, like a shell prompt', /proj ⎇ main$/.test(await page.textContent('#cwd')), await page.textContent('#cwd'));
  await page.fill('#cin', '/pwd'); await page.keyboard.press('Enter'); await sleep(250);
  check('/pwd says the folder and the branch', /proj · branch main/.test(await page.textContent('#cmsg')), await page.textContent('#cmsg'));
  await page.click('#tabs button[data-tab="files"]'); await sleep(300);
  const rows = await page.$$eval('#artlist .frow', els => els.map(e => e.innerText.replace(/\s+/g, ' ')));
  check('a real project file is listed as a deliverable, with where it lives', rows.some(r => /the landing page/.test(r) && /index\.html \(in the project\)/.test(r)), rows.join(' | '));
  const opened = () => { try { return require('fs').readFileSync(sp + '/opened.log', 'utf8'); } catch { return ''; } };
  await page.hover('#artlist .frow:has-text("the landing page")'); await page.click('#artlist .frow:has-text("the landing page") .fa .ib >> nth=0'); await sleep(500);
  check('Open opens the real project file with its app', /^open .*\/proj\/index\.html$/m.test(opened()), opened().trim());
  await page.click('#artlist .frow:has-text("the landing page") .fa .ib >> nth=1'); await sleep(500);
  check(`Show in Finder reveals it`, /^reveal .*\/proj\/index\.html$/m.test(opened()));
  await page.hover('#artlist .frow:has-text("the start script")'); await page.click('#artlist .frow:has-text("the start script") .fa .ib >> nth=0'); await sleep(500);
  check('a script is only ever shown, never run', /^reveal .*\/proj\/start\.sh$/m.test(opened()) && !/^open .*start\.sh$/m.test(opened()) && /never runs scripts/.test(await page.textContent('#cmsg')), await page.textContent('#cmsg'));
  await page.goto(`${base}all?skipboot`); await sleep(1500);
  check('/all opens the switchboard', await shown('#sessionsP'));
  const contBtn = page.locator('#sessList .scard:not(.new) button:has-text("Continue")').first();
  if (await contBtn.count()) {
    await contBtn.click(); await sleep(500);
    const lc = await page.textContent("#lCouncil"), e0 = await page.textContent('#lEffort button:first-child');
    check('Continue keeps the session pace (Quick, effort Low)', await shown('#launchP') && /Knights/.test(lc) && /Quick pace/.test(lc) && /Low/.test(e0) && !(await page.isVisible('#lPace')), `${lc} / ${e0}`);
    await page.keyboard.press('Escape'); await sleep(300);
  } else check('an open session offers Continue', false);
  await page.goto(`${base}s/${SID}?skipboot`); await sleep(2000);
  await page.click('#brand'); await sleep(1200);
  check('the wordmark goes home', new URL(page.url()).pathname === '/');

  // ---- the look follows in every open tab
  const other = await ctx.newPage(); await other.goto(`${base}s/${SID}?skipboot`); await sleep(1500);
  await page.goto(base + '?skipboot'); await sleep(1200);
  await page.evaluate(() => post('/settings', {...S, theme: 'minidark'})); await sleep(900);
  check('a theme picked in one tab shows in the other open tabs', await other.evaluate(() => document.documentElement.dataset.theme) === 'minidark');
  await page.evaluate(() => post('/settings', {...S, theme: 'wired'})); await sleep(600); await other.close();
  console.log(R.join('\n')); console.log('page errors:', errs.length ? errs : 'none');
  await browser.close();
  process.exit(R.some(r => r.startsWith('FAIL')) || errs.length ? 1 : 0);
})().catch(e => { console.log(R.join('\n')); console.error('UI FAIL', e.message); process.exit(1); });
