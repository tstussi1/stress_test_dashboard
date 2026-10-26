"""Hand-computed checks of the two calculation views (`scenario_paths_level`, `scenario_vs_baseline`).

Purpose: pin the derived-value conventions with tiny examples whose answers are computed by
hand, independent of the real database and of the SQL itself.

Required inputs: none (an in-memory DuckDB is built per test with `build_database.create_views`).
Outputs: pass/fail only.
Key assumptions: growth rates are annualized percent changes; the level index is
100 * prod (1 + g/100)^(1/4); deviation is scenario minus the same vintage's baseline.
"""

import duckdb
import pytest

from build_database import create_views

QUARTERS = ["2030Q1", "2030Q2", "2030Q3", "2030Q4"]


def make_db(growth_rates: dict[str, list[float]]) -> duckdb.DuckDBPyConnection:
    """One vintage 'v' with scenarios baseline/adverse for the variable 'g' (growth) and 'u' (level)."""
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE variables (variable_id VARCHAR, measure VARCHAR)")
    con.execute("INSERT INTO variables VALUES ('g', 'growth'), ('u', 'level')")
    con.execute("CREATE TABLE scenarios (scenario_key VARCHAR, vintage_id VARCHAR, scenario_name VARCHAR)")
    con.execute("CREATE TABLE scenario_paths (scenario_key VARCHAR, variable_id VARCHAR, quarter VARCHAR, stat VARCHAR, value DOUBLE)")
    for name, rates in growth_rates.items():
        con.execute("INSERT INTO scenarios VALUES (?, 'v', ?)", [f"v__{name}", name])
        for q, g in zip(QUARTERS, rates, strict=False):
            con.execute("INSERT INTO scenario_paths VALUES (?, 'g', ?, 'value', ?)", [f"v__{name}", q, g])
            con.execute("INSERT INTO scenario_paths VALUES (?, 'u', ?, 'value', ?)", [f"v__{name}", q, 4.0 + g])
    create_views(con)
    return con


def level(con: duckdb.DuckDBPyConnection, name: str) -> list[float]:
    rows = con.execute("SELECT level_index FROM scenario_paths_level WHERE scenario_key = ? ORDER BY quarter", [f"v__{name}"]).fetchall()
    return [r[0] for r in rows]


def test_constant_four_percent_for_four_quarters_is_104():
    con = make_db({"baseline": [4.0] * 4})
    assert level(con, "baseline")[-1] == pytest.approx(104.0, abs=1e-9)


def test_two_quarter_hand_example():
    con = make_db({"baseline": [8.0, -4.0]})
    first = 100 * 1.08**0.25
    assert level(con, "baseline") == pytest.approx([first, first * 0.96**0.25], abs=1e-9)


def test_zero_growth_stays_at_100_and_level_variables_have_no_index():
    con = make_db({"baseline": [0.0] * 4})
    assert level(con, "baseline") == pytest.approx([100.0] * 4, abs=1e-12)
    assert con.execute("SELECT COUNT(*) FROM scenario_paths_level WHERE variable_id = 'u'").fetchone()[0] == 0


def test_deviation_is_scenario_minus_same_vintage_baseline_and_baseline_is_zero():
    con = make_db({"baseline": [2.0, 2.0, 2.0, 2.0], "adverse": [-1.0, -3.5, 0.0, 5.0]})
    dev = con.execute("SELECT deviation FROM scenario_vs_baseline WHERE scenario_key = 'v__adverse' AND variable_id = 'g' ORDER BY quarter").fetchall()
    assert [d[0] for d in dev] == pytest.approx([-3.0, -5.5, -2.0, 3.0], abs=1e-12)
    zero = con.execute("SELECT MAX(ABS(deviation)) FROM scenario_vs_baseline WHERE scenario_key = 'v__baseline'").fetchone()[0]
    assert zero == 0
