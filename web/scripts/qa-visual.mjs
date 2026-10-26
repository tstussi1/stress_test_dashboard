// Visual QA screenshots (step 2.29): responsive widths and colour-vision-deficiency simulations.
//
// Purpose: produce the images a human inspects for layout defects at 1440, 1024 and 390 px and for
// colour-only encodings under protanopia, deuteranopia, tritanopia and achromatopsia (Chromium's
// vision-deficiency emulation, applied to the whole page).
// Inputs: a running preview of the production build (QA_URL, default http://localhost:4173) and the
// Playwright Chromium installed for this project.
// Outputs: PNG files in QA_OUT_DIR (default ./qa-screenshots, git-ignored); one line per file on stdout.
// Assumptions: the page is driven only through its visible controls; the scenario selection used for
// the colour tests (all 15 years, deviation from baseline, adverse and severely adverse) is the
// one in which colour carries the most information.
import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

const url = process.env.QA_URL ?? 'http://localhost:4173';
const out = resolve(process.env.QA_OUT_DIR ?? 'qa-screenshots');
mkdirSync(out, { recursive: true });

const browser = await chromium.launch();
const shoot = async (name, width, height, { deficiency = 'none', setup } = {}) => {
  const context = await browser.newContext({ viewport: { width, height } });
  const page = await context.newPage();
  const problems = [];
  page.on('console', (m) => ['error', 'warning'].includes(m.type()) && problems.push(m.text()));
  page.on('requestfailed', (r) => problems.push(`failed: ${r.url()}`));
  await page.goto(url);
  await page.locator('canvas').first().waitFor();
  if (deficiency !== 'none') {
    const session = await context.newCDPSession(page);
    await session.send('Emulation.setEmulatedVisionDeficiency', { type: deficiency });
  }
  if (setup) await setup(page);
  await page.waitForTimeout(700);
  const file = resolve(out, `${name}.png`);
  await page.screenshot({ path: file, fullPage: width < 1000 });
  console.log(`${file}${problems.length ? `  PROBLEMS: ${problems.join(' | ')}` : ''}`);
  await context.close();
};

const openControls = async (page) => {
  const toggle = page.getByRole('button', { name: /Controls/ });
  if ((await toggle.count()) && (await toggle.getAttribute('aria-expanded')) === 'false')
    await toggle.click();
};
const click = async (page, role, name) => {
  await page.getByRole(role, { name, exact: false }).first().click();
  await page.waitForTimeout(250);
};
const allYearsDeviation = async (page) => {
  await openControls(page);
  await click(page, 'button', 'Compare years');
  await click(page, 'button', 'All');
};
const fullHistory = async (page) => {
  await openControls(page);
  await click(page, 'radio', 'Full history');
};
const rangeMode = async (page) => {
  await allYearsDeviation(page);
  await click(page, 'radio', 'Range');
  await page.locator('.key .year', { hasText: '2020 (Sep)' }).first().click();
  await page.locator('.key .year', { hasText: '2026' }).first().click();
};
const levelPath = async (page) => {
  await openControls(page);
  await click(page, 'radio', 'Level path');
};
const international = async (page) => {
  await click(page, 'radio', 'International');
};
const dataPanel = async (page) => {
  await page.getByRole('button', { name: 'Data', exact: true }).click();
};
const summaryPanel = async (page) => {
  await page.getByRole('button', { name: 'Summary', exact: true }).click();
};

for (const width of [1440, 1024, 390]) {
  const height = width === 390 ? 844 : 1000;
  await shoot(`width-${width}-landing`, width, height);
  await shoot(`width-${width}-compare-years`, width, height, { setup: allYearsDeviation });
  await shoot(`width-${width}-data-panel`, width, height, { setup: dataPanel });
}
await shoot('full-history', 1440, 1000, { setup: fullHistory });
await shoot('range-pinned', 1440, 1000, { setup: rangeMode });
await shoot('level-path', 1440, 1000, { setup: levelPath });
await shoot('international', 1440, 1000, { setup: international });
await shoot('summary-panel', 1440, 1000, { setup: summaryPanel });
for (const deficiency of ['protanopia', 'deuteranopia', 'tritanopia', 'achromatopsia']) {
  await shoot(`cvd-${deficiency}`, 1440, 1000, { deficiency, setup: allYearsDeviation });
}
await browser.close();
