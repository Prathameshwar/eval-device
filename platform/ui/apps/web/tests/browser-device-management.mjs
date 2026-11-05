import { chromium } from 'playwright-core';
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
let input = '';
for await (const chunk of process.stdin) input += chunk;
const fixture = JSON.parse(input);
const browser = await chromium.launch({ executablePath: process.env.PMS_TEST_BROWSER ?? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage(); page.setDefaultTimeout(30000);
const errors = []; page.on('pageerror', error => errors.push(error.message));
let token; let step = 'login and platform tenant registration';
function passed() { console.log('PASS ' + step); }
async function api(path, method = 'GET', body, bearer = token, expected = 200) {
  const response = await fetch(fixture.api + path, { method, headers: { Authorization: 'Bearer ' + bearer, 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
  assert.equal(response.status, expected, 'API ' + method + ' ' + path);
  return response.json();
}
async function switchTo(id) {
  if (await page.getByLabel('Switch organisation').inputValue() !== id) {
    await page.getByLabel('Switch organisation').selectOption(id); await page.waitForURL('**/home');
  }
}
async function confirm(title, button) {
  const dialog = page.getByRole('dialog', { name: title, exact: true });
  await dialog.getByRole('button', { name: button, exact: true }).click(); await dialog.waitFor({ state: 'hidden' });
}
try {
  await page.goto(fixture.origin + '/devices'); await page.waitForURL('**/login');
  await page.getByLabel('Email address', { exact: true }).fill(fixture.email); await page.getByLabel('Password', { exact: true }).fill(fixture.password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click(); await page.waitForURL('**/home');
  token = (await context.cookies()).find(cookie => cookie.name.endsWith('ae-session')).value;
  await switchTo('platform'); await page.goto(fixture.origin + '/devices');
  await page.getByRole('button', { name: 'Create new device', exact: true }).click();
  await page.getByLabel('Device name', { exact: true }).fill('Browser fleet device');
  await page.getByLabel('Device unique ID', { exact: true }).fill('BROWSER-FLEET-001');
  await page.getByLabel('Tenant association', { exact: true }).selectOption(fixture.source);
  await page.getByRole('button', { name: 'Register device', exact: true }).click();
  await page.getByRole('dialog', { name: 'Register device with tenant', exact: true }).waitFor({ state: 'hidden' });
  await page.getByRole('link', { name: 'View Browser fleet device', exact: true }).waitFor();
  let row = (await api('/platform/devices?q=Browser%20fleet')).items[0];
  assert.equal(row.organization_id, fixture.source); assert.equal(row.summary_only, true);
  await page.getByRole('link', { name: 'View Browser fleet device', exact: true }).click(); await page.waitForURL('**/devices/' + row.id); passed();
  step = 'platform public metadata edit and lifecycle controls';
  await page.getByRole('button', { name: 'Edit device', exact: true }).click();
  await page.getByLabel('Device name', { exact: true }).fill('Browser renamed');
  assert.equal(await page.getByLabel('Contact name', { exact: true }).count(), 0);
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  await page.getByRole('heading', { name: 'Browser renamed', exact: true }).waitFor();
  await page.getByRole('button', { name: 'Deactivate device', exact: true }).click();
  await confirm('Deactivate Browser renamed?', 'Deactivate device');
  await page.getByRole('button', { name: 'Activate device', exact: true }).waitFor();
  assert.equal((await api('/platform/devices/' + row.id)).is_active, false);
  await page.getByRole('button', { name: 'Activate device', exact: true }).click(); await confirm('Activate Browser renamed?', 'Activate device');
  assert.equal(await page.getByRole('button', { name: 'Issue enrollment token' }).count(), 0); passed();
  step = 'tenant editing and real one-time device enrollment';
  await switchTo(fixture.source); await page.goto(fixture.origin + '/devices/' + row.id);
  await page.getByRole('button', { name: 'Edit device', exact: true }).click();
  await page.getByLabel('Location', { exact: true }).fill('Private source location');
  await page.getByRole('button', { name: 'Save changes', exact: true }).click(); await page.getByRole('dialog', { name: 'Edit device', exact: true }).waitFor({ state: 'hidden' });
  assert.equal(await page.getByRole('button', { name: 'Transfer to another tenant' }).count(), 0);
  await page.getByRole('button', { name: 'Issue enrollment token' }).click(); await confirm('Issue an enrollment token?', 'Issue token');
  const enrollment = await page.getByLabel('Enrollment token', { exact: true }).inputValue();
  const enrolled = await api('/device/enroll', 'POST', { token: enrollment }, '');
  const oldCredential = enrolled.credential;
  await page.getByRole('button', { name: 'Hide token', exact: true }).click();
  await page.getByRole('button', { name: 'Refresh device status', exact: true }).click(); passed();
  step = 'central transfer creates fresh registration and revokes old credentials';
  await switchTo('platform'); await page.goto(fixture.origin + '/devices/' + row.id);
  assert.ok(!(await page.locator('main').innerText()).includes('Private source location'));
  await page.getByRole('button', { name: 'Transfer to another tenant' }).click();
  await page.getByLabel('Destination tenant', { exact: true }).selectOption(fixture.target);
  await page.getByLabel('Registration name', { exact: true }).fill('Transferred device');
  await page.getByRole('button', { name: 'Review transfer', exact: true }).click();
  await confirm('Confirm tenant transfer', 'Transfer registration');
  await page.getByText('Tenant association changed', { exact: true }).waitFor();
  row = (await api('/platform/devices?organization_id=' + fixture.target + '&enrollment_state=current')).items[0];
  assert.equal(row.name, 'Transferred device'); assert.equal(row.is_active, false);
  assert.equal(row.enrollment_state, 'pending'); assert.equal(row.last_seen_at, null);
  await api('/device/config', 'GET', undefined, oldCredential, 401); passed();
  step = 'destination activation, enrollment and retained source privacy';
  await switchTo(fixture.target); await page.goto(fixture.origin + '/devices/' + row.id);
  await page.getByText('No location configured.', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Activate device', exact: true }).click(); await confirm('Activate Transferred device?', 'Activate device');
  await page.getByRole('button', { name: 'Issue enrollment token' }).click(); await confirm('Issue an enrollment token?', 'Issue token');
  const freshEnrollment = await page.getByLabel('Enrollment token', { exact: true }).inputValue();
  const freshCredential = (await api('/device/enroll', 'POST', { token: freshEnrollment }, '')).credential;
  await page.getByRole('button', { name: 'Hide token', exact: true }).click();
  await page.getByRole('button', { name: 'Refresh device status', exact: true }).click();
  await page.reload(); await page.getByRole('heading', { name: 'Transferred device', exact: true }).waitFor(); passed();
  step = 'remove registration, preserve history and reject device authentication';
  await page.getByRole('button', { name: 'Device actions', exact: true }).click();
  await page.getByRole('menuitem', { name: 'Retire', exact: true }).click(); await confirm('Retire Transferred device?', 'Retire device');
  await page.getByText('Retired device', { exact: true }).waitFor(); await api('/device/config', 'GET', undefined, freshCredential, 401);
  await page.goto(fixture.origin + '/devices'); await page.getByText('No devices yet', { exact: true }).waitFor();
  await page.getByLabel('Enrollment', { exact: true }).selectOption('retired');
  await page.getByRole('link', { name: 'View Transferred device', exact: true }).waitFor(); passed();
  step = 'responsive directory and browser runtime';
  await mkdir('../../../../.test_artifacts/device-management-web', { recursive: true });
  await page.screenshot({ path: '../../../../.test_artifacts/device-management-web/desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'Mobile overflow');
  await page.screenshot({ path: '../../../../.test_artifacts/device-management-web/mobile.png', fullPage: true });
  assert.deepEqual(errors, []); passed();
} catch (error) { console.error('FAIL ' + step + ': ' + error.message); process.exitCode = 1; }
finally { await browser.close(); }
