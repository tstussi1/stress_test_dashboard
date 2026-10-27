"""Independent, read-only audit of the stress-test scenario database against the Fed's raw files.

Purpose: prove (or disprove) that every number in `stress_test_scenarios.duckdb` is the
number the Federal Reserve published. This script re-reads every raw file with its OWN
extraction code (lxml/csv/openpyxl/pdftotext reading raw cell strings) and never imports
`parser.py`, so a parsing bug cannot hide behind the same bug in an "audit". It only
reuses `variables.variable_id_for()` to turn a published column label into a
`variable_id`; that dictionary is audited separately against the Fed's own variable
definitions (see `audit_reports.py`).

Required inputs:
  - the raw Fed files under `paths.RAW_DIR` (one sub-folder per vintage: xlsx/htm/csv/pdf)
  - the database at `paths.DB_PATH` (opened read-only)
  - the `pdftotext` command (poppler) for the 2014 PDF and the 2011-2012 CCAR appendix PDFs
  - for the 2012 cross-check, `paths.REPORTS_DIR/2012/methodology_appendix_a.pdf`

Outputs: a summary on stdout, `paths.AUDIT_DIR/cell_audit.md` (counts and every exception
of the raw-file comparison), `paths.AUDIT_DIR/anomaly_register.md` (every history value
that differs strongly between vintages, classified) and `paths.AUDIT_DIR/derived_audit.md`
(the two calculation views re-derived independently in pandas). Exit status is non-zero if the
database differs from the raw files.

Key assumptions:
  - A "fact" is (vintage, history-or-scenario, variable, quarter) and its value as the Fed
    printed it. A fact printed by several Fed files must agree within the rounding of the
    coarser file; the database must hold exactly one of the printed values, the most
    precise one, bit-for-bit (within 1e-9, the decimal-to-binary float tolerance).
  - Cells that are not numbers ("n.a.", blank, dashes) are unpublished: they must be
    absent from the database and are counted, never imputed.
  - In files that hold history and projection in one table (2013-2016) the first quarter
    where the baseline and severely adverse tables differ is the first projected quarter
    (history is identical across scenarios); it is derived from the data, not from the
    parser's "last 13 rows" rule, and compared with it.
  - Derived values: the cumulated level index of a growth variable is
    100 * prod over quarters of (1 + g/100)^(1/4) (g is an annualized percent change, so
    one quarter compounds by the fourth root; base 100 at the quarter before the
    horizon), and the deviation is scenario minus the same vintage's baseline. Both are
    recomputed here without SQL and must equal the database views to 1e-9.
  - Cross-vintage screen: a (variable, quarter) value from one vintage is flagged when it
    differs from the median of all vintages that report that quarter by more than 3 pp
    (growth variables), 0.5 pp (rates in percent) or 5% (index levels). Classes: (b) the
    Fed marks that value as an estimate (`estimate_flags`); (c) one vintage disagrees with
    all others while the others agree tightly; (a) otherwise a revision (the other
    vintages also move). Parsing errors (d) are excluded by the cell audit above. Nothing
    is changed in the database for any class: the Fed's number is kept as published.
  - 2011-2012 CCAR appendix PDFs are re-read with poppler (`pdftotext -bbox-layout`), a different
    PDF library from the parser's. Their tables state the last historical quarter; rows up to it
    are history. Tables with identical printed history share column identities (the baseline
    tables' text layer is damaged, see `parser.column_header`); the audit verifies the identity
    of the history itself. The 2011 levels are converted with the annualized percent change
    ((L_t / L_{t-1})^4 - 1) * 100, recomputed here from the printed digits. The 2012 stress
    tables must equal the March 2012 paper's Appendix A cell for cell, and the 2011 stress path
    must reproduce the Fed's own summary table (Q4/Q4 changes, within rounding).
  - Exploratory conditions A and B (2024) share one published international file, so those
    international facts are expected under both scenario names (Fed's own structure).
"""

from __future__ import annotations

import csv
import itertools
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import duckdb
import openpyxl
import pymupdf
from lxml import etree, html

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import AUDIT_DIR, DB_PATH, RAW_DIR, require_dir, require_file
from variables import resolve_label

QUARTER_CELL = re.compile(r"^(?:Q([1-4])\s*[,:]?\s*(\d{4})|(\d{4})\s*Q([1-4]))$")
NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")
FLOAT_TOLERANCE = 1e-9  # decimal string -> binary double
COMBINED_ROWS = 20  # more rows than any horizon: history and projection in one table
DERIVED_DECIMALS = (
    6  # a calculated value has no printed decimals; held to a tight tolerance
)
HORIZON_QUARTERS = 13  # every published horizon through 2026


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).replace("\xa0", " ")).strip()


def quarter_of(text: object) -> str | None:
    m = QUARTER_CELL.match(norm(text))
    if not m:
        return None
    return f"{m.group(2)}Q{m.group(1)}" if m.group(1) else f"{m.group(3)}Q{m.group(4)}"


def raw_string(cell: object) -> str:
    """The cell as printed; spreadsheet floats use their shortest exact repr."""
    if isinstance(cell, float):
        return repr(cell)
    return norm("" if cell is None else cell).replace("\u2212", "-").replace(",", "")


def classify(*texts: str) -> str:
    """'hist', a scenario name, or raise. Priority: file/caption text in the order given."""
    for text in texts:
        t = norm(text).lower().replace("_", " ")
        if not t:
            continue
        if "historic" in t:
            return "hist"
        if "severely adverse" in t or "supervisory stress scenario" in t:
            return "severely_adverse"
        if "alternative severe" in t:
            return "alternative_severe"
        if re.search(r"\badverse\b", t):
            return "adverse"
        if "baseline" in t:
            return "baseline"
        if "exploratory" in t:
            if re.search(r"exploratory a\b", t):
                return "exploratory_a"
            if re.search(r"exploratory b\b", t):
                return "exploratory_b"
            return "exploratory"
    raise ValueError(f"cannot classify table from {texts!r}")


# ---------------------------------------------------------------------------
# Raw extraction: each reader returns tables {file, caption, kind, header, rows}
# rows = [(quarter, [raw strings])]; header = published column labels.
# ---------------------------------------------------------------------------


def read_xlsx(path: Path) -> list[dict]:
    wb = openpyxl.load_workbook(path, data_only=True)
    tables = []
    for ws in wb.worksheets:
        grid = [list(r) for r in ws.iter_rows(values_only=True)]
        idx = [
            i
            for i, r in enumerate(grid)
            if r and quarter_of(r[0]) and isinstance(r[0], str)
        ]
        if not idx:
            continue
        if idx != list(range(idx[0], idx[0] + len(idx))):
            raise ValueError(f"{path}:{ws.title}: quarter rows are not contiguous")
        positions = [
            (j, norm(c))
            for j, c in enumerate(grid[idx[0] - 1])
            if j >= 1 and c not in (None, "")
        ]
        header = [label for _, label in positions]
        rows = [
            (quarter_of(grid[i][0]), [raw_string(grid[i][j]) for j, _ in positions])
            for i in idx
        ]
        tables.append(
            {
                "file": path,
                "caption": f"{path.name}:{ws.title}",
                "kind_texts": (ws.title, path.stem),
                "header": header,
                "rows": rows,
            }
        )
    return tables


def first_cell_text(tr) -> str:
    cells = tr.xpath("./th|./td")
    return "".join(cells[0].itertext()) if cells else ""


def read_htm(path: Path) -> list[dict]:
    root = html.parse(str(path)).getroot()
    tables = []
    for tb in root.xpath("//table"):
        trs = tb.xpath(".//tr")
        first_data = next(
            (i for i, tr in enumerate(trs) if quarter_of(first_cell_text(tr))), None
        )
        if first_data is None or first_data == 0:
            continue
        data_cells = trs[first_data].xpath("./th|./td")
        ncols = sum(int(c.get("colspan", 1)) for c in data_cells)
        grid = [[None] * ncols for _ in range(first_data)]
        for r, tr in enumerate(trs[:first_data]):
            c = 0
            for cell in tr.xpath("./th|./td"):
                while c < ncols and grid[r][c] is not None:
                    c += 1
                text = norm("".join(cell.itertext()))
                for dr in range(int(cell.get("rowspan", 1))):
                    for dc in range(int(cell.get("colspan", 1))):
                        if r + dr < first_data and c + dc < ncols:
                            grid[r + dr][c + dc] = text
                c += int(cell.get("colspan", 1))
        labels = []
        for c in range(1, ncols):
            parts = [grid[r][c] for r in range(first_data) if grid[r][c]]
            labels.append(parts[-1])
        rows = []
        for tr in trs[first_data:]:
            cells = [raw_string("".join(c.itertext())) for c in tr.xpath("./th|./td")]
            q = quarter_of(cells[0]) if cells else None
            if q is None:
                continue
            if len(cells) != ncols:
                raise ValueError(
                    f"{path}: row {cells[0]} has {len(cells)} cells, expected {ncols}"
                )
            rows.append((q, cells[1:]))
        caption = norm(tb.get("title") or tb.get("summary") or "")
        tables.append(
            {
                "file": path,
                "caption": caption,
                "kind_texts": (caption, path.stem),
                "header": labels,
                "rows": rows,
            }
        )
    return tables


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        lines = list(csv.reader(fh))
    header, body = lines[0], [r for r in lines[1:] if any(c.strip() for c in r)]
    has_scenario = norm(header[0]).lower() == "scenario name"
    date_col = 1 if has_scenario else 0
    labels = [norm(h) for h in header[date_col + 1 :]]
    rows = []
    for r in body:
        q = quarter_of(r[date_col])
        if q is None:
            raise ValueError(f"{path}: unreadable date cell {r[date_col]!r}")
        rows.append(
            (q, [raw_string(c) for c in r[date_col + 1 : date_col + 1 + len(labels)]])
        )
    return [
        {
            "file": path,
            "caption": path.stem,
            "kind_texts": (path.stem,),
            "header": labels,
            "rows": rows,
        }
    ]


def read_pdf_2014(path: Path, header_by_width: dict[int, list[str]]) -> list[dict]:
    """Layout text of the 2014 narrative PDF. Column labels wrap over many lines in this
    layout, so columns are assigned by position from the same-scope table of the 2015
    publication (independent source with explicit one-line headers) and cross-checked
    against the database's own mapping by the value comparison itself."""
    text = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    tables: dict[str, dict] = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"^\s*Table (\d[AB])\.\s*(.*)$", line)
        if m:
            tag, rest = m.groups()
            if rest.startswith("\u2014continued"):
                current = tables[tag]
            else:
                current = {
                    "file": path,
                    "caption": f"Table {tag}. {norm(rest)}",
                    "kind_texts": (norm(rest), path.stem),
                    "header": None,
                    "rows": [],
                }
                tables[tag] = current
            continue
        if current is None:
            continue
        m = re.match(r"^\s*(Q[1-4] \d{4})\s+(-?[\d.,\s-]+)$", line)
        if m:
            vals = m.group(2).split()
            current["rows"].append(
                (quarter_of(m.group(1)), [raw_string(v) for v in vals])
            )
    for t in tables.values():
        width = len(t["rows"][0][1])
        if any(len(v) != width for _, v in t["rows"]):
            raise ValueError(f"{path}: {t['caption']} has rows of unequal width")
        t["header"] = header_by_width[width]
    return list(tables.values())


APPENDIX_TITLE = re.compile(r"Supervisory (Baseline|Stress) Scenario")
APPENDIX_ROW = re.compile(r"^Q\s*([1-4])\s*(\d\s*\d\s*\d\s*\d)\s+(\S.*)$")
LAST_HISTORICAL = re.compile(r"data\s+through\s+(\d{4})\s*:\s*Q\s*([1-4])")
MIN_APPENDIX_ROWS = 13


def read_pdf_appendix(path: Path, require_statement: bool = True) -> list[dict]:
    """2011-2012 CCAR appendix tables via poppler's bbox output (words and lines in display
    coordinates). A table is a page titled 'Supervisory Baseline/Stress Scenario' with at least
    13 rows starting with a quarter; every row must be as wide as the first."""
    xml = subprocess.run(
        ["pdftotext", "-bbox-layout", str(path), "-"], capture_output=True, check=True
    ).stdout
    root = etree.fromstring(xml, etree.HTMLParser(encoding="utf-8"))
    tables: list[dict] = []
    for page_no, page in enumerate(root.iter("page"), start=1):
        words = sorted(
            (
                (
                    float(w.get("xmin")),
                    float(w.get("ymin")),
                    float(w.get("xmax")),
                    float(w.get("ymax")),
                    (w.text or "").strip(),
                )
                for w in page.iter("word")
            ),
            key=lambda w: (w[1], w[0]),
        )
        rows_by_y: list[list[tuple]] = []
        for w in words:
            if rows_by_y and abs(w[1] - rows_by_y[-1][0][1]) <= 3.0:
                rows_by_y[-1].append(w)
            else:
                rows_by_y.append([w])
        data = []
        for ln in rows_by_y:
            ln.sort()
            m = APPENDIX_ROW.match(" ".join(w[4] for w in ln))
            if m and len(m.group(3).split()) >= 5:
                data.append((ln, m))
        text = " ".join(w[4] for w in words)
        title = APPENDIX_TITLE.search(text)
        if len(data) < MIN_APPENDIX_ROWS or not title:
            continue
        n = len(data[0][1].group(3).split())
        value_words, date_words = data[0][0][-n:], data[0][0][:-n]
        centers = [(w[0] + w[2]) / 2 for w in value_words]
        date_right = max(w[2] for w in date_words)
        title_bottom = next(w[3] for w in words if w[4] == "Scenario")
        row_center_y = sum((w[1] + w[3]) / 2 for w in data[0][0]) / len(data[0][0])
        # Header cells are the text lines of the page as the PDF library groups them (poppler merges
        # neighbouring header cells into one line, so these come from pymupdf, used here only for
        # the header; every number and the dates come from poppler above).
        pm_page = pymupdf.open(path)[page_no - 1]
        cells: list[list[tuple]] = [[] for _ in range(n)]
        for block in pm_page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                r = pymupdf.Rect(line["bbox"]) * pm_page.rotation_matrix
                text_ = "".join(span["text"] for span in line["spans"]).strip()
                cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
                if text_ and title_bottom < cy < row_center_y - 3 and cx > date_right:
                    j = min(range(n), key=lambda i: abs(centers[i] - cx))
                    cells[j].append((round(r.y0), r.x0, text_))
        rows = []
        for ln, m in data:
            vals = m.group(3).split()
            if len(vals) != n:
                raise ValueError(
                    f"{path} page {page_no}: row Q{m.group(1)} {m.group(2)} has {len(vals)} values, expected {n}"
                )
            rows.append((f"{m.group(2).replace(' ', '')}Q{m.group(1)}", [raw_string(v) for v in vals]))
        last = LAST_HISTORICAL.search(text)
        if require_statement and not last:
            raise ValueError(
                f"{path} page {page_no}: no statement of the last historical quarter"
            )
        tables.append(
            {
                "file": path,
                "caption": title.group(0),
                "kind_texts": (title.group(0), path.stem),
                "header": [" ".join(t for _, _, t in sorted(c)) for c in cells],
                "rows": rows,
                "last_hist": f"{last.group(1)}Q{last.group(2)}" if last else None,
            }
        )
    return tables


def assign_appendix_columns(tables: list[dict]) -> None:
    """Appendix tables whose printed history is identical (same scope, any scenario or Fed
    document of the vintage) have the same columns; the first such table names them. The
    audit checks the history itself, so it does not rely on a damaged text layer (the 2012
    baseline tables and the March 2012 paper have damaged headers)."""
    stated = [t for t in tables if t.get("last_hist")]
    for t in stated:
        hist = [r for r in t["rows"] if r[0] <= t["last_hist"]]
        donors = [
            d
            for d in stated
            if [r for r in d["rows"] if r[0] <= d["last_hist"]] == hist
        ]
        if not donors or len(donors[0]["header"]) != len(t["header"]):
            raise ValueError(
                f"{t['file']}: no same-width table with identical printed history"
            )
        t["column_source"] = donors[0]
    for t in stated:
        t["header"] = t["column_source"]["header"]


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------


def decimals_of(s: str) -> int:
    return len(s.split(".")[1]) if "." in s else 0


def vintage_tables(vdir: Path) -> list[dict]:
    tables = []
    for f in sorted(vdir.iterdir()):
        if f.suffix == ".xlsx":
            tables += read_xlsx(f)
        elif f.suffix == ".htm":
            tables += read_htm(f)
        elif f.suffix == ".csv":
            tables += read_csv(f)
    return tables


def first_divergence(tables: list[dict]) -> str:
    """First quarter where the baseline and severely adverse tables of the same scope differ."""
    by_scope: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for t in tables:
        if t["kind"] in ("baseline", "severely_adverse"):
            by_scope[tuple(t["vids"])][t["kind"]] = t
    firsts = set()
    for pair in by_scope.values():
        base, sev = pair["baseline"], pair["severely_adverse"]
        diff = [
            qb
            for (qb, vb), (qs, vs) in zip(base["rows"], sev["rows"], strict=True)
            if qb != qs or vb != vs
        ]
        if not diff:
            raise ValueError("baseline and severely adverse tables never differ")
        firsts.add(diff[0])
    if len(firsts) != 1:
        raise ValueError(f"scopes disagree about the first projected quarter: {firsts}")
    return firsts.pop()


def build_facts(vintages: list[str]) -> tuple[dict, Counter, dict, dict]:
    """facts[(vintage, kind, variable_id, quarter)] = [(float, decimals, source)]; also the
    per-file unpublished-cell counter and the derived horizon start per combined vintage."""
    facts: dict[tuple, list] = defaultdict(list)
    unpublished: Counter = Counter()
    blanks: dict[tuple, list] = defaultdict(list)
    derived_start: dict[str, str] = {}
    header_2015 = {}
    for v in sorted(vintages):
        vdir = RAW_DIR / v
        tables = vintage_tables(vdir)
        for f in sorted(vdir.glob("*.pdf")):
            tables += read_pdf_appendix(f)
            if not header_2015:
                for t in vintage_tables(RAW_DIR / "2015"):
                    if t["caption"].startswith("Table 1"):
                        header_2015[len(t["header"])] = t["header"]
            tables += read_pdf_2014(f, header_2015)
        assign_appendix_columns(tables)
        for t in tables:
            t["kind"] = classify(*t["kind_texts"])
            resolved = [resolve_label(label, v) for label in t["header"]]
            t["vids"] = [vid for vid, _ in resolved]
            t["rules"] = [rule for _, rule in resolved]
            if len(set(t["vids"])) != len(t["vids"]):
                raise ValueError(f"{t['caption']}: two columns map to one variable_id")
        combined = [
            t for t in tables if t["kind"] != "hist" and len(t["rows"]) > COMBINED_ROWS
        ]
        if combined:
            derived_start[v] = first_divergence(combined)
        for t in tables:
            src = f"{t['file'].relative_to(RAW_DIR.parent)}:{t['caption']}"
            printed = dict(t["rows"])
            if (
                t.get("last_hist")
                and len(t["rows"]) > COMBINED_ROWS
                and t["last_hist"] >= derived_start[v]
            ):
                raise ValueError(
                    f"{src}: stated last historical quarter {t['last_hist']} is not before the data-derived horizon start {derived_start[v]}"
                )
            for q, raws in t["rows"]:
                kinds = [t["kind"]]
                if t["kind"] == "hist":
                    pass
                elif t.get("last_hist"):
                    kinds = ["hist" if q <= t["last_hist"] else t["kind"]]
                elif len(t["rows"]) > COMBINED_ROWS:
                    kinds = ["hist" if q < derived_start[v] else t["kind"]]
                elif t["kind"] == "exploratory":
                    kinds = (
                        ["exploratory_a", "exploratory_b"]
                        if (RAW_DIR / v / "exploratory_a_domestic.csv").exists()
                        else ["exploratory"]
                    )
                for j, (vid, raw) in enumerate(zip(t["vids"], raws, strict=True)):
                    if not NUMBER.match(raw):
                        unpublished[(v, t["file"].name, raw)] += 1
                        blanks[(v, t["file"].name, vid)].append(q)
                        continue
                    value, decimals = float(raw), decimals_of(raw)
                    if t[
                        "rules"
                    ][
                        j
                    ]:  # printed level -> annualized percent change from the previous quarter's level
                        prior = printed.get(prev_quarter(q))
                        if prior is None:
                            if kinds == ["hist"]:
                                continue  # growth of the first printed quarter is not published
                            raise ValueError(
                                f"{src} {q}: no prior-quarter level for derived {vid}"
                            )
                        value, decimals = (
                            ((float(raw) / float(prior[j])) ** 4 - 1) * 100,
                            DERIVED_DECIMALS,
                        )
                    for kind in kinds:
                        facts[(v, kind, vid, q)].append((value, decimals, src))
    return facts, unpublished, derived_start, blanks


# The Fed's own summary of the 2011 supervisory stress scenario (CCAR 2011 overview, Table 1):
# year-end unemployment, and four-quarter (Q4/Q4) percent changes of real GDP, house prices and
# equity prices, printed to one decimal. Used as independent evidence for the appendix table.
FED_SUMMARY_2011 = (
    ("unemployment_rate", "level_q4", 2011, 11.0),
    ("unemployment_rate", "level_q4", 2012, 10.6),
    ("unemployment_rate", "level_q4", 2013, 9.6),
    ("real_gdp_growth", "growth_q4q4", 2011, -1.5),
    ("real_gdp_growth", "growth_q4q4", 2012, 2.4),
    ("real_gdp_growth", "growth_q4q4", 2013, 3.4),
    ("house_price_index", "level_q4q4", 2011, -6.2),
    ("house_price_index", "level_q4q4", 2012, -4.1),
    ("house_price_index", "level_q4q4", 2013, 2.7),
    ("dow_jones_total_stock_market_index", "level_q4q4", 2011, -27.8),
    ("dow_jones_total_stock_market_index", "level_q4q4", 2012, 36.9),
    ("dow_jones_total_stock_market_index", "level_q4q4", 2013, 15.9),
)
SUMMARY_VINTAGE = "2011"
SUMMARY_SCENARIO = "severely_adverse"


def audit_fed_summary(con: duckdb.DuckDBPyConnection) -> tuple[list[str], list[str]]:
    """Does the stored 2011 stress path reproduce the Fed's own summary numbers (Table 1)?
    Tolerance: half a unit of the printed decimal plus the rounding of the printed levels."""
    key = f"{SUMMARY_VINTAGE}__{SUMMARY_SCENARIO}"
    path = {(v, q): x for v, q, x in con.execute("SELECT variable_id, quarter, value FROM scenario_paths WHERE scenario_key = ?", [key]).fetchall()}
    bound = dict(con.execute("SELECT variable_id, rounding_bound_pp FROM derived_series WHERE vintage_id = ?", [SUMMARY_VINTAGE]).fetchall())
    lines, problems = [], []
    for var, kind, year, printed in FED_SUMMARY_2011:
        if kind == "level_q4":
            value, tol = path[(var, f"{year}Q4")], 0.05
        elif kind == "growth_q4q4":
            ratio = 1.0
            for n in (1, 2, 3, 4):
                ratio *= (1 + path[(var, f"{year}Q{n}")] / 100) ** 0.25
            value, tol = (ratio - 1) * 100, 0.05 + bound[var]
        else:
            end, start = path[(var, f"{year}Q4")], path[(var, f"{year - 1}Q4")]
            value, tol = (end / start - 1) * 100, 0.05 + 100 * 0.5 * (1 / end + 1 / start) * end / start
        ok = abs(value - printed) <= tol
        lines.append(f"- {var} {kind} {year}: database {value:.3f}, Fed Table 1 {printed} (tolerance {tol:.3f}) -> {'ok' if ok else 'DIFFERS'}")
        if not ok:
            problems.append(f"{key} {var} {kind} {year}: {value:.3f} vs the Fed's printed {printed}")
    return lines, problems


def audit_cells(con: duckdb.DuckDBPyConnection) -> tuple[list[str], list[str]]:
    vintages = [
        r[0]
        for r in con.execute(
            "SELECT vintage_id FROM scenario_vintages ORDER BY 1"
        ).fetchall()
    ]
    disk = sorted(p.name for p in RAW_DIR.iterdir() if p.is_dir())
    problems: list[str] = []
    if disk != vintages:
        problems.append(
            f"raw vintage folders {disk} differ from database vintages {vintages}"
        )
    facts, unpublished, derived_start, blanks = build_facts(disk)

    db: dict[tuple, float] = {}
    for vid, var, q, val in con.execute(
        "SELECT vintage_id, variable_id, quarter, value FROM actuals"
    ).fetchall():
        db[(vid, "hist", var, q)] = val
    for key, var, q, val in con.execute(
        "SELECT scenario_key, variable_id, quarter, value FROM scenario_paths WHERE stat='value'"
    ).fetchall():
        vid, _, scen = key.partition("__")
        db[(vid, scen, var, q)] = val

    missing = [k for k in facts if k not in db]
    extra = [k for k in db if k not in facts]
    for kind, keys in (
        ("MISSING from database", missing),
        ("EXTRA in database (not in raw files)", extra),
    ):
        for k in keys[:50]:
            problems.append(f"{kind}: {k}")
        if len(keys) > 50:
            problems.append(f"{kind}: ... {len(keys) - 50} more")

    exact_bits = near_only = 0
    for key, obs in facts.items():
        if key not in db:
            continue
        value = db[key]
        best = max(obs, key=lambda o: o[1])
        if abs(value - best[0]) > FLOAT_TOLERANCE * max(1.0, abs(best[0])):
            problems.append(
                f"VALUE differs from most precise printed value: {key} db={value!r} printed={best[0]!r} ({best[2]})"
            )
            continue
        if value == best[0]:
            exact_bits += 1
        else:
            near_only += 1
        for o in obs:
            if abs(value - o[0]) > 0.5 * 10 ** (-o[1]) + FLOAT_TOLERANCE:
                problems.append(
                    f"INCONSISTENT printed values: {key} db={value!r} vs {o[0]!r} ({o[2]})"
                )

    horizon = {
        r[0]: r[1]
        for r in con.execute(
            "SELECT vintage_id, horizon_start_quarter FROM scenario_vintages"
        ).fetchall()
    }
    for v, q in derived_start.items():
        if horizon[v] != q:
            problems.append(
                f"HORIZON start for {v}: data-derived {q} vs database {horizon[v]}"
            )

    multi = [obs for obs in facts.values() if len(obs) > 1]
    differing = sum(1 for obs in multi if len({o[0] for o in obs}) > 1)
    summary_lines, summary_problems = audit_fed_summary(con)
    problems += summary_problems
    lines = [
        "# Cell audit: database vs raw Fed files",
        "",
        f"- facts printed in raw files: {len(facts):,}",
        f"- facts printed by more than one Fed file: {len(multi):,}; of those, printed digits differ (within the coarser file's rounding, checked below): {differing:,}",
        f"- rows in database (actuals + scenario_paths): {len(db):,}",
        f"- missing from database: {len(missing)}; extra in database: {len(extra)}",
        f"- value matches most precise printed value bit-for-bit: {exact_bits:,}; equal within {FLOAT_TOLERANCE:g} only: {near_only:,}",
        f"- first projected quarter derived from data (combined-table vintages): {derived_start}",
        "",
        "## Unpublished (non-numeric) cells by file",
        "",
    ]
    by_file: dict[tuple, int] = defaultdict(int)
    for (v, fname, raw), n in unpublished.items():
        by_file[(v, fname, raw)] += n
    lines += [
        f"- {v}/{fname}: {raw!r} x {n}"
        for (v, fname, raw), n in sorted(by_file.items())
    ] or ["- none"]
    lines += ["", "Unpublished cells by variable (first-last quarter, count):", ""]
    lines += [
        f"- {v}/{fname} {vid}: {min(qs)}-{max(qs)} ({len(qs)})"
        for (v, fname, vid), qs in sorted(blanks.items())
    ]
    lines += ["", "## The Fed's own 2011 summary table (Table 1) vs the stored stress path", ""] + summary_lines
    lines += ["", "## Problems", ""] + ([f"- {p}" for p in problems] or ["- none"])
    return lines, problems


def audit_consistency(con: duckdb.DuckDBPyConnection) -> tuple[list[str], list[str]]:
    rows = con.execute(
        """
        WITH t AS (
            SELECT a.variable_id, a.quarter, a.vintage_id, a.value, v.measure, v.unit,
                   MEDIAN(a.value) OVER (PARTITION BY a.variable_id, a.quarter) AS med,
                   COUNT(*) OVER (PARTITION BY a.variable_id, a.quarter) AS k,
                   sv.horizon_start_quarter AS vorder
            FROM actuals a JOIN variables v USING (variable_id) JOIN scenario_vintages sv USING (vintage_id))
        SELECT t.variable_id, t.quarter, t.vintage_id, t.value, t.med, t.k, (f.vintage_id IS NOT NULL) AS est, t.vorder
        FROM t LEFT JOIN estimate_flags f
          ON f.vintage_id = t.vintage_id AND f.variable_id = t.variable_id AND f.quarter = t.quarter
        WHERE t.k >= 2 AND ABS(t.value - t.med) >
              CASE WHEN t.measure = 'growth' THEN 3.0 WHEN t.unit = 'percent' THEN 0.5 ELSE 0.05 * ABS(t.med) END
        ORDER BY t.variable_id, t.quarter, t.vorder
        """
    ).fetchall()
    others = {}
    for var, q, vid, val, med, k, est, _ in rows:
        vals = [
            r[0]
            for r in con.execute(
                "SELECT value FROM actuals WHERE variable_id = ? AND quarter = ? AND vintage_id != ?",
                [var, q, vid],
            ).fetchall()
        ]
        others[(var, q, vid)] = vals
    classes: dict[str, list] = {"a": [], "b": [], "c": []}
    for var, q, vid, val, med, k, est, _ in rows:
        vals = others[(var, q, vid)]
        tight = len(vals) >= 4 and max(vals) - min(vals) <= 0.02 * max(1.0, abs(med))
        cls = "b" if est else "c" if tight else "a"
        classes[cls].append(
            f"- {var} {q} in {vid}: {val:g} (median of vintages {med:g}; {k} vintages report it)"
        )
    names = {
        "b": "(b) Fed-marked estimate in that vintage, later superseded",
        "c": "(c) one vintage disagrees with all the others, which agree tightly",
        "a": "(a) successive revisions: other vintages also move",
    }
    lines = [
        "# Cross-vintage anomaly register",
        "",
        f"Flagged values: {len(rows)} of {con.execute('SELECT COUNT(*) FROM actuals').fetchone()[0]:,} history values.",
        "The database keeps the Fed's number exactly as published in every case; these are documented data notes.",
        "",
    ]
    for key in ("b", "c", "a"):
        lines += (
            [f"## {names[key]} ({len(classes[key])})", ""]
            + (classes[key] or ["- none"])
            + [""]
        )
    return lines, []


def audit_derived(con: duckdb.DuckDBPyConnection) -> tuple[list[str], list[str]]:
    paths = con.execute(
        "SELECT scenario_key, variable_id, quarter, value FROM scenario_paths WHERE stat = 'value'"
    ).df()
    growth = {
        r[0]
        for r in con.execute(
            "SELECT variable_id FROM variables WHERE measure = 'growth'"
        ).fetchall()
    }
    problems: list[str] = []

    g = (
        paths[paths["variable_id"].isin(growth)]
        .sort_values(["scenario_key", "variable_id", "quarter"])
        .copy()
    )
    g["factor"] = (1 + g["value"] / 100.0) ** 0.25
    g["level"] = 100.0 * g.groupby(["scenario_key", "variable_id"])["factor"].cumprod()
    view = con.execute(
        "SELECT scenario_key, variable_id, quarter, level_index FROM scenario_paths_level"
    ).df()
    merged = g.merge(
        view, on=["scenario_key", "variable_id", "quarter"], how="outer", indicator=True
    )
    if (merged["_merge"] != "both").any():
        problems.append(
            f"level view and independent level differ in row set: {merged['_merge'].value_counts().to_dict()}"
        )
    level_gap = (merged["level"] - merged["level_index"]).abs().max()
    if not level_gap <= 1e-9:
        problems.append(
            f"level index differs from the independent calculation by up to {level_gap}"
        )

    base = paths[paths["scenario_key"].str.endswith("__baseline")].copy()
    base["vintage"] = base["scenario_key"].str.split("__").str[0]
    dev = paths.copy()
    dev["vintage"] = dev["scenario_key"].str.split("__").str[0]
    dev = dev.merge(
        base[["vintage", "variable_id", "quarter", "value"]].rename(
            columns={"value": "base"}
        ),
        on=["vintage", "variable_id", "quarter"],
        how="left",
    )
    # A vintage that published no baseline at all (CCAR 2011) has no deviation by construction;
    # in a vintage that has one, every scenario value must have its baseline value.
    with_baseline = set(base["vintage"])
    dev = dev[dev["vintage"].isin(with_baseline)].copy()
    if dev["base"].isna().any():
        problems.append("a scenario value has no baseline value in its own vintage")
    dev["deviation"] = dev["value"] - dev["base"]
    dview = con.execute(
        "SELECT scenario_key, variable_id, quarter, deviation FROM scenario_vs_baseline"
    ).df()
    dm = dev.merge(
        dview,
        on=["scenario_key", "variable_id", "quarter"],
        how="outer",
        indicator=True,
        suffixes=("", "_view"),
    )
    if (dm["_merge"] != "both").any():
        problems.append(
            f"deviation view and independent deviation differ in row set: {dm['_merge'].value_counts().to_dict()}"
        )
    dev_gap = (dm["deviation"] - dm["deviation_view"]).abs().max()
    if not dev_gap <= 1e-9:
        problems.append(
            f"deviation differs from the independent calculation by up to {dev_gap}"
        )
    own = (
        dm[dm["scenario_key"].str.endswith("__baseline")]["deviation_view"].abs().max()
    )
    if own != 0:
        problems.append(f"a baseline deviates from itself by {own}")

    # Quarters of each series are consecutive (so the cumulation order is the calendar order).
    for key, grp in paths.groupby("scenario_key"):
        qs = sorted(grp["quarter"].unique())
        if any(b != next_quarter(a) for a, b in itertools.pairwise(qs)):
            problems.append(f"{key}: quarters are not consecutive: {qs}")

    # Rounding bound: the Fed rounds growth to (usually) 0.1 pp; one quarter's compounding step
    # then moves by at most 0.25 * 0.0005 / (1 + g/100) in log terms; summed over the horizon.
    g["step_bound"] = 0.25 * 0.0005 / (1 + g["value"] / 100.0)
    bound = (
        g.groupby(["scenario_key", "variable_id"])["step_bound"]
        .sum()
        .apply(lambda x: 100 * (2.718281828459045**x - 1))
    ).max()
    lines = [
        "# Derived-value audit",
        "",
        f"- cumulated level: {len(merged):,} rows; max |independent - view| = {level_gap:.2e}",
        f"- deviation from baseline: {len(dm):,} rows; max |independent - view| = {dev_gap:.2e}; baseline vs itself = {own}",
        "- convention: level = 100 * prod (1 + g/100)^(1/4), base 100 at the quarter before the horizon; deviation = scenario - same-vintage baseline (none for a vintage without a baseline)",
        f"- worst-case rounding bound of a 13-quarter cumulated level if every published rate is off by 0.05 pp: {bound:.3f}% of the level",
        "",
        "## Problems",
        "",
    ] + ([f"- {p}" for p in problems] or ["- none"])
    return lines, problems


def prev_quarter(q: str) -> str:
    year, n = int(q[:4]), int(q[5])
    return f"{year}Q{n - 1}" if n > 1 else f"{year - 1}Q4"


def next_quarter(q: str) -> str:
    year, n = int(q[:4]), int(q[5])
    return f"{year + n // 4}Q{n % 4 + 1}"


def main() -> int:
    require_dir(RAW_DIR)
    require_file(DB_PATH)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    for name, audit in (
        ("cell_audit.md", audit_cells),
        ("anomaly_register.md", audit_consistency),
        ("derived_audit.md", audit_derived),
    ):
        lines, problems = audit(con)
        (AUDIT_DIR / name).write_text("\n".join(lines) + "\n")
        print("\n".join(lines[:8]) if name == "cell_audit.md" else lines[2])
        if name == "derived_audit.md":
            print("\n".join(lines[2:7]))
        print(f"{name}: {len(problems)} problems")
        total += len(problems)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
