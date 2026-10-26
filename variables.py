"""Canonical variable data dictionary for the Fed stress-test scenario database.

Purpose: the single source of truth mapping every published scenario variable to a
stable `variable_id`, and recognizing that variable's column header wherever it
appears in a raw source file, regardless of which vintage's formatting produced it.

Required inputs: none - this module only declares data, it never reads a raw file.

Outputs: none directly; `parser.py` imports `variable_id_for(label)` to canonicalize
every column header it encounters, and `build_database.py` imports `VARIABLES` to
populate the `variables` table.

Key assumptions:
- The 28 variables below (16 domestic + 12 international) are the complete set the
  Fed has published across every 2013-2026 vintage, confirmed by scanning the
  distinct column headers actually present in every fetched htm/csv/xlsx/pdf file
  (the scan was done once when the dictionary was written).
  This is a declared data dictionary, not a file scan at import time - adding or
  retiring a variable (e.g. a pre-2013 vintage that turns out to publish one the
  2013-2026 window never did) means adding or removing exactly one `Variable` entry
  here, nowhere else.
- `normalize_label()` absorbs *formatting* noise only (line-wrap hyphens inserted by
  <br/> breaks, inconsistent internal whitespace, footnote reference digits, and the
  two purely decorative qualifier suffixes the Fed has used - "(Level)" and "(VIX)" -
  which were confirmed never to co-occur with an unsuffixed column of the same name in
  any single vintage, i.e. they are never load-bearing). It does NOT decide that two
  differently-worded labels mean the same thing - that is a human judgment, recorded
  as an extra literal string in a variable's `canonical_labels`, with the reason
  stated in a comment (e.g. the 2013 "3-month Treasury yield" -> 2014+ "3-month
  Treasury rate" rewording of the same published series).
- A raw column header that does not normalize to any entry below is an error, not a
  skip or a guess (`variable_id_for` raises `KeyError`) - this is what forces a human
  to extend this file, by one entry, the moment a genuinely new or reworded variable
  shows up, rather than letting the build silently drop a column.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Label normalization - formatting-noise removal only (see module docstring).
# ---------------------------------------------------------------------------

_FOOTNOTE_DIGIT = re.compile(r"\s*\d+$")
_DECORATIVE_SUFFIX = re.compile(r"\s*\((?:level|vix)\)\s*$", re.IGNORECASE)
_NON_ALNUM = re.compile(r"[^a-z0-9]")
# Scope-grouping tokens the Fed prepends to a variable's own name in some files
# (e.g. 2013's historical.xlsx header "US Real GDP growth"; 2013's scenarios.xlsx
# header "Domestic\nReal GDP growth") instead of using a separate merged header
# row the way the htm pages do. Confirmed by direct inspection that no canonical
# variable's own name begins with any of these tokens, so stripping one leading
# occurrence is a formatting normalization, never a semantic merge.
_SCOPE_PREFIX = re.compile(r"^(?:u\.?s\.?|domestic|international)\s+", re.IGNORECASE)


def normalize_label(label: str) -> str:
    """Collapse a raw column header to a matching key.

    Strips (in order): surrounding/internal whitespace variation, a leading
    scope-grouping token ("US "/"Domestic "/"International "), a trailing
    footnote-reference digit, a trailing "(Level)"/"(VIX)" decorative qualifier,
    then every remaining non-alphanumeric character (spaces, line-wrap hyphens,
    periods, slashes, commas, parentheses) and lowercases. Two labels that differ
    only in that kind of formatting always collapse to the same key; two labels
    that differ in actual wording (a real rename, or a literal typo in a source
    file) do not, and must be reconciled explicitly via `canonical_labels` below.
    """
    s = re.sub(r"\s+", " ", str(label)).strip()
    s = _SCOPE_PREFIX.sub("", s)
    s = _FOOTNOTE_DIGIT.sub("", s)
    s = _DECORATIVE_SUFFIX.sub("", s)
    return _NON_ALNUM.sub("", s.lower())


@dataclass(frozen=True)
class Variable:
    variable_id: str
    display_name: str
    scope: str  # "domestic" | "international"
    measure: str  # "growth" | "level" - whether the Fed publishes a rate-of-change or a level/rate
    unit: str
    canonical_labels: tuple[
        str, ...
    ]  # literal header text(s) actually seen in the raw files


# 16 domestic + 12 international = 28, matching the Fed's own stated variable count
# from 2014 onward (2013 published 14 domestic/26 total - missing the 5-year Treasury
# yield and the prime rate, which is a documented per-vintage absence, not an error).
VARIABLES: tuple[Variable, ...] = (
    Variable(
        "real_gdp_growth",
        "Real GDP growth",
        "domestic",
        "growth",
        "percent",
        ("Real GDP growth",),
    ),
    Variable(
        "nominal_gdp_growth",
        "Nominal GDP growth",
        "domestic",
        "growth",
        "percent",
        ("Nominal GDP growth",),
    ),
    Variable(
        "real_disposable_income_growth",
        "Real disposable income growth",
        "domestic",
        "growth",
        "percent",
        ("Real disposable income growth",),
    ),
    Variable(
        "nominal_disposable_income_growth",
        "Nominal disposable income growth",
        "domestic",
        "growth",
        "percent",
        ("Nominal disposable income growth",),
    ),
    Variable(
        "unemployment_rate",
        "Unemployment rate",
        "domestic",
        "level",
        "percent",
        ("Unemployment rate",),
    ),
    # 2013's historical.xlsx calls this "US CPI Inflation" (no trailing "rate") -
    # confirmed by direct inspection, same published series.
    Variable(
        "cpi_inflation_rate",
        "CPI inflation rate",
        "domestic",
        "growth",
        "percent",
        ("CPI inflation rate", "CPI Inflation"),
    ),
    # 2013 called this "3-month Treasury yield"; 2014 onward calls it "3-month
    # Treasury rate" - same published series (confirmed: 2013 is the only vintage
    # using "yield" for this maturity; every other short-rate column in every
    # vintage already says "rate"), so it is one variable with two canonical labels,
    # not a rename overwrite.
    Variable(
        "treasury_3m_rate",
        "3-month Treasury rate",
        "domestic",
        "level",
        "percent",
        ("3-month Treasury rate", "3-month Treasury yield"),
    ),
    # Absent in 2013 (the Fed added this maturity starting with the 2014 vintage).
    Variable(
        "treasury_5y_yield",
        "5-year Treasury yield",
        "domestic",
        "level",
        "percent",
        ("5-year Treasury yield",),
    ),
    Variable(
        "treasury_10y_yield",
        "10-year Treasury yield",
        "domestic",
        "level",
        "percent",
        ("10-year Treasury yield",),
    ),
    Variable(
        "bbb_corporate_yield",
        "BBB corporate yield",
        "domestic",
        "level",
        "percent",
        ("BBB corporate yield",),
    ),
    Variable(
        "mortgage_rate",
        "Mortgage rate",
        "domestic",
        "level",
        "percent",
        ("Mortgage rate",),
    ),
    # Absent in 2013 (added with the 2014 vintage, same as the 5-year yield).
    Variable(
        "prime_rate", "Prime rate", "domestic", "level", "percent", ("Prime rate",)
    ),
    Variable(
        "dow_jones_total_stock_market_index",
        "Dow Jones Total Stock Market Index",
        "domestic",
        "level",
        "index",
        ("Dow Jones Total Stock Market Index",),
    ),
    Variable(
        "house_price_index",
        "House Price Index",
        "domestic",
        "level",
        "index",
        ("House Price Index",),
    ),
    Variable(
        "cre_price_index",
        "Commercial Real Estate Price Index",
        "domestic",
        "level",
        "index",
        ("Commercial Real Estate Price Index",),
    ),
    Variable(
        "vix",
        "Market Volatility Index (VIX)",
        "domestic",
        "level",
        "index",
        ("Market Volatility Index (VIX)", "Market Volatility Index"),
    ),
    Variable(
        "euro_real_gdp_growth",
        "Euro area real GDP growth",
        "international",
        "growth",
        "percent",
        ("Euro area real GDP growth",),
    ),
    Variable(
        "euro_inflation",
        "Euro area inflation",
        "international",
        "growth",
        "percent",
        ("Euro area inflation",),
    ),
    # The 2014 PDF (scenarios_narrative.pdf, Tables 1B/2B/3B) uses "($/euro)"
    # instead of "(USD/euro)" for this same column - confirmed by direct
    # inspection, a one-vintage typesetting variant, not a different series.
    Variable(
        "euro_usd_exchange_rate",
        "Euro area bilateral dollar exchange rate (USD/euro)",
        "international",
        "level",
        "currency_units",
        (
            "Euro area bilateral dollar exchange rate (USD/euro)",
            "Euro area bilateral dollar exchange rate ($/euro)",
        ),
    ),
    Variable(
        "devasia_real_gdp_growth",
        "Developing Asia real GDP growth",
        "international",
        "growth",
        "percent",
        ("Developing Asia real GDP growth",),
    ),
    # "Developin Asia Inflation" is a literal typo (missing the "g") in the Fed's
    # own 2013 historical workbook (bcreg20121115a3.xlsx, "Data_to_1976" sheet,
    # confirmed by direct inspection) - recorded as an explicit alias, not
    # silently fuzzy-matched.
    Variable(
        "devasia_inflation",
        "Developing Asia inflation",
        "international",
        "growth",
        "percent",
        ("Developing Asia inflation", "Developin Asia Inflation"),
    ),
    # 2013 (both scenarios.xlsx and historical.xlsx) and the 2014 PDF spell out
    # "(F/USD, Index, Base = 2000 Q1)" in full; 2015 onward shortens this to
    # "(F/USD, index)" - confirmed by direct inspection, same published series.
    Variable(
        "devasia_usd_exchange_rate",
        "Developing Asia bilateral dollar exchange rate (F/USD, index)",
        "international",
        "level",
        "index",
        (
            "Developing Asia bilateral dollar exchange rate (F/USD, index)",
            "Developing Asia Bilateral Dollar Exchange Rate (F/USD, Index, Base = 2000 Q1)",
        ),
    ),
    Variable(
        "japan_real_gdp_growth",
        "Japan real GDP growth",
        "international",
        "growth",
        "percent",
        ("Japan real GDP growth",),
    ),
    Variable(
        "japan_inflation",
        "Japan inflation",
        "international",
        "growth",
        "percent",
        ("Japan inflation",),
    ),
    Variable(
        "japan_usd_exchange_rate",
        "Japan bilateral dollar exchange rate (yen/USD)",
        "international",
        "level",
        "currency_units",
        ("Japan bilateral dollar exchange rate (yen/USD)",),
    ),
    Variable(
        "uk_real_gdp_growth",
        "U.K. real GDP growth",
        "international",
        "growth",
        "percent",
        ("U.K. real GDP growth",),
    ),
    Variable(
        "uk_inflation",
        "U.K. inflation",
        "international",
        "growth",
        "percent",
        ("U.K. inflation",),
    ),
    Variable(
        "uk_usd_exchange_rate",
        "U.K. bilateral dollar exchange rate (USD/pound)",
        "international",
        "level",
        "currency_units",
        ("U.K. bilateral dollar exchange rate (USD/pound)",),
    ),
)

# Built once at import time: every normalized label variant -> variable_id. A
# collision (two different variables normalizing to the same key) raises at import
# time, immediately, rather than silently shadowing one variable with another.
_LOOKUP: dict[str, str] = {}
for _v in VARIABLES:
    for _label in _v.canonical_labels:
        _key = normalize_label(_label)
        if _key in _LOOKUP and _LOOKUP[_key] != _v.variable_id:
            raise ValueError(
                f"canonical_labels collision: {_label!r} (normalized {_key!r}) maps to both "
                f"{_LOOKUP[_key]!r} and {_v.variable_id!r}"
            )
        _LOOKUP[_key] = _v.variable_id

BY_ID: dict[str, Variable] = {v.variable_id: v for v in VARIABLES}


def variable_id_for(raw_label: str) -> str | None:
    """Return the canonical variable_id for a raw column header, or None if the
    header is a known non-variable column (date/scenario-name/market-shock flag
    columns) that the caller should recognize itself. Raises KeyError only when
    `raw_label` is neither a known variable nor passed by the caller as one of
    those known non-variable columns - see `parser.py`'s NON_VARIABLE_COLUMNS."""
    key = normalize_label(raw_label)
    if key not in _LOOKUP:
        raise KeyError(
            f"unrecognized column header: {raw_label!r} (normalized {key!r})"
        )
    return _LOOKUP[key]
