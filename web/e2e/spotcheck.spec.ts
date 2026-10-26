// Number spot-checks (step 2.29). Each expected value below was read by hand straight from the raw
// Federal Reserve file named in `source` (never from the database or the exported JSON) and is
// compared with what the Data panel table and the downloaded CSV show for the same cell. The
// chart tooltip is checked for the first case. Published values must match exactly; calculated
// values (level index, deviation) must match the documented formula to the stated tolerance.
import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';

type Case = {
  name: string;
  source: string;
  variable: string;
  view: 'As published' | 'Level path' | 'Deviation from baseline';
  scenario: string;
  scenarioId: string;
  vintage: string;
  vintageId: string;
  quarter: string; // as in the Fed files, e.g. '2027Q3'
  expected: number;
  tolerance: number; // 0 = exact
};

const cases: Case[] = [
  {
    name: '2026 severely adverse unemployment rate, 2027Q3',
    source: '2026/severely_adverse_domestic.csv',
    variable: 'Unemployment rate',
    view: 'As published',
    scenario: 'Severely adverse',
    scenarioId: 'severely_adverse',
    vintage: '2026',
    vintageId: '2026',
    quarter: '2027Q3',
    expected: 10.0,
    tolerance: 0
  },
  {
    name: '2026 baseline unemployment rate, 2027Q3',
    source: '2026/baseline_domestic.csv',
    variable: 'Unemployment rate',
    view: 'As published',
    scenario: 'Baseline',
    scenarioId: 'baseline',
    vintage: '2026',
    vintageId: '2026',
    quarter: '2027Q3',
    expected: 4.3,
    tolerance: 0
  },
  {
    name: '2026 severely adverse unemployment gap to baseline, 2027Q3 (10.0 - 4.3)',
    source: 'calculated from 2026/severely_adverse_domestic.csv and 2026/baseline_domestic.csv',
    variable: 'Unemployment rate',
    view: 'Deviation from baseline',
    scenario: 'Severely adverse',
    scenarioId: 'severely_adverse',
    vintage: '2026',
    vintageId: '2026',
    quarter: '2027Q3',
    expected: 5.7,
    tolerance: 1e-9
  },
  {
    name: '2026 severely adverse real GDP growth, 2026Q1',
    source: '2026/severely_adverse_domestic.csv',
    variable: 'Real GDP growth',
    view: 'As published',
    scenario: 'Severely adverse',
    scenarioId: 'severely_adverse',
    vintage: '2026',
    vintageId: '2026',
    quarter: '2026Q1',
    expected: -5.4,
    tolerance: 0
  },
  {
    name: '2026 severely adverse real GDP cumulated level index, 2027Q2 (hand-compounded)',
    source:
      'calculated: 100 * prod (1 + g/100)^(1/4) over 2026Q1..2027Q2 of 2026/severely_adverse_domestic.csv',
    variable: 'Real GDP growth',
    view: 'Level path',
    scenario: 'Severely adverse',
    scenarioId: 'severely_adverse',
    vintage: '2026',
    vintageId: '2026',
    quarter: '2027Q2',
    expected: 95.3856,
    tolerance: 5e-4
  },
  {
    name: '2026 severely adverse House Price Index, 2027Q4',
    source: '2026/severely_adverse_domestic.csv',
    variable: 'House Price Index',
    view: 'As published',
    scenario: 'Severely adverse',
    scenarioId: 'severely_adverse',
    vintage: '2026',
    vintageId: '2026',
    quarter: '2027Q4',
    expected: 227.3,
    tolerance: 0
  },
  {
    name: '2024 severely adverse 10-year Treasury yield, 2024Q4',
    source: '2024/severely_adverse_domestic.csv',
    variable: '10-year Treasury yield',
    view: 'As published',
    scenario: 'Severely adverse',
    scenarioId: 'severely_adverse',
    vintage: '2024',
    vintageId: '2024',
    quarter: '2024Q4',
    expected: 0.8,
    tolerance: 0
  },
  {
    name: '2022 severely adverse VIX, 2022Q1',
    source: '2022/severely_adverse_domestic.csv',
    variable: 'Market Volatility Index (VIX)',
    view: 'As published',
    scenario: 'Severely adverse',
    scenarioId: 'severely_adverse',
    vintage: '2022',
    vintageId: '2022',
    quarter: '2022Q1',
    expected: 68.6,
    tolerance: 0
  },
  {
    name: '2024 exploratory A unemployment rate, 2025Q2',
    source: '2024/exploratory_a_domestic.csv',
    variable: 'Unemployment rate',
    view: 'As published',
    scenario: 'Exploratory A',
    scenarioId: 'exploratory_a',
    vintage: '2024',
    vintageId: '2024',
    quarter: '2025Q2',
    expected: 6.6,
    tolerance: 0
  },
  {
    name: '2025 baseline CPI inflation rate, 2025Q3',
    source: '2025/baseline_domestic.csv',
    variable: 'CPI inflation rate',
    view: 'As published',
    scenario: 'Baseline',
    scenarioId: 'baseline',
    vintage: '2025',
    vintageId: '2025',
    quarter: '2025Q3',
    expected: 2.6,
    tolerance: 0
  },
  {
    name: '2013 adverse 10-year Treasury yield, 2015Q4',
    source: '2013/scenarios.xlsx, sheet "Supervisory adverse"',
    variable: '10-year Treasury yield',
    view: 'As published',
    scenario: 'Adverse',
    scenarioId: 'adverse',
    vintage: '2013',
    vintageId: '2013',
    quarter: '2015Q4',
    expected: 5.4,
    tolerance: 0
  },
  {
    name: '2014 adverse 5-year Treasury yield, 2016Q4 (after the Fed errata, 4.8 -> 3.2)',
    source: '2014/scenarios_narrative.pdf, Errata and adverse table',
    variable: '5-year Treasury yield',
    view: 'As published',
    scenario: 'Adverse',
    scenarioId: 'adverse',
    vintage: '2014',
    vintageId: '2014',
    quarter: '2016Q4',
    expected: 3.2,
    tolerance: 0
  }
];

async function openWith(page: Page, c: Case): Promise<void> {
  await page.goto('/');
  await page.locator('canvas').first().waitFor();
  const box = page.getByRole('combobox', { name: 'Search variables' });
  await box.click();
  await box.fill(c.variable);
  await page.getByRole('option', { name: c.variable, exact: true }).click();
  await page.getByRole('radio', { name: c.view, exact: true }).click();
  const chip = (name: string) =>
    page.getByRole('group', { name: 'Years', exact: true }).getByRole('button', { name, exact: true });
  if (c.vintage !== '2026') {
    await chip(c.vintage).click();
    await chip('2026').click();
  }
  const scenario = page.getByRole('button', { name: new RegExp(`^${c.scenario}`) });
  if ((await scenario.getAttribute('aria-pressed')) !== 'true') await scenario.click();
  await expect(scenario).toHaveAttribute('aria-pressed', 'true');
}

/** Minimal RFC 4180 reader: quoted cells may contain commas and doubled quotes. */
function parseCsvLine(line: string): string[] {
  const cells: string[] = [];
  let cell = '';
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]!;
    if (quoted && ch === '"' && line[i + 1] === '"') {
      cell += '"';
      i++;
    } else if (ch === '"') quoted = !quoted;
    else if (ch === ',' && !quoted) {
      cells.push(cell);
      cell = '';
    } else cell += ch;
  }
  return [...cells, cell];
}

function check(actual: number, c: Case): void {
  if (c.tolerance === 0) expect(actual).toBe(c.expected);
  else expect(Math.abs(actual - c.expected)).toBeLessThanOrEqual(c.tolerance);
}

for (const [index, c] of cases.entries()) {
  test(`spot check ${index + 1}: ${c.name}`, async ({ page }) => {
    await openWith(page, c);
    await page.getByRole('button', { name: 'Data', exact: true }).click();
    const panel = page.getByRole('dialog');

    // Data panel table: the one 'Scenario' row for this vintage, scenario and quarter.
    const cell = (text: string) => page.getByRole('cell', { name: text, exact: true });
    const row = panel
      .locator('tbody tr')
      .filter({ has: cell('Scenario') })
      .filter({ has: cell(c.vintage) })
      .filter({ has: cell(c.scenario) })
      .filter({ has: cell(`${c.quarter.slice(0, 4)} Q${c.quarter.slice(5)}`) });
    await expect(row).toHaveCount(1);
    check(Number.parseFloat(await row.locator('td.num').innerText()), c);

    // CSV: same cell, same number, unrounded.
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      panel.getByRole('button', { name: 'CSV, this chart' }).click()
    ]);
    const lines = readFileSync((await download.path())!, 'utf8')
      .trimEnd()
      .split('\r\n')
      .filter((l) => !l.replace('\ufeff', '').startsWith('# '));
    const head = parseCsvLine(lines[0]!.replace('\ufeff', ''));
    const idx = Object.fromEntries(head.map((h, i) => [h, i]));
    const hits = lines
      .slice(1)
      .map(parseCsvLine)
      .filter(
        (f) =>
          f[idx.series_type!] === 'scenario' &&
          f[idx.vintage_id!] === c.vintageId &&
          f[idx.scenario!] === c.scenarioId &&
          f[idx.quarter!] === c.quarter
      );
    expect(hits).toHaveLength(1);
    check(Number(hits[0]![idx.value!]), c);
  });
}

test('the chart tooltip shows the same published number (2026 severely adverse unemployment, 2027Q3)', async ({
  page
}) => {
  await openWith(page, cases[0]!);
  await page.getByRole('radio', { name: 'Quarters since start' }).click();
  const box = (await page.locator('canvas').first().boundingBox())!;
  const x = box.x + 58 + ((box.width - 58 - 96) * 7) / 13; // the axis runs 0..13 quarters since the start; 2027Q3 is quarter 7
  const tooltip = page.locator('.tt');
  let text = '';
  for (let y = box.y + 6; y < box.y + box.height - 60 && !text; y += 2) {
    await page.mouse.move(x, y);
    const shown = (await tooltip.count()) > 0 && (await tooltip.first().isVisible());
    const now = shown ? await tooltip.first().innerText() : '';
    if (now.includes('2027 Q3 (quarter 7)') && now.startsWith('2026 Severely adverse')) text = now;
  }
  expect(text).toContain('2027 Q3 (quarter 7)');
  expect(text.split('\n')[0]).toBe('2026 Severely adverse');
  expect(text).toMatch(/\n10\s/);
});

// History spot checks, read by hand from the raw files: 2013/historical.xlsx (sheet Data_to_1976:
// Q1 1976 unemployment 7.733333333; Q1 2012 real GDP growth 1.959954193) and 2026/scenarios.htm
// (Table 2.A, Q1 2012 real GDP growth 3.4, i.e. the Fed revised this quarter between the two reports).
async function historyRow(page: Page, kind: string, year: string, quarter: string): Promise<string> {
  const row = page
    .getByRole('dialog')
    .locator('tbody tr')
    .filter({ has: page.getByRole('cell', { name: kind, exact: true }) })
    .filter({ has: page.getByRole('cell', { name: year, exact: true }) })
    .filter({ has: page.getByRole('cell', { name: quarter, exact: true }) });
  await expect(row).toHaveCount(1);
  return row.locator('td.num').innerText();
}

test('history: a pre-2000 quarter comes from the 2013 workbook and is labelled as such (unemployment 1976 Q1 = 7.733333333)', async ({
  page
}) => {
  await page.goto('/');
  await page.locator('canvas').first().waitFor();
  const box = page.getByRole('combobox', { name: 'Search variables' });
  await box.click();
  await box.fill('Unemployment rate');
  await page.getByRole('option', { name: 'Unemployment rate', exact: true }).click();
  await page.getByRole('radio', { name: 'Full history' }).click();
  await page.getByRole('button', { name: 'Data', exact: true }).click();
  expect(await historyRow(page, 'History (latest)', '2013', '1976 Q1')).toContain('7.733333333');
});

test('history: the latest report and the as-published-then source differ exactly where the Fed revised (real GDP growth 2012 Q1: 3.4 now, 1.959954193 in 2013)', async ({
  page
}) => {
  await page.goto('/');
  await page.locator('canvas').first().waitFor();
  await page.getByRole('radio', { name: 'Full history' }).click();
  await page
    .getByRole('group', { name: 'Years', exact: true })
    .getByRole('button', { name: '2013', exact: true })
    .click();
  await page.getByRole('button', { name: 'Data', exact: true }).click();
  expect(await historyRow(page, 'History (latest)', '2026', '2012 Q1')).toContain('3.4');
  await page.keyboard.press('Escape');
  await page.getByRole('radio', { name: 'As published then' }).click();
  await page.getByRole('button', { name: 'Data', exact: true }).click();
  expect(await historyRow(page, 'History (as then)', '2013', '2012 Q1')).toContain('1.959954193');
  expect(await historyRow(page, 'History (as then)', '2026', '2012 Q1')).toContain('3.4');
});
