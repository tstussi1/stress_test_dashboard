"""Download official Federal Reserve stress-test scenario source files for the dashboard.

Purpose: fetch the published scenario-variable tables (and the historical actuals
published alongside them) for the stress-test vintages 2011-2026 into
data/raw/stress_test/<vintage>/, so a later parsing step can build the scenario
database from them. This is a fresh fetch for this workstream - it does not read
or depend on scripts/stress_test_audit/ or data/raw/stress_test_audit/, which were
built for a different task (a characterization/peak-to-trough audit, deliberately
scoped to 2015+). The URL manifest below was independently assembled and every file
is verified against its own expected structure right after download, not assumed
correct because a similarly-named file exists elsewhere.

Required inputs: none (the manifest is literal; internet access to
federalreserve.gov is required).

Outputs: data/raw/stress_test/<vintage>/<filename> for every file in MANIFEST.
2016's macro_scenario_tables.zip is also extracted in place. The Fed's full scenario report
PDF for every vintage in REPORT_MANIFEST is saved to
<REPORTS_DIR>/<vintage>/scenarios_report.pdf (used to cross-check the tables and to read
which values the Fed marks as estimates; kept outside RAW_DIR because every sub-folder of
RAW_DIR is treated as a vintage by build_database.py).

Key assumptions / scope:
- Only files that carry the 28 published scenario variables (domestic + international
  macro paths) or their accompanying historical actuals are fetched. Global-market-shock
  and counterparty-default component files, and the narrative/results PDFs, are out of
  scope for this database and are not fetched here.
- 2011 and 2012 (the CCAR supervisory scenarios published in March 2011 and November 2011)
  have no Excel or CSV, but their PDFs contain real data tables ("Supervisory Stress
  Scenario" / "Supervisory Baseline Scenario" appendix pages), so they are fetched like any
  other table source. 2012 also has a second copy of its stress tables (the March 2012
  methodology paper), fetched into the same vintage folder so the build cross-checks the two.
- 2009 (SCAP) is not fetched: the Fed's SCAP report publishes only 12 annual summary numbers
  (annual-average GDP growth and unemployment, Q4/Q4 house prices, 2009 and 2010), which
  cannot sit on the quarterly axis without interpolation. The June 2020 COVID "sensitivity analysis" (V/U/W-shaped alternative downside paths) is
  not in the manifest for the same reason: its accessible-version page
  (sensitivity_accessible.htm) was checked directly and contains only bank-outcome charts,
  no macro scenario data tables. Getting those three variables' paths would require
  digitizing chart images, which this pipeline does not do.
- A file already present on disk is not re-downloaded (safe to re-run), but every file,
  on the run that first fetches it, is checked against a structural expectation specific
  to its role (an htm scenario page must contain a table captioned like a supervisory
  scenario or historical-data table with a quarter range; a CSV must have the expected
  header; an xlsx must have the expected sheet names; the 2014 PDF must contain the
  expected table captions once run through pdftotext). A mismatch raises immediately.
"""

from __future__ import annotations

import re
import subprocess
import zipfile
from pathlib import Path

import openpyxl
import requests
from bs4 import BeautifulSoup

from paths import RAW_DIR, REPORTS_DIR

BOARD = "https://www.federalreserve.gov"

# (filename, url, check) per vintage. "check" names which _verify_* function below
# confirms the download actually has the structure this pipeline needs.
MANIFEST: dict[str, list[tuple[str, str, str]]] = {
    # 2013: the Nov 15, 2012 press release's own attachments - a clean Excel scenario
    # workbook, and a separate historical workbook back to 1976Q1. Independently found
    # and content-verified during planning (not from any prior script's manifest).
    # 2011: CCAR 2011 "Objectives and Overview" (18 Mar 2011), Appendix: the supervisory stress
    # scenario only (no baseline was published), 9 variables, mostly levels.
    "2011": [
        ("ccar_overview.pdf", f"{BOARD}/newsevents/press/bcreg/bcreg20110318a1.pdf", "pdf_ccar_appendix"),
    ],
    # 2012: CCAR 2012 instructions (22 Nov 2011), Appendix III: stress and baseline,
    # domestic and international, 2001Q1-2014Q4.
    "2012": [
        ("instructions.pdf", f"{BOARD}/newsevents/press/bcreg/bcreg20111122d1.pdf", "pdf_ccar_appendix_full"),
        # March 2012 methodology paper, Appendix A: a second Fed copy of the supervisory stress
        # tables; the parser reconciles it cell by cell with the instructions (see parser.reconcile).
        ("methodology.pdf", f"{BOARD}/newsevents/press/bcreg/bcreg20120312a1.pdf", "pdf_ccar_appendix"),
    ],
    "2013": [
        ("scenarios.xlsx", f"{BOARD}/newsevents/pressreleases/files/bcreg20121115a2.xlsx", "xlsx_scenarios"),
        ("historical.xlsx", f"{BOARD}/newsevents/pressreleases/files/bcreg20121115a3.xlsx", "xlsx_historical"),
    ],
    # 2014: no separate Excel was ever attached to the Nov 1, 2013 release; the scenario
    # narrative PDF itself contains Tables 1A/1B (baseline), 2A/2B (adverse), 3A/3B
    # (severely adverse), domestic and international - confirmed with pdftotext -layout
    # during planning. Two documented errata (p.7, p.12) apply to this document.
    "2014": [
        ("scenarios_narrative.pdf", f"{BOARD}/bankinforeg/bcreg20131101a1.pdf", "pdf_scenarios"),
    ],
    # 2015-2016: one continuous history+projection table per scenario/scope; the
    # projection is the published window's last 13 quarters.
    "2015": [
        ("scenarios_variables.htm", f"{BOARD}/bankinforeg/stress-tests/2015-supervisory-scenarios-for-annual-stress-tests-scenarios-variables-considered-in-scenarios.htm", "htm_combined"),
    ],
    "2016": [
        ("macro_scenario_tables.zip", f"{BOARD}/newsevents/pressreleases/files/2016-macro-scenario-tables.zip", "zip_combined"),
    ],
    # 2017-2021: one htm page per vintage holding BOTH a dedicated "Historical data"
    # table (back to Q1:2000) and the separate scenario tables - confirmed directly by
    # byte-inspecting these files during planning (title= attribute, not summary=).
    "2017": [("scenarios.htm", f"{BOARD}/publications/2017-supervisory-scenarios-for-annual-stress-tests-introduction.htm", "htm_historical_plus_scenarios")],
    "2018": [("scenarios.htm", f"{BOARD}/publications/2018-february-supervisory-scenarios-for-annual-stress-tests.htm", "htm_historical_plus_scenarios")],
    "2019": [("scenarios.htm", f"{BOARD}/publications/2019-february-supervisory-scenarios.htm", "htm_historical_plus_scenarios")],
    "2020_feb": [("scenarios_feb.htm", f"{BOARD}/publications/2020-february-supervisory-scenarios.htm", "htm_historical_plus_scenarios")],
    "2020_sep": [("scenarios_sep.htm", f"{BOARD}/publications/2020-september-supervisory-scenarios.htm", "htm_historical_plus_scenarios")],
    "2021": [("scenarios.htm", f"{BOARD}/publications/stress-test-scenarios-february-2021.htm", "htm_historical_plus_scenarios")],
    # 2022-2026: same htm pattern for historical data, plus standalone per-scenario CSVs
    # that carry more decimal precision than the htm table - fetch both, Phase 1 prefers
    # the CSV value and cross-checks it against the htm within display rounding.
    "2022": [
        ("scenarios.htm", f"{BOARD}/publications/2022-Stress-Test-Scenarios.htm", "htm_historical_plus_scenarios"),
        ("baseline_domestic.csv", f"{BOARD}/supervisionreg/files/2022-table_2a_supervisory_baseline_domestic.csv", "csv_domestic"),
        ("baseline_international.csv", f"{BOARD}/supervisionreg/files/2022-table_2b_supervisory_baseline_international.csv", "csv_international"),
        ("severely_adverse_domestic.csv", f"{BOARD}/supervisionreg/files/2022-table_3a_supervisory_severely_adverse_domestic.csv", "csv_domestic"),
        ("severely_adverse_international.csv", f"{BOARD}/supervisionreg/files/2022-table_3b_supervisory_severely_adverse_international.csv", "csv_international"),
    ],
    "2023": [
        ("scenarios.htm", f"{BOARD}/publications/2023-Stress-Test-Scenarios.htm", "htm_historical_plus_scenarios"),
        ("baseline_domestic.csv", f"{BOARD}/supervisionreg/files/2023-Table_2A_Supervisory_Baseline_Domestic.csv", "csv_domestic"),
        ("baseline_international.csv", f"{BOARD}/supervisionreg/files/2023-Table_2B_Supervisory_Baseline_International.csv", "csv_international"),
        ("severely_adverse_domestic.csv", f"{BOARD}/supervisionreg/files/2023-Table_3A_Supervisory_Severely_Adverse_Domestic.csv", "csv_domestic"),
        ("severely_adverse_international.csv", f"{BOARD}/supervisionreg/files/2023-Table_3B_Supervisory_Severely_Adverse_International.csv", "csv_international"),
    ],
    "2024": [
        ("scenarios.htm", f"{BOARD}/publications/2024-stress-test-scenarios.htm", "htm_historical_plus_scenarios"),
        ("baseline_domestic.csv", f"{BOARD}/supervisionreg/files/2024-Table_3A_Supervisory_Baseline_Domestic.csv", "csv_domestic"),
        ("baseline_international.csv", f"{BOARD}/supervisionreg/files/2024-Table_3B_Supervisory_Baseline_International.csv", "csv_international"),
        ("severely_adverse_domestic.csv", f"{BOARD}/supervisionreg/files/2024-Table_4A_Supervisory_Severely_Adverse_Domestic.csv", "csv_domestic"),
        ("severely_adverse_international.csv", f"{BOARD}/supervisionreg/files/2024-Table_4B_Supervisory_Severely_Adverse_International.csv", "csv_international"),
        ("exploratory_a_domestic.csv", f"{BOARD}/supervisionreg/files/2024-Table_Exploratory_Macro_Conditions_A_Domestic.csv", "csv_domestic"),
        ("exploratory_b_domestic.csv", f"{BOARD}/supervisionreg/files/2024-Table_Exploratory_Macro_Conditions_B_Domestic.csv", "csv_domestic"),
        ("exploratory_international.csv", f"{BOARD}/supervisionreg/files/2024-Table_Exploratory_Macro_Conditions_International.csv", "csv_international"),
    ],
    # 2025: exploratory macro conditions are identical to severely adverse (per the
    # Fed's own exploratory-analysis document) but fetched anyway so Phase 1 verifies
    # that numerically rather than assuming it.
    "2025": [
        ("scenarios.htm", f"{BOARD}/publications/2025-stress-test-scenarios.htm", "htm_historical_plus_scenarios"),
        ("baseline_domestic.csv", f"{BOARD}/supervisionreg/files/2025-Table_2A_Supervisory_Baseline_Domestic.csv", "csv_domestic"),
        ("baseline_international.csv", f"{BOARD}/supervisionreg/files/2025-Table_2B_Supervisory_Baseline_International.csv", "csv_international"),
        ("severely_adverse_domestic.csv", f"{BOARD}/supervisionreg/files/2025-Table_3A_Supervisory_Severely_Adverse_Domestic.csv", "csv_domestic"),
        ("severely_adverse_international.csv", f"{BOARD}/supervisionreg/files/2025-Table_3B_Supervisory_Severely_Adverse_International.csv", "csv_international"),
        ("exploratory_domestic.csv", f"{BOARD}/supervisionreg/files/2025-Exploratory_Macro_Conditions_Domestic.csv", "csv_domestic"),
        ("exploratory_international.csv", f"{BOARD}/supervisionreg/files/2025-Exploratory_Macro_Conditions_International.csv", "csv_international"),
    ],
    "2026": [
        ("scenarios.htm", f"{BOARD}/publications/2026-stress-test-scenarios.htm", "htm_historical_plus_scenarios"),
        ("baseline_domestic.csv", f"{BOARD}/supervisionreg/files/2026_Final_Supervisory_Baseline_Domestic.csv", "csv_domestic"),
        ("baseline_international.csv", f"{BOARD}/supervisionreg/files/2026_Final_Supervisory_Baseline_International.csv", "csv_international"),
        ("severely_adverse_domestic.csv", f"{BOARD}/supervisionreg/files/2026_Final_Supervisory_Severely_Adverse_Domestic.csv", "csv_domestic"),
        ("severely_adverse_international.csv", f"{BOARD}/supervisionreg/files/2026_Final_Supervisory_Severely_Adverse_International.csv", "csv_international"),
    ],
}


# The Fed's own scenario report (PDF) for each vintage. URLs are the links printed on the
# Fed's publication pages for that vintage (the htm pages fetched above), except 2013
# (press-release attachment a1) and 2016 (press-release attachment a2; a1 is the CCAR
# instructions), both read from the Fed's press-release pages.
REPORT_MANIFEST: dict[str, str] = {
    "2011": f"{BOARD}/newsevents/press/bcreg/bcreg20110318a1.pdf",
    "2012": f"{BOARD}/newsevents/press/bcreg/bcreg20111122d1.pdf",
    "2013": f"{BOARD}/newsevents/pressreleases/files/bcreg20121115a1.pdf",
    "2014": f"{BOARD}/bankinforeg/bcreg20131101a1.pdf",
    "2015": f"{BOARD}/newsevents/press/bcreg/bcreg20141023a1.pdf",
    "2016": f"{BOARD}/newsevents/pressreleases/files/bcreg20160128a2.pdf",
    "2017": f"{BOARD}/publications/files/bcreg20170203a5.pdf",
    "2018": f"{BOARD}/newsevents/pressreleases/files/bcreg20180201a1.pdf",
    "2019": f"{BOARD}/newsevents/pressreleases/files/bcreg20190213a1.pdf",
    "2020_feb": f"{BOARD}/newsevents/pressreleases/files/bcreg20200206a1.pdf",
    "2020_sep": f"{BOARD}/newsevents/pressreleases/files/bcreg20200917a1.pdf",
    "2021": f"{BOARD}/newsevents/pressreleases/files/bcreg20210212a1.pdf",
    "2022": f"{BOARD}/newsevents/pressreleases/files/bcreg20220210a1.pdf",
    "2023": f"{BOARD}/newsevents/pressreleases/files/bcreg20230209a1.pdf",
    "2024": f"{BOARD}/publications/files/2024-stress-test-scenarios-20240215.pdf",
    "2025": f"{BOARD}/publications/files/2025-stress-test-scenarios-20250205.pdf",
    "2026": f"{BOARD}/publications/files/2026-final-supervisory-stress-test-scenarios-20260204.pdf",
}
REPORT_FILENAME = "scenarios_report.pdf"



# ---------------------------------------------------------------------------
# Per-kind structural verification - fetching and checking are one action, not
# a download pass followed by a separate, skippable review pass.
# ---------------------------------------------------------------------------


def _table_captions(html_bytes: bytes) -> list[str]:
    soup = BeautifulSoup(html_bytes, "lxml")
    caps = []
    for t in soup.find_all("table"):
        cap = t.get("title") or t.get("summary")
        if cap:
            caps.append(cap)
    return caps


def _verify_htm_combined(path: Path) -> None:
    caps = _table_captions(path.read_bytes())
    scenario_caps = [c for c in caps if "scenario" in c.lower() and ("q1" in c.lower() or "q:" in c.lower())]
    if len(scenario_caps) < 6:
        raise ValueError(f"{path}: expected >=6 combined scenario tables (3 scenarios x domestic/international), found {len(scenario_caps)}: {caps}")


def _verify_htm_historical_plus_scenarios(path: Path) -> None:
    caps = _table_captions(path.read_bytes())
    hist = [c for c in caps if "historical" in c.lower()]
    scen = [c for c in caps if "scenario" in c.lower()]
    if len(hist) < 2:
        raise ValueError(f"{path}: expected >=2 'Historical data' tables (domestic+international), found {len(hist)}: {caps}")
    if len(scen) < 4:
        raise ValueError(f"{path}: expected >=4 scenario tables, found {len(scen)}: {caps}")


def _verify_zip_combined(path: Path) -> None:
    with zipfile.ZipFile(path) as zf:
        bad = zf.testzip()
        if bad is not None:
            raise ValueError(f"{path}: corrupt member {bad}")
        names = zf.namelist()
        if not any("baseline" in n.lower() for n in names) or not any("severely" in n.lower() for n in names):
            raise ValueError(f"{path}: expected baseline and severely-adverse members, found {names}")
        zf.extractall(path.parent)


def _verify_csv_domestic(path: Path) -> None:
    header = path.read_text(errors="replace").splitlines()[0]
    if "Real GDP growth" not in header or "Unemployment rate" not in header:
        raise ValueError(f"{path}: header missing expected domestic columns: {header}")


def _verify_csv_international(path: Path) -> None:
    header = path.read_text(errors="replace").splitlines()[0]
    if "real GDP growth" not in header and "Real GDP Growth" not in header:
        raise ValueError(f"{path}: header missing expected international GDP-growth column: {header}")


def _verify_xlsx_scenarios(path: Path) -> None:
    wb = openpyxl.load_workbook(path, read_only=True)
    expected = {"Supervisory baseline", "Supervisory adverse", "Supervisory severely adverse"}
    if not expected.issubset(set(wb.sheetnames)):
        raise ValueError(f"{path}: expected sheets {expected}, found {wb.sheetnames}")


def _verify_xlsx_historical(path: Path) -> None:
    wb = openpyxl.load_workbook(path, read_only=True)
    if not any("1976" in s or "Data" in s for s in wb.sheetnames):
        raise ValueError(f"{path}: expected a historical-data sheet, found {wb.sheetnames}")


def _verify_pdf_scenarios(path: Path) -> None:
    text = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=True
    ).stdout
    needed = [
        "Table 1A. Supervisory baseline scenario: Domestic",
        "Table 2A. Supervisory adverse scenario: Domestic",
        "Table 3A. Supervisory severely adverse scenario: Domestic",
    ]
    missing = [n for n in needed if n not in text]
    if missing:
        raise ValueError(f"{path}: missing expected table captions: {missing}")


def _ccar_table_pages(path: Path) -> int:
    """Pages titled 'Supervisory Baseline/Stress Scenario' with at least 13 quarter rows."""
    text = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=True).stdout
    return sum(
        1
        for page in text.split("\f")
        if re.search(r"Supervisory\s+(?:Baseline|Stress)\s+Scenario", page)
        and len(re.findall(r"^\s*Q\s?[1-4]\s?\d{4}\s+\S", page, flags=re.MULTILINE)) >= 13
    )


def _verify_pdf_ccar_appendix(path: Path) -> None:
    if _ccar_table_pages(path) < 1:
        raise ValueError(f"{path}: no 'Supervisory ... Scenario' page with at least 13 quarter rows")


def _verify_pdf_ccar_appendix_full(path: Path) -> None:
    n = _ccar_table_pages(path)
    if n < 4:
        raise ValueError(f"{path}: expected 4 scenario table pages (stress/baseline x domestic/international), found {n}")


def _verify_pdf_report(path: Path, vintage: str) -> None:
    """The report's first pages must name this vintage's year and be a scenarios report."""
    text = subprocess.run(
        ["pdftotext", "-l", "3", str(path), "-"], capture_output=True, text=True, check=True
    ).stdout
    flat = " ".join(text.split())
    year = vintage[:4]
    if year not in flat or "cenarios" not in flat.replace(" ", ""):
        raise ValueError(f"{path}: first pages do not look like the {year} scenarios report: {flat[:200]!r}")
    if vintage == "2020_sep" and "September 2020" not in flat:
        raise ValueError(f"{path}: expected the September 2020 resubmission scenarios")
    if vintage == "2020_feb" and "February" not in flat and "2020 Supervisory Scenarios for Annual" not in flat:
        raise ValueError(f"{path}: expected the February 2020 scenarios")


VERIFIERS = {
    "htm_combined": _verify_htm_combined,
    "htm_historical_plus_scenarios": _verify_htm_historical_plus_scenarios,
    "zip_combined": _verify_zip_combined,
    "csv_domestic": _verify_csv_domestic,
    "csv_international": _verify_csv_international,
    "xlsx_scenarios": _verify_xlsx_scenarios,
    "xlsx_historical": _verify_xlsx_historical,
    "pdf_scenarios": _verify_pdf_scenarios,
    "pdf_ccar_appendix": _verify_pdf_ccar_appendix,
    "pdf_ccar_appendix_full": _verify_pdf_ccar_appendix_full,
}


def fetch_and_verify(vintage: str, filename: str, url: str, kind: str) -> None:
    dest = RAW_DIR / vintage / filename
    if dest.exists():
        print(f"skip (already fetched and verified): {dest.relative_to(RAW_DIR.parent)}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"{url} returned HTTP {resp.status_code}")
    dest.write_bytes(resp.content)
    VERIFIERS[kind](dest)
    print(f"fetched and verified: {dest.relative_to(RAW_DIR.parent)} ({len(resp.content)} bytes) <- {url}")


def fetch_report(vintage: str, url: str) -> None:
    dest = REPORTS_DIR / vintage / REPORT_FILENAME
    if dest.exists():
        print(f"skip (already fetched and verified): {dest.relative_to(REPORTS_DIR.parent)}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"{url} returned HTTP {resp.status_code}")
    dest.write_bytes(resp.content)
    try:
        _verify_pdf_report(dest, vintage)
    except ValueError:
        dest.unlink()
        raise
    print(f"fetched and verified: {dest.relative_to(REPORTS_DIR.parent)} ({len(resp.content)} bytes) <- {url}")


def main() -> None:
    for vintage, files in MANIFEST.items():
        for filename, url, kind in files:
            fetch_and_verify(vintage, filename, url, kind)
    for vintage, url in REPORT_MANIFEST.items():
        fetch_report(vintage, url)


if __name__ == "__main__":
    main()
