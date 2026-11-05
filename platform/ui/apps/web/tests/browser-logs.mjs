import { chromium } from 'playwright-core';
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
let input = '';
for await (const chunk of process.stdin) input += chunk;
const fixture = JSON.parse(input);
const browser = await chromium.launch({ executablePath: process.env.PMS_TEST_BROWSER ?? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
page.setDefaultTimeout(30000);
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const rows = () => page.getByRole('table', { name: 'Logs', exact: true }).getByRole('row').filter({ has: page.getByRole('link') });
const search = () => page.getByRole('searchbox', { name: 'Search logs' });
async function expectRows(count) {
  if (count) await rows().nth(count - 1).waitFor();
  await rows().nth(count).waitFor({ state: 'hidden' });
  assert.equal(await rows().count(), count);
}
async function settled() { await page.getByRole('button', { name: 'Refresh logs', exact: true }).waitFor(); await page.waitForFunction(() => !Array.from(document.querySelectorAll('button')).find(b => b.textContent === 'Refresh logs')?.disabled); }
async function switchTo(id) {
  if (await page.getByLabel('Switch organisation').inputValue() !== id) {
    await page.getByLabel('Switch organisation').selectOption(id); await page.waitForURL('**/home');
  }
  await page.goto(fixture.origin + '/logs'); await settled();
}
let step = 'anonymous redirect and authenticated platform audit';
function passed() { console.log('PASS ' + step); }
try {
  await page.goto(fixture.origin + '/logs'); await page.waitForURL('**/login');
  await page.getByLabel('Email address', { exact: true }).fill(fixture.email);
  await page.getByLabel('Password', { exact: true }).fill(fixture.password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click(); await page.waitForURL('**/home');
  await switchTo('platform');
  await search().fill('fixture.');
  await page.getByRole('link', { name: 'fixture.audit', exact: true }).waitFor();
  await page.getByRole('status').filter({ hasText: /^1 log$/ }).waitFor();
  await expectRows(1);
  assert.equal(await page.getByLabel('Category', { exact: true }).locator('option').count(), 1);
  assert.equal(await page.getByText('Preview data', { exact: false }).count(), 0);
  passed();
  step = 'direct audit details, redaction and reload';
  await page.getByRole('link', { name: 'fixture.audit', exact: true }).click(); await page.waitForURL('**/logs/' + fixture.audit);
  await page.getByRole('heading', { name: 'fixture.audit', exact: true }).waitFor();
  await page.getByText(/Other payload fields have been omitted/).waitFor();
  assert.ok(!(await page.locator('main').innerText()).includes('private-browser'));
  await page.reload(); await page.getByRole('heading', { name: 'fixture.audit', exact: true }).waitFor(); passed();
  step = 'platform cannot read tenant operational details';
  await page.goto(fixture.origin + '/logs/' + fixture.operation);
  await page.getByRole('heading', { name: 'Log not available', exact: true }).waitFor(); passed();
  step = 'tenant pagination and real counts';
  await switchTo(fixture.org); await search().fill('fixture.page.');
  await page.getByRole('status').filter({ hasText: /^28 logs$/ }).waitFor();
  await expectRows(25);
  await page.getByRole('button', { name: 'Next page of logs' }).click(); await settled();
  await expectRows(3);
  await page.getByRole('button', { name: 'Previous page of logs' }).click(); await settled();
  await expectRows(25); passed();
  step = 'category, severity, dates, empty search, refresh and reset';
  await page.getByRole('button', { name: 'Clear filters', exact: true }).click();
  await page.getByLabel('Category', { exact: true }).selectOption('operational');
  await page.getByLabel('Severity', { exact: true }).selectOption('error');
  await page.getByRole('link', { name: 'fixture.operational', exact: true }).waitFor();
  const day = new Date().toISOString().slice(0, 10);
  await page.getByLabel('Occurred from (UTC)').fill(day);
  await page.getByLabel('Occurred through (UTC)').fill(day);
  await page.getByRole('button', { name: 'Apply date and ID filters', exact: true }).click(); await settled();
  await page.getByRole('status').filter({ hasText: /^1 log$/ }).waitFor();
  await expectRows(1);
  await search().fill('no-such-event'); await page.getByText('No matching logs', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Clear filters', exact: true }).click(); await settled();
  await page.getByRole('button', { name: 'Refresh logs', exact: true }).click(); await settled();
  passed();
  step = 'tenant deep link and expired event handling';
  await page.goto(fixture.origin + '/logs/' + fixture.operation);
  await page.getByRole('heading', { name: 'fixture.operational', exact: true }).waitFor();
  assert.ok(!(await page.locator('main').innerText()).includes('private-browser'));
  await page.goto(fixture.origin + '/logs/' + fixture.expired);
  await page.getByRole('heading', { name: 'Log not available', exact: true }).waitFor();
  await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await page.getByRole('heading', { name: 'Log not available', exact: true }).waitFor(); passed();
  step = 'selected tenant boundary and mobile layout';
  await switchTo(fixture.otherOrg);
  await page.goto(fixture.origin + '/logs/' + fixture.operation);
  await page.getByRole('heading', { name: 'Log not available', exact: true }).waitFor();
  await switchTo(fixture.org); await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('heading', { name: 'Activity logs', exact: true }).waitFor(); await settled();
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'Mobile horizontal overflow');
  await mkdir('../../../../.test_artifacts/logs-web', { recursive: true });
  await page.screenshot({ path: '../../../../.test_artifacts/logs-web/mobile.png', fullPage: true });
  assert.deepEqual(errors, []); passed();
} catch (error) {
  console.error('FAIL ' + step + ': ' + error.message);
  process.exitCode = 1;
} finally { await browser.close(); }
