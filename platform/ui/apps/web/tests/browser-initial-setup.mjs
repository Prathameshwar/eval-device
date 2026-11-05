// Start tests/setup_browser_fixture.py and Next with PMS_API_BASE_URL=http://127.0.0.1:8134/api/v1.
import { chromium } from 'playwright-core';
import { readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const artifacts = new URL('../../../../../.test_artifacts/initial-setup-20260926/', import.meta.url);
const fixture = JSON.parse(await readFile(new URL('browser-fixture.json', artifacts), 'utf8'));
const origin = process.env.PMS_TEST_WEB_ORIGIN || 'http://localhost:3124';
const browser = await chromium.launch({
  executablePath: process.env.PMS_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true,
});
const context = await browser.newContext({ viewport: { width: 1365, height: 900 } });
const page = await context.newPage();
page.setDefaultTimeout(30000);
const checks = [];
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const email = 'setup.browser@example.com';
const password = randomBytes(24).toString('base64url');
async function snapshot(name) { await page.screenshot({ path: fileURLToPath(new URL(name + '.png', artifacts)), fullPage: true }); }
async function control(path) {
  const result = await fetch(fixture.api + '/__test/' + path, { headers: { 'x-test-key': fixture.controlKey } });
  assert.equal(result.status, 200);
  return result.json();
}
try {
  await page.goto(origin);
  await page.waitForURL('**/setup');
  await page.getByRole('heading', { name: 'Set up your platform' }).waitFor();
  assert.equal((await page.content()).includes(fixture.installationKey), false);
  await snapshot('01-installation');
  checks.push('Fresh root/login routes redirect to initial setup without exposing the installation key.');
  await page.getByLabel('Installation key').fill('incorrect-installation-key');
  await page.getByRole('button', { name: 'Verify installation' }).click();
  await page.getByText(/The installation key is incorrect/).waitFor();
  assert.deepEqual(await control('summary'), { users: 0, hashed_credentials: 0, setup_audits: 0 });
  await page.getByLabel('Installation key').fill(fixture.installationKey);
  await page.getByRole('button', { name: 'Verify installation' }).click();
  await page.getByLabel('Full name').fill('Setup Browser Administrator');
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByLabel('Confirm password', { exact: true }).fill('mismatched');
  await page.getByRole('button', { name: 'Review details' }).click();
  await page.getByText('The passwords must match.').waitFor();
  await page.getByLabel('Confirm password', { exact: true }).fill(password);
  await snapshot('02-administrator');
  await page.getByRole('button', { name: 'Review details' }).click();
  await page.getByRole('heading', { name: 'Review and finish' }).waitFor();
  await snapshot('03-review');
  await page.setViewportSize({ width: 390, height: 844 });
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Mobile overflow');
  await snapshot('04-review-mobile');
  await page.setViewportSize({ width: 1365, height: 900 });
  checks.push('Key verification, field validation, password confirmation, review and mobile layout work.');
  const stalePage = await context.newPage();
  await stalePage.goto(origin + '/setup');
  await page.getByRole('button', { name: 'Create administrator' }).click();
  await page.getByRole('heading', { name: 'Your platform is ready' }).waitFor();
  await snapshot('05-complete');
  assert.deepEqual(await control('summary'), { users: 1, hashed_credentials: 1, setup_audits: 1 });
  assert.equal((await page.content()).includes(password), false);
  await stalePage.getByLabel('Installation key').fill(fixture.installationKey);
  await stalePage.getByRole('button', { name: 'Verify installation' }).click();
  await stalePage.getByRole('heading', { name: 'Setup is already complete' }).waitFor();
  await stalePage.close();
  await page.getByRole('link', { name: 'Continue to sign in' }).click();
  await page.waitForURL('**/login');
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.waitForURL('**/home');
  await snapshot('06-signed-in');
  const cookies = await context.cookies();
  assert(cookies.some(cookie => cookie.name === 'ae-session' && cookie.httpOnly && cookie.sameSite === 'Lax'));
  const fresh = await browser.newContext();
  const revisit = await fresh.newPage();
  await revisit.goto(origin + '/setup');
  await revisit.waitForURL('**/login');
  await fresh.close();
  checks.push('One hashed administrator and audit record created; stale tabs close setup; real sign-in grants platform access; setup stays closed.');
  assert.equal(errors.length, 0, 'Browser console exceptions');
  await writeFile(new URL('browser-results.json', artifacts), JSON.stringify({ passed: true, checks, browserErrors: errors }, null, 2));
  console.log(JSON.stringify({ passed: true, checks }));
} finally {
  await browser.close();
  await fetch(fixture.api + '/__test/shutdown', { method: 'POST', headers: { 'x-test-key': fixture.controlKey } });
}
