# `stress_test_scenarios.duckdb` schema

Built by `build_database.py` from the raw Fed files (`paths.RAW_DIR`, default
`data/raw/stress_test/<vintage>/*`, fetched by `fetch_sources.py`) and the Fed's scenario
reports (`paths.REPORTS_DIR`). Every file location comes from `paths.py` (override with the
`STRESS_TEST_*` environment variables listed there). Rebuild anytime with
`python3 build_database.py` from this directory - it drops and recreates the file from the
raw sources every run. The database is the system of record (BVAR output lands here later as
`origin='bvar'` rows); the browser JSON is only a derived snapshot (`export_web_data.py`).

## Tables

- **`variables`** — the 28 canonical scenario variables (`variables.py`'s data
  dictionary): `variable_id` (PK), `display_name`, `scope` (`domestic`/
  `international`), `measure` (`growth`/`level` — whether the Fed publishes this
  as a rate of change or a level/rate), `unit`.
- **`scenario_vintages`** — one row per publication event (e.g. `2013`,
  `2020_feb`, `2020_sep`): `vintage_id` (PK), `cycle_year`, `publication_label`,
  `horizon_start_quarter`/`horizon_end_quarter` (the vintage's own published
  13-quarter scenario window, derived from its own parsed data, not inferred),
  `origin` (`'fed'` for every row this phase inserts; reserved for `'bvar'` later
  for model runs added later).
- **`scenarios`** — one row per (vintage, scenario name): `scenario_key` (PK,
  `f"{vintage_id}__{scenario_name}"`), `vintage_id` (FK), `scenario_name`
  (`baseline`/`adverse`/`severely_adverse`/`alternative_severe`/`exploratory`/
  `exploratory_a`/`exploratory_b`).
- **`scenario_paths`** — the fact table, exactly as published (native unit):
  `scenario_key` (FK), `variable_id` (FK), `quarter`, `stat` (`'value'` for every
  row this phase inserts; reserved for `'median'`/`'p10'`/`'p90'` BVAR bands
  later), `value`, `source` (which raw file/table this value was read from, after
  cross-source reconciliation — see below). PK: `(scenario_key, variable_id,
  quarter, stat)`.
- **`actuals`** — realized history, kept per-vintage (the same historical quarter
  can differ across publications due to data revisions): `vintage_id` (FK),
  `variable_id` (FK), `quarter`, `value`, `source`. PK: `(vintage_id,
  variable_id, quarter)`.
- **`sources`** — literal official URL per vintage/file, from
  `fetch_sources.MANIFEST`: `vintage_id`, `file_role` (filename), `url`,
  `retrieved_date`.

- **`variable_definitions`** — the Fed's own definition of every variable in every vintage
  (`vintage_id`, `variable_id`, `label`, `definition`, `estimate_marked`, `source`), read by
  `fed_definitions.py` from each vintage's scenario report (2013: the workbook's "Data notes"
  sheet). It is the evidence for `variables.measure`: the 13 growth variables are defined as
  quarterly percent changes at an annualized rate (explicitly in 169 definitions; for the 26
  international 2013-2017 definitions that are silent, the history is the same series on the
  same scale as the nearest later vintage that says so - slope 0.80-1.07).
- **`estimate_flags`** — values the Fed marks as estimates: `vintage_id`, `variable_id`,
  `quarter` (always the vintage's last historical / jump-off quarter, enforced at build),
  `wording` ("projected" in the 2014-2020 reports, "estimates" from 2021), `statement` (the
  Fed's sentence), `source`. 165 rows. 2013 has no such statement (documented gap).

## Views

- **`scenario_paths_level`** — cumulated level *index* (base 100 at the quarter
  immediately before the scenario horizon starts) for the 13 variables the Fed
  only ever publishes as a growth rate. This is a relative index, not a dollar
  level — the Fed never publishes an actual level for these 13 series, so there
  is nothing to anchor a true level at; the index lets you see the shape and
  magnitude of the cumulative path (e.g. "GDP falls 5% peak-to-trough") without
  implying a fabricated dollar figure.
- **`scenario_vs_baseline`** — `scenario_paths` self-joined to that same
  vintage's `baseline` scenario on `(variable_id, quarter)`: `value`,
  `baseline_value`, `deviation = value - baseline_value`.

## Derived-value conventions (calculated, not published)

- Cumulated level (growth variables only): `100 * prod over quarters of (1 + g/100)^(1/4)`,
  base 100 at the quarter before the vintage's horizon. The Fed publishes `g` as an annualized
  percent change (compounding convention), so one quarter compounds by the fourth root. It is
  a relative index, not a dollar level.
- Deviation: scenario value minus the same vintage's baseline value, same quarter, native unit.
  A baseline deviates from itself by exactly 0.
- Precision: the Fed rounds growth rates to (usually) 0.1 pp; if every rate were off by the
  maximum 0.05 pp, a 13-quarter cumulated level could be off by at most 0.171%.
- Both are re-derived independently in pandas by `audit_database.py` (agreement 1.6e-13) and
  pinned by hand-computed examples in `tests/test_views.py`.

## Audits (evidence that the database equals what the Fed published)

Run `python3 audit_database.py` and `python3 audit_reports.py`; reports go to `audit/`:
`cell_audit.md` (all 49,243 raw-file facts equal the database bit for bit), `report_audit.md`
(every table printed in the 15 Fed reports equals the database), `definition_audit.md`,
`anomaly_register.md` (130 cross-vintage differences, classified; the database keeps the
Fed's number in every case) and `derived_audit.md`.

## How a value got here (cross-source reconciliation)

Several vintages publish the same fact in more than one file (e.g. 2013's three
scenario-sheet-embedded histories and the dedicated `historical.xlsx`; 2022-2026's
htm historical/scenario tables and their standalone per-scenario CSVs). Every such
case is verified, never silently preferred: `parser.reconcile()` requires every
source's value to agree with every other within a tolerance derived from the
coarser of their own published decimal places, raising with full detail on any
disagreement, and only then keeps whichever source published the most decimal
places (reporting the same fact more precisely, not a different fact). See
`parser.py`'s module docstring and `build_database.py`'s validation step 5 (2025
`exploratory` vs `severely_adverse`) for the one documented exception.

## Known, documented gaps

- 2009, 2011, 2012, and the June 2020 COVID sensitivity analysis: the Fed never
  published a data table for these, only chart figures - excluded, not digitized
  from images.
- 2013 has 26 variables (no 5-year Treasury yield, no prime rate - both were
  added starting with the 2014 vintage).
- 2013 has no asterisk (estimate) statement in the Fed's files, so no values are flagged as
  Fed-marked estimates for that vintage.
- Data notes (Fed-side, kept exactly as published): VIX 2008Q2 is 31.01000023 in the 2013
  file vs 24.1 in all later vintages; house price index 2015Q1-Q3 in the 2016 vintage differs
  from all other vintages; the 2014 report prints exchange rates to one decimal; the house
  price index (2017/2018), BBB corporate yield (2018, 2020) and Dow Jones index (Float Cap)
  series definitions change over time (see `audit/definition_audit.md`); the 2026 report says
  2025:Q4 unemployment and CPI inflation average Nov and Dec 2025 because October 2025 data
  were not published.
- Pre-2013 history is not yet in scope; `parser.py`'s reader/interpreter split is
  designed so adding it only requires a new reader if the raw format is genuinely
  new, not a rewrite of the classification/reconciliation logic.

## Export contract (`export_web_data.py` -> `web/public/data/*.json`)

The browser never reads the database. `export_web_data.py` (config: `export_config.yaml`) writes
three files from the frozen DuckDB; Python computes every number, the page only selects, aligns
quarters and takes min/max across the user's selection.

- **`catalog.json`** — `schema_version`, `state_version`, `built_at`, `db_sha256` (hash of the
  database file the snapshot was built from; `npm run build` refuses a stale snapshot), `variables`
  (id, name, scope, measure, unit, theme, Fed definition), `vintages` (id, label, scenario window,
  `jump_off` = last historical quarter, scenarios, variable ids, the Fed's estimate statement),
  `scenarios` (name, label, `family` used for line style), `sources`, `reports`, `gaps`,
  `data_notes`, `labels`, `state_order` (append-only ids behind the share code),
  `defaults` (what the page opens on), `quick_views` (one-click presets), `limits`
  (`calendar_context_quarters`: quarters of history shown by the "Recent" range).
  `defaults` and each quick view are state specs: `variable`, `scenarios`, `vintages`
  (`'all'`, `{latest: N}` or a list of ids), `view` (`published|level|deviation`), `basis`
  (`growth_gap|level_gap`), `axis` (`horizon|calendar`), `history` (`off|latest|realtime`),
  `range` (`recent|full`), `display` (`lines|range`). The exporter validates ids and choices and
  stops on any unknown key.
- **`paths.json`** — one series per (variable, vintage, scenario): `published` (the Fed's numbers,
  untouched), `level` (growth variables only: annualized rates compounded, 100 = quarter before the
  scenario starts), `dev` (scenario minus the same vintage's baseline), `dev_level` (percent gap of
  the cumulated levels), `estimated` indexes, optional `band` for model runs. Quarters are
  consecutive from `start`; horizon index = position + 1. The `realized` pseudo-scenario (latest
  report per quarter) is exported but no longer drawn; the page builds the latest-report history
  line from `actuals.json`.
- **`actuals.json`** — each vintage's own as-published Historical data (real-time data), per
  variable, with the Fed-marked estimate indexes. Some vintages start 2000Q1 or 2001Q1; the 2013
  workbook reaches 1976Q1 for most variables.
- **Share code** (`#c=<code>`, built by `web/src/lib/state.ts`): version character, one character for
  the focus variable, bit-masks for scenarios, vintages and pins, two flag characters (view, basis,
  axis, history, range, display, tab). Indexes refer to `state_order`, which the exporter refuses to
  reorder; bump `state_version` in `export_config.yaml` to reset deliberately (old links then show
  a visible notice).
- **Complete dataset** (`Download the complete dataset (CSV)` in the page): one row per stored
  number: 14,846 scenario rows and 34,397 history rows, equal to `scenario_paths` and `actuals`.
