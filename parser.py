"""Parse every raw Fed stress-test scenario source file into normalized rows.

Purpose: a single, format-agnostic parsing pipeline for every file fetched by
`fetch_sources.py` into `data/raw/stress_test/<vintage>/*`, replacing a per-layout
("family") parser with one shared interpreter fed by four small format readers.
Pre-2013 vintages, whenever added, only need a new reader if they use a genuinely
new container format (a fifth entry in `READERS`); the interpretation logic below
(scenario/historical classification, history/projection split, label
canonicalization, cross-source reconciliation) never needs vintage-specific code.

Required inputs: `data/raw/stress_test/<vintage>/*.{xlsx,htm,csv,pdf}`.

Outputs: `parse_vintage(vintage_dir)` returns `(scenario_rows, actual_rows)`.
`scenario_rows` dicts have keys `scenario_name`, `variable_id`, `quarter`,
`value`, `source`; `actual_rows` dicts have the same minus `scenario_name` (an
actual isn't scenario-specific) - the normalized long-format rows
`build_database.py` loads into `scenario_paths`/`actuals`.

Key assumptions:
- A "table" (whatever its container format) is reduced to one shared primitive,
  `RawTable`: an optional caption, an optional per-row scenario-name column, a list
  of variable column headers, and (date, scenario_name_or_None, raw_values) rows.
  Readers only produce this primitive; they contain zero scenario/historical logic.
- Every RawTable is classified as "historical" or a named scenario by searching,
  in order, its caption text, its per-row scenario-name values, and its source
  filename, for "historical" or one of the Fed's own scenario-name words
  (baseline/adverse/severely adverse/alternative severe/exploratory) - confirmed
  these are the only scenario names ever published 2013-2026. An unclassifiable
  table raises rather than being silently skipped.
- A classified-as-scenario table with far more rows than any published stress-test
  horizon (all 2013-2026 horizons are 9-13 quarters; threshold set at 20 with
  margin) is a combined history+projection table (2013 xlsx, 2014 pdf, 2015 htm,
  2016 csv): its last 13 rows are the scenario, everything earlier is that
  variable's actual history. A classified-as-historical table is never split.
- When more than one source reports an actual value for the same
  (variable_id, quarter) - e.g. 2013's three scenario sheets' embedded history
  agreeing with each other and with the dedicated historical.xlsx, or a vintage's
  htm historical table agreeing with a same-vintage standalone CSV - every value
  must agree with every other within a tolerance derived from the fewer of the two
  values' own published decimal places (never assumed to be 1 decimal place); a
  disagreement beyond that raises with the full detail. This is a verify, not a
  silent preference - see `reconcile()`. Once verified, the value with the most
  decimal places is kept, since it is reporting the same fact at finer precision.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

import openpyxl
import pandas as pd
import pymupdf
from bs4 import BeautifulSoup

from variables import normalize_label, variable_id_for

# Horizon lengths actually published 2013-2026 top out at 13 quarters; a
# classified-as-scenario table with more rows than this must be a combined
# history+projection table (decades of quarters), not a longer horizon.
MAX_PUBLISHED_HORIZON_QUARTERS = 13
COMBINED_TABLE_ROW_THRESHOLD = 20

# Header cells that name the date/scenario-name column itself, never a variable.
_NON_VARIABLE_HEADERS = {"date", "obs", "column1", "scenarioname"}


def _is_non_variable(label: str) -> bool:
    return normalize_label(label) in _NON_VARIABLE_HEADERS


# ---------------------------------------------------------------------------
# Shared primitive every reader produces.
# ---------------------------------------------------------------------------


@dataclass
class RawTable:
    source_file: Path
    caption: str | None  # table/sheet caption text, if the container format has one
    header: list[str]  # variable column headers only (date/scenario-name excluded)
    rows: list[
        tuple[str, str | None, list[str]]
    ]  # (date_text, row_scenario_name, raw_values)


# ---------------------------------------------------------------------------
# Scenario/historical classification - shared by every reader's output.
# ---------------------------------------------------------------------------

# Ordered so "severely adverse" is tried before the plain "adverse" it contains;
# this is the complete, closed set of scenario-exercise names the Fed has ever
# published 2013-2026 (confirmed directly against every fetched file's captions,
# CSV "Scenario Name" values, and filenames in Phase 0/1 - not a guess at what
# future names might be).
_SCENARIO_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("severely_adverse", re.compile(r"severely\s+adverse", re.IGNORECASE)),
    ("alternative_severe", re.compile(r"alternative\s+severe", re.IGNORECASE)),
    ("adverse", re.compile(r"\badverse\b", re.IGNORECASE)),
    ("baseline", re.compile(r"\bbaseline\b", re.IGNORECASE)),
    ("exploratory_a", re.compile(r"exploratory.*\ba\b", re.IGNORECASE)),
    ("exploratory_b", re.compile(r"exploratory.*\bb\b", re.IGNORECASE)),
    ("exploratory", re.compile(r"exploratory", re.IGNORECASE)),
)
_HISTORICAL_PATTERN = re.compile(r"historical|historic", re.IGNORECASE)


def classify_source(*texts: str | None) -> tuple[str, str]:
    """Classify a table as ("historical", "actual") or ("scenario", name) by
    searching each given text (caption, filename, per-row scenario value, ...) in
    priority order. Raises if none of them yield a classification - every table
    this pipeline is given must be recognizable as one or the other. Underscores
    are treated as word separators (so a filename stem like "exploratory_a" has
    its "a" matched as its own word, not glued to its neighbors)."""
    for text in texts:
        if not text:
            continue
        text = text.replace("_", " ")
        if _HISTORICAL_PATTERN.search(text):
            return "historical", "actual"
        for name, pattern in _SCENARIO_PATTERNS:
            if pattern.search(text):
                return "scenario", name
    raise ValueError(
        f"could not classify table as historical or a named scenario from: {texts!r}"
    )


_QUARTER_RE = re.compile(
    r"(?:(\d{4})\s*Q([1-4])|Q([1-4])\s*[,:]?\s*(\d{4}))", re.IGNORECASE
)


def parse_quarter(text: str) -> str:
    m = _QUARTER_RE.search(str(text))
    if not m:
        raise ValueError(f"unparseable quarter: {text!r}")
    return f"{m.group(1)}Q{m.group(2)}" if m.group(1) else f"{m.group(4)}Q{m.group(3)}"


def to_number(raw: object) -> tuple[float, int]:
    """Parse a published cell value; returns (value, decimal_places_as_published)."""
    s = str(raw).strip().replace(",", "").replace("%", "").replace("\u2212", "-")
    if s in ("", "\u2014", "-", "n.a.", "n.a", "nan", "None"):
        return float("nan"), 0
    value = float(s)
    decimals = len(s.split(".")[1]) if "." in s else 0
    return value, decimals


def is_quarter_indexed(first_column_values, min_fraction: float = 0.8) -> bool:
    """True if most of a table's first-column values look like a quarter ('Q1
    2001'). Used to structurally exclude tables that are not a variable panel at
    all - e.g. the "<year> Stress test banks" participant-list table the Fed
    started publishing alongside the scenario tables from 2023 onward, whose
    first column is bank names, not dates. This is a content-shape check, not a
    caption/position rule, so it applies unchanged to any future table of that
    kind regardless of what it is captioned or where it sits on the page."""
    values = list(first_column_values)
    if not values:
        return False
    hits = sum(1 for v in values if re.match(r"^Q[1-4]\s*\d{4}$", str(v).strip()))
    return hits / len(values) >= min_fraction


# ---------------------------------------------------------------------------
# Readers: one per container format. Each only knows how to chop its own byte
# format into RawTables - no scenario/historical/variable logic lives here.
# ---------------------------------------------------------------------------


def read_xlsx(path: Path) -> list[RawTable]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    tables = []
    for sheet_name in wb.sheetnames:
        rows = list(wb[sheet_name].iter_rows(values_only=True))
        first_data_idx = next(
            (
                i
                for i, r in enumerate(rows)
                if r
                and isinstance(r[0], str)
                and re.match(r"^Q[1-4]\s*\d{4}$", r[0].strip())
            ),
            None,
        )
        if first_data_idx is None or first_data_idx == 0:
            continue  # not a data sheet (e.g. "Data notes"/"Data_definitions")
        header_row = rows[first_data_idx - 1]
        header = [str(c).strip() for c in header_row[1:] if c not in (None, "")]
        data_rows = []
        for r in rows[first_data_idx:]:
            if (
                not r
                or not isinstance(r[0], str)
                or not re.match(r"^Q[1-4]\s*\d{4}$", r[0].strip())
            ):
                break
            values = [r[i + 1] for i in range(len(header))]
            data_rows.append((r[0], None, values))
        tables.append(
            RawTable(
                path, caption=f"{path.name}:{sheet_name}", header=header, rows=data_rows
            )
        )
    return tables


def read_htm(path: Path) -> list[RawTable]:
    soup = BeautifulSoup(path.read_text(errors="replace"), "lxml")
    tables = []
    for t in soup.find_all("table"):
        if len(t.find_all("tr")) < 3:
            continue
        caption = t.get("title") or t.get("summary")
        df = pd.read_html(pd.io.common.StringIO(str(t)))[0]
        if not is_quarter_indexed(df.iloc[:, 0]):
            continue  # not a variable panel (e.g. the "<year> Stress test banks" table)
        cols = [
            c[-1] if isinstance(df.columns, pd.MultiIndex) else c for c in df.columns
        ]
        header = [str(c) for c in cols[1:]]
        # Positional, not label-based: some tables repeat a column label (or carry
        # MultiIndex remnants), which would make label lookups ambiguous.
        data_rows = [
            (row.iloc[0], None, list(row.iloc[1:])) for _, row in df.iterrows()
        ]
        tables.append(RawTable(path, caption=caption, header=header, rows=data_rows))
    return tables


def read_csv(path: Path) -> list[RawTable]:
    df = pd.read_csv(path)
    cols = list(df.columns)
    if _is_non_variable(cols[0]) and normalize_label(cols[0]) == "scenarioname":
        date_col, header = cols[1], cols[2:]
        tables = []
        for scenario_value, group in df.groupby(cols[0], sort=False):
            rows = [
                (row[date_col], str(scenario_value), [row[c] for c in header])
                for _, row in group.iterrows()
            ]
            tables.append(RawTable(path, caption=None, header=list(header), rows=rows))
        return tables
    date_col, header = cols[0], cols[1:]
    rows = [(row[date_col], None, [row[c] for c in header]) for _, row in df.iterrows()]
    return [
        RawTable(
            path, caption=path.stem.replace("_", " "), header=list(header), rows=rows
        )
    ]


def read_pdf(path: Path) -> list[RawTable]:
    """Word-position based table extraction: PDF text layout is reconstructed from
    each word's bounding box rather than whitespace alignment, so header labels
    wrapped across multiple lines are recovered without assuming any fixed column
    order or width; this generalizes better than a fixed-width/regex reader to an unseen PDF."""
    doc = pymupdf.open(path)
    open_tables: dict[str, RawTable] = {}  # "1A" -> in-progress table, across pages
    tables: list[RawTable] = []
    for page in doc:
        words = page.get_text("words")  # (x0, y0, x1, y1, text, block, line, word_no)
        first_line = (
            page.get_text().strip().split("\n")[0] if page.get_text().strip() else ""
        )
        m = re.match(r"^Table (\d+[A-Z])\.", first_line)
        if not m:
            continue
        table_num = m.group(1)
        is_continuation = "continued" in first_line.lower()

        date_words = sorted(
            (w for w in words if w[0] < 110 and re.fullmatch(r"Q[1-4]", w[4])),
            key=lambda w: w[1],
        )
        if not date_words:
            continue
        first_row_y = date_words[0][1]
        row_bands = [w[1] for w in date_words]

        def words_in_band(y: float, tol: float = 4.0, words=words):
            return sorted(
                (w for w in words if abs(w[1] - y) <= tol), key=lambda w: w[0]
            )

        first_row_words = words_in_band(first_row_y)
        value_words = [
            w for w in first_row_words if not re.fullmatch(r"Q[1-4]|\d{4}", w[4])
        ]
        centers = [(w[0] + w[2]) / 2 for w in value_words]

        # Exclude the page's running header (date/page-number, above the title) and
        # the title line itself ("Table 1A. Supervisory ... scenario: Domestic") -
        # both sit above the real column-header block, which starts strictly below
        # whichever line carries the word "Table".
        title_y = next(w[1] for w in words if w[4] == "Table")
        header_words = [w for w in words if title_y + 2 < w[1] < first_row_y - 2]
        header_words = [
            w for w in header_words if w[4] not in ("Date",) and abs(w[0] - 80) > 3
        ]
        buckets: dict[int, list] = {i: [] for i in range(len(centers))}
        for w in header_words:
            cx = (w[0] + w[2]) / 2
            best = min(range(len(centers)), key=lambda i: abs(centers[i] - cx))
            buckets[best].append(w)
        header = []
        for i in range(len(centers)):
            ws = sorted(buckets[i], key=lambda w: (w[1], w[0]))
            header.append(" ".join(w[4] for w in ws))

        rows = []
        for y in row_bands:
            row_words = words_in_band(y)
            date_tok = next(w for w in row_words if re.fullmatch(r"Q[1-4]", w[4]))
            year_tok = next(w for w in row_words if re.fullmatch(r"\d{4}", w[4]))
            date_text = f"{date_tok[4]} {year_tok[4]}"
            vals = [w for w in row_words if w not in (date_tok, year_tok)]
            vals.sort(key=lambda w: w[0])
            rows.append((date_text, None, [w[4] for w in vals]))

        if is_continuation and table_num in open_tables:
            open_tables[table_num].rows.extend(rows)
        else:
            caption_text = re.sub(
                r"\s+", " ", page.get_text().strip().split("\n")[0]
            ).strip()
            # The continuation page repeats only "Table 1A.\u2014continued"; the real
            # caption (with scenario/scope) was captured when the table first opened.
            rt = RawTable(path, caption=caption_text, header=header, rows=rows)
            open_tables[table_num] = rt
            tables.append(rt)
    return tables


READERS = {".xlsx": read_xlsx, ".htm": read_htm, ".csv": read_csv, ".pdf": read_pdf}


# ---------------------------------------------------------------------------
# Cross-source reconciliation - never silently prefer one source's value over
# another's; verify agreement, then keep the more precise one.
# ---------------------------------------------------------------------------

# A table's own per-row "Scenario Name" cell is independent evidence of which
# scenario it is, checked against the publication-level classification (from its
# caption/filename) rather than blended into it. A disagreement is fine only when
# it is this one documented case: the Fed's 2025 exploratory-analysis publication
# states the exploratory macro conditions are identical to that cycle's severely
# adverse scenario, and its own CSV literally reuses the "Supervisory Severely
# Adverse" row label inside the file named for the exploratory exercise. Even
# here, the pipeline does not just trust the documentation - see validation
# check 5 in `build_database.run_validations`, which checks the actual numbers
# agree before this is treated as resolved.
KNOWN_LABEL_REUSE = {("exploratory", "severely_adverse")}


def classify_table(
    primary_texts: tuple[str | None, ...], row_scenario_names: set[str]
) -> tuple[str, str]:
    """Classify by caption/filename (the publication-level identity) and, if the
    table also carries its own per-row scenario-name cell(s), cross-check that
    independently - raising on any disagreement not in `KNOWN_LABEL_REUSE`."""
    kind, name = classify_source(*primary_texts)
    for row_name_text in row_scenario_names:
        row_kind, row_name = classify_source(row_name_text)
        if (row_kind, row_name) == (kind, name):
            continue
        if (name, row_name) in KNOWN_LABEL_REUSE or (
            row_name,
            name,
        ) in KNOWN_LABEL_REUSE:
            continue
        raise ValueError(
            f"scenario label mismatch: classified as {kind}/{name} from {primary_texts!r}, "
            f"but a row's own 'Scenario Name' cell says {row_kind}/{row_name} ({row_name_text!r})"
        )
    return kind, name


def reconcile(observations: list[tuple[float, int, str]]) -> tuple[float, str]:
    """`observations` is a list of (value, decimal_places_as_published, source) for
    the same (variable_id, quarter) [, scenario_key]. When more than one source
    reports a value for the same fact, every pair must agree within a tolerance
    derived from the coarser of the two published precisions (0.51 at the last
    published digit, matching ordinary display rounding) - never a silent pick.
    Once verified, the most precise observation is kept, since it states the same
    fact with less rounding, not a different fact."""
    if len(observations) == 1:
        return observations[0][0], observations[0][2]
    for i in range(len(observations)):
        for j in range(i + 1, len(observations)):
            v_i, d_i, s_i = observations[i]
            v_j, d_j, s_j = observations[j]
            tolerance = 0.51 * 10 ** (-min(d_i, d_j))
            if abs(v_i - v_j) > tolerance:
                raise ValueError(
                    f"conflicting values for the same fact: {s_i}={v_i} vs {s_j}={v_j} "
                    f"(tolerance {tolerance} from {min(d_i, d_j)} published decimal places)"
                )
    best = max(observations, key=lambda o: o[1])
    return best[0], best[2]


# ---------------------------------------------------------------------------
# Orchestration: every file in a vintage directory -> normalized scenario and
# actual rows for that vintage.
# ---------------------------------------------------------------------------


def parse_vintage(vintage_dir: Path) -> tuple[list[dict], list[dict]]:
    """Returns (scenario_rows, actual_rows). Each scenario_row has keys
    scenario_name/scope/variable_id/quarter/value/source; each actual_row has
    scope/variable_id/quarter/value/source (no scenario_name - an actual isn't
    scenario-specific)."""
    scenario_obs: dict[tuple[str, str, str], list[tuple[float, int, str]]] = {}
    actual_obs: dict[tuple[str, str], list[tuple[float, int, str]]] = {}

    for f in sorted(vintage_dir.iterdir()):
        reader = READERS.get(f.suffix)
        if reader is None:
            continue
        for table in reader(f):
            row_scenario_names = {r[1] for r in table.rows if r[1]}
            kind, scenario_name = classify_table(
                (table.caption, f.stem), row_scenario_names
            )

            split = (
                kind == "scenario" and len(table.rows) > COMBINED_TABLE_ROW_THRESHOLD
            )
            if kind == "historical":
                hist_rows, scen_rows = table.rows, []
            elif split:
                hist_rows, scen_rows = (
                    table.rows[:-MAX_PUBLISHED_HORIZON_QUARTERS],
                    table.rows[-MAX_PUBLISHED_HORIZON_QUARTERS:],
                )
            else:
                hist_rows, scen_rows = [], table.rows

            source = f"stress_test/{f.relative_to(vintage_dir.parent)}:{table.caption or scenario_name}"
            for date_text, _, raw_values in hist_rows:
                quarter = parse_quarter(date_text)
                for label, raw in zip(table.header, raw_values, strict=True):
                    value, decimals = to_number(raw)
                    if math.isnan(value):  # not published for this quarter
                        continue
                    variable_id = variable_id_for(label)
                    actual_obs.setdefault((variable_id, quarter), []).append(
                        (value, decimals, source)
                    )
            for date_text, _, raw_values in scen_rows:
                quarter = parse_quarter(date_text)
                for label, raw in zip(table.header, raw_values, strict=True):
                    value, decimals = to_number(raw)
                    if math.isnan(value):
                        continue
                    variable_id = variable_id_for(label)
                    scenario_obs.setdefault(
                        (scenario_name, variable_id, quarter), []
                    ).append((value, decimals, source))

    actual_rows = []
    for (vid, q), obs in actual_obs.items():
        value, source = reconcile(obs)
        actual_rows.append(
            {"variable_id": vid, "quarter": q, "value": value, "source": source}
        )
    scenario_rows = []
    for (sn, vid, q), obs in scenario_obs.items():
        value, source = reconcile(obs)
        scenario_rows.append(
            {
                "scenario_name": sn,
                "variable_id": vid,
                "quarter": q,
                "value": value,
                "source": source,
            }
        )
    return scenario_rows, actual_rows
