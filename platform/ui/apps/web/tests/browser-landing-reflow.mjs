// Read-only public-page regression against a running local web build.
// No login, provider calls, database fixtures or tenant information are required.
import { chromium } from 'playwright-core';
import assert from 'node:assert/strict';

const origin = process.env.PMS_TEST_WEB_ORIGIN || 'http://127.0.0.1:3188';
const browser = await chromium.launch({
  executablePath: process.env.PMS_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  headless: true,
});
const checks = [];
try {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  for (const route of ['/', '/privacy', '/terms']) {
    await page.goto(new URL(route, origin).href, { waitUntil: 'networkidle' });
    for (const textSize of ['100%', '200%']) {
      await page.evaluate(value => { document.documentElement.style.fontSize = value; }, textSize);
      for (const width of [320, 390, 640, 820, 1024, 1440]) {
        await page.setViewportSize({ width, height: 900 });
        const dimensions = await page.evaluate(() => ({ viewport: innerWidth, scroll: document.documentElement.scrollWidth }));
        assert.ok(dimensions.scroll <= dimensions.viewport, `${route} at ${textSize}/${width}px overflows: ${dimensions.scroll}px`);
        if (await page.locator('header summary').isVisible()) {
          const menu = page.locator('header details');
          await menu.locator('summary').click();
          const bounds = await menu.locator('nav').boundingBox();
          assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= width + 1, `${route}: expanded menu overflows at ${textSize}/${width}px`);
          await page.keyboard.press('Escape');
          assert.equal(await menu.evaluate(element => element.open), false);
        }
      }
      checks.push(`${route}: ${textSize} text at six widths; expanded mobile menu stays in view`);
    }
    await page.evaluate(() => document.documentElement.style.removeProperty('font-size'));
  }
  for (const textSize of ['100%', '200%']) {
    for (const width of [320, 640]) {
      await page.setViewportSize({ width, height: 360 });
      await page.goto(origin, { waitUntil: 'networkidle' });
      await page.evaluate(value => { document.documentElement.style.fontSize = value; }, textSize);
      await page.locator('header summary').click();
      const nav = await page.locator('header nav[aria-label="Mobile navigation"]').boundingBox();
      assert.ok(nav.y + nav.height <= 360, `Landscape menu extends below viewport at ${textSize}/${width}px`);
      await page.keyboard.press('Escape');
    }
  }
  await page.evaluate(() => document.documentElement.style.removeProperty('font-size'));
  await page.locator('#faq summary').first().focus();
  await page.keyboard.press('Enter');
  assert.equal(await page.locator('#faq details').first().evaluate(element => element.open), true);
  const summary = await page.locator('#faq summary').first().boundingBox();
  const header = await page.locator('header').boundingBox();
  assert.ok(summary.y >= header.y + header.height, 'Focused FAQ obscured by sticky header');
  checks.push('Landscape: menu fits, FAQ keyboard interaction and sticky-header focus clearance');
  assert.deepEqual(errors, [], 'Browser page errors');
  console.log(JSON.stringify({ passed: true, checks }, null, 2));
} finally {
  await browser.close();
}
