// usage: node examples.js <base-url> <out-dir>
// The Examples window: opened from Agents, Councils, New + and the generator; council ideas open the generator filled in
// (size too), agent ideas a new agent filled in (sources ready, or the Add a source of truth box with the words), built-in
// ones open as they are; Esc closes only the window. Nothing is saved.
const { chromium } = require('playwright');
const [base, out] = process.argv.slice(2);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const R = []; const check = (n, ok, x = '') => R.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  · ' + x : ''}`);
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript(() => { try { localStorage.setItem('navi.tour', '1'); } catch {} });
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(e.message));
  const shown = sel => page.$eval(sel, e => e.classList.contains('show')).catch(() => false);
  const text = sel => page.$eval(sel, e => e.textContent).catch(() => '');
  const cards = () => page.$$eval('#exList .excard', els => els.map(e => ({ title: (e.querySelector('h3') || e.querySelector('.n b')).textContent,
    btn: e.querySelector('.exfoot .btn').textContent, members: [...e.querySelectorAll('.exmem .m b')].map(b => b.textContent), src: [...e.querySelectorAll('.exsrc')].map(x => x.textContent) })));
  const use = title => page.evaluate(t => [...document.querySelectorAll('#exList .excard')].find(e => (e.querySelector('h3') || e.querySelector('.n b')).textContent === t)
    .querySelector('.exfoot .btn').click(), title);
  try {
    await page.goto(base + '?skipboot'); await page.waitForSelector('#menu.show', { timeout: 8000 }); await sleep(500);

    // ---- from Agents: the agent ideas
    await page.click('#tAgents'); await sleep(700);
    await page.click('#aEx'); await sleep(300);
    let c = await cards();
    check('Examples opens over Agents, on the agent ideas', await shown('#exm') && await shown('#agentsP') && c.length === 10
      && /Agents/.test(await text('#exTabs .on')), `${c.length} cards`);
    check('an idea says where it checks its facts', c.find(x => x.title === 'Azure docs checker')?.src.join('') === 'Source of truth: Microsoft Learn');
    check('built-in ones open as they are', c.find(x => x.title === 'Red team')?.btn === 'Open Adversary', c.find(x => x.title === 'Red team')?.btn);
    await page.screenshot({ path: `${out}/examples-agents.png` });
    await page.keyboard.press('Escape'); await sleep(200);
    check('Esc closes the window, Agents stays', !(await shown('#exm')) && await shown('#agentsP'));

    // ---- an agent idea with a source ready
    await page.click('#aEx'); await sleep(200);
    await use('Azure docs checker'); await sleep(500);
    const f = await page.evaluate(() => ({ name: $('#aName').value, role: $('#aRole').value, help: $('#aHelp').value, job: $('#aJob').textContent,
      chips: [...document.querySelectorAll('#aSources .tag.src')].map(e => e.textContent), focus: document.activeElement?.id }));
    check('Use this idea fills in a new agent', !(await shown('#exm')) && f.name === 'azure-docs' && f.role === 'Azure docs checker' && /Microsoft Learn/.test(f.help), JSON.stringify(f));
    check('...with its source of truth ready', f.chips.length === 1 && /learn\.microsoft\.com\/azure.*Azure docs/.test(f.chips[0]), f.chips.join(' / '));
    check('...and points at Write it for me (nothing is saved yet)', /Write it for me/.test(f.job) && f.focus === 'aGenerate', `${f.focus}: ${f.job}`);
    // ---- an agent idea whose source is yours to name
    await page.click('#aEx'); await sleep(200);
    await use('Wiki keeper'); await sleep(500);
    check('a source that\'s yours opens Add a source of truth with the words in it', await page.$eval('#aSources .srcbox textarea', e => e.value).catch(() => '') === 'My Obsidian vault');
    // ---- a built-in one
    await page.click('#aEx'); await sleep(200);
    await use('Red team'); await sleep(500);
    check('Open Adversary opens the built-in agent', /Adversary/.test(await text('#aTitle')) && !(await shown('#exm')), await text('#aTitle'));

    // ---- the council ideas, from Councils
    await page.click('#aClose'); await sleep(300);
    if (!(await shown('#menu'))) { await page.goto(base + '?skipboot'); await page.waitForSelector('#menu.show', { timeout: 8000 }); }
    await page.click('#tCouncils'); await sleep(700);
    await page.click('#coEx'); await sleep(300);
    c = await cards();
    check('from Councils it opens on the council ideas', /Councils/.test(await text('#exTabs .on')) && c.map(x => x.title).join('|') === 'Platform team|Small and quick|PR and architecture review|Terraform on Azure',
      c.map(x => x.title).join('|'));
    const plat = c[0] || { members: [], src: [] };
    check('the platform team: a GitHub expert, a wiki keeper on your vault, red and blue teams, an Azure docs checker',
      plat.members.join(',') === 'GitHub expert,Wiki keeper,Red team,Blue team,Azure docs checker,Warden' && plat.src.includes('Source of truth: your Obsidian vault'), plat.members.join(','));
    check('a small one: two agents and the guard', (c[1]?.members || []).length === 3);
    await page.screenshot({ path: `${out}/examples-councils.png` });
    await use('Platform team'); await sleep(500);
    const g = await page.evaluate(() => ({ want: $('#cgWant').value, size: document.querySelector('#cgSize .on')?.textContent, note: $('#cgNote').textContent }));
    check('Use this idea opens the generator with it written in, size and all', await shown('#cgen') && !(await shown('#exm')) && /platform team/.test(g.want)
      && g.size === 'Medium' && /Platform team/.test(g.note), JSON.stringify(g));
    check('...over Councils, where the new council will land', await shown('#councilsP'));
    // the generator's own list of tries ends with the full set
    await page.click('#cgEx .cg-chip:last-child'); await sleep(300);
    check('the generator\'s More examples… opens the window', await shown('#exm') && !(await shown('#cgen')));
    await page.keyboard.press('Escape'); await sleep(200);
    // New + has a way in too
    await page.click('#coCreate'); await sleep(200);
    await page.click('#coNewEx'); await sleep(300);
    check('New + → Start from an example opens it', await shown('#exm') && /Councils/.test(await text('#exTabs .on')));
    await page.click('#exTabs button[data-ex="agents"]'); await sleep(150);
    check('the tabs switch between councils and agents', (await cards()).length === 10);
    await page.click('#exClose'); await sleep(200);
    // the server restarted (navi update, navi stop): the page's token is stale, its next click still works
    const tk = await page.evaluate(async () => { const real = TOKEN; TOKEN = 'stale-from-before-a-restart'; const r = await post('/sources/check', { sources: [] }); return { ok: r.ok, back: TOKEN === real }; });
    check('after a server restart an open page picks up the new token and carries on', tk.ok && tk.back, JSON.stringify(tk));
    check('no page errors', errs.length === 0, errs.join(' | '));

    // phone width: one column, nothing cut off
    await page.setViewportSize({ width: 420, height: 860 }); await sleep(200);
    await page.evaluate(() => openExamples('councils')); await sleep(300);    // the lists (and their buttons) hide below 900px
    const wide = await page.$eval('#exList', e => e.scrollWidth <= e.clientWidth + 1);
    check('on a phone the cards fit, one column', wide);
    await page.screenshot({ path: `${out}/examples-phone.png` });
  } catch (e) {
    check('the run finished', false, e.message.split('\n')[0]);
  } finally {
    await browser.close();
  }
  console.log(R.join('\n'));
  const failed = R.filter(x => x.startsWith('FAIL')).length;
  console.log(failed ? `EXAMPLES SUITE FAILED: ${failed}` : 'EXAMPLES SUITE PASSED');
  process.exit(failed ? 1 : 0);
})();
