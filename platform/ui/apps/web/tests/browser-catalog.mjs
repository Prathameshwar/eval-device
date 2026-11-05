import { chromium } from 'playwright-core';
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';

let input = '';
for await (const chunk of process.stdin) input += chunk;
const fixture = JSON.parse(input);
const browser = await chromium.launch({
  executablePath: process.env.PMS_TEST_BROWSER ?? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  headless: true,
});
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
page.setDefaultTimeout(45000);
const errors = [];
page.on('pageerror', (error) => errors.push(error.message));
const artifact = '../../../../.test_artifacts/catalog-web';
await mkdir(artifact, { recursive: true });
let step = 'sign in and tenant scope';
async function go(path) {
  await page.goto(fixture.origin + path);
  await page.waitForLoadState('networkidle');
}
try {
  await go('/catalog/categories');
  await page.waitForURL('**/login');
  await page.getByLabel('Email address', { exact: true }).fill(fixture.email);
  await page.getByLabel('Password', { exact: true }).fill(fixture.password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.waitForURL('**/home');
  const switcher = page.getByLabel('Switch organisation');
  if (await switcher.count() && (await switcher.inputValue()) !== fixture.org) {
    await Promise.all([
      page.waitForResponse((response) => response.request().method() === 'POST' && new URL(response.url()).pathname === '/home'),
      switcher.selectOption(fixture.org),
    ]);
  }
  console.log('PASS ' + step);

  step = 'tenant specialty and patient editing';
  await go('/catalog/categories/new');
  await page.getByLabel('Code', { exact: true }).fill('browser_category');
  await page.getByLabel('English name', { exact: true }).fill('Browser category');
  await page.getByLabel('Description', { exact: true }).fill('Fictional content for a browser test.');
  await page.getByRole('button', { name: 'Save clinical specialty', exact: true }).click();
  await page.waitForURL(/catalog\/categories\/(?!new)[^/]+$/);
  await page.getByLabel('English name', { exact: true }).fill('Browser category revised');
  await page.getByRole('button', { name: 'Save clinical specialty', exact: true }).click();
  await page.getByText('Your changes are saved.', { exact: true }).waitFor();
  await go('/catalog/patients/new');
  await page.getByLabel('Code', { exact: true }).fill('browser_patient');
  await page.getByLabel('English name', { exact: true }).fill('Morgan Browser');
  await page.getByLabel('Occupation (en)', { exact: true }).fill('Teacher');
  await page.getByLabel('Background (en)', { exact: true }).fill('Fictional patient for testing.');
  await page.getByRole('button', { name: 'Save patient profile', exact: true }).click();
  await page.waitForURL(/catalog\/patients\/(?!new)[^/]+$/);
  console.log('PASS ' + step);

  step = 'tenant case Q&A and rehearsal selection';
  await go('/catalog/cases/new');
  await page.getByLabel('Code', { exact: true }).fill('browser_case');
  await page.getByLabel('English title', { exact: true }).fill('Browser case');
  await page.getByLabel('Clinical specialty', { exact: true }).selectOption({ label: 'Browser category revised' });
  await page.getByLabel('Patient profile', { exact: true }).selectOption({ label: 'Morgan Browser' });
  await page.getByRole('tab', { name: 'Questions & answers', exact: true }).click();
  await page.getByRole('button', { name: 'Add Q&A topic', exact: true }).click();
  await page.getByLabel('Intent / topic', { exact: true }).fill('pain');
  await page.getByLabel('Example questions', { exact: true }).fill('Where does it hurt?');
  await page.getByLabel('Answer (en)', { exact: true }).fill('My left knee hurts.');
  await page.getByRole('button', { name: 'Save case', exact: true }).click();
  await page.waitForURL(/catalog\/cases\/(?!new)[^/]+$/);
  await page.reload();
  await page.getByRole('tab', { name: 'Questions & answers', exact: true }).click();
  assert.equal(await page.getByLabel('Answer (en)', { exact: true }).inputValue(), 'My left knee hurts.');
  await go('/patient-setup');
  await page.getByLabel('Clinical specialty', { exact: true }).selectOption(fixture.case.category_id);
  await page.getByLabel('Patient profile', { exact: true }).selectOption(fixture.case.patient_identity_id);
  await page.getByLabel('Case', { exact: true }).selectOption(fixture.case.id);
  await page.getByRole('button', { name: 'Save practice setup', exact: true }).click();
  await page.getByText(/Practice setup saved\. New staff practice/).waitFor();
  console.log('PASS ' + step);

  step = 'copy an active tenant case into a training draft';
  await go('/catalog/cases/' + fixture.case.id);
  await page.getByRole('link', { name: 'Copy into training draft' }).click();
  await page.waitForURL(/\/scenarios\?source_case_id=/);
  await page.getByText('Copy tenant case to a draft', { exact: true }).waitFor();
  await page.getByLabel('New scenario code', { exact: true }).fill('browser_training_case');
  await page.getByRole('dialog').getByRole('button', { name: 'Create draft', exact: true }).click();
  await page.getByRole('heading', { name: 'Scenario draft', exact: true }).waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Mobile overflow');
  assert.deepEqual(errors, []);
  console.log('PASS ' + step);
} catch (error) {
  await page.screenshot({ path: artifact + '/failure.png', fullPage: true }).catch(() => {});
  console.error('FAIL ' + step);
  console.error(error.message);
  console.error('URL ' + page.url());
  console.error('PAGE ERRORS ' + JSON.stringify(errors));
  console.error((await page.locator('main').innerText().catch(() => page.locator('body').innerText())).slice(0, 6000));
  process.exitCode = 1;
} finally {
  await browser.close();
}
