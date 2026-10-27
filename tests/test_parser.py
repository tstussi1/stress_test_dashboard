"""Tests of the pre-2013 (CCAR 2011-2012) handling in parser.py and variables.py.

Purpose: pin the derivation of 2011 growth from published levels with hand-computed values,
the history/scenario split from a table's own statement, fail-fast behaviour, and the label
validity windows; the last tests read the real Fed PDFs when they are present locally.

Required inputs: none for the synthetic tests (a stub reader replaces the PDF reader);
`paths.RAW_DIR/2011` and `/2012` for the last two tests (skipped when the raw files are absent).
Outputs: pass/fail only.
Key assumptions: g_t = ((L_t / L_{t-1})^4 - 1) * 100; a scenario is the 13 quarters after the
table's stated last historical quarter.
"""

import math
from pathlib import Path

import pytest

import parser as fed_parser
from parser import (
    RawTable,
    classify_source,
    level_to_growth,
    parse_vintage,
    rounding_bound_pp,
    to_number,
)
from paths import RAW_DIR
from variables import resolve_label

QUARTERS = [f"Q{n} {y}" for y in (2010, 2011, 2012, 2013, 2014) for n in (1, 2, 3, 4)]


def test_level_to_growth_hand_examples():
    assert level_to_growth(13332, 13261) == pytest.approx(2.159, abs=5e-4)
    assert level_to_growth(13255, 13393) == pytest.approx(-4.058, abs=5e-4)
    assert level_to_growth(219.0, 218.0) == pytest.approx(1.8475, abs=5e-5)


def test_rounding_bound_matches_half_unit_of_printed_digit():
    assert rounding_bound_pp(13332, 13261, 0, 0) == pytest.approx(0.0312, abs=2e-3)
    assert rounding_bound_pp(219.0, 218.0, 1, 1) == pytest.approx(0.1866, abs=5e-3)


def test_unicode_hyphen_and_minus_are_negative_numbers():
    assert to_number("\u22121.5") == (-1.5, 1)
    assert to_number("\u20102.40") == (-2.4, 2)
    assert math.isnan(to_number("n.a.")[0])


def test_supervisory_stress_scenario_is_the_severely_adverse_family():
    assert classify_source("Supervisory Stress Scenario", "x") == ("scenario", "severely_adverse")
    assert classify_source("Supervisory Baseline Scenario") == ("scenario", "baseline")


def test_label_validity_windows():
    assert resolve_label("Real GDP", "2011") == ("real_gdp_growth", "annualized_pct_change_from_level")
    assert resolve_label("3-Month T-Bill Rate", "2012") == ("treasury_3m_rate", None)
    assert resolve_label("Unemployment Rate", "2011") == ("unemployment_rate", None)
    with pytest.raises(KeyError):
        resolve_label("Real GDP", "2012")
    with pytest.raises(KeyError):
        resolve_label("3-Month T-Bill Rate", "2014")


def stub_vintage(tmp_path: Path, monkeypatch, tables: list[RawTable]) -> Path:
    vdir = tmp_path / "2011"
    vdir.mkdir()
    (vdir / "stub.pdf").write_bytes(b"")
    monkeypatch.setitem(fed_parser.READERS, ".pdf", lambda path: tables)
    return vdir


def table(header: list[str], n_rows: int, last_historical: str, make_row, caption: str = "Supervisory Stress Scenario") -> RawTable:
    rows = [(QUARTERS[i], None, make_row(i)) for i in range(n_rows)]
    return RawTable(Path("stub.pdf"), caption, header, rows, last_historical)


def test_split_follows_the_stated_last_historical_quarter(tmp_path, monkeypatch):
    t = table(["Unemployment Rate"], 14, "2010Q1", lambda i: [str(5 + i)])
    sc, ac, derived = parse_vintage(stub_vintage(tmp_path, monkeypatch, [t]))
    assert [r["quarter"] for r in ac] == ["2010Q1"]
    assert min(r["quarter"] for r in sc) == "2010Q2" and len(sc) == 13
    assert derived == [] and {r["scenario_name"] for r in sc} == {"severely_adverse"}
    assert {r["published_name"] for r in sc} == {"Supervisory Stress Scenario"}


def test_wrong_number_of_scenario_quarters_raises(tmp_path, monkeypatch):
    t = table(["Unemployment Rate"], 14, "2010Q2", lambda i: [str(5 + i)])
    with pytest.raises(ValueError, match="expected 13"):
        parse_vintage(stub_vintage(tmp_path, monkeypatch, [t]))


def test_derived_growth_uses_previous_level_and_leaves_first_history_quarter_unpublished(tmp_path, monkeypatch):
    levels = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0, 112.0, 113.0]
    t = table(["Real GDP"], 14, "2010Q1", lambda i: [f"{levels[i]:.1f}"])
    sc, ac, derived = parse_vintage(stub_vintage(tmp_path, monkeypatch, [t]))
    assert ac == []  # only 2010Q1 is history and it has no prior level
    first = next(r for r in sc if r["quarter"] == "2010Q2")
    assert first["value"] == pytest.approx(((101.0 / 100.0) ** 4 - 1) * 100, abs=1e-12)
    assert derived[0]["variable_id"] == "real_gdp_growth" and derived[0]["rounding_bound_pp"] > 0


def test_derived_scenario_quarter_without_prior_level_raises(tmp_path, monkeypatch):
    t = table(["Real GDP"], 14, "2010Q1", lambda i: ["100.0"])
    t.rows = [(QUARTERS[0], None, ["100.0"])] + [(QUARTERS[i], None, ["100.0"]) for i in range(2, 15)]  # 2010Q2 missing
    with pytest.raises(ValueError, match="no prior-quarter level"):
        parse_vintage(stub_vintage(tmp_path, monkeypatch, [t]))


def test_unknown_header_raises(tmp_path, monkeypatch):
    with pytest.raises(KeyError):
        parse_vintage(stub_vintage(tmp_path, monkeypatch, [table(["Not A Variable"], 14, "2010Q1", lambda i: ["1.0"])]))


def test_ragged_row_raises(tmp_path, monkeypatch):
    ragged = table(["Unemployment Rate"], 14, "2010Q1", lambda i: ["1.0"])
    ragged.rows[3] = (QUARTERS[3], None, ["1.0", "2.0"])
    with pytest.raises(ValueError, match="values for 1 columns"):
        parse_vintage(stub_vintage(tmp_path, monkeypatch, [ragged]))


def test_tables_with_identical_history_take_the_first_tables_columns(tmp_path, monkeypatch):
    stress = table(["Unemployment Rate", "Real GDP growth"], 14, "2010Q1", lambda i: ["5.0", "2.0"])
    damaged = table(["Unemplovm ent rate", "garbage"], 14, "2010Q1", lambda i: ["5.0", "2.0"] if i == 0 else ["4.0", "1.0"], "Supervisory Baseline Scenario")
    sc, _, _ = parse_vintage(stub_vintage(tmp_path, monkeypatch, [stress, damaged]))
    assert {r["scenario_name"] for r in sc} == {"severely_adverse", "baseline"}
    assert {r["variable_id"] for r in sc} == {"unemployment_rate", "real_gdp_growth"}
    assert next(r for r in sc if r["scenario_name"] == "baseline" and r["variable_id"] == "unemployment_rate")["value"] == 4.0


needs_raw = pytest.mark.skipif(not (RAW_DIR / "2011").is_dir() or not (RAW_DIR / "2012").is_dir(), reason="2011/2012 raw files not downloaded")


@needs_raw
def test_2012_published_values_read_straight_from_the_pdf_tables():
    sc, ac, derived = parse_vintage(RAW_DIR / "2012")
    by = {(r["scenario_name"], r["variable_id"], r["quarter"]): r["value"] for r in sc}
    assert by[("severely_adverse", "unemployment_rate", "2013Q2")] == 13.05
    assert by[("baseline", "unemployment_rate", "2011Q4")] == 9.1
    assert derived == [] and min(r["quarter"] for r in ac) == "2001Q1" and max(r["quarter"] for r in ac) == "2011Q3"


@needs_raw
def test_2011_stress_path_and_derived_growth():
    sc, _, derived = parse_vintage(RAW_DIR / "2011")
    by = {(r["variable_id"], r["quarter"]): r["value"] for r in sc}
    assert by[("unemployment_rate", "2011Q4")] == 11.0 and by[("unemployment_rate", "2012Q1")] == 11.1
    assert by[("real_gdp_growth", "2010Q4")] == pytest.approx(2.159, abs=5e-4)
    assert {d["variable_id"] for d in derived} == {"real_gdp_growth", "cpi_inflation_rate", "real_disposable_income_growth"}
    assert {r["scenario_name"] for r in sc} == {"severely_adverse"} and len({r["variable_id"] for r in sc}) == 9
