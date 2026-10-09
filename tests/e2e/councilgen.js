// usage: node councilgen.js <base-url> <out-dir>
// The council generator end to end, against the fake claude (tests/fake-claude answers the generator's prompts):
// the server's checks, New + as a menu, describe, working + Cancel, review (badges, seats, Rewrite by NAVI and by hand,
// Remove, Add by description and from the library), Create (personas written, council saved, lands in the editor).
// It cleans up after itself: the council and the agents it creates are deleted at the end.
const { chromium } = require('playwright');
const [base, out] = process.argv.slice(2);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const waitFor = async (fn, ms) => { const end = Date.now() + ms; while (Date.now() < end) { if (await fn()) return true; await sleep(250); } return false; };
const R = []; const check = (n, ok, x = '') => R.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  · ' + x : ''}`);
const NEW = ['tf-reviewer', 'azure-red-team', 'cost-watch'];
async function cleanup() {   // delete what this run created, even when it stopped halfway (plain HTTP, no page needed)
  try {
    const token = (await (await fetch(base)).text()).match(/name="navi-token" content="([^"]+)"/)[1];
    const post = (p, b) => fetch(new URL(p, base), { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Navi-Token': token }, body: JSON.stringify(b) });
    const { councils } = await (await fetch(new URL('/councils', base))).json();
    for (const c of councils) if (c.scope === 'mine' && /^(Generator test council|Azure Terraform reviews)$/.test(c.title)) await post('/councils/delete', { name: c.name });
    for (const n of [...NEW, 'pr-scribe']) await post('/agents/remove', { name: n, delete: true, scope: 'library' });
  } catch (e) { console.log('cleanup failed:', e.message); }
}
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript(() => { try { localStorage.setItem('navi.tour', '1'); } catch {} });
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(e.message));
  const shown = sel => page.$eval(sel, e => e.classList.contains('show')).catch(() => false);
  const api = (path, body) => page.evaluate(([p, b]) => fetch(p, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Navi-Token': TOKEN }, body: JSON.stringify(b) })
    .then(r => r.json()), [path, body]);
  const get = path => page.evaluate(p => fetch(p).then(r => r.json()), path);
  const job = async id => { for (let i = 0; i < 80; i++) { const j = await get('/jobs?id=' + id); if (j.state !== 'running') return j; await sleep(250); } return { state: 'timeout' }; };
  const cards = () => page.$$eval('#cgRoster .cg-card:not(.edit)', els => els.map(e => ({
    name: e.dataset.name, badge: e.querySelector('.cg-top .tag')?.textContent || e.querySelector('.cg-pick .on')?.textContent, seat: e.querySelector('select')?.value,
    role: e.querySelector('.n small')?.textContent, brief: e.querySelector('.cg-brief')?.textContent, color: e.querySelector('.av')?.style.getPropertyValue('--c') })));
  const card = async name => (await cards()).find(c => c.name === name);
  const panelGone = () => page.waitForSelector('#cgRoster .cg-card.edit', { state: 'detached', timeout: 10000 });
  const sessionNoise = async () => {   // generator jobs belong to no session: they must never log into one
    let n = 0;
    for (const s of await get('/sessions')) n += (await get('/log?session=' + s.id)).filter(e => e.type === 'roster').length;
    return n;
  };

  // ---- the server: sizes, tidy names, draft-agent validation
  await page.goto(base + '?skipboot'); await page.waitForSelector('#menu.show', { timeout: 8000 }); await sleep(600);
  const noise0 = await sessionNoise();
  let r = await api('/councils/suggest', { description: 'review terraform for azure', size: 'large', session: '' });
  const s = (await job(r.job)).result || {};
  check('suggest: the size hint reaches the prompt', /size: large/.test(s.why || ''), s.why);
  check('suggest: new agents never take a built-in or invalid name', (s.new_agents || []).map(a => a.name).join(',') === 'tf-reviewer,pr-scribe',
    (s.new_agents || []).map(a => a.name).join(','));
  check('suggest: seats only point at real or drafted agents, the guard is warden', s.lead === 'architect' && (s.reviewers || []).join(',') === 'tf-reviewer,adversary'
    && s.recorder === 'pr-scribe' && s.guard === 'warden', `${s.lead} / ${s.reviewers} / ${s.recorder} / ${s.guard}`);
  check('suggest: unknown models dropped, new colours distinct', s.models && !('warden' in s.models) && new Set((s.new_agents || []).map(a => a.color)).size === 2,
    JSON.stringify(s.models));
  r = await api('/councils/draft-agent', { want: 'dup-name-test: another architect', session: '' });
  const dup = (await job(r.job)).result || {};
  check('draft-agent: a built-in name becomes a free one', /^architect-\d+$/.test(dup.name || ''), dup.name);
  r = await api('/councils/draft-agent', { want: 'focus on cost', agent: { name: 'adversary', role: 'red team', brief: 'b' }, session: '' });
  const lib = (await job(r.job)).result || {};
  check('draft-agent: rewriting a library agent makes a new one', lib.name && lib.name !== 'adversary' && /cost/.test(lib.role), `${lib.name} (${lib.role})`);
  r = await api('/councils/draft-agent', { want: '  ', session: '' });
  check('draft-agent: empty text is refused', /say what/.test(r.error || ''), r.error);
  r = await api('/councils/draft-agent', { want: 'x', agent: { name: 'Bad Name!' }, session: '' });
  check('draft-agent: bad names are refused', /a-z/.test(r.error || ''), r.error);

  // ---- New +: a small menu with two choices, the recommended one first
  await page.click('#tCouncils'); await sleep(800);
  await page.click('#coCreate'); await sleep(300);
  const items = await page.$$eval('#coNewPop .li b', els => els.map(e => e.textContent));
  check('New opens a menu: generate one (recommended, first), start from scratch, or from an example', await shown('#coNewPop')
    && items.join('|') === 'Generate one Recommended|Start from scratch|Start from an example', items.join('|'));
  await page.screenshot({ path: `${out}/councilgen-popover.png` });
  await page.keyboard.press('Escape'); await sleep(200);
  check('Esc closes the menu, the councils panel stays', !(await shown('#coNewPop')) && await shown('#councilsP'));
  await page.click('#coCreate'); await sleep(200); await page.click('#coNewBlank'); await sleep(300);
  check('Start from scratch: an empty council, no draft bar', (await page.inputValue('#coTitleIn')) === '' && await page.isVisible('#coSave')
    && (await page.$$eval('#coRoster .mem', e => e.length)) === 0 && !(await page.$('#coWant')));
  check('an empty new council offers to generate it instead', await page.isVisible('#coRoster .empty button'));

  // ---- Generate one: describe
  await page.click('#coCreate'); await sleep(200); await page.click('#coNewGen'); await sleep(500);
  check('Generate one opens its own view over the councils panel', await shown('#cgen') && await shown('#councilsP') && await page.isVisible('#cgDescribe'));
  check('describe: the box is focused', await page.evaluate(() => document.activeElement?.id === 'cgWant'));
  const chips = await page.$$eval('#cgEx .cg-chip', els => els.map(e => e.textContent)), sizes = await page.$$eval('#cgSize button', els => els.map(e => e.textContent));
  check('describe: three examples, a way to more, and four sizes', chips.length === 4 && chips[3] === 'More examples…' && sizes.join(',') === 'Let NAVI decide,Small,Medium,Large', `${chips} · ${sizes}`);
  await page.click('#cgGo'); await sleep(200);
  check('Generate with nothing described explains itself', /Describe the work/.test(await page.textContent('#cgNote')) && await page.isVisible('#cgDescribe'));
  await page.click('#cgEx .cg-chip >> nth=0'); await sleep(100);
  check('an example fills the box', /Terraform/.test(await page.inputValue('#cgWant')));
  await page.click('#cgSize button[data-size="small"]'); await sleep(100);
  check('a size says what it means', /3 to 4/.test(await page.textContent('#cgSizeHint')), await page.textContent('#cgSizeHint'));
  await page.screenshot({ path: `${out}/councilgen-describe.png` });

  // ---- working: elapsed time and Cancel
  await page.click('#cgGo'); await sleep(1500);
  check('working: calm progress with the elapsed time', await page.isVisible('#cgWorking') && /^0:0\d$/.test(await page.textContent('#cgTime')), await page.textContent('#cgTime'));
  check('working: the only action is Cancel', (await page.textContent('#cgBack')) === 'Cancel' && !(await page.isVisible('#cgGo')));
  await page.click('#cgBack'); await sleep(300);
  check('Cancel goes back to the description, text kept', await page.isVisible('#cgDescribe') && /Terraform/.test(await page.inputValue('#cgWant')));
  await sleep(2600);
  check('a cancelled draft never lands', await page.isVisible('#cgDescribe') && !(await page.isVisible('#cgReview')));

  // ---- review
  await page.click('#cgWant'); await page.keyboard.press('Control+Enter');
  await page.waitForSelector('#cgReview.on', { timeout: 15000 }); await sleep(400);
  let cs = await cards();
  check('⌘⏎ generates; the review shows the roster as cards', cs.length === 5, cs.map(c => c.name).join(','));
  check('review: names the server dropped never show', !cs.some(c => /ghost|bad/i.test(c.name)));
  check('review: New, and Yours for the agents you already have', cs.filter(c => c.badge === 'New').length === 2 && cs.filter(c => c.badge === 'Yours').length === 3,
    cs.map(c => `${c.name}:${c.badge}`).join(','));
  check('review: exactly one lead, the guard is Warden', cs.filter(c => c.seat === 'lead').length === 1 && cs.find(c => c.name === 'warden')?.seat === 'guard');
  check('review: every card has a role and a brief', cs.every(c => c.role && c.brief && !/No brief/.test(c.brief)));
  check('review: the new agents have distinct colours', (await card('tf-reviewer')).color !== (await card('pr-scribe')).color);
  check('review: an editable title and description from the draft', (await page.inputValue('#cgTitle')) === 'Azure Terraform reviews' && /RBAC/.test(await page.inputValue('#cgDesc')));
  check('review: who proposes, who reviews, who records', /proposes and builds.*challenge it.*writes it up/.test(await page.textContent('#cgFlow')), await page.textContent('#cgFlow'));
  check('review: the footer says what Create will write', /2 new agents will be written/.test(await page.textContent('#cgNote')), await page.textContent('#cgNote'));
  await page.screenshot({ path: `${out}/councilgen-review.png` });
  const banner = await page.textContent('#cgReuse');
  check('reuse: a banner names the seats that use agents you already have', /2 of these seats use an agent you already have/.test(banner) && /Architect/.test(banner) && /Adversary/.test(banner), banner);
  check('reuse: nothing to write until you switch one to "New one"', await page.isDisabled('#cgReuse button'));
  check('reuse: the guard is always Warden, no switch', !(await page.$('#cgRoster .cg-card[data-name="warden"] .cg-pick')));

  // seats: one lead at a time
  await page.selectOption('#cgRoster .cg-card[data-name="adversary"] select >> nth=0', 'lead'); await sleep(200);
  cs = await cards();
  check('seats: a new lead, and the old one steps down', cs.filter(c => c.seat === 'lead').map(c => c.name).join() === 'adversary' && (await card('architect')).seat === 'reviewer');
  await page.selectOption('#cgRoster .cg-card[data-name="architect"] select >> nth=0', 'lead'); await sleep(200);

  // Rewrite, by NAVI
  await page.click('#cgRoster .cg-card[data-name="tf-reviewer"] >> text=Rewrite'); await sleep(300);
  check('Rewrite opens a panel under its card', await page.isVisible('#cgRoster .cg-card.edit') && !!(await page.$('#cgRoster .cg-card.on[data-name="tf-reviewer"]')));
  await page.fill('#cgRoster .cg-card.edit textarea', 'focus on cost'); await page.keyboard.press('Enter');
  await panelGone(); await sleep(200);
  const tf = await card('tf-reviewer');
  check('Rewrite: NAVI redrafts the role and the brief', tf && tf.role === 'cost reviewer' && /Rewritten by NAVI/.test(tf.brief) && tf.badge === 'New', JSON.stringify(tf));

  // Rewrite, by hand: a library agent becomes a new one, under a new name
  await page.click('#cgRoster .cg-card[data-name="adversary"] >> text=Rewrite'); await sleep(300);
  check('rewriting a library agent says the original stays', /stays in your library/.test(await page.textContent('#cgRoster .cg-card.edit')));
  await page.click('#cgRoster .cg-card.edit .cg-link'); await sleep(200);
  await page.fill('#cgRoster .cg-card.edit .cg-hand input >> nth=1', 'azure red team');
  await page.click('#cgRoster .cg-card.edit >> text=Save'); await sleep(200);
  check('by hand: the same name is refused for a changed library agent', /new name/.test(await page.textContent('#cgRoster .cg-card.edit .err')), await page.textContent('#cgRoster .cg-card.edit .err'));
  await page.fill('#cgRoster .cg-card.edit .cg-hand input >> nth=0', 'azure-red-team');
  await page.click('#cgRoster .cg-card.edit >> text=Save'); await panelGone(); await sleep(200);
  const red = await card('azure-red-team');
  check('by hand: it becomes a new agent, the original leaves this council', red && red.badge === 'New' && red.role === 'azure red team' && !(await card('adversary')), JSON.stringify(red));

  // Esc closes an open panel first
  await page.click('#cgRoster .cg-card[data-name="pr-scribe"] >> text=Rewrite'); await sleep(200);
  await page.keyboard.press('Escape'); await sleep(200);
  check('Esc closes the rewrite panel, the view stays', !(await page.$('#cgRoster .cg-card.edit')) && await shown('#cgen'));

  // Remove
  await page.click('#cgRoster .cg-card[data-name="pr-scribe"] .cg-foot .ib'); await sleep(200);
  check('Remove takes an agent out', (await cards()).length === 4 && !(await card('pr-scribe')));

  // Add an agent: describe one
  await page.click('#cgRoster .cg-add'); await sleep(200);
  await page.fill('#cgRoster .cg-card.edit textarea', 'someone who watches the cost'); await page.click('#cgRoster .cg-card.edit >> text=Draft it');
  await panelGone(); await sleep(200);
  const cw = await card('cost-watch');
  check('Add an agent: NAVI drafts it, as a new reviewer', cw && cw.badge === 'New' && cw.seat === 'reviewer' && /cost/.test(cw.brief), JSON.stringify(cw));
  // Add an agent: pick one from the library
  await page.click('#cgRoster .cg-add'); await sleep(200); await page.click('#cgRoster .cg-card.edit .cg-link'); await sleep(300);
  const libs = await page.$$eval('#cgPick .li b', els => els.map(e => e.textContent));
  check('Add an agent: the library lists only agents not seated yet', await shown('#cgPick') && libs.includes('Ledger') && !libs.includes('Architect'), libs.join(','));
  await page.click('#cgPick .li:has-text("Ledger")'); await sleep(300);
  check('a library pick joins as Yours', (await card('ledger'))?.badge === 'Yours' && !(await page.$('#cgRoster .cg-card.edit')));

  // Back keeps the draft; Esc closes the view and keeps it too
  await page.click('#cgBack'); await sleep(200);
  check('Back returns to the description and offers the draft again', await page.isVisible('#cgDescribe') && (await page.textContent('#cgBack')) === 'Back to the draft');
  await page.click('#cgBack'); await sleep(300);
  check('Back to the draft keeps every change', !!(await card('azure-red-team')) && !!(await card('cost-watch')) && !!(await card('ledger')));
  await page.click('#cgTitle'); await page.keyboard.press('Escape'); await sleep(300);
  check('Esc closes the generator, back to the councils panel', !(await shown('#cgen')) && await shown('#councilsP'));
  await page.click('#coCreate'); await sleep(200); await page.click('#coNewGen'); await sleep(400);
  check('reopening returns to the draft', await page.isVisible('#cgReview') && (await cards()).length === 6);

  // Create: personas written in parallel, the council saved, then the editor
  await page.fill('#cgTitle', 'Generator test council');
  await page.click('#cgGo');
  let progress = '';
  for (let i = 0; i < 60 && !progress; i++) { const t = await page.textContent('#cgNote'); if (/Writing agents \d of 3/.test(t)) progress = t; else await sleep(100); }
  check('Create: "Writing agents 1 of 3" while the personas are written', !!progress, progress);
  check('Create: each new card shows it is being written', (await page.$$eval('#cgRoster .tag.busy', els => els.length)) >= 1);
  await page.waitForSelector('#cgen.show', { state: 'hidden', timeout: 30000 }); await sleep(600);
  check('Create lands in the councils editor on the new council', await shown('#councilsP') && (await page.inputValue('#coTitleIn')) === 'Generator test council'
    && /Created\. 3 new agents are in your library/.test(await page.textContent('#coErr')), await page.textContent('#coErr'));
  const mems = await page.$$eval('#coRoster .mem', els => els.map(e => e.querySelector('.n b').textContent + ':' + e.querySelector('select').value));
  check('the editor shows the reviewed roster and seats', mems.length === 6 && mems.includes('Architect:lead') && mems.includes('Warden:guard') && mems.includes('Ledger:reviewer'), mems.join(','));
  const agents = await get('/agents');
  check('every new agent is in the library with a full persona', NEW.every(n => agents.find(a => a.name === n && a.source === 'library' && /You are \*\*/.test(a.directive))),
    NEW.map(n => `${n}:${agents.find(a => a.name === n)?.source || 'missing'}`).join(','));
  const mine = (await get('/councils')).councils.find(c => c.title === 'Generator test council') || {};
  check('the council file: seats, models as tiers (the draft said opus: strong on every engine), rules and deliverables', mine.lead === 'architect' && mine.guard === 'warden' && mine.models?.architect === 'strong'
    && /terraform apply/.test(mine.instructions || '') && (mine.outputs || []).length === 2 && mine.scope === 'mine', `${mine.name}: ${mine.lead} / ${mine.reviewers}`);
  check('the generator never logs into a session', (await sessionNoise()) === noise0);
  await page.click('#coCreate'); await sleep(200); await page.click('#coNewGen'); await sleep(400);
  check('the next generator starts fresh', await page.isVisible('#cgDescribe') && (await page.inputValue('#cgWant')) === '' && (await page.textContent('#cgBack')) === 'Cancel');
  // the seats it filled with agents you already have: switch one to "New one", and NAVI writes a fresh agent for that seat
  await page.fill('#cgWant', 'reviews Terraform pull requests for Azure'); await page.keyboard.press('Control+Enter');
  await page.waitForSelector('#cgReview.on', { timeout: 15000 }); await sleep(400);
  const seatsMine = async () => +((await page.textContent('#cgReuse')).match(/(\d+) of these seats/) || [])[1];
  const before = await seatsMine();
  await page.click('#cgRoster .cg-card[data-name="adversary"] .cg-pick button:has-text("New one")'); await sleep(200);
  check('reuse: switching one says how many new agents it will write', (await page.textContent('#cgReuse button')).trim() === 'Write 1 new agent' && !(await page.isDisabled('#cgReuse button')));
  await page.click('#cgReuse button');
  await page.waitForFunction(() => !CG.swapping, null, { timeout: 15000 }); await sleep(300);
  const swapped = await card('adversary-2');
  check('reuse: a fresh agent with its own name takes the seat; yours stays in the library', swapped && swapped.badge === 'New' && swapped.seat === 'reviewer' && !(await card('adversary'))
    && (await get('/agents')).some(a => a.name === 'adversary'), JSON.stringify(swapped));
  check('reuse: the banner counts one seat fewer and no longer names it', await seatsMine() === before - 1 && !/Adversary/.test(await page.textContent('#cgReuse')), `${before} -> ${await seatsMine()}`);
  await page.keyboard.press('Escape'); await sleep(200);

  await cleanup();
  const left = (await get('/agents')).filter(a => [...NEW, 'pr-scribe'].includes(a.name)).length
    + (await get('/councils')).councils.filter(c => c.scope === 'mine' && /^(Generator test council|Azure Terraform reviews)$/.test(c.title)).length;
  check('cleanup leaves no test agents or councils behind', left === 0, String(left));

  // End sessions, from home: this one or all of them (the last suite on this project, so ending everything is fine)
  await page.goto(base + '?skipboot'); await page.waitForSelector('#menu.show', { timeout: 8000 }); await sleep(1500);
  check('home has End sessions when something is open', await page.isVisible('#tEnd'));
  await page.click('#tEnd'); await page.waitForSelector('#endP.show'); await sleep(200);
  const ends = await page.$$eval('#endOpts .opt b', els => els.map(e => e.textContent)), nOpen = await page.evaluate(() => SESSIONS.filter(x => !x.ended).length);
  check('the window offers this session, and all of them (with the count) when more than one is open',
    ends[0] === 'End this session' && (nOpen > 1 ? ends[1] === `End all ${nOpen} sessions` : ends.length === 1), `${nOpen} open: ${ends.join(' | ')}`);
  check('...and says navi --end-all does it from a terminal', /navi --end-all/.test(await page.textContent('#endP')));
  await page.click('#endOpts .opt >> nth=-1'); await sleep(600);
  check('ending closes them and says how many', /Ended \d+ sessions?/.test(await page.textContent('#endSub')), await page.textContent('#endSub'));
  check('then nothing is open: the button offers removing them', await waitFor(async () => (await page.textContent('#tEnd')).trim() === 'Remove sessions', 8000));
  await page.click('#tEnd'); await page.waitForSelector('#endP.show'); await sleep(200);
  check('the window offers removing the ended ones', /^Remove the \d+ ended sessions?$/.test((await page.textContent('#rmOpts .opt b')).trim()), await page.textContent('#rmOpts'));
  await page.click('#rmOpts .opt'); await sleep(200);
  check('removing asks for a second click first', /Click again/.test(await page.textContent('#rmOpts .opt small')) && (await page.evaluate(() => SESSIONS.length)) > 0);
  await page.click('#rmOpts .opt'); await sleep(800);
  check('the second click removes them for good', /Removed \d+ sessions?/.test(await page.textContent('#endSub')), await page.textContent('#endSub'));
  await waitFor(async () => !(await page.isVisible('#endP')), 3000);
  check('then nothing is left: the button stays, as End sessions', await waitFor(async () => (await page.isVisible('#tEnd')) && (await page.textContent('#tEnd')).trim() === 'End sessions', 8000),
    await page.textContent('#tEnd'));
  await page.click('#tEnd'); await page.waitForSelector('#endP.show'); await sleep(200);
  check('...and its window says there are none yet, and how to end them later', /No sessions in this folder yet/.test(await page.textContent('#endSub'))
    && await page.isVisible('#endNone') && /navi end/.test(await page.textContent('#endP')) && !(await page.$('#endOpts .opt')) && !(await page.$('#rmOpts .opt')));
  await page.click('#endClose'); await sleep(200);

  console.log(R.join('\n')); console.log('page errors:', errs.length ? errs : 'none');
  await browser.close();
  process.exit(R.some(x => x.startsWith('FAIL')) || errs.length ? 1 : 0);
})().catch(async e => { await cleanup(); console.log(R.join('\n')); console.error('COUNCILGEN FAIL', e.message); process.exit(1); });
