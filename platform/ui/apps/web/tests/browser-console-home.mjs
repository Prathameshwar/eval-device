import { chromium } from 'playwright-core';
import { readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
const fixture = JSON.parse(await readFile(new URL('../../../../../.test_artifacts/login-implementation-20260923/browser-fixture.json', import.meta.url), 'utf8'));
const origin = 'http://localhost:3123';
const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
const context = await browser.newContext();
const page = await context.newPage();
page.setDefaultTimeout(30000);
let step = 'setup';
const checks = [];
async function api(path, method = 'GET', body, token) {
  const response = await fetch(fixture.api + '/api/v1' + path, { method, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) }, body: body === undefined ? undefined : JSON.stringify(body) });
  assert.ok(response.ok, 'API request failed: ' + path + ' (' + response.status + ')');
  return response.json();
}
try {
  const control = await fetch(fixture.api + '/__test/action/setup', { headers: { 'x-test-key': fixture.controlKey } });
  const setup = (await control.json()).token;
  const password = 'Browser console password September 2026!';
  await api('/auth/password/setup', 'POST', { token: setup, password });
  await page.goto(origin + '/login');
  await page.getByLabel('Email address', { exact: true }).fill('browser-login@example.com');
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.waitForURL('**/home');
  await page.getByRole('heading', { name: 'Good to see you, Browser reviewer' }).waitFor();
  const token = (await context.cookies()).find(c => c.name.endsWith('ae-session')).value;
  step = 'platform home matches API and contains no preview values';
  const stats = await api('/platform/dashboard-stats', 'GET', undefined, token);
  assert.equal(await page.locator('.pms-stat').filter({ hasText: 'Total devices' }).locator('.pms-stat__value').innerText(), String(stats.total_devices));
  assert.equal(await page.getByText('Preview data', { exact: true }).count(), 0);
  checks.push(step);
  step = 'tenant context home uses real subscription and empty sessions';
  const plans = await api('/subscription-plans', 'GET', undefined, token);
  const org = await api('/organizations', 'POST', { name: 'Browser Home Tenant', subscription_plan_id: plans.items[0].id }, token);
  await page.reload();
  await page.getByLabel('Switch organisation').selectOption(org.id);
  await page.getByText('Subscription plan', { exact: true }).waitFor();
  await page.getByText('No sessions in this scope yet.', { exact: true }).waitFor();
  assert.equal(await page.getByText('Total tenants', { exact: true }).count(), 0);
  checks.push(step);
  await page.getByLabel('Switch organisation').selectOption('platform');
  await page.getByText('Total tenants', { exact: true }).waitFor();
  await writeFile(new URL('../../../../../.test_artifacts/console-binding-20260923/browser-home.json', import.meta.url), JSON.stringify({ checks, passed: true }, null, 2));
  checks.forEach(check => console.log('PASS ' + check));
} catch (error) {
  console.error('FAIL ' + step + ': ' + error.message.split('\n')[0]);
  process.exitCode = 1;
} finally { await browser.close(); }
