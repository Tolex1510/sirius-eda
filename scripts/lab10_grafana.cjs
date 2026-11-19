// Screenshot a local disposable Grafana dashboard; uses the project's Playwright.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { chromium } = require('../frontend/node_modules/playwright');
(async () => {
  const options = {headless: true};
  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE) options.executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE;
  else if (!fs.existsSync(chromium.executablePath())) {
    const cache = path.join(os.homedir(), '.cache/ms-playwright');
    const candidates = fs.existsSync(cache) ? fs.readdirSync(cache).filter(x => /^chromium-\d+$/.test(x)).sort().reverse() : [];
    for (const name of candidates) {
      const candidate = path.join(cache, name, 'chrome-linux64/chrome');
      if (fs.existsSync(candidate)) { options.executablePath = candidate; break; }
    }
  }
  const browser = await chromium.launch(options);
  try {
    const page = await browser.newPage({viewport: {width: 1500, height: 1250}});
    await page.goto(process.argv[2] + '/d/sirius-lab10?orgId=1&kiosk&from=now-5m&to=now', {waitUntil: 'networkidle'});
    await page.getByText('Celery pending tasks', {exact: true}).waitFor();
    await page.waitForTimeout(4000);
    await page.screenshot({path: process.argv[3], fullPage: true});
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode=1; });
