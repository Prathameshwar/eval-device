import { chromium } from 'playwright-core';
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
let input = '';
for await (const chunk of process.stdin) input += chunk;
const fixture = JSON.parse(input);
const browser = await chromium.launch({ executablePath: process.env.PMS_TEST_BROWSER ?? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage(); page.setDefaultTimeout(45000);
const errors = []; const checks = []; let step = 'login'; let token;
page.on('pageerror', error => errors.push(error.name));
const output = '../../../../.test_artifacts/tenant-associations-20260928';
const popup = () => page.getByRole('dialog', { name: 'Tenant administration', exact: true });
const tableRow = name => page.getByRole('row').filter({ has: page.getByText(name, { exact: true }) });
function passed() { checks.push(step); console.log('PASS ' + step); }
async function api(path) {
  const response = await fetch(fixture.api + path, { headers: { Authorization: 'Bearer ' + token } });
  assert.ok(response.ok, 'Read-only fixture API check failed: ' + response.status);
  return response.json();
}
async function confirm(title, button) {
  const role = ['Register device?', 'Transfer device into this tenant?'].includes(title) ? 'region' : 'dialog';
  const dialog = page.getByRole(role, { name: title, exact: true });
  await dialog.getByRole('button', { name: button, exact: true }).click();
  await dialog.waitFor({ state: 'hidden' });
}
async function ready(caption) {
  const table = popup().getByRole('table', { name: caption, exact: true });
  await table.waitFor();
  await page.waitForFunction(name => [...document.querySelectorAll('table')].some(table => table.getAttribute('aria-label') === name && table.getAttribute('aria-busy') !== 'true' || table.querySelector('caption')?.textContent === name && table.getAttribute('aria-busy') !== 'true'), caption);
}
try {
  await mkdir(output, { recursive: true });
  await page.goto(fixture.origin + '/login');
  await page.getByLabel('Email address', { exact: true }).fill(fixture.email);
  await page.getByLabel('Password', { exact: true }).fill(fixture.password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click(); await page.waitForURL('**/home');
  token = (await context.cookies()).find(cookie => cookie.name.endsWith('ae-session')).value;
  await page.getByLabel('Switch organisation').selectOption('platform');
  await page.goto(fixture.origin + '/tenants');
  step = 'Administrator follows View and opens only the selected tenant';
  const trigger = page.getByRole('button', { name: 'Administrator for ' + fixture.tenant.name, exact: true });
  await trigger.waitFor();
  assert.equal(await trigger.evaluate(button => button.previousElementSibling?.getAttribute('aria-label')), 'View ' + fixture.tenant.name);
  await trigger.click(); await popup().getByRole('heading', { name: 'Current administrators' }).waitFor();
  assert.equal(await popup().getByRole('tab').count(), 3);
  assert.equal(await popup().getByRole('tab', { name: 'Users', exact: true }).count(), 0);
  assert.equal(await popup().getByRole('tab', { name: 'Administrators' }).getAttribute('aria-selected'), 'true'); passed();

  step = 'assign an existing account only as tenant administrator';
  await popup().getByLabel('Account name or email').fill(fixture.candidate.email);
  await popup().getByRole('button', { name: 'Search accounts', exact: true }).click();
  await popup().getByLabel('Account to assign').selectOption(fixture.candidate.id);
  await popup().getByRole('button', { name: 'Assign administrator', exact: true }).click();
  await confirm('Assign tenant administrator?', 'Assign administrator');
  await popup().getByText(fixture.candidate.email, { exact: true }).waitFor();
  const membership = (await api(`/platform/organizations/${fixture.tenant.id}/members?q=${encodeURIComponent(fixture.candidate.email)}`)).items[0];
  assert.equal(membership.role, 'org_admin'); passed();

  step = 'device registration, deactivation and reactivation use the selected tenant';
  await popup().getByRole('tab', { name: 'Devices', exact: true }).click();
  await tableRow(fixture.device.name).getByRole('button', { name: 'Deactivate', exact: true }).click();
  await confirm('Deactivate device?', 'Deactivate device');
  await tableRow(fixture.device.name).getByRole('button', { name: 'Activate', exact: true }).click();
  await confirm('Activate device?', 'Activate device');
  await popup().getByRole('button', { name: 'Register device', exact: true }).click();
  await popup().getByLabel('Device name', { exact: true }).fill('Popup registered device');
  await popup().getByLabel('Device unique ID', { exact: true }).fill('BROWSER-POPUP-001');
  await popup().getByLabel('Device type', { exact: true }).selectOption('laptop');
  await popup().getByRole('button', { name: 'Review registration' }).click();
  await confirm('Register device?', 'Register device');
  await tableRow('Popup registered device').waitFor();
  const registered = (await api(`/platform/devices?organization_id=${fixture.tenant.id}&q=Popup%20registered`)).items[0];
  assert.equal(registered.device_unique_id, 'BROWSER-POPUP-001'); assert.equal(registered.is_active, false); assert.equal(registered.enrollment_state, 'pending'); passed();

  step = 'device transfer retires the source and creates a fresh inactive registration';
  await popup().getByRole('button', { name: 'Transfer device' }).click();
  await popup().getByLabel('Device to find').fill(fixture.sourceDevice.name);
  await popup().getByRole('button', { name: 'Search devices', exact: true }).click();
  await tableRow(fixture.sourceDevice.name).getByRole('button', { name: 'Review transfer' }).click();
  const transfer = page.getByRole('region', { name: 'Transfer device into this tenant?', exact: true });
  await transfer.getByText(/fresh enrollment/).waitFor();
  await transfer.getByRole('button', { name: 'Back to search', exact: true }).click();
  assert.equal((await api('/platform/devices/' + fixture.sourceDevice.id)).enrollment_state, 'enrolled');
  await tableRow(fixture.sourceDevice.name).getByRole('button', { name: 'Review transfer' }).click();
  await confirm('Transfer device into this tenant?', 'Transfer device');
  await popup().getByText(/Transferred into this tenant/).waitFor();
  const moved = (await api(`/platform/devices?organization_id=${fixture.tenant.id}&q=${encodeURIComponent(fixture.sourceDevice.name)}`)).items[0];
  assert.notEqual(moved.id, fixture.sourceDevice.id); assert.equal(moved.is_active, false);
  assert.equal((await api('/platform/devices/' + fixture.sourceDevice.id)).enrollment_state, 'retired'); passed();

  step = 'device rename and confirmed removal preserve its history registration';
  await tableRow('Popup registered device').getByRole('button', { name: 'Rename' }).click();
  await page.getByLabel('New device name').fill('Popup renamed device');
  await confirm('Save name?', 'Save name');
  await tableRow('Popup renamed device').getByRole('button', { name: 'Remove', exact: true }).click();
  await confirm('Remove device?', 'Remove device');
  assert.equal((await api('/platform/devices/' + registered.id)).enrollment_state, 'retired'); passed();
  await page.screenshot({ path: output + '/devices-desktop.png', fullPage: true });

  step = 'mobile popup fits, closes cleanly and restores focus';
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: output + '/devices-mobile.png', fullPage: true });
  assert.ok(await popup().evaluate(panel => { const box = panel.getBoundingClientRect(); return box.left >= 0 && box.right <= window.innerWidth + 1; }));
  await popup().getByRole('tab', { name: 'Administrators', exact: true }).click();
  await popup().getByRole('heading', { name: 'Current administrators' }).waitFor();
  await page.screenshot({ path: output + '/administrators-mobile.png', fullPage: true });
  await popup().getByRole('button', { name: 'Done', exact: true }).click();
  await popup().waitFor({ state: 'hidden' });
  assert.ok(await trigger.evaluate(button => document.activeElement === button));
  assert.deepEqual(errors, []); passed();
  await writeFile(output + '/result.json', JSON.stringify({ checks, errors }, null, 2));
} catch (error) {
  console.error('FAIL at ' + step + ': ' + error.name);
  await page.screenshot({ path: output + '/failure.png', fullPage: true });
  process.exitCode = 1;
} finally { await browser.close(); }
