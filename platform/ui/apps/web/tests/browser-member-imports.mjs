import { chromium } from 'playwright-core';
import assert from 'node:assert/strict';
import { mkdir, readFile } from 'node:fs/promises';
let input = '';
for await (const chunk of process.stdin) input += chunk;
const fixture = JSON.parse(input);
const browser = await chromium.launch({ executablePath: process.env.PMS_TEST_BROWSER ?? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
page.setDefaultTimeout(45000);
const errors = [];
page.on('pageerror', error => errors.push(error.message));
let step = 'login and tenant member import entry';
function passed() { console.log('PASS ' + step); }
try {
  await page.goto(fixture.origin + '/members/import'); await page.waitForURL('**/login');
  await page.getByLabel('Email address', { exact: true }).fill(fixture.email);
  await page.getByLabel('Password', { exact: true }).fill(fixture.password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click(); await page.waitForURL('**/home');
  await Promise.all([page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === '/home'), page.getByLabel('Switch organisation').selectOption(fixture.org)]);
  await page.waitForLoadState('networkidle');
  await page.goto(fixture.origin + '/members');
  await page.getByRole('link', { name: 'Import members', exact: true }).click();
  await page.getByRole('heading', { name: 'Choose access for this batch' }).waitFor();
  await page.getByLabel('Role', { exact: true }).selectOption('org_trainee'); passed();
  const artifact = '../../../../.test_artifacts/member-imports-web';
  await mkdir(artifact, { recursive: true });
  await page.screenshot({ path: artifact + '/access.png', fullPage: true });
  step = 'download actual Excel template and upload workbook';
  await page.getByRole('button', { name: 'Continue', exact: true }).click();
  const templatePromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download template', exact: true }).click();
  const template = await templatePromise;
  await template.saveAs(artifact + '/template.xlsx');
  assert.ok((await readFile(artifact + '/template.xlsx')).subarray(0, 2).equals(Buffer.from('PK')));
  await page.getByLabel('Upload completed workbook').setInputFiles({ name: 'trainees.xlsx',
    mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from(fixture.workbook, 'base64') });
  await page.getByRole('button', { name: 'Validate workbook', exact: true }).click();
  await page.getByRole('heading', { name: 'Review before importing', exact: true }).waitFor(); passed();
  step = 'review row errors and download correctable failures';
  await page.getByText('bad', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'Import 1 member', exact: true }).waitFor();
  const errorsPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download errors', exact: true }).click();
  await (await errorsPromise).saveAs(artifact + '/errors.xlsx');
  await page.screenshot({ path: artifact + '/review.png', fullPage: true });
  const savedUrl = page.url();
  await page.reload();
  await page.getByRole('heading', { name: 'Review before importing', exact: true }).waitFor(); passed();
  step = 'partial import persisted results and safe repeated commit';
  await page.getByRole('button', { name: 'Import 1 member', exact: true }).click();
  await page.getByRole('heading', { name: 'Import results', exact: true }).waitFor();
  await page.getByText('1 invitation created; 1 row(s) could not be imported.', { exact: false }).waitFor();
  const resultPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download results', exact: true }).click();
  await (await resultPromise).saveAs(artifact + '/results.xlsx');
  const token = (await context.cookies()).find(cookie => cookie.name.endsWith('ae-session')).value;
  const batch = new URL(savedUrl).searchParams.get('batch');
  const response = await fetch(fixture.api + '/organizations/' + fixture.org + '/member-imports/' + batch + '/commit', {
    method: 'POST', headers: { Authorization: 'Bearer ' + token },
  });
  assert.equal(response.status, 200);
  assert.deepEqual((await response.json()).counts, { total: 2, ready: 0, failed: 1, succeeded: 1 });
  await page.reload(); await page.getByRole('heading', { name: 'Import results', exact: true }).waitFor();
  await page.screenshot({ path: artifact + '/results.png', fullPage: true }); passed();
  step = 'mobile display and saved history';
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'Mobile document overflow');
  await page.screenshot({ path: artifact + '/mobile.png', fullPage: true });
  await page.getByRole('button', { name: 'Start another import', exact: true }).click();
  await page.getByText('Recent imports - results retained for 30 days', { exact: true }).click();
  await page.getByRole('button', { name: 'View results', exact: true }).click();
  await page.getByRole('heading', { name: 'Import results', exact: true }).waitFor();
  assert.deepEqual(errors, []); passed();
} catch (error) {
  await page.screenshot({ path: '../../../../.test_artifacts/member-imports-web/failure.png', fullPage: true }).catch(() => {});
  console.error('FAIL ' + step + ': ' + error.message); process.exitCode = 1;
} finally { await browser.close(); }
