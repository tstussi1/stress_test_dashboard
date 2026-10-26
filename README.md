# Stress Test Scenario Explorer

An interactive explorer of the Federal Reserve's supervisory stress-test scenarios, 2013-2026:
compare years, scenarios and variables as published, as deviation from the baseline, or as a
cumulated level path, together with the history each report ships. Every number marked "as
published" is the Federal Reserve's own; everything else is calculated by a documented formula
(see the Methodology tab).

**Live dashboard: https://tstussi1.github.io/stress_test_dashboard/**

Nothing to install: open the link in any browser. "Copy link" in the page header copies a link
that reopens exactly the view you are looking at. The site is rebuilt and republished
automatically one to two minutes after every push to `main`; progress is shown under the
repository's **Actions** tab.

## Using the dashboard

- **Variable**: pick one in the Variable box, or click any panel in the grid below the large chart.
  Domestic and International variables are separate grids.
- **Years**: choose publications with the presets, the year buttons or the slider. 2020 has two
  publications (Feb and Sep). Each year keeps one colour everywhere.
- **Scenarios**: baseline, adverse, severely adverse and the Fed's alternative scenarios; the line
  pattern tells the scenario, the colour tells the year.
- **View**: *As published* (the Fed's numbers), *Level path* (growth rates compounded into an index),
  *Deviation from baseline* (scenario minus the same year's baseline).
- **Time axis**: *Calendar* or *Quarters since start* (lines aligned at the quarter each scenario starts).
- **History**: the history the Fed published, shown in the As published view on the calendar axis. It
  stops at the newest selected year's start; history that only newer years knew is drawn lighter.
- **Min-max band**: shades the lowest to the highest value among all lines drawn, behind the lines.
- **Hover, pin, Esc**: hover a line to isolate a year, click to pin it, Esc clears pins.
- **Data, Summary, PNG, Copy link**: download exactly the plotted numbers as CSV (or the complete
  dataset), list each line's peak and trough, save a picture, share the view.

## Run it locally

You need Node.js 22 or newer (with npm) and git.

```
git clone https://github.com/tstussi1/stress_test_dashboard.git
cd stress_test_dashboard/web
npm ci
npm run dev
```

Then open http://localhost:5173. To try the production build instead:

```
ALLOW_MISSING_DB=1 npm run build
npm run preview
```

and open http://localhost:4173. `ALLOW_MISSING_DB=1` is needed in a fresh clone because the build
normally checks that the data files match the DuckDB database, and the database is not stored in
the repository. On Windows with WSL, run the commands in WSL and open the same `localhost` address
in the Windows browser.

Checks: `npm run verify` (type check, lint, unit tests) and `npm run e2e` (browser tests; run
`npx playwright install chromium` once first).

## What is in the repository

```
web/                      the website (Vite, Svelte, TypeScript, ECharts; see web/README.md)
  public/data/            the three JSON files the site loads (catalog, paths, actuals)
  src/lib/                logic: query.ts (what is plotted), focus.ts (what is bright), chart.ts (ECharts), state.ts (share link)
  src/components/         Svelte components (toolbar, focus chart, grid, panels, Methodology)
  src/styles/             design tokens and base CSS
  tests/                  unit tests (vitest)
  e2e/                    browser tests (Playwright), including hand-checked Fed values
  scripts/                build checks (data freshness, size budgets, visual QA)
.github/workflows/        deploy.yml: builds web/ and publishes it to GitHub Pages on every push to main
fetch_sources.py          downloads the Fed's public scenario files
build_database.py         builds the DuckDB database from them (the system of record)
parser.py, variables.py,  parsing rules, the variable dictionary and the Fed's definitions
  fed_definitions.py
audit_database.py,        independent audit of the database against the raw files and the Fed reports
  audit_reports.py
export_web_data.py        writes the three JSON files in web/public/data from the database
export_config.yaml        labels, themes, gaps, data notes, the opening view and the quick views
state_order.json          append-only order of ids behind the share link, so old links keep working
paths.py                  every file location, in one place (override with STRESS_TEST_* variables)
SCHEMA.md                 database schema and the JSON export contract
audit/                    audit reports
tests/                    Python tests (pytest)
requirements.txt          pinned Python dependencies;  pytest.ini  pytest settings
```

Not in the repository, by design: the DuckDB database (`*.duckdb`) and the raw downloads (`data/`),
which are rebuilt from the public Fed files (below), and local tool configuration (`.devin/`).
The site itself only needs the committed JSON in `web/public/data/`.

## Refresh the data

Needs a recent Python 3 (the database was built with Python 3.14).

```
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python3 fetch_sources.py && python3 build_database.py && python3 audit_database.py
python3 export_web_data.py        # rewrites web/public/data/*.json from the database
python3 -m pytest && ruff check .
```

Every file location is defined once in `paths.py`; override with the `STRESS_TEST_*` environment
variables it lists. To add a new publication, add it to `fetch_sources.py`'s manifest and rerun the
steps above; new vintages and variables are appended to `state_order.json`, so old share links
keep working. Commit the changed JSON files and push.

## Publish

Pushing to `main` runs `.github/workflows/deploy.yml`, which runs the checks, builds `web/` from the
committed JSON and deploys it to GitHub Pages (Settings, Pages, Source: GitHub Actions). The site is
served from `/<repository>/`; the workflow sets `VITE_BASE_PATH` accordingly.

## Where the numbers come from

Board of Governors of the Federal Reserve System, supervisory stress test scenarios (public reports
linked in the Sources list of the site). The Methodology tab gives every formula, the known gaps
and the data notes; `SCHEMA.md` documents the database and the export. The repository owner chooses
the licence for the code; none is set here.
