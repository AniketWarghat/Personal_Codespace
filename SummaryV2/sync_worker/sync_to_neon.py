"""
sync_to_neon.py — TrafficLenz Direct HTTP → NeonDB Fast Sync Worker
====================================================================
High-Performance Pipeline:
  1. Direct lightweight HTTP POST to TrafficLenz questionnaire export
     (No heavy Playwright / Chromium browser required, ~18s execution, <15MB RAM)
  2. Runs process_dataframe() from app-2.py (cleans & derives 29 columns)
  3. Incremental upsert to NeonDB via HTTPS API with SHA-256 deduplication

Usage:
    python sync_to_neon.py --once              # Run once and exit
    python sync_to_neon.py --interval 60       # Run in continuous background loop
    python sync_to_neon.py --once --from-file  # Offline mode using disk file
"""

import os
import sys
import io
import time
import hashlib
import json
import argparse
import importlib.util
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Paths ────────────────────────────────────────────────────────────────────
SYNC_DIR    = Path(__file__).parent
PROJECT_DIR = SYNC_DIR.parent.parent
SUMMARY_DIR = PROJECT_DIR / "Summary"
SESSION_DIR = Path(os.getenv("TL_SESSION_DIR", str(SUMMARY_DIR / "data")))
SESSION_FILE = SESSION_DIR / "session.json"

# Load .env if present
_env_files = [SYNC_DIR / ".env", PROJECT_DIR / ".env"]
for _ef in _env_files:
    if _ef.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(str(_ef))
        except ImportError:
            for _line in _ef.read_text(encoding="utf-8").splitlines():
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    k, v = _line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ─── Import process_dataframe from Summary/app-2.py ─────────────────────────
def _load_process_dataframe():
    """Dynamically import process_dataframe() from Summary/app-2.py."""
    import types

    mock_st = types.ModuleType("streamlit")
    mock_st.cache_data = lambda **k: (lambda f: f)
    mock_st.cache_resource = lambda **k: (lambda f: f)
    mock_st.session_state = {}
    mock_st.set_page_config = lambda **k: None
    mock_st.warning = lambda *a, **k: None
    mock_st.error = lambda *a, **k: None
    mock_st.info = lambda *a, **k: None
    mock_st.success = lambda *a, **k: None
    mock_st.write = lambda *a, **k: None
    mock_st.markdown = lambda *a, **k: None
    mock_st.title = lambda *a, **k: None
    mock_st.header = lambda *a, **k: None
    mock_st.subheader = lambda *a, **k: None
    mock_st.caption = lambda *a, **k: None
    mock_st.stop = lambda *a, **k: None
    mock_st.secrets = {}
    mock_st.spinner = lambda *a, **k: __import__("contextlib").nullcontext()
    mock_st.expander = lambda *a, **k: __import__("contextlib").nullcontext()

    class _NullCtx:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def __call__(self, *a, **k): return self
        def __getattr__(self, name): return lambda *a, **k: _NullCtx()

    mock_st.sidebar = _NullCtx()
    mock_st.columns = lambda *a, **k: [_NullCtx() for _ in range(a[0] if a else 1)]
    mock_st.tabs = lambda labels: [_NullCtx() for _ in labels]
    mock_st.container = lambda *a, **k: _NullCtx()
    mock_st.form = lambda *a, **k: _NullCtx()
    mock_st.empty = lambda *a, **k: _NullCtx()
    mock_st.button = lambda *a, **k: False
    mock_st.text_input = lambda *a, **k: ""
    mock_st.selectbox = lambda *a, **k: None
    mock_st.multiselect = lambda *a, **k: []
    mock_st.checkbox = lambda *a, **k: False
    mock_st.slider = lambda *a, **k: None
    mock_st.date_input = lambda *a, **k: None
    mock_st.metric = lambda *a, **k: None
    mock_st.dataframe = lambda *a, **k: None
    mock_st.plotly_chart = lambda *a, **k: None
    mock_st.map = lambda *a, **k: None
    mock_st.file_uploader = lambda *a, **k: None

    mock_errors = types.ModuleType("streamlit.errors")
    class _SecretNotFound(Exception): pass
    mock_errors.StreamlitSecretNotFoundError = _SecretNotFound
    mock_st.errors = mock_errors

    sys.modules["streamlit"] = mock_st
    sys.modules["streamlit.errors"] = mock_errors

    for mod_name in ["plotly", "plotly.express", "pydeck"]:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)

    app2_path = SUMMARY_DIR / "app-2.py"
    if not app2_path.exists():
        raise FileNotFoundError(f"app-2.py not found at {app2_path}")

    spec = importlib.util.spec_from_file_location("app2", str(app2_path))
    module = importlib.util.module_from_spec(spec)

    try:
        spec.loader.exec_module(module)
    except Exception as e:
        log.debug("Module-level execution error ignored: %s", e)

    if not hasattr(module, "process_dataframe"):
        raise RuntimeError("process_dataframe() not found in app-2.py after import.")

    return module.process_dataframe


# ─── Direct Fast HTTP TrafficLenz Downloader ────────────────────────────────
def download_excel_fast_http(site_id: str = "93A8309C", task_id: str = "642AD95B") -> Tuple[bytes, str]:
    """
    Downloads the questionnaire report via direct HTTP POST without spawning Playwright.
    Executes in ~15-20 seconds with negligible RAM usage.
    """
    if not SESSION_FILE.exists():
        raise FileNotFoundError(f"Session file not found at {SESSION_FILE}. Run interactive login first.")

    with open(SESSION_FILE, "r", encoding="utf-8") as f:
        session_data = json.load(f)

    session = requests.Session()
    csrf_token = ""
    for cookie in session_data.get("cookies", []):
        session.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain", "www.trafficlenz.com"))
        if cookie["name"] == "csrftoken":
            csrf_token = cookie["value"]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.trafficlenz.com/Home/viewgraph",
        "Origin": "https://www.trafficlenz.com",
        "X-CSRFToken": csrf_token,
        "X-Requested-With": "XMLHttpRequest",
    }

    url = "https://www.trafficlenz.com/Home/downloadQuestionnaireReport"
    log.info("⚡ Triggering direct fast HTTP download from TrafficLenz...")
    t0 = time.time()

    resp = session.post(
        url,
        data={
            "site_id": site_id,
            "task_id": task_id,
            "csrfmiddlewaretoken": csrf_token,
        },
        headers=headers,
        verify=False,
        timeout=60,
    )

    elapsed = time.time() - t0

    if resp.status_code != 200:
        raise RuntimeError(f"TrafficLenz export error ({resp.status_code}): {resp.text[:300]}")

    if len(resp.content) < 1000:
        raise RuntimeError(f"TrafficLenz returned non-excel response: {resp.text[:300]}")

    log.info("✅ Direct download complete! Received %d bytes in %.2fs", len(resp.content), elapsed)
    now_str = datetime.now(timezone.utc).isoformat()
    return resp.content, now_str


# ─── Neon HTTPS API ───────────────────────────────────────────────────────────
def _neon_execute(query: str) -> dict:
    """Execute SQL query over Neon HTTPS API (Port 443)."""
    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is not set.")

    host = db_url.split("@")[-1].split("/")[0].split("?")[0]
    url  = f"https://{host}/sql"
    headers = {"Neon-Connection-String": db_url, "Content-Type": "application/json"}

    resp = requests.post(url, headers=headers, json={"query": query}, verify=False, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Neon HTTPS error ({resp.status_code}): {resp.text[:500]}")
    return resp.json()


def ensure_schema():
    """Ensure survey_records table and indexes exist."""
    schema_path = SYNC_DIR.parent / "src" / "lib" / "schema.sql"
    if not schema_path.exists():
        return
    ddl = schema_path.read_text(encoding="utf-8")
    for stmt in [s.strip() for s in ddl.split(";") if s.strip()]:
        try:
            _neon_execute(stmt)
        except Exception:
            pass


# ─── Data Normalization & Hashing ───────────────────────────────────────────
def _fmt_date(val) -> str:
    import pandas as pd
    if val is None or (hasattr(pd, "isna") and pd.isna(val)):
        return ""
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    return s[:10] if len(s) >= 10 else s


def _fmt_time(val) -> str:
    import pandas as pd
    if val is None or (hasattr(pd, "isna") and pd.isna(val)):
        return ""
    if hasattr(val, "strftime"):
        return val.strftime("%H:%M:%S")
    return str(val).strip()


def _safe_str(val) -> str:
    import pandas as pd
    if val is None or (hasattr(pd, "isna") and pd.isna(val)):
        return ""
    return str(val).strip()


def _safe_float(val) -> float:
    try:
        import pandas as pd
        if val is None or (hasattr(pd, "isna") and pd.isna(val)):
            return 0.0
        return float(val)
    except Exception:
        return 0.0


def _safe_int(val) -> int:
    try:
        import pandas as pd
        if val is None or (hasattr(pd, "isna") and pd.isna(val)):
            return 0
        return int(val)
    except Exception:
        return 0


def _compute_hash(rec: dict) -> str:
    key = (
        f"{rec.get('username')}|{rec.get('date')}|{rec.get('start_time')}|"
        f"{rec.get('end_time')}|{rec.get('surveyor')}|{rec.get('direction')}|"
        f"{rec.get('vehicle_type')}|{rec.get('origin')}|{rec.get('destination')}|{rec.get('occupancy')}"
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def dataframe_to_records(df) -> list[dict]:
    """Convert process_dataframe() DataFrame to list of dicts for NeonDB."""
    records = []
    for _, row in df.iterrows():
        rec = {
            "date":                       _fmt_date(row.get("Date")),
            "start_time":                 _fmt_time(row.get("start_time")),
            "end_time":                   _fmt_time(row.get("end_time")),
            "username":                   _safe_str(row.get("Username")),
            "location":                   _safe_str(row.get("Location")),
            "remarks1":                   _safe_str(row.get("Remarks1")),
            "remarks2":                   _safe_str(row.get("Remarks2")),
            "direction_raw":              _safe_str(row.get("0.Direction")),
            "survey_type_raw":            _safe_str(row.get("1.Survey Type")),
            "surveyor":                   _safe_str(row.get("surveyor")),
            "contact":                    _safe_str(row.get("contact")),
            "direction":                  _safe_str(row.get("direction")),
            "survey_type":                _safe_str(row.get("survey_type")),
            "vehicle_type":               _safe_str(row.get("vehicle_type")),
            "origin":                     _safe_str(row.get("origin")),
            "destination":                _safe_str(row.get("destination")),
            "likely_shift":               _safe_str(row.get("likely_shift")),
            "trip_frequency":             _safe_str(row.get("trip_frequency")),
            "trip_purpose_or_commodity":  _safe_str(row.get("trip_purpose_or_commodity")),
            "occupancy":                  _safe_str(row.get("occupancy")),
            "entry_duration_sec":         _safe_int(row.get("entry_duration_sec")),
            "survey_duration_mins":       _safe_float(row.get("survey_duration_mins")),
            "has_origin_destination":     bool(row.get("has_origin_destination")),
            "bad_od_entry":               bool(row.get("bad_od_entry")),
            "sample_quality_flags":       _safe_str(row.get("sample_quality_flags")),
            "sample_quality_suspicious":  bool(row.get("sample_quality_suspicious")),
        }
        rec["record_hash"] = _compute_hash(rec)
        records.append(rec)
    return records


COLUMNS = [
    "date", "start_time", "end_time", "username", "location", "remarks1", "remarks2",
    "direction_raw", "survey_type_raw", "raw_data_json", "surveyor", "contact",
    "direction", "survey_type", "vehicle_type", "origin", "destination", "likely_shift",
    "trip_frequency", "trip_purpose_or_commodity", "occupancy", "entry_duration_sec",
    "survey_duration_mins", "has_origin_destination", "bad_od_entry", "sample_quality_flags",
    "sample_quality_suspicious", "last_synced_at", "record_hash",
]


def _esc(val) -> str:
    if val is None:
        return "NULL"
    return "'" + str(val).replace("'", "''") + "'"


def upsert_records(records: list[dict]) -> int:
    """Incremental batch upsert into NeonDB survey_records."""
    if not records:
        log.info("No records to upsert.")
        return 0

    ensure_schema()
    now_iso = datetime.now(timezone.utc).isoformat()
    total = 0

    for i in range(0, len(records), 200):
        chunk = records[i : i + 200]
        rows_sql = []
        seen = set()

        for r in chunk:
            h = r["record_hash"]
            if h in seen:
                continue
            seen.add(h)

            row_vals = [
                _esc(r.get("date")),
                _esc(r.get("start_time")),
                _esc(r.get("end_time")),
                _esc(r.get("username")),
                _esc(r.get("location")),
                _esc(r.get("remarks1")),
                _esc(r.get("remarks2")),
                _esc(r.get("direction_raw")),
                _esc(r.get("survey_type_raw")),
                "'{}'::jsonb",
                _esc(r.get("surveyor")),
                _esc(r.get("contact")),
                _esc(r.get("direction")),
                _esc(r.get("survey_type")),
                _esc(r.get("vehicle_type")),
                _esc(r.get("origin")),
                _esc(r.get("destination")),
                _esc(r.get("likely_shift")),
                _esc(r.get("trip_frequency")),
                _esc(r.get("trip_purpose_or_commodity")),
                _esc(str(r.get("occupancy", ""))),
                str(r.get("entry_duration_sec", 0) or 0),
                str(r.get("survey_duration_mins", 0.0) or 0.0),
                "TRUE" if r.get("has_origin_destination") else "FALSE",
                "TRUE" if r.get("bad_od_entry") else "FALSE",
                _esc(r.get("sample_quality_flags", "")),
                "TRUE" if r.get("sample_quality_suspicious") else "FALSE",
                _esc(now_iso),
                _esc(h),
            ]
            rows_sql.append(f"({', '.join(row_vals)})")

        if not rows_sql:
            continue

        insert_sql = f"""
            INSERT INTO survey_records ({', '.join(COLUMNS)})
            VALUES {', '.join(rows_sql)}
            ON CONFLICT (record_hash) DO UPDATE SET
                last_synced_at          = EXCLUDED.last_synced_at,
                surveyor                = EXCLUDED.surveyor,
                direction               = EXCLUDED.direction,
                vehicle_type            = EXCLUDED.vehicle_type,
                origin                  = EXCLUDED.origin,
                destination             = EXCLUDED.destination,
                sample_quality_flags    = EXCLUDED.sample_quality_flags,
                sample_quality_suspicious = EXCLUDED.sample_quality_suspicious;
        """
        _neon_execute(insert_sql)
        total += len(rows_sql)

    log.info("✅ Sync complete. Total synced: %d records.", total)
    return total


# ─── Full Sync Cycle ──────────────────────────────────────────────────────────
def run_sync_cycle(from_file: bool = False):
    process_dataframe = _load_process_dataframe()

    if from_file:
        xlsx_path = SESSION_DIR / "latest_survey.xlsx"
        if not xlsx_path.exists():
            xlsx_path = SUMMARY_DIR / "Input" / "DC513DL01 _ Delhi OD_Passenger_ Goods  OD_2026-08-25 03_03_10__survey_results.xlsx"
        log.info("Reading from file: %s", xlsx_path)
        with open(xlsx_path, "rb") as f:
            raw_bytes = f.read()
    else:
        # Fast Direct HTTP Download (~18 seconds)
        raw_bytes, _ = download_excel_fast_http()

    log.info("Processing records with process_dataframe()...")
    df = process_dataframe(raw_bytes)
    log.info("Processed %d rows.", len(df))

    records = dataframe_to_records(df)
    upsert_records(records)


# ─── Entry Point ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="TrafficLenz Fast HTTP → NeonDB Sync Worker")
    parser.add_argument("--once",      action="store_true", help="Run one cycle and exit")
    parser.add_argument("--interval",  type=int, default=60, help="Interval between sync cycles in seconds (default: 60)")
    parser.add_argument("--from-file", action="store_true", help="Use disk file instead of live HTTP download")
    args = parser.parse_args()

    log.info("=== TrafficLenz Fast HTTP → NeonDB Sync Worker ===")
    log.info("DATABASE_URL: %s", "SET ✅" if os.getenv("DATABASE_URL") else "NOT SET ❌")
    log.info("Session file: %s", SESSION_FILE)

    if args.once or args.from_file:
        run_sync_cycle(from_file=args.from_file)
    else:
        log.info("Running in loop every %ds. Press Ctrl+C to stop.", args.interval)
        while True:
            try:
                run_sync_cycle()
            except KeyboardInterrupt:
                log.info("Stopped by user.")
                break
            except Exception as e:
                log.error("Sync cycle error: %s", e, exc_info=True)
            log.info("Sleeping %ds before next sync cycle...", args.interval)
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
