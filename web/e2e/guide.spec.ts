import { expect, test, type Page } from '@playwright/test';
import { GUIDE } from '../src/lib/guide';

// A first-time visitor: the shared storage state that marks the guide as seen is replaced by an empty one.
test.use({ storageState: { cookies: [], origins: [] } });

async function load(page: Page) {
  await page.goto('/');
  await page.locator('canvas').first().waitFor();
}

const guideButton = (page: Page) => page.getByRole('button', { name: /^How to use this dashboard/ });

test('the guide is open on a first visit, collapsed on the next, and reopens from the masthead', async ({
  page
}) => {
  await load(page);
  await expect(guideButton(page)).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByRole('heading', { name: 'Start here' })).toBeVisible();
  await guideButton(page).click();
  await expect(guideButton(page)).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByRole('heading', { name: 'Start here' })).toBeHidden();
  await page.reload();
  await page.locator('canvas').first().waitFor();
  await expect(guideButton(page)).toHaveAttribute('aria-expanded', 'false');
  await page.getByRole('button', { name: 'How to use', exact: true }).click();
  await expect(guideButton(page)).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByRole('heading', { name: 'Controls', exact: true })).toBeVisible();
});

test('the guide opens from the Methodology tab, and is operable by keyboard', async ({ page }) => {
  await load(page);
  await guideButton(page).click();
  await page.getByRole('tab', { name: 'Methodology' }).click();
  await page.getByRole('button', { name: 'Explorer tab' }).click();
  await expect(guideButton(page)).toHaveAttribute('aria-expanded', 'true');
  await guideButton(page).focus();
  await page.keyboard.press('Enter');
  await expect(guideButton(page)).toHaveAttribute('aria-expanded', 'false');
  await page.keyboard.press('Space');
  await expect(guideButton(page)).toHaveAttribute('aria-expanded', 'true');
});

test('every control the guide names exists on the page under that label', async ({ page }) => {
  await load(page);
  await page.getByRole('radio', { name: 'Deviation from baseline' }).click(); // shows every control that depends on the view
  await page.getByRole('radio', { name: 'As published', exact: true }).click();
  const named = GUIDE.flatMap((section) => section.items.flatMap((i) => (i.control ? [i.control] : [])));
  expect(named.length).toBeGreaterThan(15);
  for (const label of named) {
    const byRole = (['button', 'radio', 'switch', 'slider', 'group'] as const).map((role) =>
      page.getByRole(role, { name: label, exact: true })
    );
    const found = await byRole
      .reduce((all, next) => all.or(next))
      .or(page.locator('.eyebrow', { hasText: new RegExp(`^${label}$`) }))
      .count();
    expect(found, `the guide names "${label}" but no control has that label`).toBeGreaterThan(0);
  }
});
