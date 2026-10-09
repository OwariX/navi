// usage: node engines.js <base-url> <out-dir>
// The engines in the interface, against the fakes (tests/run.sh: fake codex and gemini on the PATH, a fake Ollama):
// Settings > Engine (pick one, a model per tier, Test it, save), the launch sheet's Engine row (the models, effort and
// permissions follow it; `?engine=` starts it on one), a council started on Local (its header says so), the model
// pickers in the agent and council editors. It puts your default back to Claude at the end.
const { chromium } = require('playwright');
const [base, out] = process.argv.slice(2);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const waitFor = async (fn, ms) => { const end = Date.now() + ms; while (Date.now() < end) { if (await fn()) return true; await sleep(200); } return false; };
const R = []; const check = (n, ok, x = '') => R.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  · ' + x : ''}`);
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript(() => { try { localStorage.setItem('navi.tour', '1'); } catch {} });
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(e.message));
  const text = sel => page.$eval(sel, e => e.textContent).catch(() => '');
  const opts = sel => page.$$eval(sel, els => els.map(e => e.textContent));
  const api = (p, b) => page.evaluate(([p, b]) => post(p, b), [p, b]);
  try {
    await page.goto(base + '?skipboot'); await page.waitForSelector('#menu.show', { timeout: 8000 }); await sleep(500);

    // ---- Settings > Engine
    await page.click('#tSettings'); await page.waitForSelector('#setup.show'); await sleep(300);
    const cards = await opts('#sEngines .opt b');
    check('Settings shows every engine that is installed', cards.join('|') === 'Claude|Local (Ollama)|Codex|Local (Ollama) via Codex|Gemini', cards.join('|'));
    await page.click('#sEngines .opt:has-text("Local (Ollama)") >> nth=0'); await sleep(150);
    const tiers = await page.$$eval('#sTiers select.tier', els => els.map(e => e.value));
    check('picking Local shows a model per tier, from Ollama', tiers.join('|') === 'qwen3-coder:30b|qwen3-coder:30b|qwen2.5:7b', tiers.join('|'));
    check('...and what works on it', /registered with their own models · hard guard · permission cards/.test(await text('#sEngCan')), await text('#sEngCan'));
    const fastOpts = await page.$eval('#sTiers select.tier >> nth=2', e => [...e.options].map(o => o.value));
    check('a tier offers the models that can use tools (not the ones that can\'t)', fastOpts.includes('gpt-oss:20b') && !fastOpts.includes('tinyllama:latest'), fastOpts.join(','));
    await page.selectOption('#sTiers select.tier >> nth=2', 'gpt-oss:20b');
    check('local engines show the window they run with (64k)', await page.$eval('#sTiers select.win', e => e.value) === '65536');
    await page.click('#sEngTest');
    check('Test it asks the fast model one question and shows the answer', await waitFor(async () => /gpt-oss:20b answered in [\d.]+s: “NAVI ONLINE”/.test(await text('#sEngNote')), 15000), await text('#sEngNote'));
    await page.screenshot({ path: `${out}/engines-settings.png` });
    await page.click('#sNext'); await sleep(600);
    const saved = await page.evaluate(() => fetch('/settings').then(r => r.json()));
    check('Save keeps the engine and the model you picked', saved.engine === 'local' && saved.engines?.local?.models?.fast === 'gpt-oss:20b', JSON.stringify({ e: saved.engine, m: saved.engines?.local }));
    if (!(await page.isVisible('#menu.show'))) { await page.goto(base + '?skipboot'); await page.waitForSelector('#menu.show', { timeout: 8000 }); }
    await sleep(400);
    check('home says where councils run', /on Local \(Ollama\)/.test(await text('#mStatus')), await text('#mStatus'));

    // ---- the launch sheet follows the engine
    await page.click('#mStart'); await page.waitForSelector('#launchP.show'); await sleep(300);
    check('the launch sheet starts on your default engine', /Local \(Ollama\)/.test(await text('#lEngines .opt.on')), await text('#lEngines .opt.on'));
    let models = await opts('#lModels .opt b');
    check('on Local the models are tiers, with the model each one is', models.join('|') === 'Default|Strong|Balanced|Fast'
      && /gpt-oss:20b/.test(await text('#lModels .opt:nth-child(4)')), models.join('|') + ' · ' + await text('#lModels .opt:nth-child(4)'));
    check('...no effort (local models have none)', !(await page.isVisible('#lEffortSec')));
    check('...and no Auto mode, saying why', await page.$eval('#lPerms .opt:nth-child(2)', e => e.disabled && /Not on Local/.test(e.textContent)));
    await page.screenshot({ path: `${out}/engines-launch-local.png` });
    await page.click('#lEngines .opt:has-text("Claude")'); await sleep(150);
    models = await opts('#lModels .opt b');
    check('switching to Claude: its models, effort, Auto', models.join('|') === 'Default|Fable|Opus|Sonnet|Haiku' && await page.isVisible('#lEffortSec')
      && await page.$eval('#lPerms .opt:nth-child(2)', e => !e.disabled), models.join('|'));
    check('...and it says that\'s just this time', /just this time/.test(await text('#lEngineHint')), await text('#lEngineHint'));
    await page.click('#lEngines .opt:has-text("Codex") >> nth=0'); await sleep(150);
    check('Codex: its tiers are its models, Ask me says it can\'t stop to ask', /gpt-test-sol/.test(await text('#lModels'))
      && /can't stop to ask/.test(await text('#lPerms .opt:nth-child(1)')), await text('#lPerms .opt:nth-child(1)'));
    await page.click('#lEngines .opt:has-text("Gemini")'); await sleep(150);
    check('Gemini has the hard guard, and says it has no permission cards', /hard guard/.test(await text('#lEngineCan')) && !/no hard guard/.test(await text('#lEngineCan')) && /no permission cards/.test(await text('#lEngineCan')), await text('#lEngineCan'));
    await page.click('#lEngines .opt:has-text("Local (Ollama)") >> nth=0'); await sleep(100);
    await page.click('#lModels .opt:has-text("Balanced")'); await sleep(100);
    await page.click('#lGo');
    await page.waitForURL(/\/s\/\d{8}-\d{6}/, { timeout: 15000 }); await sleep(2500);
    const sid = page.url().match(/\/s\/([\d-]+)/)[1];
    const meta = await page.evaluate(s => fetch('/sessions').then(r => r.json()).then(xs => xs.find(x => x.id === s)), sid);
    check('the council starts on Local', meta?.engine === 'local', JSON.stringify(meta && { engine: meta.engine }));
    check('...and its header says so', await waitFor(async () => /Local \(Ollama\)/.test(await text('#meta')), 8000), await text('#meta'));
    const pill = await text('#modPill');
    check('NAVI\'s pill shows its model on this engine', /Balanced · qwen3-coder:30b/.test(pill), pill);
    await page.screenshot({ path: `${out}/engines-session-local.png` });

    // ---- the pickers and ?engine=
    await page.goto(base + '?skipboot&engine=gemini'); await page.waitForSelector('#menu.show', { timeout: 8000 }); await sleep(400);
    await page.click('#mStart'); await page.waitForSelector('#launchP.show'); await sleep(300);
    check('?engine=gemini (what `navi --engine gemini` opens) starts the launch sheet on Gemini', /Gemini/.test(await text('#lEngines .opt.on')), await text('#lEngines .opt.on'));
    await page.click('#lClose'); await sleep(200);
    await page.click('#tAgents'); await sleep(700);
    const am = await page.$$eval('#aModel option', els => els.map(e => e.textContent));
    check('the agent editor\'s models are this engine\'s: tiers with their models', am.includes('Strong · qwen3-coder:30b') && am.includes('Fast · gpt-oss:20b'), am.join(' | '));
    await page.click('#aClose'); await sleep(200);
    await page.goto(base + '?skipboot'); await page.waitForSelector('#menu.show', { timeout: 8000 });
    await page.click('#tCouncils'); await sleep(700);
    await page.click('#coList .li >> nth=0'); await sleep(300);
    const cm = await page.$$eval('#coRoster select.mdl', els => els.map(e => e.options[e.selectedIndex]?.textContent));
    check('the Knights on Local: each seat shows the local model its tier is', cm.some(x => /Balanced · qwen3-coder:30b/.test(x)) && cm.some(x => /Fast · gpt-oss:20b/.test(x)), cm.join(' | '));
    // ---- a council's own start values (Councils > When it starts): the start window starts from them
    const sv = await api('/councils', { name: 'nightly', title: 'Nightly', lead: 'architect', reviewers: ['adversary'], engine: 'local', model: 'fast', permissions: 'all', pace: 'quick' });
    check('a council keeps what it starts with', sv.ok && sv.data.council.engine === 'local' && sv.data.council.model === 'fast' && sv.data.council.permissions === 'all', JSON.stringify(sv.data).slice(0, 300));
    await api('/settings', { engine: 'claude', engines: {} });
    await page.goto(base + '?skipboot'); await page.waitForSelector('#menu.show', { timeout: 8000 }); await sleep(400);
    await page.evaluate(() => { menuCouncil = 'nightly'; renderCouncilPick(); });
    await page.click('#mStart'); await page.waitForSelector('#launchP.show'); await sleep(300);
    const on = async sel => (await text(sel)) || '';
    check('the start window starts from it: Local (the council\'s default), Fast, Allow all, Quick',
      /Local \(Ollama\)/.test(await on('#lEngines .opt.on')) && /the council's default/.test(await on('#lEngineHint')) && /Fast/.test(await on('#lModels .opt.on'))
      && /Allow all/.test(await on('#lPerms .opt.on')) && /Quick/.test(await on('#lPace .opt.on')),
      [await on('#lEngines .opt.on'), await on('#lEngineHint'), await on('#lModels .opt.on'), await on('#lPerms .opt.on'), await on('#lPace .opt.on')].join(' | '));
    await page.click('#lEngines .opt:has-text("Claude")'); await sleep(150);
    check('...pick another engine and it says that\'s just this time', /just this time|your default/.test(await on('#lEngineHint')), await on('#lEngineHint'));
    await page.click('#lClose'); await sleep(200);
    await page.click('#tCouncils'); await sleep(700);
    await page.click('#coList .li:has-text("Nightly")'); await sleep(300);
    check('Councils shows them under When it starts', await page.$eval('#coEngine', e => e.value) === 'local' && await page.$eval('#coModel', e => e.value) === 'fast'
      && await page.$eval('#coPerms', e => e.value) === 'all' && await page.$eval('#coPace', e => e.value) === 'quick' && await page.isVisible('#coStart'));
    await page.click('#coClose'); await sleep(200);
    // a launch that leaves them out (the terminal menu, the TUI, the CLI): the council's values fill the gaps
    const lr = await api('/launch', { action: 'new', task: 'a nightly check', council: 'nightly' });
    const sst = await page.evaluate(s => fetch('/status?session=' + s).then(r => r.json()), lr.data.session || '');
    check('...and a launch that names none of them gets the council\'s', lr.ok && sst.session?.engine === 'local' && sst.session?.permissions === 'all',
      JSON.stringify({ engine: sst.session?.engine, perms: sst.session?.permissions, r: lr.data }).slice(0, 300));

    // ---- only the engines you use show up anywhere; Settings > Add an engine has the rest
    await api('/settings', { engine: 'claude', engines_on: ['claude'] });
    await page.goto(base + '?skipboot'); await page.waitForSelector('#menu.show', { timeout: 8000 }); await sleep(500);
    await page.fill('#mTask', 'one engine only'); await page.click('#mStart'); await page.waitForSelector('#launchP.show'); await sleep(300);
    check('with only Claude in use, the launch sheet offers no other engine', !(await page.isVisible('#lEngineSec')), await opts('#lEngines .opt b').then(x => x.join('|')));
    await page.click('#lClose'); await sleep(300);
    await page.click('#tSettings'); await page.waitForSelector('#setup.show'); await sleep(300);
    let cs = await opts('#sEngines .opt b');
    check('Settings lists only the engines you use', cs.join('|') === 'Claude', cs.join('|'));
    await page.click('#sEngOn .engadd summary'); await sleep(150);
    const more = await opts('#sEngOn .engadd .opt b');
    check('...and Add an engine has the rest', more.join('|') === 'Local (Ollama)|Codex|Local (Ollama) via Codex|Gemini', more.join('|'));
    await page.click('#sEngOn .engadd .opt:has-text("Codex") >> nth=0'); await sleep(150);
    cs = await opts('#sEngines .opt b');
    check('adding one shows it at once', cs.join('|') === 'Claude|Codex', cs.join('|'));
    await page.screenshot({ path: `${out}/engines-add.png` });
    await page.click('#sNext'); await sleep(800);
    const on2 = (await page.evaluate(() => fetch('/settings').then(r => r.json()))).engines_on;
    check('...and Save keeps it', JSON.stringify(on2) === '["claude","codex"]', JSON.stringify(on2));
    await page.fill('#mTask', 'two engines'); await page.click('#mStart'); await page.waitForSelector('#launchP.show'); await sleep(300);
    const le = await opts('#lEngines .opt b');
    check('the launch sheet now offers those two, and only those', le.join('|') === 'Claude|Codex', le.join('|'));
    await page.click('#lClose'); await sleep(200);
    check('no page errors', errs.length === 0, errs.join(' | '));
  } catch (e) {
    check('the run finished', false, e.message.split('\n')[0]);
  } finally {
    try { await api('/settings', { engine: 'claude', engines: {}, engines_on: ['claude', 'local', 'codex', 'local-codex', 'gemini'] }); } catch {}
    await browser.close();
  }
  console.log(R.join('\n'));
  const failed = R.filter(x => x.startsWith('FAIL')).length;
  console.log(failed ? `ENGINES UI SUITE FAILED: ${failed}` : 'ENGINES UI SUITE PASSED');
  process.exit(failed ? 1 : 0);
})();
