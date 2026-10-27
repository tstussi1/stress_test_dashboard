import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';

const origin = `http://localhost:${process.env.E2E_PORT ?? '4173'}`;

async function open(page: Page, hash = '') {
  const problems: string[] = [];
  const foreign: string[] = [];
  page.on(
    'console',
    (m) => ['error', 'warning'].includes(m.type()) && problems.push(`${m.type()}: ${m.text()}`)
  );
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  page.on('requestfailed', (r) => problems.push(`requestfailed: ${r.url()}`));
  page.on('request', (r) => {
    if (!r.url().startsWith(origin) && !r.url().startsWith('data:') && !r.url().startsWith('blob:'))
      foreign.push(r.url());
  });
  await page.goto(`/${hash}`);
  await page.locator('canvas').first().waitFor();
  return { problems, foreign };
}

const heading = (page: Page, name: string) => page.getByRole('heading', { name, level: 2 });
const yearChip = (page: Page, name: string) =>
  page.getByRole('group', { name: 'Years', exact: true }).getByRole('button', { name, exact: true });
const keyChips = (page: Page) => page.locator('.key .year');

/** Hover down a vertical line of the large chart until the tooltip (i.e. a data line) appears, then click there. */
async function clickALine(page: Page) {
  const box = (await page.locator('canvas').first().boundingBox())!;
  const x = box.x + 58 + ((box.width - 58 - 96) * 8) / 13;
  for (let y = box.y + 30; y < box.y + box.height - 60; y += 3) {
    await page.mouse.move(x, y);
    if (await page.locator('.tt').first().isVisible()) {
      await page.mouse.click(x, y);
      return;
    }
  }
  throw new Error('no line found under the cursor');
}

test('lands on the latest year as published, with the focus chart and all domestic variables, no console problems and no foreign request', async ({
  page
}) => {
  const { problems, foreign } = await open(page);
  await expect(heading(page, 'Real GDP growth: as published')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Levels and history' })).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  await expect(heading(page, 'All domestic variables')).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight)); // panels are drawn as they near the viewport
  await expect(page.locator('canvas')).toHaveCount(17); // the focus chart and 16 domestic panels
  await expect(keyChips(page)).toHaveCount(1);
  expect(problems).toEqual([]);
  expect(foreign).toEqual([]);
});

test('a variable can be chosen from the list or by clicking a panel; International switches the grid', async ({
  page
}) => {
  await open(page);
  const box = page.getByRole('combobox', { name: 'Search variables' });
  await box.click();
  await box.fill('house price');
  await page.keyboard.press('Enter');
  await expect(heading(page, 'House Price Index: as published')).toBeVisible();
  await page.getByRole('button', { name: /^CPI inflation rate/ }).click();
  await expect(heading(page, 'CPI inflation rate: as published')).toBeVisible();
  await page.getByRole('radio', { name: 'International' }).click();
  await expect(heading(page, 'Euro area real GDP growth: as published')).toBeVisible();
  await expect(heading(page, 'All international variables')).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await expect(page.locator('canvas')).toHaveCount(13);
});

test('"Compare years" gives the deviation view for the latest six years on the quarters-since axis', async ({
  page
}) => {
  await open(page);
  await page.getByRole('button', { name: 'Compare years' }).click();
  await expect(heading(page, 'Real GDP growth: deviation from baseline')).toBeVisible();
  await expect(page.getByRole('radio', { name: 'Deviation from baseline' })).toHaveAttribute(
    'aria-checked',
    'true'
  );
  await expect(page.getByRole('radio', { name: 'Quarters since start' })).toHaveAttribute(
    'aria-checked',
    'true'
  );
  await expect(keyChips(page)).toHaveCount(6);
  await expect(page.getByText(/6 publications/).first()).toBeVisible();
});

test('year presets and chips change the lines; the baseline is disabled in deviation with the reason', async ({
  page
}) => {
  await open(page);
  await page.getByRole('button', { name: 'Latest 3' }).click();
  await expect(keyChips(page)).toHaveCount(3);
  await yearChip(page, '2020 (Sep)').click();
  await expect(keyChips(page)).toHaveCount(4);
  const baseline = page.getByRole('button', { name: /^Baseline/ });
  await expect(baseline).toBeEnabled();
  await page.getByRole('radio', { name: 'Deviation from baseline' }).click();
  await expect(baseline).toBeDisabled();
});

test('Level path needs the quarters-since axis: it switches the axis and disables Calendar with the reason', async ({
  page
}) => {
  await open(page);
  await page.getByRole('radio', { name: 'Level path' }).click();
  await expect(heading(page, 'Real GDP growth: level path')).toBeVisible();
  await expect(page.getByRole('radio', { name: 'Quarters since start' })).toHaveAttribute(
    'aria-checked',
    'true'
  );
  await expect(page.getByRole('radio', { name: 'Calendar' })).toBeDisabled();
  await expect(page.getByText(/indexed to each year’s own start/)).toBeVisible();
});

test('history is offered only in the as-published calendar view, and Full history reaches back to the first published quarter', async ({
  page
}) => {
  await open(page);
  await page.getByRole('radio', { name: 'Full history' }).click();
  await page.getByRole('button', { name: 'Data', exact: true }).click();
  const panel = page.getByRole('dialog');
  const history = panel.locator('tbody tr').filter({ hasText: 'History (latest)' });
  await expect(history.first().locator('td').nth(3)).toHaveText('1976 Q1');
  await page.keyboard.press('Escape');
  await page.getByRole('radio', { name: 'Deviation from baseline' }).click();
  await expect(page.getByRole('radio', { name: 'Full history' })).toBeDisabled();
  await expect(page.getByText(/History is shown in the As published view only/)).toBeVisible();
});

test('Compare years turns the min-max band on behind all six year lines; the switch turns it off', async ({
  page
}) => {
  await open(page);
  await page.getByRole('button', { name: 'Compare years' }).click();
  const band = page.getByRole('switch', { name: 'Min-max band' });
  await expect(band).toBeChecked();
  await page.getByRole('button', { name: 'Data', exact: true }).click();
  const panel = page.getByRole('dialog');
  await expect(panel.locator('tbody tr').filter({ hasText: 'Minimum' }).first()).toBeVisible();
  await expect(panel.locator('tbody tr').filter({ hasText: 'Maximum' }).first()).toBeVisible();
  const years = await panel
    .locator('tbody tr')
    .filter({ hasText: /^Scenario/ })
    .locator('td:nth-child(2)')
    .allInnerTexts();
  expect(new Set(years).size).toBe(6);
  await band.uncheck();
  await expect(panel.locator('tbody tr').filter({ hasText: 'Minimum' })).toHaveCount(0);
});

test('the band is disabled with a reason while only one line is drawn', async ({ page }) => {
  await open(page);
  await page
    .getByRole('group', { name: 'Scenarios' })
    .getByRole('button', { name: /^Baseline/ })
    .click();
  await expect(page.getByRole('switch', { name: /Min-max band/ })).toBeDisabled();
  await expect(page.getByText(/Only one line is drawn/).first()).toBeVisible();
});

test('click a line to pin its year in every chart; pins are removable chips; Escape clears', async ({
  page
}) => {
  await open(page);
  await page.getByRole('button', { name: 'Compare years' }).click();
  await clickALine(page);
  const pinned = page.locator('.key .year[aria-pressed="true"]');
  await expect(pinned).toHaveCount(1);
  const chips = page.getByRole('group', { name: 'Pinned years' });
  await expect(chips).toBeVisible();
  await chips.getByRole('button', { name: /^Unpin/ }).click();
  await expect(pinned).toHaveCount(0);
  await clickALine(page);
  await expect(pinned).toHaveCount(1);
  await page.keyboard.press('Escape');
  await expect(pinned).toHaveCount(0);
});

test('share code round trip restores the exact state, and the link is short', async ({
  page,
  context,
  browser
}) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await open(page);
  const box = page.getByRole('combobox', { name: 'Search variables' });
  await box.click();
  await box.fill('unemployment');
  await page.keyboard.press('Enter');
  await page.getByRole('button', { name: 'Compare years' }).click();
  await page.locator('.key .year', { hasText: '2023' }).click();
  await page.getByRole('button', { name: 'Copy link' }).click();
  const link = await page.evaluate(() => navigator.clipboard.readText());
  expect(link).toMatch(/#c=[A-Za-z0-9_-]+$/);
  expect(link.split('#c=')[1]!.length).toBeLessThanOrEqual(24);

  const fresh = await (await browser.newContext({ viewport: { width: 1440, height: 1000 } })).newPage();
  await fresh.goto(link);
  await fresh.locator('canvas').first().waitFor();
  await expect(heading(fresh, 'Unemployment rate: deviation from baseline')).toBeVisible();
  await expect(fresh.getByRole('switch', { name: 'Min-max band' })).toBeChecked();
  await expect(fresh.getByRole('group', { name: 'Pinned years' })).toContainText('2023');
  await expect(keyChips(fresh)).toHaveCount(6);
  await expect(fresh.locator('.notices')).toHaveCount(0);
});

test('an unreadable or stale link shows a notice and the default view, never a silent guess', async ({
  page
}) => {
  await open(page, '#c=!!!!');
  await expect(page.getByRole('status').filter({ hasText: 'could not be restored' })).toBeVisible();
  await expect(heading(page, 'Real GDP growth: as published')).toBeVisible();
  await open(page, '#c=Zzzzzz');
  await expect(page.getByRole('status').filter({ hasText: 'older version of the data' })).toBeVisible();
});

test('Data panel opens beside the chart and downloads exactly the plotted rows under header lines', async ({
  page
}) => {
  await open(page);
  await page.getByRole('button', { name: 'Data', exact: true }).click();
  const panel = page.getByRole('dialog');
  await expect(panel).toBeVisible();
  const canvasBox = (await page.locator('canvas').first().boundingBox())!;
  const panelBox = (await panel.boundingBox())!;
  expect(panelBox.x).toBeGreaterThanOrEqual(canvasBox.x + canvasBox.width - 2); // docked to the right of the chart
  const rowsText = await panel.getByText(/rows: exactly the numbers plotted/).innerText();
  const rows = Number(rowsText.split(' ')[0]!.replaceAll(',', ''));
  await expect(panel.locator('tbody tr')).toHaveCount(rows);
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    panel.getByRole('button', { name: 'CSV, this chart' }).click()
  ]);
  const csv = readFileSync((await download.path())!, 'utf8');
  expect(csv.charCodeAt(0)).toBe(0xfeff);
  const lines = csv.trimEnd().split('\r\n');
  const header = lines.filter((l) => l.startsWith('# ') || l.startsWith('\ufeff# '));
  expect(header.join('\n')).toMatch(/Real GDP growth: as published/);
  expect(header.join('\n')).toMatch(/Transform: none; values exactly as published/);
  expect(lines.length - header.length).toBe(rows + 1);
  await page.keyboard.press('Escape');
  await expect(panel).toHaveCount(0);
});

test('Summary lists the peak and trough of each scenario line', async ({ page }) => {
  await open(page);
  const box = page.getByRole('combobox', { name: 'Search variables' });
  await box.click();
  await box.fill('unemployment');
  await page.keyboard.press('Enter');
  await page.getByRole('button', { name: 'Summary', exact: true }).click();
  const row = page.getByRole('dialog').locator('tbody tr').filter({ hasText: 'Severely adverse' });
  await expect(row).toContainText('10');
  await expect(row).toContainText('2027 Q3');
});

test('the complete dataset downloads with one row per stored number', async ({ page }) => {
  await open(page);
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Download the complete dataset (CSV)' }).click()
  ]);
  const lines = readFileSync((await download.path())!, 'utf8')
    .trimEnd()
    .split('\r\n');
  const comments = lines.filter((l) => l.replace('\ufeff', '').startsWith('# ')).length;
  const dataDir = new URL('../public/data/', import.meta.url);
  const stored =
    (
      JSON.parse(readFileSync(new URL('paths.json', dataDir), 'utf8')).series as {
        scenario: string;
        published: number[];
      }[]
    )
      .filter((s) => s.scenario !== 'realized')
      .reduce((n, s) => n + s.published.length, 0) +
    (
      JSON.parse(readFileSync(new URL('actuals.json', dataDir), 'utf8')).series as { values: number[] }[]
    ).reduce((n, a) => n + a.values.length, 0);
  expect(lines.length - comments - 1).toBe(stored);
});

test('PNG export downloads a figure', async ({ page }) => {
  await open(page);
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'PNG', exact: true }).click()
  ]);
  expect(download.suggestedFilename()).toMatch(
    /^stress-scenarios_real_gdp_growth_published_\d{4}-\d{2}-\d{2}\.png$/
  );
});

test('PNG of all panels draws the panels that were off screen too', async ({ page }) => {
  await open(page);
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'PNG, all panels' }).click()
  ]);
  expect(download.suggestedFilename()).toMatch(
    /^stress-scenarios_16-variables_published_\d{4}-\d{2}-\d{2}\.png$/
  );
  await expect(page.locator('canvas')).toHaveCount(17);
});

test('methodology tab lists the formulas, gaps and sources', async ({ page }) => {
  await open(page);
  await page.getByRole('tab', { name: 'Methodology' }).click();
  await expect(page.getByRole('heading', { name: 'What is not available' })).toBeVisible();
  await expect(page.getByText('2009 (SCAP)')).toBeVisible();
  await expect(page.getByText(/June 2020 COVID sensitivity analysis/)).toBeVisible();
  await expect(page.locator('math').first()).toBeVisible();
  await page.getByRole('tab', { name: 'Explorer' }).click();
  await expect(page.getByRole('heading', { name: 'Sources', exact: true })).toBeVisible();
});

test('missing data stops the page with an explicit error, not a blank chart', async ({ page }) => {
  await page.route('**/data/catalog.json', (route) => route.fulfill({ status: 404, body: 'not found' }));
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('Could not load');
  await expect(page.locator('canvas')).toHaveCount(0);
});

test('narrow screens collapse the controls above the figure', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await open(page);
  await expect(page.getByRole('button', { name: /Controls/ })).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByRole('combobox', { name: 'Search variables' })).toBeHidden();
  await page.getByRole('button', { name: /Controls/ }).click();
  await expect(page.getByRole('combobox', { name: 'Search variables' })).toBeVisible();
});

test('All years quick view draws every baseline-bearing year with the band, a readout naming minimum and maximum, and markers', async ({
  page
}) => {
  const { problems } = await open(page);
  await page.getByRole('button', { name: 'All years' }).click();
  await expect(keyChips(page)).toHaveCount(16); // 2011 has no baseline, so it has no deviation line
  const readout = page.getByTestId('band-readout');
  await expect(readout).toContainText('Band minimum');
  await expect(readout).toContainText('Band maximum');
  await expect(readout).toContainText('percentage points');
  await expect(readout).toContainText(/quarter \d+\)/);
  await expect(page.locator('.note', { hasText: '2011: no baseline was published' })).toBeVisible();
  await page.getByRole('switch', { name: 'Min-max band' }).click();
  await expect(readout).toHaveCount(0);
  expect(problems).toEqual([]);
});

test('the 2011 and 2012 CCAR years carry a tag, a note and the Fed’s original scenario name', async ({
  page
}) => {
  await open(page);
  const chips = page.getByRole('group', { name: 'Years', exact: true });
  await expect(chips.getByRole('button', { name: '2011 CCAR' })).toBeVisible();
  await expect(chips.getByRole('button', { name: '2012 CCAR' })).toBeVisible();
  await expect(chips.getByRole('button', { name: '2013', exact: true })).toBeVisible();
  await chips.getByRole('button', { name: '2012 CCAR' }).click();
  await expect(page.locator('.note', { hasText: /Comprehensive Capital Analysis and Review/ })).toBeVisible();
  await expect(page.locator('.note', { hasText: "'Supervisory Stress Scenario'" })).toBeVisible();
});
