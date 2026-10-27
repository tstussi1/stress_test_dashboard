"""Tests of export_web_data.py on a tiny synthetic database, plus spot checks of the real JSON.

Purpose: prove the exporter's contract (published values untouched, level/deviation formulas,
latest-available realized path with Fed estimate flags, bands for model runs, fail-fast
validation, append-only share-code order, freshness check) without depending on the real
database; the last tests read the committed JSON for known values.

Required inputs: none for the synthetic tests; `paths.WEB_DATA_DIR/*.json` for the last two.
Outputs: pass/fail only.
Key assumptions: vintage ids '2013' and '2014' are used because the exporter looks up the Fed
report URL by vintage id; 'bvar_demo' stands for a model run (origin 'bvar', no report).
"""

import json

import duckdb
import pytest

import export_web_data as ex
from build_database import create_views

CFG = {
    "state_version": 2,
    "scenarios": {
        "baseline": {"label": "Baseline", "family": "baseline", "order": 1},
        "severely_adverse": {"label": "Severely adverse", "family": "severely_adverse", "order": 2},
    },
    "theme_order": ["T"],
    "themes": {"g": "T", "u": "T"},
    "unit_labels": {"percent": "percent"},
    "growth_unit_label": "g", "level_index_label": "l", "level_gap_label": "d",
    "band_stats": {"lo": "p16", "hi": "p84", "label": "68% band"},
    "methodology": {"rounding_bound_percent": 0.171},
    "exercises": {}, "exercise_labels": {"CCAR": "CCAR exercise"}, "gaps": [], "data_notes": [],
    "defaults": {"variable": "g", "scenarios": ["baseline"], "vintages": {"latest": 1}, "view": "published", "basis": "growth_gap", "axis": "calendar", "history": "latest", "range": "recent", "band": False},
    "quick_views": [{"id": "q", "label": "Q", "description": "d", "state": {"view": "deviation", "vintages": {"latest": 2}}}],
    "limits": {"calendar_context_quarters": 40},
}


def make_db(with_model_run: bool = False, with_no_baseline_vintage: bool = False) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE variables (variable_id VARCHAR, display_name VARCHAR, scope VARCHAR, measure VARCHAR, unit VARCHAR)")
    con.execute("INSERT INTO variables VALUES ('g', 'Growth', 'domestic', 'growth', 'percent'), ('u', 'Level', 'domestic', 'level', 'percent')")
    con.execute("CREATE TABLE scenario_vintages (vintage_id VARCHAR, cycle_year INTEGER, publication_label VARCHAR, horizon_start_quarter VARCHAR, horizon_end_quarter VARCHAR, origin VARCHAR)")
    con.execute("CREATE TABLE scenarios (scenario_key VARCHAR, vintage_id VARCHAR, scenario_name VARCHAR, published_name VARCHAR)")
    con.execute("CREATE TABLE derived_series (vintage_id VARCHAR, variable_id VARCHAR, source_label VARCHAR, rule VARCHAR, rounding_bound_pp DOUBLE)")
    con.execute("CREATE TABLE scenario_paths (scenario_key VARCHAR, variable_id VARCHAR, quarter VARCHAR, stat VARCHAR, value DOUBLE, source VARCHAR)")
    con.execute("CREATE TABLE actuals (vintage_id VARCHAR, variable_id VARCHAR, quarter VARCHAR, value DOUBLE, source VARCHAR)")
    con.execute("CREATE TABLE sources (vintage_id VARCHAR, file_role VARCHAR, url VARCHAR, retrieved_date VARCHAR)")
    con.execute("CREATE TABLE variable_definitions (vintage_id VARCHAR, variable_id VARCHAR, label VARCHAR, definition VARCHAR, estimate_marked BOOLEAN, source VARCHAR)")
    con.execute("CREATE TABLE estimate_flags (vintage_id VARCHAR, variable_id VARCHAR, quarter VARCHAR, wording VARCHAR, statement VARCHAR, source VARCHAR)")
    vintages = [("2013", 2013, "2013", "2030Q1", "2032Q1", "fed"), ("2014", 2014, "2014", "2031Q1", "2033Q1", "fed")]
    if with_model_run:
        vintages.append(("bvar_demo", 2030, "bvar", "2034Q1", "2036Q1", "bvar"))
    if with_no_baseline_vintage:
        vintages.append(("2012", 2012, "2012", "2027Q1", "2029Q1", "fed"))
    for v in vintages:
        con.execute("INSERT INTO scenario_vintages VALUES (?, ?, ?, ?, ?, ?)", list(v))
        start = int(v[3][:4]) * 4
        quarters = [f"{(start + i) // 4}Q{(start + i) % 4 + 1}" for i in range(13)]
        for scen, base in (("baseline", 2.0), ("severely_adverse", -3.0)):
            if scen == "baseline" and v[0] == "2012":
                continue  # this vintage published no baseline
            key = f"{v[0]}__{scen}"
            con.execute("INSERT INTO scenarios VALUES (?, ?, ?, ?)", [key, v[0], scen, "Supervisory Stress Scenario" if v[0] == "2012" else None])
            for i, q in enumerate(quarters):
                con.execute("INSERT INTO scenario_paths VALUES (?, 'g', ?, 'value', ?, 's')", [key, q, base + i * 0.1])
                con.execute("INSERT INTO scenario_paths VALUES (?, 'u', ?, 'value', ?, 's')", [key, q, 4.0 + (i if scen == "severely_adverse" else 0) * 0.5])
                if v[5] == "bvar" and scen == "severely_adverse":
                    con.execute("INSERT INTO scenario_paths VALUES (?, 'g', ?, 'p16', ?, 's')", [key, q, base + i * 0.1 - 1])
                    con.execute("INSERT INTO scenario_paths VALUES (?, 'g', ?, 'p84', ?, 's')", [key, q, base + i * 0.1 + 1])
        con.execute("INSERT INTO sources VALUES (?, 'f', 'http://x', '2026-01-01')", [v[0]])
        if v[5] == "fed":
            for var in ("g", "u"):
                con.execute("INSERT INTO variable_definitions VALUES (?, ?, 'l', 'def', ?, 's')", [v[0], var, var == "g"])
    # history: 2013 ends 2029Q4; 2014 ends 2030Q4 (so 2030Q1-Q4 are "realized" for the 2013 window)
    for v, first, n in (("2013", 2029 * 4 - 8, 12), ("2014", 2029 * 4 - 8, 16)):
        for var in ("g", "u"):
            for i in range(n):
                q = f"{(first + i) // 4}Q{(first + i) % 4 + 1}"
                con.execute("INSERT INTO actuals VALUES (?, ?, ?, ?, 's')", [v, var, q, 1.0 + i * 0.01 + (0.5 if v == "2014" else 0)])
    if with_no_baseline_vintage:
        con.execute("INSERT INTO derived_series VALUES ('2012', 'g', 'Level', 'rule', 0.03)")
    con.execute("INSERT INTO estimate_flags VALUES ('2014', 'g', '2030Q4', 'estimates', 'The 2030:Q4 values ... are estimates.', 's')")
    create_views(con)
    return con


@pytest.fixture
def tmp_state(monkeypatch, tmp_path):
    monkeypatch.setattr(ex, "STATE_ORDER_PATH", tmp_path / "state_order.json")
    return tmp_path / "state_order.json"


def run(con, cfg=CFG):
    return ex.export(con, cfg, "hash")


def find(series, **kw):
    return next(s for s in series if all(s[k] == v for k, v in kw.items()))


def test_published_untouched_level_and_deviation(tmp_state):
    _, paths, _ = run(make_db())
    sa = find(paths["series"], vintage="2013", scenario="severely_adverse", variable="g")
    assert sa["published"] == [pytest.approx(-3.0 + i * 0.1, abs=1e-12) for i in range(13)]
    expected = 100.0
    for g in sa["published"]:
        expected *= (1 + g / 100) ** 0.25
    assert sa["level"][-1] == pytest.approx(expected, abs=1e-5)
    base = find(paths["series"], vintage="2013", scenario="baseline", variable="g")
    assert base["dev"] is None and base["dev_level"] is None
    assert sa["dev"][0] == pytest.approx(-5.0, abs=1e-5)
    assert sa["dev_level"][3] == pytest.approx(100 * (sa["level"][3] / base["level"][3] - 1), abs=1e-5)
    level_var = find(paths["series"], vintage="2013", scenario="severely_adverse", variable="u")
    assert level_var["level"] is None and level_var["dev_level"] is None and level_var["dev"][2] == pytest.approx(1.0)


def test_realized_is_latest_vintage_value_with_fed_estimate_flag(tmp_state):
    _, paths, _ = run(make_db())
    r = find(paths["series"], vintage="2013", scenario="realized", variable="g")
    assert r["origin"] == "actual" and r["start"] == "2030Q1" and len(r["published"]) == 4
    # 2013's window quarters 2030Q1-Q4 are history positions 12-15 of the 2014 vintage (value 1.5 + 0.01 * i)
    assert r["published"] == [pytest.approx(1.0 + (12 + i) * 0.01 + 0.5, abs=1e-12) for i in range(4)]
    assert r["estimated"] == [3]  # 2030Q4 is the quarter the Fed marks as an estimate in the 2014 vintage
    base = find(paths["series"], vintage="2013", scenario="baseline", variable="g")
    assert r["dev"][0] == pytest.approx(r["published"][0] - base["published"][0], abs=1e-5)
    assert not any(s["vintage"] == "2014" and s["scenario"] == "realized" for s in paths["series"])  # nothing reported yet


def test_actuals_are_each_vintages_own_history(tmp_state):
    _, _, actuals = run(make_db())
    a13 = find(actuals["series"], vintage="2013", variable="g")
    a14 = find(actuals["series"], vintage="2014", variable="g")
    assert len(a13["values"]) == 12 and len(a14["values"]) == 16 and a13["values"][0] != a14["values"][0]
    assert a13["estimated"] == [] and a14["estimated"] == [15]


def test_model_run_gets_band_and_no_fed_report(tmp_state):
    catalog, paths, _ = run(make_db(with_model_run=True))
    band = find(paths["series"], vintage="bvar_demo", scenario="severely_adverse", variable="g")
    assert band["origin"] == "bvar" and band["band"]["label"] == "68% band"
    assert band["band"]["hi"][0] - band["band"]["lo"][0] == pytest.approx(2.0)
    assert "band" not in find(paths["series"], vintage="2013", scenario="severely_adverse", variable="g")
    assert [r["vintage"] for r in catalog["reports"]] == ["2013", "2014"]


def test_unlabelled_scenario_fails_fast(tmp_state):
    cfg = {**CFG, "scenarios": {"baseline": CFG["scenarios"]["baseline"]}}
    with pytest.raises(ValueError, match="severely_adverse"):
        run(make_db(), cfg)


def test_variable_without_theme_fails_fast(tmp_state):
    with pytest.raises(ValueError, match="'u'|\\['u'\\]"):
        run(make_db(), {**CFG, "themes": {"g": "T"}})


@pytest.mark.parametrize(
    "patch, match",
    [
        ({"variable": "nope"}, "variable"),
        ({"view": "levels"}, "view"),
        ({"vintages": {"latest": 99}}, "vintages"),
        ({"vintages": ["1999"]}, "vintages"),
        ({"scenarios": []}, "scenarios"),
        ({"colour": "x"}, "unknown keys"),
    ],
)
def test_default_state_is_validated(tmp_state, patch, match):
    with pytest.raises(ValueError, match=match):
        run(make_db(), {**CFG, "defaults": {**CFG["defaults"], **patch}})


def test_quick_view_may_be_partial_but_not_wrong(tmp_state):
    run(make_db(), {**CFG, "quick_views": [{"id": "q", "label": "Q", "description": "d", "state": {"axis": "horizon"}}]})
    with pytest.raises(ValueError, match="quick view 'q'"):
        run(make_db(), {**CFG, "quick_views": [{"id": "q", "label": "Q", "description": "d", "state": {"axis": "weekly"}}]})


def test_vintage_without_baseline_exports_no_deviation_and_marks_the_catalog(tmp_state):
    catalog, paths, _ = run(make_db(with_no_baseline_vintage=True), {**CFG, "exercises": {"2012": "CCAR"}})
    sa = find(paths["series"], vintage="2012", scenario="severely_adverse", variable="g")
    assert sa["dev"] is None and sa["dev_level"] is None and sa["level"] is not None
    v12 = next(v for v in catalog["vintages"] if v["id"] == "2012")
    assert v12["has_baseline"] is False and v12["exercise"] == "CCAR"
    assert v12["published_names"] == {"severely_adverse": "Supervisory Stress Scenario"}
    assert v12["derived_variable_ids"] == ["g"] and v12["derived_rounding_bound_pp"] == {"g": 0.03}
    v13 = next(v for v in catalog["vintages"] if v["id"] == "2013")
    assert v13["has_baseline"] is True and v13["exercise"] is None and v13["published_names"] == {}


def test_unknown_exercise_vintage_fails_fast(tmp_state):
    with pytest.raises(ValueError, match="exercises"):
        run(make_db(), {**CFG, "exercises": {"1999": "CCAR"}})


def test_state_order_is_append_only(tmp_state):
    run(make_db())
    committed = json.loads(tmp_state.read_text())["order"]["vintages"]
    # a vintage that sorts BEFORE the committed ones in time is appended, never inserted
    catalog, _, _ = run(make_db(with_no_baseline_vintage=True))
    assert catalog["state_order"]["vintages"] == [*committed, "2012"]
    assert [v["id"] for v in catalog["vintages"]][-1] != "2012"  # display order is chronological, share-code order is not


def test_state_order_never_drops_an_id(tmp_state):
    run(make_db(with_model_run=True))
    with pytest.raises(ValueError, match="no longer exist"):
        run(make_db())  # the model-run vintage disappeared: old links would decode wrongly


def test_freshness_check(monkeypatch, tmp_path):
    db, data = tmp_path / "db.duckdb", tmp_path / "data"
    data.mkdir()
    db.write_bytes(b"one")
    monkeypatch.setattr(ex, "DB_PATH", db)
    monkeypatch.setattr(ex, "WEB_DATA_DIR", data)
    assert ex.check() == 1  # no data yet
    for name in ("catalog", "paths", "actuals"):
        (data / f"{name}.json").write_text(json.dumps({"db_sha256": ex.sha256_of(db)}))
    assert ex.check() == 0
    db.write_bytes(b"two")  # database changed after the export
    assert ex.check() == 1


def web_json(name):
    path = ex.WEB_DATA_DIR / name
    return json.loads(ex.require_file(path).read_text())


def test_real_json_spot_values():
    series = web_json("paths.json")["series"]
    sa = find(series, vintage="2026", scenario="severely_adverse", variable="unemployment_rate")
    assert sa["start"] == "2026Q1" and sa["published"][6] == 10.0 and sa["dev"][6] == pytest.approx(5.7, abs=1e-6)
    gdp = find(series, vintage="2026", scenario="severely_adverse", variable="real_gdp_growth")
    assert gdp["level"][5] == pytest.approx(95.39, abs=0.005)
    assert find(series, vintage="2026", scenario="baseline", variable="real_gdp_growth")["dev"] is None
    catalog = web_json("catalog.json")
    ids = {v["id"] for v in catalog["vintages"]}
    assert {s["vintage"] for s in series} == ids and {s["variable"] for s in series} == {v["id"] for v in catalog["variables"]}


def test_real_catalog_is_complete_and_consistent():
    catalog = web_json("catalog.json")
    ids = [v["id"] for v in catalog["vintages"]]
    assert len(catalog["variables"]) == len(catalog["state_order"]["variables"])
    assert sorted(ids) == sorted(catalog["state_order"]["vintages"])  # same ids; share-code order is append-only
    assert next(v for v in catalog["vintages"] if v["id"] == "2013")["estimate_statement"] is None
    assert [v["horizon_start"] for v in catalog["vintages"]] == sorted(v["horizon_start"] for v in catalog["vintages"])
    for v in catalog["vintages"]:
        assert v["n_variables"] == len(v["variable_ids"])
        assert set(v["derived_variable_ids"]) <= set(v["variable_ids"])
        assert v["has_baseline"] == ("baseline" in v["scenarios"])
        assert (v["exercise"] is not None) == bool(v["published_names"])  # the CCAR years carry the Fed's own scenario name
