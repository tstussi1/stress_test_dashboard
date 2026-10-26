"""Read the Fed's own variable definitions and estimate markings for each vintage.

Purpose: every Fed scenario publication describes each variable ("U.S. real GDP growth:
Quarterly percent change ... expressed at an annualized rate ...") and states which
values of the last historical (jump-off) quarter are estimates by marking the variable
with an asterisk ("The 2025:Q4 values of variables marked with an asterisk (*) are
estimates"; "projected" in the 2014-2020 reports). This module extracts both, so the
database can (a) prove each variable's growth-versus-level classification from the Fed's
wording instead of from a label, and (b) flag the Fed-marked estimates in the dashboard.

Required inputs: for each vintage, the Fed scenario report PDF at
`<REPORTS_DIR>/<vintage>/scenarios_report.pdf` (`pdftotext`, reading-order text), or, for
2013, whose PDF is letter-spaced and unreliable to parse, the "Data notes" sheet of
`<RAW_DIR>/2013/scenarios.xlsx`.

Outputs: `read_vintage_definitions(vintage_id)` returns `(definitions, statement)`:
  definitions: list of dicts `variable_id, label, definition, estimate_marked, source`
  statement: dict `quarter, wording, sentence` or None when the Fed made no such statement.

Key assumptions:
  - A definition starts at a line beginning with an optional "*" and one of the Fed's
    scope words ("U.S.", "Euro area", "Developing Asia", "Japan", "U.K.") up to a colon,
    and runs to the next blank line. Labels map to `variable_id` through
    `variables.variable_id_for`; the one definition-section naming that differs from the
    column header (the Dow Jones index "(Float Cap)") is listed in DEFINITION_ALIASES.
  - A definition labelled "Exchange rates" describes every exchange-rate variable.
  - A label that matches no variable is an error (no silent skipping).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import openpyxl

from paths import RAW_DIR, REPORTS_DIR, require_file
from variables import VARIABLES, normalize_label, variable_id_for

REPORT_FILENAME = "scenarios_report.pdf"
LABEL = re.compile(r"^(\*?)((?:U\.S\.|U\.K\.|Euro area|Developing Asia|Japan)[^:]{3,120}|Exchange rates?):\s*(.*)$")
LABEL_START = re.compile(r"^\*?(?:U\.S\.|U\.K\.|Euro area|Developing Asia|Japan)")
STATEMENT = re.compile(
    r"The\s+(\d{4}):Q([1-4])\s+values\s+of\s+variables\s+marked\s+with\s+an\s+asterisk\s+\(\*\)\s+are\s+(estimates|projected)",
    re.IGNORECASE,
)
# Definition-section names that differ from the table column header for the same variable.
# The report's definition names the Dow Jones index "(Float Cap)"; its tables label the
# column "Dow Jones Total Stock Market Index (Level)". Same position in the same list.
DEFINITION_ALIASES = {
    normalize_label("U.S. Dow Jones Total Stock Market (Float Cap) Index"): "dow_jones_total_stock_market_index",
}
FX_IDS = [v.variable_id for v in VARIABLES if "exchange rate" in v.display_name.lower()]


def clean(text: str) -> str:
    text = re.sub(r"(?<=[A-Za-z])-\s+(?=[a-z])", "", text)  # soft line-wrap hyphen
    return re.sub(r"\s+", " ", text).strip()


def pdf_entries(path: Path) -> tuple[list[tuple[bool, str, str]], dict]:
    text = subprocess.run(["pdftotext", str(path), "-"], capture_output=True, text=True, check=True).stdout
    m = STATEMENT.search(text)
    if not m:
        raise ValueError(f"{path}: no 'values of variables marked with an asterisk (*) are estimates/projected' statement")
    year, q, word = m.groups()
    statement = {"quarter": f"{year}Q{q}", "wording": word.lower(), "sentence": clean(text[m.start() : m.end() + 1])}
    start = m.start()
    entries: list[tuple[bool, str, str]] = []
    current: list | None = None
    lines = [ln.strip() for ln in text[start:].splitlines()]
    for i, stripped in enumerate(lines):
        if LABEL_START.match(stripped) and ":" not in stripped and i + 1 < len(lines) and not LABEL_START.match(lines[i + 1]) and re.match(r"^[^:]{1,60}:", lines[i + 1]):
            lines[i + 1] = f"{stripped} {lines[i + 1]}"  # label wrapped onto a second line
            continue
        label = LABEL.match(stripped)
        if label:
            current = [bool(label.group(1)), label.group(2), label.group(3)]
            entries.append(current)  # type: ignore[arg-type]
        elif not stripped:
            current = None
        elif current is not None:
            current[2] += " " + stripped
    return [(star, name, clean(body)) for star, name, body in entries], statement


def xlsx_entries(path: Path) -> list[tuple[bool, str, str]]:
    ws = openpyxl.load_workbook(path, data_only=True)["Data notes"]
    entries = []
    for row in ws.iter_rows(values_only=True):
        text = clean(" ".join(str(c) for c in row if c))
        m = LABEL.match(text)
        if m:
            entries.append((bool(m.group(1)), m.group(2), clean(m.group(3))))
    return entries


def read_vintage_definitions(vintage_id: str) -> tuple[list[dict], dict | None]:
    pdf = REPORTS_DIR / vintage_id / REPORT_FILENAME
    if vintage_id == "2013":
        xlsx = require_file(RAW_DIR / "2013" / "scenarios.xlsx")
        entries, statement, source = xlsx_entries(xlsx), None, "stress_test/2013/scenarios.xlsx:Data notes"
    else:
        entries, statement = pdf_entries(require_file(pdf))
        source = f"stress_test_reports/{vintage_id}/{REPORT_FILENAME}"
    definitions: list[dict] = []
    for star, label, body in entries:
        key = normalize_label(label)
        if key in ("exchangerates", "exchangerate"):
            ids = FX_IDS
        elif key in DEFINITION_ALIASES:
            ids = [DEFINITION_ALIASES[key]]
        else:
            ids = [variable_id_for(label)]
        for variable_id in ids:
            definitions.append({"variable_id": variable_id, "label": label, "definition": body, "estimate_marked": star, "source": source})
    seen = [d["variable_id"] for d in definitions]
    if len(seen) != len(set(seen)):
        raise ValueError(f"{vintage_id}: a variable is defined twice in the report: {sorted(v for v in set(seen) if seen.count(v) > 1)}")
    return definitions, statement
