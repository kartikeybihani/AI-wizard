const { chromium } = require('@playwright/test');

const baseUrl = process.argv[2] || 'http://127.0.0.1:3026';

async function collectState(page, tag) {
  return page.evaluate((stateTag) => {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const sectionRects = Array.from(document.querySelectorAll('.narrative-section')).map((el) => {
      const rect = el.getBoundingClientRect();
      const title = el.querySelector('.narrative-title')?.textContent?.trim() || '';
      return {
        title,
        left: Math.round(rect.left),
        right: Math.round(rect.right),
        top: Math.round(rect.top),
        bottom: Math.round(rect.bottom),
        width: Math.round(rect.width),
        offscreenX: rect.left < 0 || rect.right > vw,
      };
    });

    const buttons = Array.from(document.querySelectorAll('button'))
      .map((b) => (b.textContent || '').replace(/\s+/g, ' ').trim())
      .filter(Boolean)
      .slice(0, 24);

    const debugDrawer = document.querySelector('.debug-drawer');
    const debugTrigger = document.querySelector('.debug-trigger');

    return {
      stateTag,
      viewport: { vw, vh },
      title: document.title,
      pageHeader: document.querySelector('.landing-page-title')?.textContent?.trim() || null,
      sectionTitles: Array.from(document.querySelectorAll('.narrative-title')).map((n) => n.textContent?.trim() || ''),
      sectionRects,
      hasHorizontalOverflow: document.documentElement.scrollWidth > vw,
      hasVerticalOverflow: document.documentElement.scrollHeight > vh,
      callButton: Array.from(document.querySelectorAll('button')).find((b) => (b.textContent || '').includes('Call Blake'))?.textContent?.trim() || null,
      diagnosticsExpanded: Boolean(debugDrawer),
      diagnosticsAriaExpanded: debugTrigger?.getAttribute('aria-expanded') || null,
      buttons,
    };
  }, tag);
}

async function runScenario(viewport, name) {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();

  await page.goto(baseUrl, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);

  const before = await collectState(page, `${name}-before`);
  await page.screenshot({ path: `/tmp/ui_blake_${name}_before.png`, fullPage: true });

  await page.evaluate(() => {
    window.__UI_BLAKE_MOCK_SESSION__ = true;
  });

  const callBtn = page.getByRole('button', { name: /Call Blake/i });
  if ((await callBtn.count()) > 0) {
    await callBtn.click();
    await page.waitForTimeout(1300);
  }

  const after = await collectState(page, `${name}-after`);
  await page.screenshot({ path: `/tmp/ui_blake_${name}_after.png`, fullPage: true });

  await browser.close();
  return { before, after };
}

(async () => {
  const desktop = await runScenario({ width: 1440, height: 900 }, 'desktop');
  const mobile = await runScenario({ width: 390, height: 844 }, 'mobile');
  console.log(JSON.stringify({ desktop, mobile }, null, 2));
})();
