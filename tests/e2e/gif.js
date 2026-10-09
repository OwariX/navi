// usage: node gif.js <base-url> <video-dir>  — records the demo as a video (webm); ffmpeg turns it into the README gif
const { chromium } = require('playwright');
const [base, dir] = process.argv.slice(2);
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, recordVideo: { dir, size: { width: 1280, height: 800 } } });
  const page = await ctx.newPage();
  await page.goto(base + 'demo');            // with the boot sequence this time: it's the money shot
  await page.waitForSelector('#toasts .toast', { timeout: 90000 });
  await sleep(1500);
  await page.click('#toasts .toast'); await sleep(1800);
  await page.click('#askOpts .btn >> nth=0');
  await page.waitForSelector('#consensus.show', { timeout: 90000 });
  await sleep(3500);
  await ctx.close();
  await browser.close();
  console.log('recorded');
})().catch(e => { console.error('GIF FAIL', e.message); process.exit(1); });
