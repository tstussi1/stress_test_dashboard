"""Export the scenario database to the three JSON files the dashboard page loads.

Purpose: turn the DuckDB (the system of record) into a small, read-only snapshot for the
browser. Python computes every number here; the page only selects, aligns, takes min/max
across the user's selection and formats. Nothing flows back into the database.

Required inputs:
  - the database at `paths.DB_PATH` (opened read-only), built and audited by
    `build_database.py` / `audit_database.py`
  - `export_config.yaml` (labels, groups, gaps, data notes, defaults, quick views, limits)
  - `state_order.json` (committed append-only id order behind the share code; created on
    the first export, appended to when the database gains a vintage/scenario/variable)

Outputs, in `paths.WEB_DATA_DIR`:
  - `catalog.json`  variables, vintages, scenarios, sources, gaps, data notes, defaults, build info
  - `paths.json`    one series per (vintage, scenario, variable): published value, cumulated
                    level, gap to baseline, % level gap; plus a `realized` series per vintage
  - `actuals.json`  each vintage's own as-published Historical data
`python3 export_web_data.py --check` writes nothing; it exits non-zero if the JSON is not
built from the current database file (hash) or is older than it.

Key assumptions:
  - `published` is the stored Fed value, untouched. `level` comes from the database view
    `scenario_paths_level`; `dev` from `scenario_vs_baseline`; both are re-derived here with
    one Python cumulation function that must match the view to 1e-9 before anything is
    written. `dev_level` = 100 * (L_scenario / L_baseline - 1).
  - `realized` for a vintage = for each quarter of its horizon, the value in the Historical
    data table of the most recent vintage that reports that quarter, exactly as the Fed
    prints it (no other source, no exclusion rule); values the Fed marks as estimates in
    the supplying vintage are listed in `estimated`. The Fed's own scenario and history of
    a vintage are never mixed with another vintage's.
  - Quarters are 'YYYYQn' strings; arrays are aligned to consecutive quarters from `start`.
    The horizon index is the array position + 1. Baseline series have `dev = null`.
  - A statistic other than 'value' (`band_stats` in the config) becomes a `band`; the central
    path is always stored as stat 'value'.
"""

from __future__ import annotations

import argparse
import datetime
import gzip
import hashlib
import json
import sys
from pathlib import Path

import duckdb
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_sources import REPORT_MANIFEST
from paths import (
    DB_PATH,
    EXPORT_CONFIG_PATH,
    REPORTS_DIR,
    STATE_ORDER_PATH,
    WEB_DATA_DIR,
    require_file,
)

SCHEMA_VERSION = 1
LEVEL_TOLERANCE = 1e-9
DERIVED_DECIMALS = 6  # decimals kept for calculated values; published values are never rounded


def q_num(q: str) -> int:
    return int(q[:4]) * 4 + int(q[5]) - 1


def q_str(n: int) -> str:
    return f"{n // 4}Q{n % 4 + 1}"


def quarters_from(start: str, count: int) -> list[str]:
    return [q_str(q_num(start) + i) for i in range(count)]


def cumulate(growth: list[float]) -> list[float]:
    """Level index of annualized percent changes: 100 * prod (1 + g/100)^(1/4)."""
    out, level = [], 100.0
    for g in growth:
        level *= (1 + g / 100.0) ** 0.25
        out.append(level)
    return out


def rounded(values: list[float] | None) -> list[float] | None:
    return None if values is None else [round(v, DERIVED_DECIMALS) for v in values]


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contiguous(quarters: list[str], what: str) -> None:
    if quarters != quarters_from(quarters[0], len(quarters)):
        raise ValueError(f"{what}: quarters are not consecutive: {quarters}")


def load_config() -> dict:
    return yaml.safe_load(require_file(EXPORT_CONFIG_PATH).read_text())


STATE_CHOICES = {
    "view": {"published", "level", "deviation"},
    "basis": {"growth_gap", "level_gap"},
    "axis": {"horizon", "calendar"},
    "history": {"off", "latest", "realtime"},
    "range": {"recent", "full"},
    "band": {True, False},
}
STATE_KEYS = {"variable", "scenarios", "vintages", *STATE_CHOICES}


def validate_state_spec(spec: dict, name: str, var_ids: set[str], scenarios: set[str], vint_ids: list[str], complete: bool) -> None:
    """Fail fast if a default / quick-view state names an unknown key, id or choice."""
    unknown = set(spec) - STATE_KEYS
    missing = STATE_KEYS - set(spec) if complete else set()
    if unknown or missing:
        raise ValueError(f"{name}: unknown keys {sorted(unknown)}, missing keys {sorted(missing)}")
    for key, allowed in STATE_CHOICES.items():
        if key in spec and spec[key] not in allowed:
            raise ValueError(f"{name}: {key}={spec[key]!r} is not one of {sorted(allowed)}")
    if "variable" in spec and spec["variable"] not in var_ids:
        raise ValueError(f"{name}: variable {spec['variable']!r} is not in the database")
    if "scenarios" in spec and (not spec["scenarios"] or any(s not in scenarios for s in spec["scenarios"])):
        raise ValueError(f"{name}: scenarios {spec['scenarios']!r} must be a non-empty list of known scenarios")
    v = spec.get("vintages")
    if v is None or v == "all":
        return
    if isinstance(v, dict):
        if set(v) != {"latest"} or not isinstance(v["latest"], int) or not 1 <= v["latest"] <= len(vint_ids):
            raise ValueError(f"{name}: vintages {v!r} must be 'all', {{latest: N}} with 1 <= N <= {len(vint_ids)}, or a list of vintage ids")
    elif not isinstance(v, list) or not v or any(x not in vint_ids for x in v):
        raise ValueError(f"{name}: vintages {v!r} must be 'all', {{latest: N}}, or a list of known vintage ids")


def check_state_order(cfg: dict, current: dict[str, list[str]]) -> dict:
    """The share code indexes these lists, so they may only grow at the end."""
    snapshot = json.loads(STATE_ORDER_PATH.read_text()) if STATE_ORDER_PATH.exists() else None
    if snapshot is not None and snapshot["state_version"] == cfg["state_version"]:
        for key, old in snapshot["order"].items():
            if current[key][: len(old)] != old:
                raise ValueError(f"state order for '{key}' changed (old links would decode wrongly): was {old}, now {current[key]}; bump state_version in {EXPORT_CONFIG_PATH.name} to reset deliberately")
    state = {"state_version": cfg["state_version"], "order": current}
    STATE_ORDER_PATH.write_text(json.dumps(state, indent=1) + "\n")
    return state


def export(con: duckdb.DuckDBPyConnection, cfg: dict, db_hash: str) -> tuple[dict, dict, dict]:
    variables = con.execute("SELECT variable_id, display_name, scope, measure, unit FROM variables").fetchall()
    vintages = con.execute("SELECT vintage_id, cycle_year, publication_label, horizon_start_quarter, horizon_end_quarter, origin FROM scenario_vintages ORDER BY horizon_start_quarter").fetchall()
    scen_names = [r[0] for r in con.execute("SELECT DISTINCT scenario_name FROM scenarios").fetchall()]

    missing = {
        "scenario(s) without a label": [s for s in scen_names if s not in cfg["scenarios"]],
        "variable(s) without a theme": [v[0] for v in variables if v[0] not in cfg["themes"]],
        "theme(s) not in theme_order": sorted({t for t in cfg["themes"].values() if t not in cfg["theme_order"]}),
        "unit(s) without a label": sorted({v[4] for v in variables if v[4] not in cfg["unit_labels"]}),
    }
    missing = {k: v for k, v in missing.items() if v}
    if missing:
        raise ValueError(f"{EXPORT_CONFIG_PATH.name} is incomplete for this database: {missing}")
    var_ids = {v[0] for v in variables}
    vint_ids = [v[0] for v in vintages]
    validate_state_spec(cfg["defaults"], "defaults", var_ids, set(cfg["scenarios"]), vint_ids, complete=True)
    for qv in cfg["quick_views"]:
        validate_state_spec(qv["state"], f"quick view '{qv['id']}'", var_ids, set(cfg["scenarios"]), vint_ids, complete=False)
    if not isinstance(cfg["limits"].get("calendar_context_quarters"), int) or cfg["limits"]["calendar_context_quarters"] < 0:
        raise ValueError("limits.calendar_context_quarters must be a non-negative integer")
    for note in cfg["data_notes"]:
        if any(v not in var_ids for v in note["variables"]) or any(v not in vint_ids for v in note["vintages"]):
            raise ValueError(f"data note {note['id']} names an unknown variable or vintage")

    var_order = sorted(var_ids, key=lambda v: (cfg["theme_order"].index(cfg["themes"][v]), [x[0] for x in variables].index(v)))
    scen_order = sorted(scen_names, key=lambda s: cfg["scenarios"][s]["order"])
    measure = {v[0]: v[3] for v in variables}
    horizon = {v[0]: (v[3], v[4]) for v in vintages}
    origin = {v[0]: v[5] for v in vintages}
    state = check_state_order(cfg, {"variables": var_order, "scenarios": scen_order, "vintages": vint_ids})

    # ---- published, level, deviation ------------------------------------------------------
    value: dict[tuple, dict[str, float]] = {}
    extra: dict[tuple, dict[str, dict[str, float]]] = {}
    for key, var, q, stat, val in con.execute("SELECT scenario_key, variable_id, quarter, stat, value FROM scenario_paths").fetchall():
        v, _, sc = key.partition("__")
        if stat == "value":
            value.setdefault((v, sc, var), {})[q] = val
        else:
            extra.setdefault((v, sc, var), {}).setdefault(stat, {})[q] = val
    view_level, view_dev = {}, {}
    for key, var, q, lv in con.execute("SELECT scenario_key, variable_id, quarter, level_index FROM scenario_paths_level").fetchall():
        view_level[(*key.split("__"), var, q)] = lv
    for key, var, q, dv in con.execute("SELECT scenario_key, variable_id, quarter, deviation FROM scenario_vs_baseline").fetchall():
        view_dev[(*key.split("__"), var, q)] = dv

    series, level_of, published_of = [], {}, {}
    for (v, sc, var), by_q in value.items():
        qs = sorted(by_q)
        contiguous(qs, f"{v}/{sc}/{var}")
        if len(qs) > 13:
            raise ValueError(f"{v}/{sc}/{var}: {len(qs)} quarters")
        published = [by_q[q] for q in qs]
        level = None
        if measure[var] == "growth":
            level = cumulate(published)
            gap = max(abs(a - view_level[(v, sc, var, q)]) for a, q in zip(level, qs, strict=True))
            if gap > LEVEL_TOLERANCE:
                raise ValueError(f"{v}/{sc}/{var}: Python level differs from the database view by {gap}")
            level_of[(v, sc, var)] = dict(zip(qs, level, strict=True))
        published_of[(v, sc, var)] = by_q
        dev = None if sc == "baseline" else [view_dev[(v, sc, var, q)] for q in qs]
        series.append({"variable": var, "vintage": v, "scenario": sc, "origin": origin[v], "start": qs[0], "published": published, "level": level, "dev": dev, "dev_level": None})
        series[-1]["_keys"] = (v, sc, var, qs)
    for s in series:
        v, sc, var, qs = s.pop("_keys")
        if s["level"] is not None and sc != "baseline":
            base = level_of[(v, "baseline", var)]
            s["dev_level"] = [100.0 * (lv / base[q] - 1.0) for lv, q in zip(s["level"], qs, strict=True)]
        stats = extra.get((v, sc, var))
        if stats:
            bs = cfg["band_stats"]
            if bs["lo"] not in stats or bs["hi"] not in stats:
                raise ValueError(f"{v}/{sc}/{var}: has statistics {sorted(stats)} but not both {bs['lo']} and {bs['hi']}")
            s["band"] = {"lo": [stats[bs["lo"]][q] for q in qs], "hi": [stats[bs["hi"]][q] for q in qs], "label": bs["label"]}

    # ---- the Fed's Historical data of each vintage, and the latest-available path -----------
    hist: dict[tuple, dict[str, float]] = {}
    for v, var, q, val in con.execute("SELECT vintage_id, variable_id, quarter, value FROM actuals").fetchall():
        hist.setdefault((v, var), {})[q] = val
    flagged = {(r[0], r[1], r[2]) for r in con.execute("SELECT vintage_id, variable_id, quarter FROM estimate_flags").fetchall()}
    latest: dict[tuple, tuple[float, str]] = {}
    for v in vint_ids:  # chronological: later vintages overwrite earlier ones
        for (hv, var), by_q in hist.items():
            if hv == v:
                for q, val in by_q.items():
                    latest[(var, q)] = (val, v)

    actuals = []
    for (v, var), by_q in sorted(hist.items(), key=lambda kv: (vint_ids.index(kv[0][0]), var_order.index(kv[0][1]))):
        qs = sorted(by_q)
        contiguous(qs, f"actuals {v}/{var}")
        actuals.append({"vintage": v, "variable": var, "start": qs[0], "values": [by_q[q] for q in qs], "estimated": [i for i, q in enumerate(qs) if (v, var, q) in flagged]})

    for v in vint_ids:
        for var in var_order:
            if (v, "baseline", var) not in published_of:
                continue
            window = quarters_from(horizon[v][0], 13)
            have = [q for q in window if (var, q) in latest]
            if not have:
                continue
            if have != window[: len(have)]:
                raise ValueError(f"realized {v}/{var}: reported quarters are not a run from the start of the horizon: {have}")
            vals = [latest[(var, q)][0] for q in have]
            level = cumulate(vals) if measure[var] == "growth" else None
            base = published_of[(v, "baseline", var)]
            base_level = level_of.get((v, "baseline", var))
            series.append({
                "variable": var, "vintage": v, "scenario": "realized", "origin": "actual", "start": have[0], "published": vals,
                "level": level, "dev": [x - base[q] for x, q in zip(vals, have, strict=True)],
                "dev_level": None if level is None else [100.0 * (lv / base_level[q] - 1.0) for lv, q in zip(level, have, strict=True)],
                "estimated": [i for i, q in enumerate(have) if (latest[(var, q)][1], var, q) in flagged],
            })

    order_key = {s: i for i, s in enumerate(scen_order + ["realized"])}
    series.sort(key=lambda s: (vint_ids.index(s["vintage"]), order_key[s["scenario"]], var_order.index(s["variable"])))
    for s in series:
        for k in ("level", "dev", "dev_level"):
            s[k] = rounded(s[k])
        if "band" in s:
            s["band"]["lo"], s["band"]["hi"] = rounded(s["band"]["lo"]), rounded(s["band"]["hi"])

    # ---- catalog --------------------------------------------------------------------------
    defs = {(r[0], r[1]): r[2] for r in con.execute("SELECT vintage_id, variable_id, definition FROM variable_definitions").fetchall()}
    statements = {r[0]: {"quarter": r[1], "wording": r[2], "sentence": r[3]} for r in con.execute("SELECT DISTINCT vintage_id, quarter, wording, statement FROM estimate_flags").fetchall()}
    newest = [v[0] for v in vintages if v[5] == "fed"][-1]  # definitions come from the newest Fed vintage
    cat_vars = [{
        "id": v, "name": next(x[1] for x in variables if x[0] == v), "scope": next(x[2] for x in variables if x[0] == v), "measure": measure[v],
        "unit": next(x[4] for x in variables if x[0] == v), "unit_label": cfg["unit_labels"][next(x[4] for x in variables if x[0] == v)],
        "theme": cfg["themes"][v], "definition": defs.get((newest, v)),
    } for v in var_order]
    cat_vints = []
    for v, year, label, start, end, org in vintages:
        ids = sorted({var for (hv, var) in hist if hv == v} | {var for (sv, _, var) in value if sv == v}, key=var_order.index)
        history_quarters = [q for (hv, var), by_q in hist.items() if hv == v for q in by_q]
        last = max(history_quarters) if history_quarters else None  # a model run has no Fed history
        suffix = v.partition("_")[2]
        cat_vints.append({
            "id": v, "cycle_year": year, "label": f"{year} ({suffix.capitalize()})" if suffix else str(year), "horizon_start": start, "horizon_end": end,
            "jump_off": last, "origin": org, "n_variables": len(ids), "variable_ids": ids,
            "scenarios": [s for s in scen_order if any(k[0] == v and k[1] == s for k in value)],
            "estimate_statement": statements.get(v),
            "estimate_statement_note": None if v in statements or org != "fed" else "The Federal Reserve's files for this vintage contain no statement marking estimated values; none are flagged.",
        })
    sources = [{"vintage": r[0], "file": r[1], "url": r[2], "retrieved": r[3]} for r in con.execute("SELECT vintage_id, file_role, url, retrieved_date FROM sources ORDER BY vintage_id, file_role").fetchall()]
    reports = []
    for v in (v for v in vint_ids if origin[v] == "fed"):
        f = REPORTS_DIR / v / "scenarios_report.pdf"
        reports.append({"vintage": v, "url": REPORT_MANIFEST[v], "retrieved": datetime.date.fromtimestamp(f.stat().st_mtime).isoformat() if f.exists() else None})
    catalog = {
        "schema_version": SCHEMA_VERSION, "state_version": cfg["state_version"], "built_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "db_sha256": db_hash, "variables": cat_vars, "vintages": cat_vints,
        "scenarios": [{"name": s, **cfg["scenarios"][s]} for s in scen_order] + [{"name": "realized", "label": "Historical data, latest Federal Reserve publication", "family": "realized", "order": 99}],
        "sources": sources, "reports": reports, "methodology": cfg["methodology"], "gaps": cfg["gaps"], "data_notes": cfg["data_notes"], "defaults": cfg["defaults"], "quick_views": cfg["quick_views"], "limits": cfg["limits"],
        "labels": {"growth_unit": cfg["growth_unit_label"], "level_index": cfg["level_index_label"], "level_gap": cfg["level_gap_label"]},
        "state_order": state["order"],
    }
    return catalog, {"schema_version": SCHEMA_VERSION, "series": series}, {"schema_version": SCHEMA_VERSION, "series": actuals}


def write_json(path: Path, obj: dict, indent: int | None = None) -> None:
    text = json.dumps(obj, indent=indent, separators=None if indent else (",", ":"), ensure_ascii=False, allow_nan=False)
    path.write_text(text + "\n")
    print(f"wrote {path.name}: {len(text) / 1e3:,.0f} KB ({len(gzip.compress(text.encode())) / 1e3:,.0f} KB gzipped)")


def check() -> int:
    catalog_path = WEB_DATA_DIR / "catalog.json"
    require_file(DB_PATH)
    if not all((WEB_DATA_DIR / f).exists() for f in ("catalog.json", "paths.json", "actuals.json")):
        print(f"STALE: dashboard data missing in {WEB_DATA_DIR}; run export_web_data.py")
        return 1
    built = json.loads(catalog_path.read_text())["db_sha256"]
    if built != sha256_of(DB_PATH):
        print("STALE: dashboard data was built from a different database file; run export_web_data.py")
        return 1
    if min((WEB_DATA_DIR / f).stat().st_mtime for f in ("catalog.json", "paths.json", "actuals.json")) < DB_PATH.stat().st_mtime:
        print("STALE: dashboard data is older than the database; run export_web_data.py")
        return 1
    print("fresh: dashboard data matches the current database")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="only verify the JSON is fresh")
    if parser.parse_args().check:
        return check()
    require_file(DB_PATH)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    catalog, paths_json, actuals = export(con, load_config(), sha256_of(DB_PATH))
    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_json(WEB_DATA_DIR / "catalog.json", catalog, indent=1)
    write_json(WEB_DATA_DIR / "paths.json", paths_json)
    write_json(WEB_DATA_DIR / "actuals.json", actuals)
    return 0


if __name__ == "__main__":
    sys.exit(main())
