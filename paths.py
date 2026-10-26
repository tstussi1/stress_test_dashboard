"""Single source of truth for every file location in the stress_test_dashboard workstream.

Purpose: no other script defines a file path. Every script imports its locations from
here, so moving this folder into its own repository means setting an environment
variable (or editing one default line below), never hunting through scripts.

Required inputs: none at import time (nothing here touches the disk). Scripts call
`require_dir()` / `require_file()` right before they need a location, which stops with a
message naming the environment variable that controls it.

Outputs: the path constants below plus the two `require_*` helpers.

Key assumptions:
- `DASHBOARD_DIR` is the folder containing this file, so it is always correct wherever
  the folder lives.
- Each external location has one environment variable that overrides its default. The
  defaults describe today's layout inside the research repository (the parent of this
  folder is the repository root). In a standalone repository, set the variables (or
  change the defaults here) once.
- A location that does not exist is an error, never silently replaced by another one.

Environment variables (all optional):
  STRESS_TEST_RAW_DIR        raw Fed scenario files, one sub-folder per vintage
  STRESS_TEST_REPORTS_DIR    the Fed's full scenario-report PDFs (audit / estimate flags)
  STRESS_TEST_DB_PATH        the DuckDB database (system of record)
  STRESS_TEST_REFERENCE_DIR  reference copies of Fed report PDFs (audit cross-check)
  STRESS_TEST_AUDIT_DIR      where audit reports are written
  STRESS_TEST_WEB_DATA_DIR   where the exporter writes the browser JSON snapshot
  STRESS_TEST_EXPORT_CONFIG  the exporter's labels/themes/gaps/defaults YAML
  STRESS_TEST_STATE_ORDER    the committed append-only id order used by share codes
"""

from __future__ import annotations

import os
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent
_REPO_ROOT = DASHBOARD_DIR.parent  # the research repository; only used for defaults below


def _location(env_var: str, default: Path) -> Path:
    value = os.environ.get(env_var)
    return Path(value).expanduser().resolve() if value else default


RAW_DIR = _location("STRESS_TEST_RAW_DIR", _REPO_ROOT / "data" / "raw" / "stress_test")
REPORTS_DIR = _location("STRESS_TEST_REPORTS_DIR", _REPO_ROOT / "data" / "raw" / "stress_test_reports")
DB_PATH = _location("STRESS_TEST_DB_PATH", DASHBOARD_DIR / "stress_test_scenarios.duckdb")
REFERENCE_DIR = _location(
    "STRESS_TEST_REFERENCE_DIR", _REPO_ROOT / "documentation" / "reference" / "stress_tests"
)
AUDIT_DIR = _location("STRESS_TEST_AUDIT_DIR", DASHBOARD_DIR / "audit")
WEB_DATA_DIR = _location("STRESS_TEST_WEB_DATA_DIR", DASHBOARD_DIR / "web" / "public" / "data")

EXPORT_CONFIG_PATH = _location("STRESS_TEST_EXPORT_CONFIG", DASHBOARD_DIR / "export_config.yaml")
STATE_ORDER_PATH = _location("STRESS_TEST_STATE_ORDER", DASHBOARD_DIR / "state_order.json")

# The environment variable that controls each location, for error messages.
_ENV_FOR = {
    RAW_DIR: "STRESS_TEST_RAW_DIR",
    REPORTS_DIR: "STRESS_TEST_REPORTS_DIR",
    DB_PATH: "STRESS_TEST_DB_PATH",
    REFERENCE_DIR: "STRESS_TEST_REFERENCE_DIR",
    AUDIT_DIR: "STRESS_TEST_AUDIT_DIR",
    WEB_DATA_DIR: "STRESS_TEST_WEB_DATA_DIR",
    EXPORT_CONFIG_PATH: "STRESS_TEST_EXPORT_CONFIG",
    STATE_ORDER_PATH: "STRESS_TEST_STATE_ORDER",
}


def require_dir(path: Path) -> Path:
    """Return `path` if it is an existing directory, else stop naming the controlling variable."""
    if not path.is_dir():
        raise FileNotFoundError(
            f"required directory not found: {path} (set {_ENV_FOR.get(path, 'the matching STRESS_TEST_* variable')})"
        )
    return path


def require_file(path: Path) -> Path:
    """Return `path` if it is an existing file, else stop naming the controlling variable."""
    if not path.is_file():
        raise FileNotFoundError(
            f"required file not found: {path} (set {_ENV_FOR.get(path, 'the matching STRESS_TEST_* variable')})"
        )
    return path
