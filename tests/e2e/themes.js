// usage: node themes.js <base-url> <out-dir>
// Every theme, picked in Settings like a person would: each applies at once (no reload), is saved, survives a reload,
// and home, the fixture session and Settings render without page errors. The canvas takes its colours from the theme,
// CRT raises edge darkness (never grain) only while it is on, Cancel puts the old theme back, text in the new themes keeps 4.5:1,
// the themes with their own colourways keep 4.5:1 in every one of them, and every theme's sounds play.
// Screenshots: theme-<name>-home.png, theme-<name>-session.png, theme-<name>-settings.png,
//              theme-<name>-<colourway>-home.png and theme-<name>-<colourway>-session.png for Journey's End and Devil Hunter
const { chromium } = require('playwright');
const [base, out] = process.argv.slice(2);
const SID = '20261006-144220';
const ORDER = ['crt', 'glass', 'minimal', 'minidark', 'eva', 'journey', 'hunter', 'wired'];   // wired last: the suites after this one expect it
const sleep = ms => new Promise(r => setTimeout(r, ms));
// text below 4.5:1 (3:1 when large) in the visible page: colour against its backgrounds composited over the theme's canvas colour
const lowContrast = () => {
  const parse = c => {
    let m = c.match(/rgba?\(([^)]+)\)/); if (m){ const v = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return [v[0], v[1], v[2], v[3] ?? 1]; }
    m = c.match(/color\(srgb ([^)]+)\)/); if (m){ const v = m[1].split(/[ /]+/).filter(Boolean).map(Number); return [v[0] * 255, v[1] * 255, v[2] * 255, v[3] ?? 1]; }
    return null;
  };
  const over = (a, b) => [0, 1, 2].map(i => a[i] * a[3] + b[i] * (1 - a[3]));
  const lin = v => (v /= 255) <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4;
  const L = c => .2126 * lin(c[0]) + .7152 * lin(c[1]) + .0722 * lin(c[2]);
  const low = [], walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()){
    const e = walker.currentNode.parentElement; if (!walker.currentNode.textContent.trim() || !e || e.closest('svg,style,script,.tp,#boot,option,:disabled,.off')) continue;
    const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
    if (!r.width || !r.height || r.bottom < 0 || r.top > innerHeight || cs.visibility === 'hidden') continue;
    const hit = document.elementFromPoint(Math.min(innerWidth - 1, Math.max(0, r.left + r.width / 2)), Math.min(innerHeight - 1, Math.max(0, r.top + r.height / 2)));
    if (!hit || !(e.contains(hit) || hit.contains(e))) continue;               // covered by something else
    let bg = rgb(TH.bg), op = 1; const chain = [];
    for (let x = e; x; x = x.parentElement){ chain.push(x); op *= +getComputedStyle(x).opacity; }
    if (op < .2) continue;
    for (const x of chain.reverse()){
      const xs = getComputedStyle(x), b = parse(xs.backgroundColor), img = xs.backgroundImage;
      if (b && b[3] > 0) bg = over(b, bg);
      else if ((img.match(/gradient\(/g) || []).length === 1){              // a fill that is one gradient: its average colour
        const stops = (img.match(/rgba?\([^)]+\)|color\(srgb [^)]+\)/g) || []).map(parse).filter(Boolean);
        if (stops.length) bg = over([0, 1, 2, 3].map(i => stops.reduce((s, c) => s + c[i], 0) / stops.length), bg);
      }
    }
    const f = parse(cs.color); if (!f) continue;
    const fg = over([f[0], f[1], f[2], f[3] * op], bg), c = (Math.max(L(fg), L(bg)) + .05) / (Math.min(L(fg), L(bg)) + .05);
    const large = parseFloat(cs.fontSize) >= 24 || parseFloat(cs.fontSize) >= 18.66 && +cs.fontWeight >= 700;
    if (c < (large ? 3 : 4.5)) low.push(`${c.toFixed(2)} "${walker.currentNode.textContent.trim().slice(0, 24)}"`);
  }
  return low;
};
const R = []; const check = (n, ok, x = '') => R.push(`${ok ? 'PASS' : 'FAIL'}  ${n}${x ? '  · ' + x : ''}`);
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript(() => { try { localStorage.setItem('navi.tour', '1'); } catch {} });
  const page = await ctx.newPage();
  const errs = []; page.on('pageerror', e => errs.push(e.message));
  const theme = () => page.evaluate(() => document.documentElement.dataset.theme);
  const saved = () => page.evaluate(async () => (await (await fetch('/settings')).json()));
  const home = async () => { await page.goto(base + '?skipboot'); await page.waitForSelector('#menu.show', { timeout: 8000 }); await sleep(500); };
  // the finite animations and transitions running now, finished (a busy machine runs them slower than any fixed wait)
  const settled = () => page.evaluate(() => Promise.race([new Promise(r => setTimeout(r, 4000)), Promise.all(document.getAnimations()
    .filter(a => isFinite(a.effect?.getComputedTiming().endTime)).map(a => a.finished.catch(() => {})))])).catch(() => {});
  const settings = async () => { await home(); await page.click('#tSettings'); await page.waitForSelector('#setup.show'); await sleep(300); await settled(); };
  const gallery = async () => { await page.click('#curTheme'); await page.waitForSelector('#themesm.show'); await sleep(250); };
  const pick = async t => { await gallery(); await page.click(`#themePick .theme[data-t="${t}"]`); await sleep(250); await page.click('#thDone'); await sleep(150); };

  // ---- the picker: a card per theme at the top of Look, the same sheet as the first-run setup
  await settings();
  check('Settings shows the theme you have, with a way to all of them', /The Wired/.test(await page.textContent('#curTheme')) && /All themes · \d+/.test(await page.textContent('#curTheme')));
  await gallery();
  const cards = await page.$$eval('#themePick .theme', els => els.map(e => `${e.dataset.t}:${e.querySelector('.nm').textContent}`));
  check('Settings shows the eight built-in themes as cards (then your own skins)', cards.slice(0, 8).join(',') === 'wired:The Wired,crt:CRT,glass:Liquid glass,minimal:Minimal,minidark:Minimal dark,eva:MAGI,journey:Journey\'s End,hunter:Devil Hunter', cards.join(','));
  check('each card carries a small preview', (await page.$$eval('#themePick .theme .tp', els => els.filter(e => e.children.length && e.offsetHeight > 40).length)) === cards.length);
  check('The Wired is the default and marked current', await theme() === 'wired' && await page.getAttribute('#themePick .theme[data-t="wired"]', 'aria-pressed') === 'true');
  const groups = await page.$$eval('#themePick .thgrp h4', els => els.map(e => e.firstChild.textContent));
  check('the themes window groups them: NAVI, Stories, Yours', groups.join(',') === 'NAVI,Stories,Yours', groups.join(','));
  check('a theme with colourways shows them as dots', (await page.$$eval('#themePick .theme[data-t="journey"] .tw i', els => els.map(e => e.title))).join(',') === 'Frieren,Himmel,Fern,Stark');
  await page.fill('#thFind', 'blood'); await sleep(150);
  check('finding "blood" leaves Devil Hunter', (await page.$$eval('#themePick .theme', els => els.map(e => e.dataset.t))).join(',') === 'hunter');
  await page.fill('#thFind', ''); await sleep(150);
  await page.click('#themePick .theme[data-t="journey"] .tw i[title="Himmel"]'); await sleep(250);
  check('a colourway dot picks the theme in that colour', await theme() === 'journey' && await page.evaluate(() => S.variant) === 'Himmel' && /Himmel/.test(await page.textContent('#curTheme')));
  await page.click('#themePick .theme[data-t="minimal"]'); await sleep(200);
  const previewed = await theme();
  await page.keyboard.press('Escape'); await sleep(250);
  check('Esc closes the themes window back to Settings', !(await page.isVisible('#themesm')) && await page.isVisible('#setup'));
  await page.keyboard.press('Escape'); await sleep(300);
  check('Cancel puts the previous theme back', previewed === 'minimal' && await theme() === 'wired' && (await saved()).theme === 'wired', `${previewed} -> ${await theme()}`);

  for (const t of ORDER) {
    // pick it: instant, no reload
    await settings();
    const was = await page.evaluate(() => ({ grain: S.grain, vignette: S.vignette }));
    await page.evaluate(() => { window.__noReload = 1; });
    await pick(t);
    check(`${t}: applies at once, without a reload`, await theme() === t && await page.evaluate(() => window.__noReload === 1));
    const atmo = await page.evaluate(() => ({ grain: S.grain, vignette: S.vignette, g: $('input[data-k="grain"]').value, v: $('input[data-k="vignette"]').value }));
    if (t === 'crt') check('crt: raises edge darkness (never grain) while it is on, and the sliders show it', atmo.grain === 0 && atmo.vignette >= 60 && +atmo.g === atmo.grain && +atmo.v === atmo.vignette, JSON.stringify(atmo));
    if (t === 'glass') check('leaving crt puts grain and edge darkness back', atmo.grain === 0 && atmo.vignette === 0, `${JSON.stringify(was)} -> ${JSON.stringify(atmo)}`);
    if (t === 'minimal') check('minimal: scanlines, glow and flicker say they are off', await page.$$eval('#setup .off', els => els.length) === 3 && await page.isDisabled('input[data-k="glow"]'));
    await page.click('#sNext'); await sleep(700);
    check(`${t}: saved to the config`, (await saved()).theme === t);
    await page.screenshot({ path: `${out}/theme-${t}-home.png` });

    // it survives a reload
    await page.reload(); await page.waitForSelector('#menu.show', { timeout: 8000 }); await sleep(400);
    check(`${t}: persists after a reload`, await theme() === t);

    // the fixture session: page, canvas and agent colours follow the theme
    await page.goto(`${base}s/${SID}?skipboot`); await sleep(3200);
    const cv = await page.evaluate(() => {
      const d = $('#stage').getContext('2d').getImageData(Math.round(6 * DPR), Math.round((innerHeight - 6) * DPR), 1, 1).data;
      const want = rgb(TH.bg), th = THEMES[S.theme], v = th.variants ? th.variants[S.variant] || th.variants[defVariant(th)] : null, ink = ((v && v.ink) || th.ink || INK_WIRED).agents;
      return { near: [0, 1, 2].every(i => Math.abs(d[i] - want[i]) <= 8), px: [...d].slice(0, 3), want, page: getComputedStyle(document.body).backgroundColor,
               agents: colorOf('architect') === ink.architect && colorOf('warden') === ink.warden, nodes: nodes.size };
    });
    check(`${t}: session page in the theme, canvas drawn in its colours`, await theme() === t && cv.near && cv.agents && cv.nodes >= 4, `canvas ${cv.px} vs ${cv.want}, ${cv.nodes} nodes`);
    const lowS = await page.evaluate(lowContrast);
    await page.screenshot({ path: `${out}/theme-${t}-session.png` });

    // settings, opened in the theme
    await settings();
    check(`${t}: Settings marks it current`, await page.getAttribute(`#themePick .theme[data-t="${t}"]`, 'aria-pressed') === 'true' && (await page.$$eval('#themePick .theme.on', els => els.length)) === 1);
    { const low = [...lowS, ...await page.evaluate(lowContrast)]; check(`${t}: text keeps 4.5:1 on the session page and in Settings`, !low.length, low.slice(0, 6).join(', ')); }
    await page.screenshot({ path: `${out}/theme-${t}-settings.png` });
    await page.keyboard.press('Escape'); await sleep(200);
  }

  // a live switch recolours what is already drawn: the wires on the canvas take the new palette at once
  await page.goto(`${base}s/${SID}?skipboot`); await sleep(3000);
  await page.click('#cog'); await page.waitForSelector('#setup.show'); await sleep(200);
  await pick('minimal');
  const wires = await page.evaluate(() => { const pal = new Set(canvasColors()), cols = [...links.values()].map(L => L.color); return { n: cols.length, off: [...new Set(cols.filter(c => !pal.has(c)))] }; });
  check('a live switch recolours the wires already on the canvas', wires.n > 0 && !wires.off.length, `${wires.n} wires${wires.off.length ? ', still old: ' + wires.off.join(' ') : ''}`);
  await page.keyboard.press('Escape'); await sleep(200);

  // MAGI: its own colourways instead of the palettes, saved; the rainbow one; and the themes' taglines on home
  await page.goto(base + '?skipboot'); await sleep(1200);
  const tag = async () => (await page.textContent('#menu .tagline')).trim();
  check('The Wired has its own tagline on home', await tag() === 'No matter where you go, everyone is connected.', await tag());
  await page.click('#tSettings'); await page.waitForSelector('#setup.show'); await sleep(200);
  await pick('eva');
  const ways = await page.$$eval('#presets .preset .nm', els => els.map(e => e.textContent));
  check('MAGI shows its own colourways instead of the palettes', ways.join(',') === '00,01,02,03,08,+1.0', ways.join(','));
  check('nothing on the page says Evangelion', !/evangelion/i.test(await page.evaluate(() => document.body.innerText)));
  await page.click('#presets .preset:has-text("02")'); await sleep(200);
  check('picking 02 recolours at once', await page.evaluate(() => TH.accent) === '#da4549');
  await page.click('#sNext'); await sleep(500);
  check('MAGI shows its own tagline', await tag() === 'You are (not) alone.', await tag());
  await page.reload(); await sleep(1500);
  check('the colourway survives a reload', (await saved()).variant === '02' && await page.evaluate(() => TH.accent) === '#da4549');
  await page.evaluate(() => post('/settings', {...S, variant: '+1.0'})); await page.reload(); await sleep(1500);
  check('+1.0 turns the rainbow on', await page.evaluate(() => document.documentElement.dataset.variant) === 'rainbow');
  await page.screenshot({ path: `${out}/theme-magi-rainbow-home.png` });
  await page.evaluate(() => post('/settings', {...S, theme: 'crt', variant: ''})); await page.reload(); await sleep(1500);
  check('CRT has its own tagline', await tag() === 'Close the world. Open the next.', await tag());
  check('CRT no longer raises grain', (await saved()).grain === 0);
  await page.evaluate(() => post('/settings', {...S, theme: 'glass'})); await page.reload(); await sleep(1500);
  check('themes that reference nothing keep the plain tagline', /council of AI agents/.test(await tag()), await tag());
  await page.evaluate(() => post('/settings', {...S, theme: 'wired', variant: ''})); await page.reload(); await sleep(1500);

  // Journey's End and Devil Hunter: their own colourways in the palette row, each one recolours the page and the canvas, keeps 4.5:1 on home,
  // the session page and in Settings, survives a reload, and the theme's own tagline shows on home
  const OWN = { journey: { ways: ['Frieren', 'Himmel', 'Fern', 'Stark'], tagline: 'The hero would have done the same.' },
                hunter: { ways: ['Chainsaw', 'Control', 'Blood'], tagline: 'Pull the cord.' } };
  for (const [t, own] of Object.entries(OWN)) {
    await settings(); await pick(t);
    const ways = await page.$$eval('#presets .preset .nm', els => els.map(e => e.textContent));
    check(`${t}: shows its own colourways instead of the palettes`, ways.join(',') === own.ways.join(','), ways.join(','));
    check(`${t}: nothing on the page names a series`, !/chainsaw man|evangelion|sousou no/i.test(await page.evaluate(() => document.body.innerText)));
    await page.click('#sNext'); await sleep(500);
    for (const v of own.ways) {
      const tag = `${t}-${v.toLowerCase()}`, pal = await page.evaluate(([t, v]) => THEMES[t].variants[v].pal, [t, v]);
      await settings(); await page.click(`#presets .preset:has-text("${v}")`); await sleep(200);
      check(`${tag}: picking it recolours at once`, await page.evaluate(() => [TH.bg, TH.accent, TH.accent2].join()) === [pal.bg, pal.accent, pal.accent2].join());
      const lowSet = await page.evaluate(lowContrast);
      await page.click('#sNext'); await sleep(500);
      await page.reload(); await page.waitForSelector('#menu.show', { timeout: 8000 }); await sleep(1300);
      const kept = await page.evaluate(() => ({ theme: document.documentElement.dataset.theme, variant: document.documentElement.dataset.variant, accent: TH.accent }));
      check(`${tag}: survives a reload`, (await saved()).variant === v && kept.theme === t && kept.variant === v && kept.accent === pal.accent, JSON.stringify(kept));
      check(`${tag}: home shows the theme's tagline`, (await page.textContent('#menu .tagline')).trim() === own.tagline, await page.textContent('#menu .tagline'));
      const lowHome = await page.evaluate(lowContrast);
      await page.screenshot({ path: `${out}/theme-${tag}-home.png` });
      await page.goto(`${base}s/${SID}?skipboot`); await sleep(3200);
      const cv = await page.evaluate(() => {
        const d = $('#stage').getContext('2d').getImageData(Math.round(6 * DPR), Math.round((innerHeight - 6) * DPR), 1, 1).data, want = rgb(TH.bg);
        return { near: [0, 1, 2].every(i => Math.abs(d[i] - want[i]) <= 8), px: [...d].slice(0, 3), bg: TH.bg, nodes: nodes.size };
      });
      check(`${tag}: the canvas is drawn in the colourway`, cv.near && cv.bg === pal.bg && cv.nodes >= 4, `canvas ${cv.px} vs ${cv.bg}`);
      const low = [...lowSet, ...lowHome, ...await page.evaluate(lowContrast)];
      check(`${tag}: text keeps 4.5:1 on home, the session page and in Settings`, !low.length, low.slice(0, 6).join(', '));
      await page.screenshot({ path: `${out}/theme-${tag}-session.png` });
    }
  }
  await page.evaluate(() => post('/settings', {...S, theme: 'wired', variant: ''})); await page.reload(); await sleep(1500);

  // your own skin: in the picker, applied, saved, and its CSS can't load anything from outside
  await page.goto(base + '?skipboot'); await sleep(1200);
  await page.click('#tSettings'); await page.waitForSelector('#setup.show'); await sleep(200);
  await gallery();
  check('your own skin is in the picker', await page.isVisible('#themePick .theme[data-t="acme"]') && /Acme/.test(await page.textContent('#themePick .theme[data-t="acme"]')));
  await page.click('#themePick .theme[data-t="acme"]'); await sleep(250); await page.click('#thDone'); await sleep(150); await page.click('#sNext'); await sleep(500);
  await page.reload(); await sleep(1500);
  check('your skin applies and survives a reload', await theme() === 'acme' && (await saved()).theme === 'acme' && await page.evaluate(() => TH.accent) === '#4f8cff');
  const css = await page.evaluate(async () => (await fetch('/themes/acme.css')).text());
  check('a skin can never load from outside (@import and remote url() removed)', !/https?:/.test(css) && !/@import\s+url/.test(css) && /\.composer/.test(css));
  await page.evaluate(() => post('/settings', {...S, theme: 'wired', variant: ''})); await page.reload(); await sleep(1200);

  // every theme's sound kit plays every cue without an error (headless: nothing is heard)
  const snd = await page.evaluate(async () => {
    const was = S.theme, bad = [];
    sfx.set(true); instant = false;
    for (const t of Object.keys(THEMES)) {
      S.theme = t; sfx.retheme();
      try { sfx.boot(); sfx.tick(true); sfx.join(); sfx.send('proposal'); sfx.send('challenge'); sfx.send('verdict'); sfx.click('reject'); sfx.click('ack');
            sfx.ping(); sfx.gate('allow'); sfx.gate('ask'); sfx.gate('deny'); sfx.chord(); sfx.sample(); } catch (e) { bad.push(`${t}: ${e.message}`); }
    }
    S.theme = was; sfx.retheme(); await new Promise(r => setTimeout(r, 600)); sfx.set(false);
    return bad;
  });
  check('every theme has its own sounds, and all of them play', !snd.length, snd.join('; '));
  check('back on Wired for the suites that follow', (await saved()).theme === 'wired' && await theme() === 'wired');

  console.log(R.join('\n')); console.log('page errors:', errs.length ? errs : 'none');
  // sound in three parts: alerts, clicks, ambience, each its own switch under Sound
  await settings();
  const parts = await page.$$eval('#sndParts label', els => els.map(e => e.firstChild.nextSibling.textContent.trim()));
  check('sound comes in three parts: Alerts, Clicks, Ambience', parts.join(',') === 'Alerts,Clicks,Ambience', parts.join(','));
  if (await page.isChecked('input[data-k="sound"]')) { await page.click('input[data-k="sound"]'); await sleep(100); }
  check('with Sound off the three parts are hidden', !(await page.isVisible('#sndParts')));
  await page.click('input[data-k="sound"]'); await sleep(100);
  await page.click('input[data-k="sound_clicks"]'); await page.click('input[data-k="sound_ambient"]'); await sleep(100);
  await page.click('#sNext'); await sleep(600);
  const sndCfg = await saved();
  check('just alerts: saved as sound on, alerts on, clicks and ambience off', sndCfg.sound === true && sndCfg.sound_alerts === true && sndCfg.sound_clicks === false && sndCfg.sound_ambient === false, JSON.stringify({sound: sndCfg.sound, a: sndCfg.sound_alerts, c: sndCfg.sound_clicks, m: sndCfg.sound_ambient}));
  await page.evaluate(() => post('/settings', {sound: false, sound_clicks: true, sound_ambient: true}));
  await browser.close();
  process.exit(R.some(r => r.startsWith('FAIL')) || errs.length ? 1 : 0);
})().catch(e => { console.log(R.join('\n')); console.error('THEMES FAIL', e.message); process.exit(1); });
