import { chromium } from 'playwright-core';
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
let input = ''; for await (const chunk of process.stdin) input += chunk;
const fixture = JSON.parse(input);
const browser = await chromium.launch({ executablePath: process.env.PMS_TEST_BROWSER ?? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage(); page.setDefaultTimeout(30000);
const errors = []; page.on('pageerror', e => errors.push(e.message));
let token; let step = 'authentication and subscription directory';
function passed() { console.log('PASS ' + step); }
async function api(path, method = 'GET', body, bearer = token) {
  const response = await fetch(fixture.api + path, { method, headers: { Authorization: 'Bearer ' + bearer, 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
  assert.equal(response.status, 200, 'API ' + method + ' ' + path); return response.json();
}
async function switchTo(id) {
  if (await page.getByLabel('Switch organisation').inputValue() !== id) { await page.getByLabel('Switch organisation').selectOption(id); await page.waitForURL('**/home'); }
}
async function confirm(title, name) {
  const dialog = page.getByRole('dialog', { name: title, exact: true });
  await dialog.getByRole('button', { name, exact: true }).click(); await dialog.waitFor({ state: 'hidden' });
}
const path = '/platform/organizations/' + fixture.source + '/subscription';
const inputDate = days => new Date(Date.now() + days * 86400000).toISOString().slice(0, 19);
try {
  await page.goto(fixture.origin + '/licenses'); await page.waitForURL('**/login');
  await page.getByLabel('Email address', { exact: true }).fill(fixture.email); await page.getByLabel('Password', { exact: true }).fill(fixture.password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click(); await page.waitForURL('**/home');
  token = (await context.cookies()).find(c => c.name.endsWith('ae-session')).value;
  await switchTo('platform'); await page.goto(fixture.origin + '/licenses');
  await page.getByRole('heading', { name: 'Subscriptions', exact: true }).waitFor();
  await page.getByRole('link', { name: 'Source subscription tenant', exact: true }).waitFor(); passed();
  step = 'manual plan catalog edit and persistence';
  await page.getByRole('button', { name: 'Edit Standard plan', exact: true }).click();
  await page.getByLabel('Price amount', { exact: true }).fill('1234.56');
  await page.getByLabel('Billing period', { exact: true }).selectOption('annual');
  await page.getByRole('button', { name: 'Review plan changes', exact: true }).click();
  await confirm('Apply catalog changes?', 'Save plan');
  assert.equal((await api('/platform/subscription-plans')).items.find(p => p.code === 'standard').price_amount, '1234.56'); passed();
  step = 'manual expiry and private reference without processing restrictions';
  await page.getByRole('link', { name: 'Source subscription tenant', exact: true }).click(); await page.waitForURL('**/licenses/' + fixture.source);
  await page.getByRole('button', { name: 'Edit or renew subscription', exact: true }).click();
  await page.getByLabel('Starts at (UTC)', { exact: true }).fill(inputDate(-30));
  await page.getByLabel('Ends at (UTC)', { exact: true }).fill(inputDate(-1));
  await page.getByLabel('Manual reference', { exact: true }).fill('Browser agreement');
  await page.getByLabel('Internal notes', { exact: true }).fill('Browser private note');
  await page.getByRole('button', { name: 'Save subscription', exact: true }).click();
  await page.getByRole('dialog', { name: 'Edit or renew Source subscription tenant', exact: true }).waitFor({ state: 'hidden' });
  assert.equal((await api(path)).state, 'expired');
  assert.equal((await api('/device/config', 'GET', undefined, fixture.credential)).processing_allowed, true); passed();
  step = 'renewal and direct detail reload';
  await page.getByRole('button', { name: 'Edit or renew subscription', exact: true }).click();
  await page.getByLabel('Ends at (UTC)', { exact: true }).fill(inputDate(365));
  await page.getByRole('button', { name: 'Save subscription', exact: true }).click();
  await page.getByRole('dialog', { name: 'Edit or renew Source subscription tenant', exact: true }).waitFor({ state: 'hidden' });
  await page.reload(); await page.getByText('Standard subscription', { exact: true }).waitFor();
  assert.equal((await api(path)).state, 'active'); passed();
  step = 'suspension resume cancellation and retained history';
  await page.getByRole('button', { name: 'Suspend subscription', exact: true }).click(); await confirm('Suspend subscription?', 'Confirm status change');
  assert.equal((await api(path)).state, 'suspended');
  await page.getByRole('button', { name: 'Resume subscription', exact: true }).click(); await confirm('Resume subscription?', 'Confirm status change');
  await page.getByRole('button', { name: 'Cancel subscription', exact: true }).click(); await confirm('Cancel subscription?', 'Confirm status change');
  assert.equal((await api(path)).state, 'cancelled');
  assert.equal((await api('/device/config', 'GET', undefined, fixture.credential)).processing_allowed, true);
  assert.ok((await api(path + '/history')).total >= 5); passed();
  step = 'tenant read-only subscription and private-note isolation';
  await switchTo(fixture.source); await page.goto(fixture.origin + '/licenses');
  await page.getByText('Standard subscription', { exact: true }).waitFor();
  assert.equal(await page.getByRole('button', { name: 'Edit or renew subscription', exact: true }).count(), 0);
  assert.ok(!(await page.locator('main').innerText()).includes('Browser private note'));
  await page.reload(); await page.getByText('Standard subscription', { exact: true }).waitFor();
  await page.goto(fixture.origin + '/licenses/' + fixture.target);
  await page.waitForURL('**/licenses'); await page.getByRole('heading', { name: 'Source subscription tenant', exact: true }).waitFor(); passed();
  step = 'status filter and responsive display';
  await switchTo('platform'); await page.goto(fixture.origin + '/licenses');
  await page.getByLabel('Subscription status', { exact: true }).selectOption('cancelled');
  await page.getByRole('link', { name: 'Source subscription tenant', exact: true }).waitFor();
  await page.getByRole('link', { name: 'Destination subscription tenant', exact: true }).waitFor({ state: 'hidden' });
  await mkdir('../../../../.test_artifacts/subscriptions-web', { recursive: true });
  await page.screenshot({ path: '../../../../.test_artifacts/subscriptions-web/desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'Mobile document overflow');
  await page.screenshot({ path: '../../../../.test_artifacts/subscriptions-web/mobile.png', fullPage: true });
  assert.deepEqual(errors, []); passed();
} catch (error) { console.error('FAIL ' + step + ': ' + error.message); process.exitCode = 1; }
finally { await browser.close(); }
