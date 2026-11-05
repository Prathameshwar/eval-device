import { chromium } from 'playwright-core';
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
let input = '';
for await (const chunk of process.stdin) input += chunk;
const fixture = JSON.parse(input);
const browser = await chromium.launch({ executablePath: process.env.PMS_TEST_BROWSER ?? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
page.setDefaultTimeout(45000);
const errors = [];
page.on('pageerror', error => errors.push(error.message));
let step = 'anonymous access and login';
let token;
const base = `/organizations/${fixture.org}/llm`;
async function api(path, method = 'GET', body) {
  const response = await fetch(fixture.api + path, { method, headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
  assert.ok(response.ok, `API ${method} failed (${response.status})`);
  return response.json();
}
const dialog = () => page.getByRole('dialog');
const row = name => page.getByRole('row').filter({ has: page.getByRole('button', { name, exact: true }) });
async function confirm(name) { await dialog().getByRole('button', { name, exact: true }).click(); await dialog().waitFor({ state: 'hidden' }); }
async function edit(name) { await row(name).getByRole('button', { name: 'Edit', exact: true }).click(); await dialog().getByRole('heading', { name: 'Edit LLM connection' }).waitFor(); }
async function save() { await dialog().getByRole('button', { name: 'Save changes', exact: true }).click(); await dialog().waitFor({ state: 'hidden' }); }
function passed() { console.log('PASS ' + step); }
try {
  await page.goto(fixture.origin + '/llm-connections');
  await page.waitForURL('**/login');
  await page.getByLabel('Email address', { exact: true }).fill(fixture.email);
  await page.getByLabel('Password', { exact: true }).fill(fixture.password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.waitForURL('**/home');
  token = (await context.cookies()).find(cookie => cookie.name.endsWith('ae-session')).value;
  await page.goto(fixture.origin + '/settings');
  await page.getByRole('link', { name: 'LLM connections', exact: true }).click();
  await page.getByRole('heading', { name: 'LLM connections', exact: true }).waitFor();
  passed();
  step = 'create local connection and persist it across reload';
  await page.getByRole('button', { name: 'Create connection', exact: true }).click();
  await page.getByLabel('Connection name', { exact: true }).fill('Browser local');
  await page.getByLabel('API key', { exact: true }).fill('browser-test-key');
  await dialog().getByRole('button', { name: 'Create connection', exact: true }).click();
  await dialog().waitFor({ state: 'hidden' });
  await row('Browser local').waitFor();
  await page.reload();
  await row('Browser local').waitFor();
  let record = (await api(base + '/configurations')).items[0];
  assert.equal(record.model, 'qwen3.5-4b-local');
  assert.equal(record.max_tokens, 256);
  assert.ok(!JSON.stringify(record).includes('browser-test-key'));
  const path = base + '/connections/' + record.id;
  passed();
  step = 'read details and truthful local connection check';
  await row('Browser local').getByRole('button', { name: 'Browser local', exact: true }).click();
  await dialog().getByText('Stored securely', { exact: true }).waitFor();
  await dialog().getByRole('button', { name: 'Check connection', exact: true }).click();
  await dialog().getByText(/Run inference on the device/).waitFor();
  await dialog().getByRole('button', { name: 'Close', exact: true }).last().click();
  passed();
  step = 'edit response settings and rotate credentials';
  await edit('Browser local');
  assert.equal(await page.getByLabel('Replace API key').inputValue(), '');
  await page.getByLabel('Maximum output tokens').fill('320');
  await page.getByLabel('System prompt').fill('Use clear, brief English answers.');
  await page.getByLabel('Replace API key').fill('browser-rotated-key');
  await save();
  record = await api(path);
  assert.equal(record.max_tokens, 320);
  assert.equal(record.system_prompt, 'Use clear, brief English answers.');
  await edit('Browser local');
  assert.equal(await page.getByLabel('Replace API key').inputValue(), '');
  await dialog().getByRole('button', { name: 'Cancel', exact: true }).click();
  passed();
  step = 'disable, archive, filter, restore disabled, and enable';
  await row('Browser local').getByRole('button', { name: 'Disable', exact: true }).click(); await confirm('Disable');
  assert.equal((await api(path)).is_active, false);
  await row('Browser local').getByRole('button', { name: 'Archive', exact: true }).click(); await confirm('Archive');
  await page.getByLabel('Status filter').selectOption('archived');
  await row('Browser local').getByRole('button', { name: 'Restore', exact: true }).click(); await confirm('Restore');
  record = await api(path); assert.equal(record.archived_at, null); assert.equal(record.is_active, false);
  await page.getByLabel('Status filter').selectOption('inactive');
  await row('Browser local').getByRole('button', { name: 'Enable', exact: true }).click(); await confirm('Enable');
  assert.equal((await api(path)).is_active, true);
  await page.getByLabel('Status filter').selectOption('all');
  passed();
  step = 'reject a stale browser edit without losing input';
  await edit('Browser local');
  await page.getByLabel('Connection name').fill('Stale name');
  const latest = await api(path);
  const fields = ['name', 'provider', 'base_url', 'model', 'system_prompt', 'max_tokens', 'model_definition_id', 'token_parameter', 'instruction_role', 'stream_usage', 'model_options', 'is_active'];
  await api(path, 'PUT', { ...Object.fromEntries(fields.map(key => [key, latest[key]])), expected_revision: latest.revision, max_tokens: 321 });
  await dialog().getByRole('button', { name: 'Save changes', exact: true }).click();
  await dialog().getByText(/Close the editor and reload/).waitFor();
  assert.equal(await page.getByLabel('Connection name').inputValue(), 'Stale name');
  assert.equal((await api(path)).name, 'Browser local');
  await dialog().getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.getByRole('dialog', { name: 'Discard connection changes?' }).getByRole('button', { name: 'Discard changes' }).click();
  passed();
  step = 'create all supported cloud provider configurations without cloud calls';
  for (const [provider, endpoint, model] of [
    ['openai', 'https://api.openai.com/v1', 'test-model'],
    ['azure_openai', 'https://fixture.openai.azure.com/openai/v1', 'test-deployment'],
    ['openai_compatible', 'https://models.example/v1', 'test-compatible'],
  ]) {
    await page.getByRole('button', { name: 'Create connection', exact: true }).click();
    await page.getByLabel('Connection name').fill('Browser ' + provider);
    await page.getByLabel('Provider', { exact: true }).selectOption(provider);
    await page.getByLabel('API base URL').fill(endpoint);
    await page.getByLabel('API key', { exact: true }).fill('test-cloud-key');
    await page.getByLabel(provider === 'azure_openai' ? 'Deployment ID' : 'Model ID', { exact: true }).fill(model);
    await dialog().getByRole('button', { name: 'Create connection', exact: true }).click();
    await dialog().waitFor({ state: 'hidden' });
    await row('Browser ' + provider).waitFor();
  }
  assert.equal((await api(base + '/configurations')).total, 4);
  passed();
  step = 'search, provider filter, responsive layout and no runtime errors';
  await page.getByLabel('Search connections').fill('Browser local');
  await row('Browser local').waitFor();
  await page.getByRole('button', { name: 'Browser openai', exact: true }).waitFor({ state: 'hidden' });
  await page.getByLabel('Search connections').fill('');
  await page.getByLabel('Provider filter').selectOption('azure_openai');
  await row('Browser azure_openai').waitFor();
  await page.getByRole('button', { name: 'Browser local', exact: true }).waitFor({ state: 'hidden' });
  await page.getByLabel('Provider filter').selectOption('');
  await row('Browser local').waitFor();
  await mkdir('../../../../.test_artifacts/llm-web', { recursive: true });
  await page.screenshot({ path: '../../../../.test_artifacts/llm-web/desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: '../../../../.test_artifacts/llm-web/mobile.png', fullPage: true });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'Page overflows on mobile');
  assert.deepEqual(errors, []);
  passed();
} catch (error) {
  console.error('FAIL at ' + step + ': ' + error.message);
  process.exitCode = 1;
} finally { await browser.close(); }
