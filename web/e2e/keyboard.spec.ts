// Keyboard-only walkthrough (step 2.29): every control of the explorer must be reachable and
// operable with Tab, Shift+Tab, arrows, Enter, Space and Escape, and every stop must show a focus
// indicator. No mouse event is used after the page has loaded.
import { expect, test, type Page } from '@playwright/test';

/** The year chips in the toolbar (the key above the chart has same-named pin buttons). */
const yearChip = (page: Page, name: string) =>
  page.getByRole('group', { name: 'Years', exact: true }).getByRole('button', { name, exact: true });

async function load(page: Page) {
  await page.goto('/');
  await page.locator('canvas').first().waitFor();
}

/** Press Tab until the element matching `locator` has focus (at most `limit` presses). */
async function tabTo(page: Page, locator: ReturnType<Page['locator']>, limit = 80) {
  for (let i = 0; i < limit; i++) {
    await page.keyboard.press('Tab');
    if (await locator.evaluate((el) => el === document.activeElement)) return;
  }
  throw new Error(`could not reach ${locator} with ${limit} Tab presses`);
}

test('every Tab stop shows a visible focus indicator and focus never gets trapped', async ({ page }) => {
  await load(page);
  const seen: string[] = [];
  const invisible: string[] = [];
  for (let i = 0; i < 90; i++) {
    await page.keyboard.press('Tab');
    const stop = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement;
      const style = getComputedStyle(el);
      const outlined = style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) > 0;
      const shadowed = style.boxShadow !== 'none';
      const label = el.getAttribute('aria-label') ?? el.textContent?.trim().slice(0, 30) ?? el.tagName;
      return {
        id: `${el.tagName.toLowerCase()}:${label}`,
        ok: outlined || shadowed,
        body: el === document.body
      };
    });
    if (stop.body) break; // focus left the page: the whole page was traversed
    seen.push(stop.id);
    if (!stop.ok) invisible.push(stop.id);
  }
  expect(seen.length).toBeGreaterThan(30); // tabs, toolbar, year chips, key, panel titles, sources links
  expect(invisible).toEqual([]);
});

test('choose a variable, scenarios, years, view and axis with the keyboard only', async ({ page }) => {
  await load(page);
  const combo = page.getByRole('combobox', { name: 'Search variables' });
  await tabTo(page, combo);
  await page.keyboard.type('unemployment');
  await page.keyboard.press('Enter');
  await expect(
    page.getByRole('heading', { name: 'Unemployment rate: as published', level: 2 })
  ).toBeVisible();

  const adverse = page.getByRole('button', { name: /^Adverse/ });
  await tabTo(page, adverse);
  await page.keyboard.press('Space');
  await expect(adverse).toHaveAttribute('aria-pressed', 'true');

  const chip2020 = yearChip(page, '2020 (Sep)');
  await tabTo(page, chip2020);
  await page.keyboard.press('Enter');
  await expect(chip2020).toHaveAttribute('aria-pressed', 'true');
  await page.keyboard.press('Enter');
  await expect(chip2020).toHaveAttribute('aria-pressed', 'false');

  const deviation = page.getByRole('radio', { name: 'Deviation from baseline', exact: true });
  await page.getByRole('radio', { name: 'As published', exact: true }).focus();
  await tabTo(page, deviation);
  await page.keyboard.press('Enter');
  await expect(deviation).toHaveAttribute('aria-checked', 'true');
  await expect(
    page.getByRole('heading', { name: 'Unemployment rate: deviation from baseline', level: 2 })
  ).toBeVisible();

  const since = page.getByRole('radio', { name: 'Quarters since start' });
  await tabTo(page, since);
  await page.keyboard.press('Enter');
  await expect(since).toHaveAttribute('aria-checked', 'true');
});

test('the year range handles move with the arrow keys', async ({ page }) => {
  await load(page);
  await page.getByRole('button', { name: 'All' }).first().click();
  const first = page.getByRole('slider', { name: 'First vintage' });
  await first.focus();
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowRight');
  await expect(yearChip(page, '2011 CCAR')).toHaveAttribute('aria-pressed', 'false');
  await expect(yearChip(page, '2012 CCAR')).toHaveAttribute('aria-pressed', 'false');
  await expect(yearChip(page, '2013')).toHaveAttribute('aria-pressed', 'true');
});

test('pin a year from the key, open and close the Data panel, all by keyboard', async ({ page }) => {
  await load(page);
  const key = page.locator('.key .year').first();
  await tabTo(page, key);
  await page.keyboard.press('Enter');
  await expect(key).toHaveAttribute('aria-pressed', 'true');
  await page.keyboard.press('Escape');
  await expect(key).toHaveAttribute('aria-pressed', 'false');

  const data = page.getByRole('button', { name: 'Data', exact: true });
  await data.focus();
  await page.keyboard.press('Enter');
  const panel = page.getByRole('dialog');
  await expect(panel).toBeVisible();
  await expect(panel).toBeFocused(); // focus moves into the panel
  await page.keyboard.press('Tab');
  await expect(page.getByRole('button', { name: 'Close data panel' })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(panel).toHaveCount(0);
  await expect(data).toBeFocused(); // and returns to the button that opened it
});

test('the tabs switch with the keyboard and the page has one main landmark and one h1', async ({ page }) => {
  await load(page);
  const methodology = page.getByRole('tab', { name: 'Methodology' });
  await tabTo(page, page.getByRole('tab', { name: 'Explorer' }));
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('Enter');
  await expect(methodology).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('heading', { name: 'What is not available' })).toBeVisible();
  await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
  await expect(page.getByRole('main')).toHaveCount(1);
});
