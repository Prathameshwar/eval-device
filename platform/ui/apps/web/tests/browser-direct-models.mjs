import { chromium } from 'playwright-core';
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
let input = '';
for await (const chunk of process.stdin) input += chunk;
const fixture = JSON.parse(input);
const artifacts = '../../../../.test_artifacts/device-models-20261004';
await mkdir(artifacts, { recursive: true });
const browser = await chromium.launch({ executablePath: process.env.PMS_TEST_BROWSER ?? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
page.setDefaultTimeout(60000);
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const dialog = () => page.getByRole('dialog').first();
let step = 'login', layouts = 0;
async function capture(name) {
  for (const theme of ['light', 'dark']) {
    await page.evaluate(value => document.documentElement.setAttribute('data-theme', value), theme);
    for (const width of [320, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: 960 });
      await page.waitForTimeout(100);
      const issues = await page.evaluate(() => {
        const root = document.querySelector('[role="dialog"]') ?? document.querySelector('.direct-model-directory');
        const issues = [];
        if (document.documentElement.scrollWidth > innerWidth + 1) issues.push('page overflow');
        if (root.scrollWidth > root.clientWidth + 1) issues.push('panel overflow');
        for (const control of root.querySelectorAll('button,input,select')) {
          if (!control.checkVisibility()) continue;
          const bounds = control.getBoundingClientRect();
          if (bounds.left < 0 || bounds.right > innerWidth + 1) issues.push('control outside viewport');
        }
        return issues;
      });
      assert.deepEqual(issues, [], `${name}/${theme}/${width}`);
      await page.screenshot({ path: `${artifacts}/${name}-${theme}-${width}.png`, fullPage: true });
      layouts++;
    }
  }
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'light'));
}
async function saveModel() {
  await dialog().getByRole('button', { name: 'Save model', exact: true }).click();
  await dialog().waitFor({ state: 'hidden' });
}
async function openDevice() {
  await page.getByRole('button', { name: 'Actions for ' + fixture.device_name, exact: true }).click();
  await page.getByRole('menuitem', { name: 'Configure model', exact: true }).click();
  await dialog().getByLabel('Conversation', { exact: true }).waitFor();
}
try {
  await page.goto(fixture.origin + '/models');
  await page.waitForURL('**/login');
  await page.getByLabel('Email address', { exact: true }).fill(fixture.email);
  await page.getByLabel('Password', { exact: true }).fill(fixture.password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.waitForURL('**/home');
  await page.goto(fixture.origin + '/models');
  await page.getByRole('button', { name: 'Add LLM', exact: true }).waitFor();
  await page.getByText('Loading models…', { exact: true }).waitFor({ state: 'hidden' });
  step = 'model directory'; await capture('directory');
  assert.equal(await page.getByRole('link', { name: /connection|profile|assignment/i }).count(), 0);
  await page.getByRole('button', { name: 'Add LLM', exact: true }).click();
  await dialog().getByLabel('Name', { exact: true }).fill('Cloud fixture');
  await dialog().getByLabel('Model ID', { exact: true }).fill('fixture-model');
  await dialog().getByLabel('API endpoint', { exact: true }).fill('https://api.openai.com/v1');
  await dialog().getByLabel('API key', { exact: true }).fill('mock-not-a-live-key');
  step = 'cloud editor'; await capture('cloud-editor'); await saveModel();
  await page.getByRole('button', { name: 'Edit Cloud fixture', exact: true }).click();
  assert.equal(await dialog().getByLabel('API key', { exact: true }).inputValue(), '');
  await dialog().getByLabel('Name', { exact: true }).fill('Cloud fixture edited'); await saveModel();
  await page.getByRole('button', { name: 'Test connection for Cloud fixture edited', exact: true }).click();
  await page.getByText(/Cloud calls are disabled on the API server/).waitFor();
  step = 'cloud directory'; await capture('cloud-directory');
  await page.getByRole('button', { name: 'Add audio', exact: true }).click();
  await dialog().getByRole('button', { name: 'Local', exact: true }).click();
  await dialog().getByLabel('Name', { exact: true }).fill('Local speech fixture');
  await dialog().getByLabel('Local model', { exact: true }).selectOption('large-v3');
  assert.equal(await dialog().getByLabel('API key', { exact: true }).count(), 0);
  step = 'local editor'; await capture('local-editor'); await saveModel();
  await page.getByRole('button', { name: 'Add video', exact: true }).click();
  await dialog().getByRole('button', { name: 'Local', exact: true }).click();
  await dialog().getByLabel('Name', { exact: true }).fill('Video fixture'); await saveModel();
  await page.getByLabel('Type', { exact: true }).selectOption('video');
  assert.equal(await page.getByRole('heading', { name: 'Cloud fixture edited', exact: true }).count(), 0);
  await page.getByRole('button', { name: 'Delete Video fixture', exact: true }).click();
  await dialog().getByRole('button', { name: 'Delete model', exact: true }).click();
  await dialog().waitFor({ state: 'hidden' });
  await page.getByRole('heading', { name: 'Video fixture', exact: true }).waitFor({ state: 'hidden' });
  step = 'device popup';
  await page.goto(fixture.origin + '/devices');
  await openDevice();
  assert.equal(new URL(page.url()).pathname, '/devices');
  assert.equal(await dialog().getByRole('combobox').count(), 4);
  assert.equal(await dialog().getByText(/profile|connection|publish/i).count(), 0);
  await dialog().getByRole('button', { name: 'Local', exact: true }).click();
  const choices = await dialog().getByLabel('Conversation', { exact: true }).locator('option').evaluateAll(options => options.map(o => ({ value: o.value, label: o.textContent })));
  const local = choices.find(o => /qwen/i.test(o.label) && o.value);
  assert.ok(local, 'installed Qwen is offered');
  await dialog().getByLabel('Conversation', { exact: true }).selectOption(local.value);
  await dialog().getByLabel('Speech recognition', { exact: true }).selectOption({ label: 'Local speech fixture' });
  await capture('device-popup');
  await dialog().getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.getByRole('dialog', { name: 'Discard model changes?' }).getByRole('button', { name: 'Cancel', exact: true }).click();
  assert.equal(await dialog().getByLabel('Conversation', { exact: true }).inputValue(), local.value);
  await dialog().getByRole('button', { name: 'Save', exact: true }).click();
  await dialog().waitFor({ state: 'hidden' });
  await openDevice();
  assert.equal(await dialog().getByLabel('Conversation', { exact: true }).inputValue(), local.value);
  assert.equal(await dialog().getByLabel('Speech recognition', { exact: true }).locator('option:checked').textContent(), 'Local speech fixture');
  await dialog().getByRole('button', { name: 'Cancel', exact: true }).click();
  step = 'switch device to cloud';
  await openDevice();
  await dialog().getByRole('button', { name: 'Cloud', exact: true }).click();
  await dialog().getByLabel('Conversation', { exact: true }).selectOption({ label: 'Cloud fixture edited' });
  assert.equal(await dialog().getByLabel('Speech recognition', { exact: true }).inputValue(), '');
  await dialog().getByRole('button', { name: 'Save', exact: true }).click();
  await dialog().waitFor({ state: 'hidden' });
  await openDevice();
  assert.equal(await dialog().getByLabel('Conversation', { exact: true }).locator('option:checked').textContent(), 'Cloud fixture edited');
  assert.equal(await dialog().getByRole('button', { name: 'Cloud', exact: true }).getAttribute('aria-pressed'), 'true');
  await dialog().getByLabel('Conversation', { exact: true }).selectOption('');
  await dialog().getByRole('button', { name: 'Save', exact: true }).click();
  await dialog().waitFor({ state: 'hidden' });
  await openDevice();
  for (const label of ['Conversation', 'Speech recognition', 'Speech output', 'Video']) assert.equal(await dialog().getByLabel(label, { exact: true }).inputValue(), '');
  await dialog().getByRole('button', { name: 'Cancel', exact: true }).click();
  step = 'legacy links';
  for (const path of ['/connections', '/profiles']) { await page.goto(fixture.origin + path); await page.waitForURL('**/models'); }
  assert.deepEqual(errors, []);
  await writeFile(`${artifacts}/result.json`, JSON.stringify({ passed: true, layouts, checks: ['cloud create/edit', 'connection test deployment gate', 'credential redaction', 'local audio create', 'video create/delete', 'type filter', 'four direct dropdowns', 'cancel retains draft', 'save/reopen selections', 'switch local to cloud', 'clear all device models', 'legacy redirects', 'responsive light/dark'], errors }, null, 2));
  console.log(JSON.stringify({ passed: true, layouts }));
} catch (error) {
  await page.screenshot({ path: `${artifacts}/failure.png`, fullPage: true });
  console.error(`Step: ${step}\n${error.stack}`); process.exitCode = 1;
} finally { await browser.close(); }
