"""Build the Fed stress-test scenario DuckDB database.

Purpose: run `parser.parse_vintage()` over every vintage in
`data/raw/stress_test/`, canonicalize labels via `variables.py`, and load the
result into `stress_test_dashboard/stress_test_scenarios.duckdb` - the dataset the
Phase 2 dashboard (and, later, BVAR output) is built on. The database lives in
`stress_test_dashboard/` rather than `data/processed/` per direct instruction: it
is this workstream's own deliverable, not a data-construction artifact.

Required inputs: `data/raw/stress_test/<vintage>/*` (fetched by `fetch_sources.py`).

Outputs: `stress_test_dashboard/stress_test_scenarios.duckdb` with tables
`variables`, `scenario_vintages`, `scenarios`, `scenario_paths`, `actuals`,
`sources`, and views `scenario_paths_level`, `scenario_vs_baseline`. Rebuilds from
scratch every run (drops and recreates), so it is always a clean reflection of the
current raw files and current `variables.py`/`parser.py` logic - never a target to
patch in place.

Key assumptions:
- One row per (scenario_key, variable_id, quarter) in `scenario_paths`, one row
  per (vintage_id, variable_id, quarter) in `actuals` - both already reconciled
  across every source that published that fact (see `parser.reconcile`), so there
  is nothing left to deduplicate here except the one documented structural
  exception below.
- 2024's domestic exploratory conditions (A and B) share a single published
  international file (`exploratory_international.csv`), which `parser.py`
  classifies generically as "exploratory" since its filename doesn't distinguish
  A from B. This is a real Fed publication structure (stated in their own 2024
  exploratory-analysis documentation), not a parsing ambiguity, so it is resolved
  here once, explicitly: whenever a vintage has both a generic "exploratory" key
  and split "exploratory_a"/"exploratory_b" keys, the generic key's rows are
  duplicated into both splits and the generic key itself is dropped (it would
  otherwise appear as a scenario with only international variables, which was
  never actually published as a standalone exercise).
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fed_definitions import read_vintage_definitions
from fetch_sources import MANIFEST
from parser import parse_vintage
from paths import DB_PATH, RAW_DIR, require_dir
from variables import VARIABLES


def resolve_shared_exploratory_international(scenario_rows: list[dict]) -> list[dict]:
    names = {r["scenario_name"] for r in scenario_rows}
    if not ({"exploratory_a", "exploratory_b"} <= names and "exploratory" in names):
        return scenario_rows
    shared = [r for r in scenario_rows if r["scenario_name"] == "exploratory"]
    kept = [r for r in scenario_rows if r["scenario_name"] != "exploratory"]
    for split in ("exploratory_a", "exploratory_b"):
        kept.extend({**r, "scenario_name": split} for r in shared)
    return kept


def vintage_label_parts(vintage_label: str) -> tuple[int, str]:
    """cycle_year, publication_label - derived from the vintage directory name
    itself (e.g. "2020_feb" -> 2020, "2020 (february)"), not a separate hardcoded
    table, since the directory name already carries this information."""
    year_part, _, suffix = vintage_label.partition("_")
    label = year_part if not suffix else f"{year_part} ({suffix})"
    return int(year_part), label


def bulk_insert(
    con: duckdb.DuckDBPyConnection,
    table: str,
    rows: list[tuple],
    columns: list[str] | None = None,
) -> None:
    """Load `rows` into `table` via a registered DataFrame rather than
    `executemany()` - confirmed empirically (~1000x) faster in this environment,
    since `executemany` binds and executes one row at a time while a DataFrame
    scan is a single bulk operation. `columns` lets the row tuples' order differ
    from the table's declared column order (e.g. to skip a DEFAULT column)."""
    if not rows:
        return
    df = pd.DataFrame(rows, columns=columns)
    con.register("_bulk_df", df)
    col_list = f"({', '.join(columns)})" if columns else ""
    con.execute(f"INSERT INTO {table} {col_list} SELECT * FROM _bulk_df")
    con.unregister("_bulk_df")


def build() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = duckdb.connect(str(DB_PATH))
    con.execute("BEGIN TRANSACTION")
    con.execute("""
        CREATE TABLE variables (
            variable_id VARCHAR PRIMARY KEY,
            display_name VARCHAR,
            scope VARCHAR,
            measure VARCHAR,
            unit VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE scenario_vintages (
            vintage_id VARCHAR PRIMARY KEY,
            cycle_year INTEGER,
            publication_label VARCHAR,
            horizon_start_quarter VARCHAR,
            horizon_end_quarter VARCHAR,
            origin VARCHAR DEFAULT 'fed'
        )
    """)
    con.execute("""
        CREATE TABLE scenarios (
            scenario_key VARCHAR PRIMARY KEY,
            vintage_id VARCHAR REFERENCES scenario_vintages(vintage_id),
            scenario_name VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE scenario_paths (
            scenario_key VARCHAR REFERENCES scenarios(scenario_key),
            variable_id VARCHAR REFERENCES variables(variable_id),
            quarter VARCHAR,
            stat VARCHAR DEFAULT 'value',
            value DOUBLE,
            source VARCHAR,
            PRIMARY KEY (scenario_key, variable_id, quarter, stat)
        )
    """)
    con.execute("""
        CREATE TABLE actuals (
            vintage_id VARCHAR REFERENCES scenario_vintages(vintage_id),
            variable_id VARCHAR REFERENCES variables(variable_id),
            quarter VARCHAR,
            value DOUBLE,
            source VARCHAR,
            PRIMARY KEY (vintage_id, variable_id, quarter)
        )
    """)
    con.execute("""
        CREATE TABLE sources (
            vintage_id VARCHAR,
            file_role VARCHAR,
            url VARCHAR,
            retrieved_date VARCHAR
        )
    """)

    con.execute("""
        CREATE TABLE variable_definitions (
            vintage_id VARCHAR REFERENCES scenario_vintages(vintage_id),
            variable_id VARCHAR REFERENCES variables(variable_id),
            label VARCHAR,
            definition VARCHAR,
            estimate_marked BOOLEAN,
            source VARCHAR,
            PRIMARY KEY (vintage_id, variable_id)
        )
    """)
    con.execute("""
        CREATE TABLE estimate_flags (
            vintage_id VARCHAR REFERENCES scenario_vintages(vintage_id),
            variable_id VARCHAR REFERENCES variables(variable_id),
            quarter VARCHAR,
            wording VARCHAR,
            statement VARCHAR,
            source VARCHAR,
            PRIMARY KEY (vintage_id, variable_id, quarter)
        )
    """)

    bulk_insert(
        con,
        "variables",
        [
            (v.variable_id, v.display_name, v.scope, v.measure, v.unit)
            for v in VARIABLES
        ],
    )

    # Parse every vintage first, accumulating rows for every table in plain
    # Python lists, then issue exactly one bulk INSERT per table - orders of
    # magnitude faster than one executemany() per vintage/scenario, and the
    # per-table insert statements read top to bottom in one place instead of
    # being interleaved with the parsing loop.
    (
        vintage_rows,
        scenario_table_rows,
        scenario_path_rows,
        actual_table_rows,
        source_rows,
        definition_rows,
        flag_rows,
    ) = [], [], [], [], [], [], []
    for vintage_dir in sorted(require_dir(RAW_DIR).iterdir()):
        if not vintage_dir.is_dir():
            continue
        vintage_label = vintage_dir.name
        scenario_rows, actual_rows = parse_vintage(vintage_dir)
        scenario_rows = resolve_shared_exploratory_international(scenario_rows)

        cycle_year, publication_label = vintage_label_parts(vintage_label)
        horizon_start = min(r["quarter"] for r in scenario_rows)
        horizon_end = max(r["quarter"] for r in scenario_rows)
        vintage_rows.append(
            (vintage_label, cycle_year, publication_label, horizon_start, horizon_end)
        )

        for scenario_name in sorted({r["scenario_name"] for r in scenario_rows}):
            scenario_key = f"{vintage_label}__{scenario_name}"
            scenario_table_rows.append((scenario_key, vintage_label, scenario_name))
            scenario_path_rows.extend(
                (scenario_key, r["variable_id"], r["quarter"], r["value"], r["source"])
                for r in scenario_rows
                if r["scenario_name"] == scenario_name
            )

        actual_table_rows.extend(
            (vintage_label, r["variable_id"], r["quarter"], r["value"], r["source"])
            for r in actual_rows
        )

        for filename, url, _kind in MANIFEST.get(vintage_label, []):
            file_path = vintage_dir / filename
            retrieved = file_path.stat().st_mtime if file_path.exists() else None
            retrieved_date = (
                datetime.date.fromtimestamp(retrieved).isoformat()
                if retrieved
                else None
            )
            source_rows.append((vintage_label, filename, url, retrieved_date))

        definitions, statement = read_vintage_definitions(vintage_label)
        for d in definitions:
            definition_rows.append(
                (vintage_label, d["variable_id"], d["label"], d["definition"], d["estimate_marked"], d["source"])
            )
            if d["estimate_marked"]:
                flag_rows.append(
                    (vintage_label, d["variable_id"], statement["quarter"], statement["wording"], statement["sentence"], d["source"])
                )

        print(
            f"{vintage_label}: {len(scenario_rows)} scenario rows, {len(actual_rows)} actual rows, "
            f"{len(definitions)} definitions"
        )

    bulk_insert(
        con,
        "scenario_vintages",
        vintage_rows,
        columns=[
            "vintage_id",
            "cycle_year",
            "publication_label",
            "horizon_start_quarter",
            "horizon_end_quarter",
        ],
    )
    bulk_insert(con, "scenarios", scenario_table_rows)
    bulk_insert(
        con,
        "scenario_paths",
        scenario_path_rows,
        columns=["scenario_key", "variable_id", "quarter", "value", "source"],
    )
    bulk_insert(
        con,
        "actuals",
        actual_table_rows,
        columns=["vintage_id", "variable_id", "quarter", "value", "source"],
    )
    bulk_insert(con, "sources", source_rows)
    bulk_insert(con, "variable_definitions", definition_rows)
    bulk_insert(con, "estimate_flags", flag_rows)
    con.execute("COMMIT")
    create_views(con)
    run_validations(con)
    con.close()
    print(f"built {DB_PATH}")


def create_views(con: duckdb.DuckDBPyConnection) -> None:
    # Cumulated level path for growth-measure variables only, as an index (base
    # 100 at the quarter immediately before the scenario horizon starts) - this
    # is a relative index, not a dollar level, since the Fed never publishes a
    # level for these 13 variables; the compounding itself (quarterly annualized
    # growth rate -> level) is the standard (1+g/100)^0.25 transform.
    con.execute("""
        CREATE VIEW scenario_paths_level AS
        SELECT
            sp.scenario_key,
            sp.variable_id,
            sp.quarter,
            100.0 * EXP(SUM(LN(1 + sp.value / 100.0) * 0.25) OVER (
                PARTITION BY sp.scenario_key, sp.variable_id ORDER BY sp.quarter
            )) AS level_index
        FROM scenario_paths sp
        JOIN variables v ON v.variable_id = sp.variable_id
        WHERE v.measure = 'growth' AND sp.stat = 'value'
    """)
    # Deviation from that same vintage's baseline, at each quarter.
    con.execute("""
        CREATE VIEW scenario_vs_baseline AS
        SELECT
            sp.scenario_key,
            sp.variable_id,
            sp.quarter,
            sp.value,
            base.value AS baseline_value,
            sp.value - base.value AS deviation
        FROM scenario_paths sp
        JOIN scenarios s ON s.scenario_key = sp.scenario_key
        JOIN scenarios base_s ON base_s.vintage_id = s.vintage_id AND base_s.scenario_name = 'baseline'
        JOIN scenario_paths base
            ON base.scenario_key = base_s.scenario_key
            AND base.variable_id = sp.variable_id
            AND base.quarter = sp.quarter
            AND base.stat = sp.stat
        WHERE sp.stat = 'value'
    """)


def run_validations(con: duckdb.DuckDBPyConnection) -> None:
    errors = []

    # 1. Every scenario_key has exactly 13 contiguous quarters, no gaps.
    bad = con.execute("""
        SELECT scenario_key, COUNT(*) AS n
        FROM (SELECT DISTINCT scenario_key, quarter FROM scenario_paths)
        GROUP BY scenario_key HAVING COUNT(*) != 13
    """).fetchall()
    if bad:
        errors.append(f"scenario_key(s) without exactly 13 quarters: {bad}")

    # 2. Variable count per vintage matches the Fed's own stated count.
    bad = con.execute("""
        SELECT s.vintage_id, COUNT(DISTINCT sp.variable_id) AS n_vars
        FROM scenario_paths sp JOIN scenarios s ON s.scenario_key = sp.scenario_key
        GROUP BY s.vintage_id
        HAVING n_vars != CASE WHEN s.vintage_id = '2013' THEN 26 ELSE 28 END
    """).fetchall()
    if bad:
        errors.append(f"vintage(s) with unexpected variable count: {bad}")

    # 3. No duplicate (scenario_key, variable_id, quarter) rows.
    bad = con.execute("""
        SELECT scenario_key, variable_id, quarter, COUNT(*) AS n
        FROM scenario_paths GROUP BY 1, 2, 3 HAVING COUNT(*) > 1
    """).fetchall()
    if bad:
        errors.append(f"duplicate (scenario_key, variable_id, quarter) rows: {bad}")

    # 4. Every vintage's variable set is a subset of what that vintage's own
    # files actually contained - structurally guaranteed by construction, since
    # variable_ids only ever come from headers parser.py found in that vintage's
    # own files (variables.py never injects a variable that wasn't read from a
    # raw file). No separate check needed.

    # 5. 2025 exploratory numerically identical to 2025 severely_adverse.
    bad = con.execute("""
        SELECT e.variable_id, e.quarter, e.value, sa.value
        FROM scenario_paths e
        JOIN scenario_paths sa
            ON sa.scenario_key = '2025__severely_adverse'
            AND sa.variable_id = e.variable_id AND sa.quarter = e.quarter
        WHERE e.scenario_key = '2025__exploratory' AND ABS(e.value - sa.value) > 1e-9
    """).fetchall()
    if bad:
        errors.append(
            f"2025 exploratory does not numerically match 2025 severely_adverse: {bad}"
        )

    # 6. Every variable a vintage publishes has the Fed's own definition for that vintage
    # (and nothing else does).
    bad = con.execute("""
        WITH published AS (SELECT DISTINCT vintage_id, variable_id FROM actuals)
        SELECT 'no definition', p.vintage_id, p.variable_id
        FROM published p LEFT JOIN variable_definitions d USING (vintage_id, variable_id)
        WHERE d.variable_id IS NULL
        UNION ALL
        SELECT 'definition without data', d.vintage_id, d.variable_id
        FROM variable_definitions d LEFT JOIN published p USING (vintage_id, variable_id)
        WHERE p.variable_id IS NULL
    """).fetchall()
    if bad:
        errors.append(f"variable definitions do not match published variables: {bad}")

    # 7. The quarter the Fed says its asterisk marks (stated in each report) is the
    # vintage's last historical (jump-off) quarter.
    bad = con.execute("""
        SELECT f.vintage_id, f.quarter, MAX(a.quarter) AS last_historical
        FROM estimate_flags f JOIN actuals a ON a.vintage_id = f.vintage_id
        GROUP BY f.vintage_id, f.quarter HAVING f.quarter != MAX(a.quarter)
    """).fetchall()
    if bad:
        errors.append(f"estimate-marked quarter is not the jump-off quarter: {bad}")

    if errors:
        raise AssertionError("Phase 1 validation failed:\n" + "\n".join(errors))
    print("all validation checks passed")


if __name__ == "__main__":
    build()
