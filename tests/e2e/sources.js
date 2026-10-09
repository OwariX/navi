// usage: node sources.js <base-url> <out-dir> <scratch dir>
// Sources of truth in the app, against the fake claude: Add a source of truth -> describe it -> the model fills it in ->
// every row checked (a folder found with what's in it, a site, your MCP server, a vault picked from the ones found) ->
// add -> Save; the model failing (the plain reader takes over and says so); by hand; a built-in agent's (saved right
// away, for every project); the launch sheet's (every agent). It cleans up after itself.
const fs = require('fs');
const { chromium } = require('playwright');
const [base, out, sp] = process.argv.slice(2);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const waitFor = async (fn, ms) => { const end = Date.now() + ms; while (Date.now() < end) { if (await fn()) return true; await sleep(200); } return false; };
const R = []; const check = (n, ok, x = '') => R.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  · ' + x : ''}`);
const BUILTIN_SRC = `${sp}/home/agent-sources.json`;
async function cleanup() {   // what this run made, even when it stopped halfway
  try {
    const token = (await (await fetch(base)).text()).match(/name="navi-token" content="([^"]+)"/)[1];
    const post = (p, b) => fetch(new URL(p, base), { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Navi-Token': token }, body: JSON.stringify(b) });
    for (const scope of ['project', 'library']) await post('/agents/remove', { name: 'src-test', delete: true, scope });
    await post('/sources', { sources: [] });
    await post('/agents/sources', { name: 'architect', sources: [] });
  } catch (e) { console.log('cleanup failed:', e.message); }
  fs.rmSync(`${sp}/proj/docs`, { recursive: true, force: true });
}
(async () => {
  fs.mkdirSync(`${sp}/proj/docs`, { recursive: true });
  fs.writeFileSync(`${sp}/proj/docs/spec.pdf`, '%PDF-1.4');
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript(() => { try { localStorage.setItem('navi.tour', '1'); } catch {} });
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(e.message));
  const get = path => page.evaluate(p => fetch(p).then(r => r.json()), path);
  const rows = box => page.$$eval(`${box} .srow`, els => els.map(e => ({ cls: e.className, kind: e.querySelector('select').value,
    value: e.querySelector('.in.v').value, note: e.querySelector('.in.n').value, say: e.querySelector('.say').textContent })));
  const chips = box => page.$$eval(`${box} .tag.src`, els => els.map(e => e.textContent));
  const text = sel => page.$eval(sel, e => e.textContent).catch(() => '');
  try {
    await page.goto(base + '?skipboot'); await page.waitForSelector('#menu.show', { timeout: 8000 }); await sleep(500);

    // ---- an agent of yours: describe it, the model fills it in, check each row
    await page.click('#tAgents'); await sleep(700);
    await page.click('#aNew'); await sleep(200);
    await page.fill('#aName', 'src-test'); await page.fill('#aRole', 'source tester');
    await page.click('#aTemplate'); await sleep(100);
    check('the agent editor has an Add a source of truth button', await page.isVisible('#aSources .srcopen'));
    await page.click('#aSources .srcopen');
    check('it opens a box to describe it in your own words, with examples to try', await page.isVisible('#aSources .srcbox textarea')
      && (await page.$$('#aSources .srcbox .cg-chip')).length === 5 && !(await page.isVisible('#aSources .srcopen')));
    await page.click('#aSources .srcbox .btn.pri');
    check('Fill it in with nothing written says what to write', /Describe it first/.test(await text('#aSources .srcbox .err')));
    await page.fill('#aSources .srcbox textarea', 'the docs folder, Microsoft Learn for Azure, the team wiki MCP, and my vault');
    await page.click('#aSources .srcbox .btn.pri');
    check('while the model reads it: Reading it…', await waitFor(() => page.$eval('#aSources .srcbox .job', e => /Reading it/.test(e.textContent)).catch(() => false), 3000));
    await waitFor(async () => (await page.$$('#aSources .srow')).length > 0, 15000);
    let r = await rows('#aSources');
    check('its answer becomes four rows to check (a kind that isn\'t one is dropped)', r.length === 4, JSON.stringify(r));
    if (r.length === 4) {
      check('the folder is found, and it says what\'s in it', r[0].kind === 'folder' && /\bok\b/.test(r[0].cls) && /Found it: 1 PDF/.test(r[0].say)
        && r[0].value.endsWith('/proj/docs') && r[0].note === 'the project docs', JSON.stringify(r[0]));
      check('the site gets an https address', r[1].kind === 'web' && r[1].value === 'https://learn.microsoft.com/azure', JSON.stringify(r[1]));
      check('the MCP server is matched to yours, whatever the case', r[2].kind === 'mcp' && r[2].value === 'team-wiki' && /\bok\b/.test(r[2].cls), JSON.stringify(r[2]));
      check('the vault it can\'t place asks where it is', r[3].kind === 'folder' && /\bask\b/.test(r[3].cls) && r[3].value === '', JSON.stringify(r[3]));
    }
    check('...and NAVI asks the question', /Which folder is the vault in/.test(await text('#aSources .srcq')));
    const vaults = await page.$$eval('#aSources .srcpick .cg-chip', els => els.map(e => e.textContent));
    check('the Obsidian vaults it found are offered', vaults.some(v => v.endsWith('/vhome/Documents/Brain')), vaults.join(', '));
    await page.screenshot({ path: `${out}/sources-review.png` });
    await page.click('#aSources .srcpick .cg-chip');
    r = await rows('#aSources');
    check('clicking one fills the row that asked for it', r.length === 4 && r[3].value.endsWith('/vhome/Documents/Brain') && /\bnew\b/.test(r[3].cls), JSON.stringify(r[3] || {}));
    await page.click('#aSources .srow .how summary');
    check('each checked row shows the line its agent is told', /search it before you state a fact/.test(await text('#aSources .srow .how p')));
    await (await page.$$('#aSources .srow .ib'))[1].click();      // leave the website out
    check('a row can be left out, and the button counts what it adds', (await page.$$('#aSources .srow')).length === 3 && /Add these 3/.test(await text('#aSources .srcgo')));
    await page.click('#aSources .srcgo');
    await waitFor(async () => (await chips('#aSources')).length === 3, 5000);
    let c = await chips('#aSources');
    check('three sources added, each with its note', c.length === 3 && c.some(x => /the project docs/.test(x)) && c.some(x => /team-wiki.*the team wiki/.test(x)), c.join(' / '));
    check('the box closes; it says it isn\'t saved yet', !(await page.isVisible('#aSources .srcbox')) && /Not saved yet/.test(await text('#aSources')));
    await page.click('#aSave'); await sleep(900);
    const persona = () => { for (const f of [`${sp}/proj/.navi/agents/src-test.md`, `${sp}/home/agents/src-test.md`]) { try { return fs.readFileSync(f, 'utf8'); } catch {} } return ''; };
    const line = () => persona().split('\n').find(l => l.startsWith('sources:')) || '';
    check('Save writes them into the agent, notes and all', /folder \S*\/proj\/docs \| the project docs/.test(line()) && /mcp team-wiki \| the team wiki/.test(line())
      && /vhome\/Documents\/Brain \| my vault/.test(line()), line());
    check('...and the hint goes away', !/Not saved yet/.test(await text('#aSources')));

    // ---- the model is down: the plain reader takes over, and says so
    await page.click('#aSources .srcopen');
    await page.fill('#aSources .srcbox textarea', 'FAKE_FAIL the specs in docs/ and https://example.com/handbook');
    await page.click('#aSources .srcbox .btn.pri');
    await waitFor(async () => (await page.$$('#aSources .srow')).length > 0, 15000);
    r = await rows('#aSources');
    check('when the model fails, NAVI reads it without one and says so', /didn't answer/.test(await text('#aSources .srcbox'))
      && r.map(x => x.kind).sort().join(',') === 'folder,web', JSON.stringify(r));
    await page.keyboard.press('Escape'); await sleep(150);
    check('Esc closes the box, the agent editor stays', !(await page.isVisible('#aSources .srcbox')) && await page.isVisible('#agentsP'));

    // ---- by hand
    await page.click('#aSources .srcopen');
    await page.click('#aSources .srcbox .btn.ghost');                 // Enter it by hand
    await page.selectOption('#aSources .srow select', 'web');
    await page.fill('#aSources .srow .in.v', 'example.com/docs');
    await page.fill('#aSources .srow .in.n', 'Example docs');
    await page.click('#aSources .srcgo');
    await waitFor(async () => (await chips('#aSources')).length === 4, 15000);     // a slow CI runner needs more than 5 s
    c = await chips('#aSources');
    check('by hand: a website, made an https address', c.some(x => /https:\/\/example\.com\/docs.*Example docs/.test(x)), c.join(' / '));
    await page.click('#aSources .srcopen');
    await page.click('#aSources .srcbox .btn.ghost');
    await page.fill('#aSources .srow .in.v', '/no/such/folder');
    await page.click('#aSources .srcgo'); await sleep(600);
    check('a path that isn\'t there: NAVI says so first, and the box stays open', /Nothing there on this machine/.test(await text('#aSources .srcbox')) && (await chips('#aSources')).length === 4,
      await text('#aSources .srcbox'));
    await page.click('#aSources .srcgo');
    await waitFor(async () => (await chips('#aSources')).length === 5, 5000);
    check('...and Add again keeps it as written (anything can be a source)', (await chips('#aSources')).some(x => /\/no\/such\/folder/.test(x)), (await chips('#aSources')).join(' / '));
    await page.click('#aSources .srcopen');
    await page.click('#aSources .srcbox .btn.ghost');
    await page.fill('#aSources .srow .in.v', `${sp}/proj/docs/spec.pdf`);
    await page.click('#aSources .srcgo');
    await waitFor(async () => (await chips('#aSources')).length === 6, 5000);
    check('one file is a source too (typed as a folder, it becomes a File)', (await chips('#aSources')).some(x => /^File.*spec\.pdf/.test(x)), (await chips('#aSources')).join(' / '));

    // ---- a built-in agent: saved right away, for every project
    await page.evaluate(() => [...document.querySelectorAll('#agList .li')].find(e => /architect/i.test(e.querySelector('b').textContent)).click());
    await sleep(300);
    check('a built-in agent can have sources too', await page.isVisible('#aSources .srcopen') && /in all your projects/.test(await text('#aSources')));
    await page.click('#aSources .srcopen');
    await page.click('#aSources .srcbox .btn.ghost');
    await page.fill('#aSources .srow .in.v', `${sp}/proj/docs`);
    await page.fill('#aSources .srow .in.n', 'design notes');
    await page.click('#aSources .srcgo');
    await waitFor(async () => (await chips('#aSources')).length === 1, 5000);
    const saved = () => { try { return JSON.parse(fs.readFileSync(BUILTIN_SRC, 'utf8')); } catch { return {}; } };
    check('...saved for it at once, in your config', /proj\/docs \| design notes$/.test((saved().architect || [])[0] || ''), JSON.stringify(saved()));
    await page.click('#aSources .tag.src .x'); await sleep(500);
    check('...and removed the same way', !saved().architect && (await chips('#aSources')).length === 0, JSON.stringify(saved()));
    await page.click('#aClose'); await sleep(300);

    // ---- the launch sheet: every agent in this project
    if (!(await page.isVisible('#menu.show'))) { await page.goto(base + '?skipboot'); await page.waitForSelector('#menu.show', { timeout: 8000 }); }
    await page.click('#mStart'); await page.waitForSelector('#launchP.show', { timeout: 5000 }); await sleep(300);
    await page.click('#lSources .srcopen');
    await page.click('#lSources .srcbox .btn.ghost');
    await page.selectOption('#lSources .srow select', 'web');
    await page.fill('#lSources .srow .in.v', 'learn.microsoft.com/azure');
    await page.click('#lSources .srcgo');
    await waitFor(async () => (await chips('#lSources')).length === 1, 5000);
    check('the launch sheet adds a source for every agent here', ((await get('/sources')).sources || []).includes('web https://learn.microsoft.com/azure'), JSON.stringify(await get('/sources')));
    await page.click('#lSources .srcopen');
    const how = await text('#lSources .srcbox .hint:last-child');
    check('the box says who reads it and that you check it first', /You check them before anything is added/.test(how), how);
    await page.keyboard.press('Escape');
    await page.click('#lSources .tag.src .x'); await sleep(500);
    check('...and removes it', ((await get('/sources')).sources || []).length === 0);
    await page.click('#lClose');
    check('no page errors', errs.length === 0, errs.join(' | '));
  } catch (e) {
    check('the run finished', false, e.message.split('\n')[0]);
  } finally {
    await browser.close();
    await cleanup();
  }
  console.log(R.join('\n'));
  const failed = R.filter(x => x.startsWith('FAIL')).length;
  console.log(failed ? `SOURCES SUITE FAILED: ${failed}` : 'SOURCES SUITE PASSED');
  process.exit(failed ? 1 : 0);
})();
