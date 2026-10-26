"""Audit the scenario database against the Fed's own scenario REPORTS (PDF).

Purpose: a second, independent Fed source for the numbers. `audit_database.py` proves the
database equals the raw data files (htm/csv/xlsx); this script proves it also equals the
tables printed in the Fed's published scenario report for the same vintage (a different
file format of the same publication), and records any difference with its cause.

Required inputs:
  - the Fed report PDFs at `paths.REPORTS_DIR/<vintage>/scenarios_report.pdf`
    (downloaded and verified by `fetch_sources.py`)
  - the raw data files under `paths.RAW_DIR` (only to learn each table's column order)
  - the database at `paths.DB_PATH` (opened read-only)
  - the `pdftotext` command (poppler)

Outputs: stdout summary, `paths.AUDIT_DIR/report_audit.md` (table comparison) and
`paths.AUDIT_DIR/definition_audit.md` (the Fed's variable definitions per vintage, the
growth-versus-level check, and every place a variable's published definition changes). Exit status is non-zero if
any difference is unexplained.

Key assumptions:
  - A report table row is a quarter ("Q1 2000") followed by one number per column; columns
    are matched to variables by position using the column order of the same-width table in
    the vintage's raw files (2014 uses the 2015 order; both list the same 28 variables).
  - Reports print fewer decimals than the data files for some series (e.g. index levels as
    integers), so a report value agrees with the database when they differ by no more than
    half a unit of the report's last printed digit.
  - Rows from a combined history+projection table are history before the vintage's
    `horizon_start_quarter` and the table's scenario from that quarter on.
  - A growth variable is accepted as an annualized percent change when the Fed's own
    definition says so ("percent change ... annualized/at an annual rate"). A definition
    that is silent (international series in the 2013-2017 reports) is accepted only if its
    history for the overlapping quarters is the same series, on the same scale, as the
    nearest later vintage whose definition does say so (regression slope 0.5-1.5 and
    correlation above 0.8, i.e. far from the 0.25 a non-annualized quarterly series would
    show, while allowing for the data revisions between vintages).
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_database import (
    NUMBER,
    classify,
    decimals_of,
    norm,
    quarter_of,
    vintage_tables,
)
from paths import AUDIT_DIR, DB_PATH, RAW_DIR, REPORTS_DIR, require_dir, require_file
from variables import VARIABLES, variable_id_for

REPORT_FILENAME = "scenarios_report.pdf"
CAPTION = re.compile(r"^\s*Table\s+(\d+)\.?\s*([AB])\.?\s*(.*)$")
ROW = re.compile(r"^\s*(Q[1-4])\s+(\d(?:\s?\d){3})\*?\s+(\S.*)$")
FLOAT_TOLERANCE = 1e-9


def report_text(path: Path) -> str:
    return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=True).stdout


def next_quarter(q: str) -> str:
    year, n = int(q[:4]), int(q[5])
    return f"{year + n // 4}Q{n % 4 + 1}"


def report_tables(text: str) -> list[dict]:
    """Tables of the report: {tag, caption, kind, rows: [(quarter, [raw tokens])], skipped: [line]}."""
    tables: list[dict] = []
    current = None
    continuation = False
    for line in text.splitlines():
        m = CAPTION.match(line)
        if m:
            number, letter, rest = m.groups()
            tag = f"{number}{letter}"
            rest = norm(rest)
            if rest.startswith("\u2014") or "contin" in rest.lower()[:12]:
                # A continuation page is attached to the table it actually continues: the most
                # recent table of the same width whose last quarter directly precedes the
                # first row below. (The 2013 report mislabels some continuation captions.)
                current = None
                continuation = True
                continue
            if "supervisory" in rest.lower() or "historical" in rest.lower():
                current = {"tag": tag, "letter": letter, "caption": rest, "kind": classify(rest), "rows": [], "skipped": []}
                tables.append(current)
                continuation = False
            continue
        m = ROW.match(line)
        if m:
            q, y, rest = m.groups()
            tokens = [t.replace(",", "").replace("\u2212", "-") for t in rest.split()]
            if continuation and all(NUMBER.match(t) for t in tokens):
                quarter = quarter_of(f"{q} {y.replace(' ', '')}")
                current = next(
                    (t for t in reversed(tables) if t["rows"] and len(t["rows"][0][1]) == len(tokens) and next_quarter(t["rows"][-1][0]) == quarter),
                    None,
                )
                continuation = False
            if current is None:
                continue
            if all(NUMBER.match(t) for t in tokens):
                current["rows"].append((quarter_of(f"{q} {y.replace(' ', '')}"), tokens))
            else:
                current["skipped"].append(norm(line))
    return [t for t in tables if t["rows"]]


def vids_by_width(vintage: str) -> dict[int, list[str]]:
    """Column order (variable_ids) of the vintage's raw tables, keyed by column count."""
    widths: dict[int, list[str]] = {}
    tables = vintage_tables(RAW_DIR / vintage)
    # Scenario tables set the order; a separate history file (2013's historical.xlsx lists
    # the columns in a different order) is only used for widths no scenario table has.
    for group in ([t for t in tables if classify(*t["kind_texts"]) != "hist"], [t for t in tables if classify(*t["kind_texts"]) == "hist"]):
        seen: dict[int, list[str]] = {}
        for t in group:
            vids = [variable_id_for(h) for h in t["header"]]
            if seen.setdefault(len(vids), vids) != vids:
                raise ValueError(f"{vintage}: two raw tables of width {len(vids)} list different column orders")
        for width, vids in seen.items():
            widths.setdefault(width, vids)
    # A raw table that holds both scopes in one sheet (2013) is split the way the report
    # prints it: domestic columns, then international columns, in the table's own order.
    scope = {v.variable_id: v.scope for v in VARIABLES}
    for vids in list(widths.values()):
        for part in ("domestic", "international"):
            sub = [v for v in vids if scope[v] == part]
            if sub and len(sub) != len(vids):
                widths.setdefault(len(sub), sub)
    return widths


def audit_reports(con: duckdb.DuckDBPyConnection) -> tuple[list[str], list[str]]:
    horizon = {r[0]: r[1] for r in con.execute("SELECT vintage_id, horizon_start_quarter FROM scenario_vintages").fetchall()}
    db: dict[tuple, float] = {}
    for vid, var, q, val in con.execute("SELECT vintage_id, variable_id, quarter, value FROM actuals").fetchall():
        db[(vid, "hist", var, q)] = val
    for key, var, q, val in con.execute("SELECT scenario_key, variable_id, quarter, value FROM scenario_paths WHERE stat='value'").fetchall():
        vid, _, scen = key.partition("__")
        db[(vid, scen, var, q)] = val

    lines = ["# Report audit: database vs the Fed's scenario report PDFs", ""]
    problems: list[str] = []
    fallback_widths = vids_by_width("2015")
    summary = []
    for vintage in sorted(horizon):
        pdf = REPORTS_DIR / vintage / REPORT_FILENAME
        require_file(pdf)
        try:
            widths = vids_by_width(vintage)
        except (ValueError, KeyError):
            widths = {}
        widths = {**fallback_widths, **widths}
        tables = report_tables(report_text(pdf))
        agree = disagree = absent = 0
        unparsed = sum(len(t["skipped"]) for t in tables)
        kinds = Counter()
        for t in tables:
            width = len(t["rows"][0][1])
            if width not in widths or any(len(v) != width for _, v in t["rows"]):
                problems.append(f"{vintage} {t['tag']} {t['caption']}: rows are not {width} wide / no column order known")
                continue
            vids = widths[width]
            for q, tokens in t["rows"]:
                kind = t["kind"]
                if kind != "hist" and len(t["rows"]) > 20:
                    kind = "hist" if q < horizon[vintage] else t["kind"]
                kinds[kind] += 1
                for vid, tok in zip(vids, tokens, strict=True):
                    key = (vintage, kind, vid, q)
                    printed = float(tok)
                    if key not in db:
                        absent += 1
                        problems.append(f"{vintage}: report prints a value the database lacks: {key} = {tok} ({t['caption']})")
                        continue
                    if abs(db[key] - printed) <= 0.5 * 10 ** (-decimals_of(tok)) + FLOAT_TOLERANCE:
                        agree += 1
                    else:
                        disagree += 1
                        problems.append(f"{vintage}: database {db[key]!r} vs report {tok} for {key} ({t['caption']})")
        summary.append((vintage, len(tables), sum(kinds.values()), agree, disagree, absent, unparsed))
    lines += ["| vintage | tables | rows | cells agree | disagree | not in DB | unparsed lines |", "|---|---|---|---|---|---|---|"]
    lines += [f"| {v} | {nt} | {nr} | {a} | {d} | {ab} | {u} |" for v, nt, nr, a, d, ab, u in summary]
    lines += ["", "## Problems", ""] + ([f"- {p}" for p in problems] or ["- none"])
    return lines, problems


def audit_definitions(con: duckdb.DuckDBPyConnection) -> tuple[list[str], list[str]]:
    rows = con.execute(
        """SELECT d.vintage_id, d.variable_id, v.measure, d.definition
           FROM variable_definitions d JOIN variables v USING (variable_id)
           JOIN scenario_vintages sv USING (vintage_id) ORDER BY d.variable_id, sv.horizon_start_quarter"""
    ).fetchall()
    order = [r[0] for r in con.execute("SELECT vintage_id FROM scenario_vintages ORDER BY horizon_start_quarter").fetchall()]
    problems: list[str] = []
    lines = ["# Definition audit: the Fed's own wording for every variable and vintage", ""]
    explicit: dict[str, list[str]] = defaultdict(list)
    silent: list[tuple[str, str]] = []
    for vintage, var, measure, text in rows:
        low = text.lower()
        annualized = "percent change" in low and ("annualized" in low or "annual rate" in low)
        if measure == "level" and ("percent change" in low or "annualized" in low):
            problems.append(f"{vintage} {var}: classified level but the Fed's definition describes a change: {text[:120]}")
        if measure == "growth" and annualized:
            explicit[var].append(vintage)
        elif measure == "growth":
            silent.append((vintage, var))
    lines += ["## Growth variables: annualized percent change", ""]
    lines.append(f"- stated explicitly by the Fed: {sum(len(v) for v in explicit.values())} (vintage, variable) definitions")
    for vintage, var in silent:
        later = [v for v in explicit.get(var, []) if order.index(v) > order.index(vintage)]
        if not later:
            problems.append(f"{vintage} {var}: definition silent on annualization and no later explicit vintage to compare with")
            continue
        ref = later[0]
        pairs = con.execute(
            """SELECT a.value, b.value FROM actuals a JOIN actuals b ON a.variable_id = b.variable_id AND a.quarter = b.quarter
               WHERE a.vintage_id = ? AND b.vintage_id = ? AND a.variable_id = ?""", [vintage, ref, var]
        ).fetchall()
        n = len(pairs)
        mean_a, mean_b = sum(p[0] for p in pairs) / n, sum(p[1] for p in pairs) / n
        sxy = sum((a - mean_a) * (b - mean_b) for a, b in pairs)
        sxx = sum((b - mean_b) ** 2 for _, b in pairs)
        syy = sum((a - mean_a) ** 2 for a, _ in pairs)
        slope, corr = sxy / sxx, sxy / (sxx * syy) ** 0.5
        ok = 0.5 <= slope <= 1.5 and corr > 0.8
        lines.append(f"- {vintage} {var}: definition silent; vs {ref} (explicit) over {n} quarters slope {slope:.2f}, corr {corr:.3f} -> {'same annualized series' if ok else 'NOT the same scale'}")
        if not ok:
            problems.append(f"{vintage} {var}: history is not on the same scale as {ref}'s annualized series (slope {slope:.2f}, corr {corr:.3f})")
    lines += ["", "## Where a variable's published definition changes (text differs between consecutive vintages)", ""]
    runs: dict[str, list] = defaultdict(list)
    for vintage, var, _, text in rows:
        key = re.sub(r"[^a-z]", "", text.lower())
        if runs[var] and runs[var][-1][0] == key:
            runs[var][-1][1].append(vintage)
        else:
            runs[var].append([key, [vintage], text])
    for var, rr in sorted(runs.items()):
        if len(rr) > 1:
            lines.append(f"### {var}")
            lines += [f"- {vs[0]} to {vs[-1]}: {text[:230]}" for _, vs, text in rr]
            lines.append("")
    lines += ["## Problems", ""] + ([f"- {p}" for p in problems] or ["- none"])
    return lines, problems


def main() -> int:
    require_dir(REPORTS_DIR)
    require_dir(RAW_DIR)
    require_file(DB_PATH)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    for name, audit in (("report_audit.md", audit_reports), ("definition_audit.md", audit_definitions)):
        lines, problems = audit(con)
        (AUDIT_DIR / name).write_text("\n".join(lines) + "\n")
        print(f"{name}: {len(problems)} problems")
        for p in problems[:10]:
            print("  -", p)
        total += len(problems)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
