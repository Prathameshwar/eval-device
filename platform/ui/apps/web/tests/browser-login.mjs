// Real browser -> Next server actions -> isolated FastAPI -> PostgreSQL.
// Start tests/browser_fixture.py and Next with PMS_API_BASE_URL=http://127.0.0.1:8133/api/v1.
// Uses an installed Chromium browser; set PMS_TEST_BROWSER if Edge is elsewhere.
import { chromium } from 'playwright-core';
import { readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

const artifacts = new URL('../../../../../.test_artifacts/login-implementation-20260923/', import.meta.url);
const fixture = JSON.parse(await readFile(new URL('browser-fixture.json', artifacts), 'utf8'));
const origin = process.env.PMS_TEST_WEB_ORIGIN || 'http://localhost:3123';
const checks = [];
let step = 'launch';
const browser = await chromium.launch({
  executablePath: process.env.PMS_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  headless: true,
});
const context = await browser.newContext();
const page = await context.newPage();
page.setDefaultTimeout(20000);
let email = 'browser-login@example.com';
let password = 'Browser test original password 2026!';
let signInAction;
page.on('request', request => {
  const action = request.headers()['next-action'];
  if (action && new URL(request.url()).pathname === '/login') signInAction = action;
});
async function control(path, method = 'GET') {
  const result = await fetch(fixture.api + '/__test/' + path, { method, headers: { 'x-test-key': fixture.controlKey } });
  assert.equal(result.status, 200, 'Test fixture control failed');
  return result.json();
}
async function visible(locator) { await locator.waitFor({ state: 'visible' }); }
async function openAction(purpose, token, nextPassword) {
  await page.goto(origin + '/account/' + purpose + '#token=' + encodeURIComponent(token));
  if (nextPassword) {
    await page.getByLabel('New password', { exact: true }).fill(nextPassword);
    await page.getByLabel('Confirm new password', { exact: true }).fill(nextPassword);
  }
  await page.getByRole('button', { name: nextPassword ? 'Save password' : 'Confirm email change', exact: true }).click();
}
async function login(remember = false) {
  await page.goto(origin + '/login');
  await page.getByLabel('Email address', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  if (await page.getByLabel('Keep me signed in').isChecked() !== remember) await page.getByText('Keep me signed in', { exact: true }).click();
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.waitForURL('**/home');
  await visible(page.getByRole('heading', { name: /Good to see you/ }));
}
async function cookie() {
  return (await context.cookies()).find(value => value.name.endsWith('ae-session'));
}
async function apiStatus(token) {
  return (await fetch(fixture.api + '/api/v1/auth/context', { headers: { Authorization: 'Bearer ' + token } })).status;
}
async function menu(label) {
  await page.getByRole('button', { name: /Browser reviewer/ }).click();
  await page.getByRole('menuitem', { name: label, exact: true }).click();
}
function passed(name) { checks.push(name); console.log('PASS ' + name); }
try {
  step = 'forged demo cookie rejected';
  await context.addCookies([{ name: 'ae-demo-session', value: 'platform-admin', url: origin }]);
  await page.goto(origin + '/tenants');
  await page.waitForURL('**/login');
  passed(step);

  step = 'setup fragment consumed and removed';
  const setup = (await control('action/setup')).token;
  await openAction('setup', setup, password);
  await visible(page.getByText('Account updated', { exact: true }));
  assert.equal(new URL(page.url()).hash, '');
  passed(step);

  step = 'invalid password gives recoverable error';
  await page.goto(origin + '/login');
  await page.getByLabel('Email address', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill('incorrect password');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await visible(page.getByText('Sign-in failed', { exact: true }));
  await page.getByRole('button', { name: 'Sign in', exact: true }).waitFor({ state: 'visible' });
  assert.equal(await page.getByRole('button', { name: 'Sign in', exact: true }).isEnabled(), true);
  passed(step);

  step = 'real login and bounded HttpOnly browser session';
  await login();
  const first = await cookie();
  assert.ok(first?.value.startsWith('web_'));
  assert.equal(first.httpOnly, true);
  assert.equal(first.sameSite, 'Lax');
  assert.equal(first.expires, -1);
  assert.equal(await apiStatus(first.value), 200);
  if (process.env.PMS_TEST_PRODUCTION === '1') assert.equal(first.secure, true);
  passed(step);

  step = 'parallel tabs share valid session';
  const second = await context.newPage();
  await Promise.all([page.reload(), second.goto(origin + '/home')]);
  assert.equal((await cookie()).value, first.value);
  assert.equal(await apiStatus(first.value), 200);
  await second.close();
  passed(step);

  step = 'cross-origin server action rejected';
  assert.ok(signInAction);
  const crossSite = await fetch(origin + '/login', {
    method: 'POST', redirect: 'manual',
    headers: { Origin: 'https://attacker.invalid', 'Next-Action': signInAction, 'Content-Type': 'text/plain;charset=UTF-8' },
    body: JSON.stringify([email, password, false]),
  });
  assert.ok(crossSite.status >= 400, 'Cross-site action must be rejected');
  assert.equal(crossSite.headers.get('set-cookie'), null);
  passed(step);

  step = 'logout revokes copied browser credential';
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await page.waitForURL('**/login');
  assert.equal(await apiStatus(first.value), 401);
  assert.equal(await cookie(), undefined);
  passed(step);

  step = 'remembered login persists with bounded expiry';
  await login(true);
  const remembered = await cookie();
  assert.ok(remembered.expires > Date.now() / 1000 + 23 * 3600);
  assert.ok(remembered.expires < Date.now() / 1000 + 25 * 3600);
  passed(step);

  step = 'password change revokes existing session';
  await menu('Change password');
  await page.getByLabel('Current password', { exact: true }).fill(password);
  const changed = 'Browser changed password 2026!';
  await page.getByLabel('New password', { exact: true }).fill(changed);
  await page.getByLabel('Confirm new password', { exact: true }).fill(changed);
  await page.getByRole('button', { name: 'Update password', exact: true }).click();
  await page.waitForURL('**/login').catch(async () => {
    await visible(page.getByText('Password changed', { exact: true }));
    await page.goto(origin + '/login');
  });
  assert.equal(await apiStatus(remembered.value), 401);
  password = changed;
  await login();
  passed(step);

  step = 'password recovery and one-time reset';
  const beforeReset = (await cookie()).value;
  await page.goto(origin + '/forgot-password');
  await page.getByLabel('Email address', { exact: true }).fill(email);
  await page.getByRole('button', { name: 'Send reset link', exact: true }).click();
  await visible(page.getByText('Request received', { exact: true }));
  const reset = (await control('action/password_reset')).token;
  password = 'Browser recovered password 2026!';
  await openAction('password-reset', reset, password);
  await visible(page.getByText('Account updated', { exact: true }));
  assert.equal(await apiStatus(beforeReset), 401);
  await openAction('password-reset', reset, password);
  await visible(page.getByText('Unable to update account', { exact: true }));
  await login();
  passed(step);

  step = 'email change confirmation changes login and revokes session';
  const beforeEmail = (await cookie()).value;
  await menu('Change email address');
  await page.getByLabel('New email address', { exact: true }).fill('browser-changed@example.com');
  await page.getByLabel('Current password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Send confirmation', exact: true }).click();
  await visible(page.getByText('Confirmation requested', { exact: true }));
  const confirmation = (await control('action/email_change')).token;
  await openAction('email-change', confirmation);
  await visible(page.getByText('Account updated', { exact: true }));
  assert.equal(await apiStatus(beforeEmail), 401);
  email = 'browser-changed@example.com';
  await login();
  passed(step);

  step = 'expired session returns to login';
  await control('expire', 'POST');
  await page.goto(origin + '/home');
  await page.waitForURL('**/login');
  passed(step);
  await writeFile(new URL('browser-result.json', artifacts), JSON.stringify({ passed: checks, count: checks.length }, null, 2));
} catch (error) {
  // Do not print request data, URLs with action tokens, cookies, or page contents.
  console.error('FAIL ' + step + ' (' + error.name + ')'); console.error(error.stack?.match(/browser-login[.]mjs:[0-9]+:[0-9]+/g));
  await writeFile(new URL('browser-result.json', artifacts), JSON.stringify({ passed: checks, failed: step, error: error.name }, null, 2));
  process.exitCode = 1;
} finally {
  await browser.close();
}
