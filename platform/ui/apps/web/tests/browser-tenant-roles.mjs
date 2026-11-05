import { chromium } from 'playwright-core';
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';

let input = '';
for await (const chunk of process.stdin) input += chunk;
const fixture = JSON.parse(input);
const output = '../../../../.test_artifacts/tenant-role-review-20261004';
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ executablePath: process.env.PMS_TEST_BROWSER ?? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
const checks = [];
const errors = [];
try {
  for (const account of fixture.accounts) {
    const context = await browser.newContext({ viewport: { width: 1366, height: 900 } });
    const page = await context.newPage();
    page.setDefaultTimeout(45000);
    page.on('pageerror', error => errors.push(error.name));
    await page.goto(fixture.origin + '/login');
    await page.getByLabel('Email address', { exact: true }).fill(account.email);
    await page.getByLabel('Password', { exact: true }).fill(account.password);
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await page.waitForURL('**/home');
    // This account also has platform access; explicitly select its tenant context.
    await context.addCookies([{ name: 'ae-context', value: fixture.tenant.id, url: fixture.origin, httpOnly: true, sameSite: 'Lax' }]);
    await page.reload();
    const rail = page.locator('.pms-rail');
    await rail.getByRole('link', { name: 'Devices', exact: true }).waitFor();
    await rail.getByRole('link', { name: 'Settings', exact: true }).waitFor();
    assert.equal(await rail.getByRole('link', { name: 'Members', exact: true }).count(), account.role === 'org_admin' ? 1 : 0);
    assert.equal(await rail.getByRole('link', { name: 'Tenants', exact: true }).count(), 0);
    await page.goto(fixture.origin + '/devices/' + fixture.device.id);
    await page.getByRole('heading', { name: fixture.device.name, exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'Edit device', exact: true }).count(), account.role === 'org_admin' ? 1 : 0);
    await page.goto(fixture.origin + '/sessions');
    await page.getByRole('heading', { name: 'Sessions', exact: true }).waitFor();
    assert.equal(await page.getByRole('link', { name: 'Start session', exact: true }).count(), account.role === 'org_admin' ? 1 : 0);
    await page.goto(fixture.origin + '/sessions/new');
    if (account.role === 'org_admin') {
      await page.getByRole('heading', { name: 'Start a session', exact: true }).waitFor();
      await page.getByLabel('Device', { exact: true }).selectOption(fixture.device.id);
      assert.ok((await page.getByLabel('Published scenario').locator('option').count()) > 1);
    } else {
      await page.waitForURL('**/sessions');
    }
    await page.goto(fixture.origin + '/settings');
    await page.getByRole('heading', { level: 1 }).waitFor();
    assert.ok(page.url().endsWith('/settings'));
    await page.screenshot({ path: `${output}/${account.role}.png`, fullPage: true });
    if (account.role !== 'org_admin') {
      for (const route of ['/members', '/tenants', '/models']) {
        await page.goto(fixture.origin + route);
        await page.waitForURL('**/home');
      }
    }
    checks.push({ role: account.role, login: true, navigation: true, routeGuards: true });
    await context.close();
  }
  assert.deepEqual(errors, []);
  await writeFile(`${output}/browser-verification.json`, JSON.stringify({ checks, errors }, null, 2));
  console.log('PASS: four tenant roles, real login, scoped device, sessions, settings and route guards');
} finally {
  await browser.close();
}
