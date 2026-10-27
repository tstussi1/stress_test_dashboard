# Stress Test Scenario Explorer (web)

See the [repository README](../README.md) for the live link, how to use the dashboard and the map of the repository.

Static dashboard (Vite + Svelte 5 + TypeScript + ECharts, all bundled, no CDN) over three JSON
files exported from the DuckDB database of the Federal Reserve's supervisory stress-test
scenarios, 2011-2026. See `../SCHEMA.md` (export contract) and the Methodology tab for every
formula and gap.

## Run, test, build

```
cd web
npm ci
npm run dev        # development server
npm run verify     # svelte-check, ESLint + Prettier, vitest
npm run build      # freshness check, production build, size budgets (in a clone without the database: ALLOW_MISSING_DB=1 npm run build)
npm run preview    # serve the production build on http://localhost:4173
npm run e2e        # build, then Playwright end-to-end tests (needs `npx playwright install chromium` once)
```

`VITE_BASE_PATH=/<repository>/ npm run build` builds for GitHub Pages (the default `./` works
from any folder). `npm run build` first compares `public/data/catalog.json` with the database
(`../stress_test_scenarios.duckdb`, or `STRESS_TEST_DB_PATH`); where the database is deliberately
absent (CI of a repository that ships only the JSON) set `ALLOW_MISSING_DB=1`.

## Refresh the data

From `stress_test_dashboard/` with the project virtualenv: add the new vintage to
`fetch_sources.py`'s manifest, run `fetch_sources.py`, `build_database.py`, `audit_database.py`,
then `export_web_data.py`, commit the three JSON files in `web/public/data/` and push. A new
vintage or variable is appended to `state_order.json`, so old share links keep working.

## Layout of `src/`

`lib/` pure logic (`query.ts` builds the plotted model that the chart, the Data panel, the Summary
and the CSV all read, and `bandExtremes` names the band's minimum and maximum; `guide.ts` is the text of the usage guide; `focus.ts` decides which lines and which stretches of history are bright; `state.ts` share code and quick views; `chart.ts` the only ECharts file;
`colors.ts` colour = year, pattern = scenario family; `export.ts` CSV, complete dataset, PNG),
`components/` Svelte components, `styles/` tokens and base CSS. Tests: `tests/` (vitest), `e2e/`
(Playwright, including hand-checked Fed values).
