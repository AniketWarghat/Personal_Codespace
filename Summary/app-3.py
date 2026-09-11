"""
app-3.py — Thane WTP (Willingness to Pay) Survey Dashboard
===========================================================
Streamlit Web Application for Thane Personal Rapid Transit (PRT) WTP Survey.
Job Code: DC513MH06

Features:
  - Live Data Sync via TrafficLenz session downloader or manual Excel upload
  - Dynamic Multi-Filter Sidebar (Date, Time, Station, Mode, PRT Willingness, Surveyor, Income, Quality)
  - Dedicated Data Quality & Flagged Entries Tab (Travel Time < 10m, Cost < 10 Rs, Waiting < 5m, Duration < 60s)
  - Comprehensive PRT Willingness, Mode Shift & Fare Sensitivity Analytics
  - Demographics, Surveyor Monitoring, OD Corridor Matrix, and Full Raw Data Grid with CSV Exports.
"""

from __future__ import annotations

import io
import os
import sys
import time
import math
import re
from datetime import datetime, time as dtime, timezone, timedelta
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Thane WTP (PRT) Survey Dashboard",
    page_icon="🚆",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# OPTIONAL PASSWORD AUTH (FROM SECRETS)
# ─────────────────────────────────────────────────────────────────────────────
def _get_app_password() -> str | None:
    try:
        if "APP_PASSWORD" in st.secrets:
            return str(st.secrets["APP_PASSWORD"])
    except Exception:
        pass
    toml_path = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")
    if os.path.exists(toml_path):
        try:
            import tomllib
            with open(toml_path, "rb") as f:
                t = tomllib.load(f)
                if "APP_PASSWORD" in t:
                    return str(t["APP_PASSWORD"])
        except Exception:
            pass
    return os.environ.get("APP_PASSWORD", None)

def _check_password() -> None:
    app_pwd = _get_app_password()
    if not app_pwd:
        return

    def _on_pwd_enter():
        if st.session_state.get("entered_password") == app_pwd:
            st.session_state["authenticated"] = True
        else:
            st.session_state["authenticated"] = False

    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        c1, c2, c3 = st.columns([1, 1.5, 1])
        with c2:
            st.markdown("### 🔒 Thane WTP PRT Dashboard")
            st.info("Please enter the dashboard access password to continue.")
            st.text_input(
                "Password",
                type="password",
                on_change=_on_pwd_enter,
                key="entered_password",
                placeholder="Enter password..."
            )
            if st.button("Unlock Dashboard", use_container_width=True):
                _on_pwd_enter()
                if st.session_state["authenticated"]:
                    st.rerun()
                else:
                    st.error("❌ Incorrect password. Please try again.")
            elif st.session_state.get("entered_password") and not st.session_state["authenticated"]:
                st.error("❌ Incorrect password. Please try again.")
        st.stop()

_check_password()

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS & THEME
# ─────────────────────────────────────────────────────────────────────────────
IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_SURVEY_ID = "DC513MH06"
_INPUT_DIR = os.path.join(os.path.dirname(__file__), "Input")
_input_files = sorted(
    [f for f in os.listdir(_INPUT_DIR) if f.endswith(".xlsx")] if os.path.isdir(_INPUT_DIR) else [],
    key=lambda f: os.path.getmtime(os.path.join(_INPUT_DIR, f)),
    reverse=True,  # newest first
)
DEFAULT_FILE = os.path.join(_INPUT_DIR, _input_files[0]) if _input_files else ""

PRIMARY_COLOR = "#4f46e5"    # Indigo
SECONDARY_COLOR = "#06b6d4"  # Cyan
SUCCESS_COLOR = "#10b981"    # Emerald
WARNING_COLOR = "#f59e0b"    # Amber
DANGER_COLOR = "#ef4444"     # Rose
PURPLE_COLOR = "#8b5cf6"     # Purple
GRAY_COLOR = "#64748b"       # Slate

# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM CSS STYLING
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* Metric Card Styling */
    div[data-testid="stMetric"] {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        padding: 14px 18px;
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.03);
    }
    div[data-testid="stMetric"]:hover {
        border-color: #cbd5e1;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
    }
    div[data-testid="stMetric"] label {
        font-size: 0.82rem !important;
        font-weight: 600 !important;
        color: #64748b !important;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        font-size: 1.65rem !important;
        font-weight: 700 !important;
        color: #0f172a !important;
    }

    /* Tabs Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        border-bottom: 2px solid #e2e8f0;
        padding-bottom: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 8px 16px;
        font-weight: 600;
        font-size: 0.88rem;
    }
    .stTabs [aria-selected="true"] {
        background-color: #eef2ff !important;
        color: #4f46e5 !important;
    }

    /* Flag Badges */
    .flag-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
        background-color: #fee2e2;
        color: #991b1b;
        margin: 2px;
    }
    .clean-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
        background-color: #dcfce7;
        color: #166534;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────
def format_seconds(sec: float | int | None) -> str:
    if sec is None or pd.isna(sec) or sec <= 0:
        return "0s"
    m = int(sec // 60)
    s = int(sec % 60)
    if m == 0:
        return f"{s}s"
    return f"{m}m {s:02d}s"


def make_download_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# DATA PROCESSING & DERIVATION PIPELINE
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def process_dataframe(raw_bytes: bytes) -> pd.DataFrame:
    """
    Parses and cleans the WTP Survey Excel file into a normalized DataFrame.
    """
    df_raw = pd.read_excel(io.BytesIO(raw_bytes))
    df = df_raw.copy()

    # 1. Parse Date
    if "Date" in df.columns:
        df["Date_parsed"] = pd.to_datetime(df["Date"], errors="coerce", dayfirst=True)
        df["Date_str"] = df["Date_parsed"].dt.strftime("%d/%m/%Y").fillna(df["Date"].astype(str))
    else:
        df["Date_parsed"] = pd.NaT
        df["Date_str"] = "-"

    # 2. Parse Start Time & End Time
    def parse_time_val(val):
        if pd.isna(val):
            return None
        if isinstance(val, dtime):
            return val
        if isinstance(val, datetime):
            return val.time()
        s = str(val).strip()
        try:
            return datetime.strptime(s, "%H:%M:%S").time()
        except Exception:
            try:
                return datetime.strptime(s, "%H:%M").time()
            except Exception:
                return None

    df["start_time_obj"] = df["start_time"].apply(parse_time_val) if "start_time" in df.columns else None
    df["end_time_obj"] = df["end_time"].apply(parse_time_val) if "end_time" in df.columns else None

    # Compute entry duration in seconds & minutes
    def calc_duration_sec(row):
        st_t = row["start_time_obj"]
        et_t = row["end_time_obj"]
        if st_t is not None and et_t is not None and not (isinstance(st_t, float) and pd.isna(st_t)) and not (isinstance(et_t, float) and pd.isna(et_t)):
            try:
                td = datetime.combine(datetime.today(), et_t) - datetime.combine(datetime.today(), st_t)
                sec = td.total_seconds()
                if sec < 0:
                    sec += 86400  # Cross midnight
                return int(sec)
            except Exception:
                pass
        return pd.NA

    df["entry_duration_sec"] = df.apply(calc_duration_sec, axis=1, result_type="reduce")
    df["survey_duration_mins"] = df["entry_duration_sec"].apply(lambda s: round(float(s) / 60.0, 2) if pd.notna(s) else None)
    df["start_hour"] = df["start_time_obj"].apply(lambda t: t.hour if t else None)

    # 3. Surveyor & Contact Info
    df["surveyor"] = df["Remarks1"].astype(str).str.strip().str.title() if "Remarks1" in df.columns else "Unknown"
    df["contact"] = df["Remarks2"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True) if "Remarks2" in df.columns else "-"

    # 4. Survey Station / Location Name
    df["station_location"] = df["0.Location Name"].astype(str).str.strip() if "0.Location Name" in df.columns else "Thane Station"

    # 5. Demographics
    df["age"] = df["1.Age (years)"].astype(str).str.strip() if "1.Age (years)" in df.columns else "-"
    df["gender"] = df["2.Gender"].astype(str).str.strip().str.capitalize() if "2.Gender" in df.columns else "-"
    df["occupation"] = df["3.Occupation"].astype(str).str.strip() if "3.Occupation" in df.columns else "-"
    def _col(col_name):
        """Safely get a DataFrame column as a Series, or NaN Series if missing."""
        return df[col_name] if col_name in df.columns else pd.Series(pd.NA, index=df.index, dtype=object)

    df["group_size"] = pd.to_numeric(_col("4.Group Size"), errors="coerce").fillna(1).astype(int)
    df["income"] = df["5.Individual Monthly Income (Rs.)"].astype(str).str.strip() if "5.Individual Monthly Income (Rs.)" in df.columns else "-"

    # 6. Trip Attributes
    df["origin"] = df["6.Trip Origin"].astype(str).str.strip().str.title() if "6.Trip Origin" in df.columns else "-"
    df["destination"] = df["7.Trip Destination"].astype(str).str.strip().str.title() if "7.Trip Destination" in df.columns else "-"
    df["od_pair"] = df["origin"] + " ➔ " + df["destination"]

    df["mode_of_travel"] = df["8.Mode of Travel"].astype(str).str.strip() if "8.Mode of Travel" in df.columns else "Other"
    df["travel_time_min"]    = pd.to_numeric(_col("9.Travel Time (Min)"),      errors="coerce")
    df["travel_cost_rs"]     = pd.to_numeric(_col("10.Travel Cost (Rs.)"),     errors="coerce")
    df["waiting_time_min"]   = pd.to_numeric(_col("11.Waiting Time (Min)"),    errors="coerce")
    df["travel_distance_km"] = pd.to_numeric(_col("12.Travel Distance (km)"),  errors="coerce")
    df["trip_frequency"] = df["13.Trip Frequency"].astype(str).str.strip() if "13.Trip Frequency" in df.columns else "-"
    df["trip_purpose"] = df["14.Trip Purpose"].astype(str).str.strip() if "14.Trip Purpose" in df.columns else "-"

    # 7. PRT Willingness & Acceptable Fare
    df["prt_willingness"] = (
        df["15.Would you be willing to use this PRT System?"]
        .astype(str)
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
        if "15.Would you be willing to use this PRT System?" in df.columns
        else "Unknown"
    )

    def derive_acceptable_fare(row):
        f1 = str(row.get("15a1.Maximum acceptable PRT fare for your trip (in Rs)?", "")).strip()
        f2 = str(row.get("15c1.Maximum acceptable PRT fare for your trip (in Rs)?", "")).strip()
        for f in [f1, f2]:
            if f and f != "-" and f.lower() != "nan":
                return f
        return "Not Specified"

    df["acceptable_prt_fare"] = df.apply(derive_acceptable_fare, axis=1, result_type="reduce")

    # Derived speed (km/h)
    def calc_speed(row):
        try:
            dist   = row["travel_distance_km"]
            time_m = row["travel_time_min"]
            if pd.notna(dist) and pd.notna(time_m) and float(time_m) > 0:
                return round(float(dist) / (float(time_m) / 60.0), 1)
        except Exception:
            pass
        return pd.NA

    df["speed_kmh"] = df.apply(calc_speed, axis=1, result_type="reduce")

    return df


# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# QUALITY CHECKS & FLAGGED ENTRIES EVALUATION
# ─────────────────────────────────────────────────────────────────────────────

def _contains_valid_thane_terminal(text: str) -> bool:
    """Returns True if the text refers to any valid Thane terminal/stand.

    Accepted values (any of):
      - Thane Auto Stand
      - Thane Bus Stand
      - Thane Railway Station
    """
    if not text:
        return False
    t = str(text).strip().lower()
    if not t or t in ["-", "nan", "none"]:
        return False
    # Auto Stand
    if "auto stand" in t or "autostand" in t or "auto-stand" in t:
        return True
    if "thane auto" in t:
        return True
    if "auto" in t and "stand" in t:
        return True
    # Bus Stand
    if "bus stand" in t or "busstand" in t or "bus-stand" in t:
        return True
    if "thane bus" in t:
        return True
    # Railway Station
    if "railway station" in t or "railway" in t or "rail station" in t:
        return True
    if "thane station" in t or "thane rail" in t:
        return True
    return False


# Keep old name as alias for any existing callers
_contains_thane_auto_stand = _contains_valid_thane_terminal


def compute_wtp_quality_flags(
    df: pd.DataFrame,
    min_travel_time: int = 10,
    min_cost: int = 10,
    min_waiting_time: float = 5.0,
    check_auto_stand: str = "Auto Stand Surveys Only",
) -> pd.DataFrame:
    """
    Evaluates quality rules and tags suspicious/flagged entries.

    Rules:
    1. Travel Time < min_travel_time minutes
    2. Travel Cost < min_cost Rs (Walk mode: flags if cost > 0)
    3. Waiting Time < min_waiting_time minutes (Walk mode: flags if wait > 0)
    4. Origin equals Destination (after normalisation)
    5. Origin or Destination missing
    6. Missing 'Thane Auto Stand' in Origin or Destination
    """
    df = df.copy()

    def evaluate_row(row):
        flags = []
        tt   = row.get("travel_time_min")
        tc   = row.get("travel_cost_rs")
        wt   = row.get("waiting_time_min")
        orig = str(row.get("origin", "")).strip()
        dest = str(row.get("destination", "")).strip()
        orig_l = orig.lower()
        dest_l = dest.lower()

        mode_str = str(row.get("mode_of_travel", "")).strip().lower()
        is_walk  = any(k in mode_str for k in ["walk", "foot", "pedestrian"])

        # 1. Travel Time < threshold
        if pd.notna(tt) and tt < min_travel_time:
            flags.append(f"Travel Time < {min_travel_time}m ({tt} min)")

        # 2 & 3. Travel Cost and Waiting Time Check (Differentiated for Walk mode)
        if is_walk:
            # For walk mode: Cost and Waiting Time are naturally 0 (Free & no transit wait).
            # Only flag if surveyor erroneously entered cost > 0 or waiting > 0 for a walk trip.
            if pd.notna(tc) and tc > 0:
                flags.append(f"Walk Mode with Non-Zero Cost (₹{tc})")
            if pd.notna(wt) and wt > 0:
                flags.append(f"Walk Mode with Non-Zero Waiting Time ({wt} min)")
        else:
            # Motorized / Transit modes: Cost should not be < min_cost, Waiting should not be < min_wait
            if pd.notna(tc) and tc < min_cost:
                flags.append(f"Travel Cost < {min_cost} Rs (₹{tc})")
            if pd.notna(wt) and wt < min_waiting_time:
                flags.append(f"Waiting Time < {min_waiting_time}m ({wt} min)")

        # 4. Origin equals Destination
        if orig_l == dest_l and orig_l not in ["-", "nan", ""]:
            flags.append(f"Origin equals Destination ('{orig}')")

        # 5. Missing Origin or Destination
        if orig_l in ["-", "nan", ""] or dest_l in ["-", "nan", ""]:
            flags.append("Missing Origin or Destination")

        # 6. Check if Origin or Destination contains the survey station name
        #    The station name (from station_location) must appear in either
        #    Origin or Destination — case-insensitive, irrespective of sentence case.
        stn_raw = str(row.get("station_location", "")).strip()
        stn = stn_raw.lower()
        is_auto_stand_stn = "auto" in stn

        apply_auto_check = False
        if check_auto_stand == "All Records":
            apply_auto_check = True
        elif check_auto_stand == "Auto Stand Surveys Only" and is_auto_stand_stn:
            apply_auto_check = True

        if apply_auto_check and stn and stn not in ["-", "nan", "none"]:
            station_in_orig = stn in orig_l
            station_in_dest = stn in dest_l
            if not station_in_orig and not station_in_dest:
                flags.append(f"Missing '{stn_raw}' in Origin or Destination")

        # 7. Income bracket mismatch: Unemployed / Student / Housewife should have No Income
        occ_val  = str(row.get("occupation", "")).strip().lower()
        inc_val  = str(row.get("income", "")).strip().lower()
        _no_income_occupations = {"unemployed", "student", "housewife", "house wife", "house-wife"}
        _no_income_values      = {"no income", "noincome", "0", "nil", "none", "-", "nan", ""}
        if occ_val in _no_income_occupations and inc_val not in _no_income_values:
            flags.append(f"Income Mismatch: '{row.get('occupation')}' should have No Income (got '{row.get('income')}')")

        return "; ".join(flags) if flags else ""

    df["quality_flags"] = df.apply(evaluate_row, axis=1, result_type="reduce").fillna("").astype(str)
    df["is_flagged"]    = df["quality_flags"].str.strip() != ""
    return df





# ─────────────────────────────────────────────────────────────────────────────
# PREPARE DISPLAY TABLE
# ─────────────────────────────────────────────────────────────────────────────
def prepare_wtp_display(df: pd.DataFrame) -> pd.DataFrame:
    cols_order = [
        "Date_str",
        "start_time",
        "end_time",
        "entry_duration_sec",
        "surveyor",
        "contact",
        "station_location",
        "age",
        "gender",
        "occupation",
        "income",
        "origin",
        "destination",
        "mode_of_travel",
        "travel_time_min",
        "travel_cost_rs",
        "waiting_time_min",
        "travel_distance_km",
        "trip_frequency",
        "trip_purpose",
        "prt_willingness",
        "acceptable_prt_fare",
        "quality_flags",
    ]
    existing = [c for c in cols_order if c in df.columns]
    rename_dict = {
        "Date_str": "Date",
        "start_time": "Start Time",
        "end_time": "End Time",
        "entry_duration_sec": "Entry Duration (sec)",
        "surveyor": "Surveyor",
        "contact": "Contact",
        "station_location": "Survey Station",
        "age": "Age",
        "gender": "Gender",
        "occupation": "Occupation",
        "income": "Monthly Income",
        "origin": "Origin",
        "destination": "Destination",
        "mode_of_travel": "Current Mode",
        "travel_time_min": "Travel Time (min)",
        "travel_cost_rs": "Travel Cost (₹)",
        "waiting_time_min": "Waiting Time (min)",
        "travel_distance_km": "Distance (km)",
        "trip_frequency": "Trip Frequency",
        "trip_purpose": "Trip Purpose",
        "prt_willingness": "PRT Willingness",
        "acceptable_prt_fare": "Max Acceptable PRT Fare",
        "quality_flags": "Quality Flags",
    }
    return df[existing].rename(columns=rename_dict)


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR: FILE LOAD & LIVE TRAFFICLENZ SYNC
# ─────────────────────────────────────────────────────────────────────────────
st.sidebar.title("🚆 Thane WTP Survey")
st.sidebar.caption(f"Personal Rapid Transit (PRT) Dashboard | Job: `{DEFAULT_SURVEY_ID}`")
st.sidebar.markdown("---")

# ── Live TrafficLenz Downloader Section ──
st.sidebar.subheader("🔄 Live Data from TrafficLenz")

_downloader_available = False
_tl_config = None
try:
    from downloader import (
        config_from_secrets,
        config_is_valid,
        download_excel_bytes,
        has_saved_session,
        perform_interactive_login,
        TrafficLenzConfig,
    )
    _tl_config = config_from_secrets()
    _tl_config.survey_id = DEFAULT_SURVEY_ID
    _tl_ok, _tl_reason = config_is_valid(_tl_config)
    _downloader_available = _tl_ok
except Exception as _dl_err:
    _downloader_available = False
    _tl_reason = str(_dl_err)

if _downloader_available and _tl_config:
    _has_session = has_saved_session(_tl_config)
    if _has_session:
        st.sidebar.success("🟢 TrafficLenz Connected")
    else:
        st.sidebar.info("ℹ️ Using TrafficLenz credentials from Secrets")

    if st.sidebar.button("🔄 Sync Live Data", use_container_width=True, type="primary", help="Download latest survey data from TrafficLenz"):
        with st.spinner(f"Downloading latest WTP data for '{DEFAULT_SURVEY_ID}'..."):
            try:
                raw_b, ts = download_excel_bytes(_tl_config)
                st.session_state["wtp_raw_bytes"] = raw_b
                st.session_state["wtp_sync_ts"] = ts
                st.sidebar.success(f"Synced at {ts}")
                process_dataframe.clear()
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Sync error: {e}")

    if "wtp_sync_ts" in st.session_state:
        st.sidebar.caption(f"Last synced: **{st.session_state['wtp_sync_ts']}**")
else:
    st.sidebar.info("ℹ️ Live sync configured for job `DC513MH06`")

st.sidebar.markdown("---")

# ── Manual File Upload Fallback ──
st.sidebar.subheader("📂 Or Upload Excel File")
uploaded_file = st.sidebar.file_uploader("Upload WTP Survey Excel (.xlsx)", type=["xlsx"])

# Resolve file priority: Uploaded > Live Synced
file_bytes: bytes = b""
file_label: str = ""

if uploaded_file is not None:
    file_bytes = uploaded_file.read()
    file_label = uploaded_file.name
    st.sidebar.success(f"Loaded: {file_label}")
elif "wtp_raw_bytes" in st.session_state and st.session_state["wtp_raw_bytes"]:
    file_bytes = st.session_state["wtp_raw_bytes"]
    file_label = f"TrafficLenz Live ({st.session_state.get('wtp_sync_ts', 'Recent')})"
else:
    # ── FIRST RUN / EMPTY STATE (No data loaded automatically) ──
    st.title("🚆 Thane WTP (Personal Rapid Transit) Survey Dashboard")
    st.caption(f"Survey Job Code: **{DEFAULT_SURVEY_ID}** | TrafficLenz Monitoring Portal")
    st.markdown("---")

    st.info("👋 **No survey data loaded yet.** Please upload an Excel file or sync live from TrafficLenz to begin.")

    c_card1, c_card2 = st.columns(2)
    with c_card1:
        st.markdown(
            """
            ### 📂 Option 1: Upload Excel File
            Upload your survey results (`.xlsx`) using the **file uploader in the sidebar**.
            """
        )
    with c_card2:
        st.markdown(
            """
            ### 🔄 Option 2: Live Sync
            Click the **🔄 Sync Live** button in the sidebar to download real-time survey records from TrafficLenz.
            """
        )

    st.markdown("---")
    st.caption("ℹ️ Waiting for survey data input to initialize dashboard metrics and tabs...")
    st.stop()


# ─────────────────────────────────────────────────────────────────────────────
# LOAD DATA & RUN FLAGGING
# ─────────────────────────────────────────────────────────────────────────────
df_base = process_dataframe(file_bytes)

# Quality Threshold Controls (in sidebar expander)
with st.sidebar.expander("⚙️ Quality Flags Thresholds", expanded=False):
    t_travel_time  = st.slider("Min Travel Time (min)", 1, 30, 10,  help="Flag trips with travel time below this")
    t_travel_cost  = st.slider("Min Travel Cost (₹)",   0, 50, 10,  help="Flag fares below this amount")
    t_waiting_time = st.slider("Min Waiting Time (min)", 1.0, 15.0, 5.0, 0.5, help="Flag waiting times below this")
    t_auto_stand_scope = st.selectbox(
        "Station name in Origin / Destination",
        options=["Auto Stand Surveys Only", "All Records", "Off"],
        index=0,
        help="Flags entries where neither Origin nor Destination contains the survey station name (case-insensitive).",
    )

df_annotated = compute_wtp_quality_flags(
    df_base,
    min_travel_time=t_travel_time,
    min_cost=t_travel_cost,
    min_waiting_time=t_waiting_time,
    check_auto_stand=t_auto_stand_scope,
)


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR GLOBAL FILTERS
# ─────────────────────────────────────────────────────────────────────────────
st.sidebar.subheader("🎯 Global Filters")

# 1. Date Range
dates_list = df_annotated["Date_parsed"].dropna().sort_values().unique()
if len(dates_list) > 0:
    min_d = pd.to_datetime(dates_list[0]).date()
    max_d = pd.to_datetime(dates_list[-1]).date()
    sel_dates = st.sidebar.date_input(
        "Date Range",
        value=(min_d, max_d),
        help="Filter survey responses by date",
    )
    if isinstance(sel_dates, (tuple, list)) and len(sel_dates) == 2:
        d_from, d_to = sel_dates
        d_mask = (df_annotated["Date_parsed"].dt.date >= d_from) & (df_annotated["Date_parsed"].dt.date <= d_to)
    elif isinstance(sel_dates, (tuple, list)) and len(sel_dates) == 1:
        d_mask = df_annotated["Date_parsed"].dt.date == sel_dates[0]
    else:
        d_mask = pd.Series(True, index=df_annotated.index)
else:
    d_mask = pd.Series(True, index=df_annotated.index)

# 2. Time Range (15-min increments)
TIME_SLOTS = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 15, 30, 45)]
t_col1, t_col2 = st.sidebar.columns(2)
with t_col1:
    time_from_str = st.selectbox("Start Time From", options=TIME_SLOTS, index=0)
with t_col2:
    time_to_str = st.selectbox("Start Time To", options=TIME_SLOTS, index=len(TIME_SLOTS) - 1)

tf_h, tf_m = map(int, time_from_str.split(":"))
tt_h, tt_m = map(int, time_to_str.split(":"))
t_from_val = dtime(tf_h, tf_m)
t_to_val = dtime(tt_h, tt_m, 59)

def in_time_range(t):
    if not t:
        return True
    return t_from_val <= t <= t_to_val

time_mask = df_annotated["start_time_obj"].apply(in_time_range)

# Helper for multi-select with select all
def sidebar_multiselect(label: str, series: pd.Series, key: str) -> List[str]:
    opts = sorted([str(x) for x in series.dropna().unique() if str(x).strip() and str(x) != "-"])
    if not opts:
        return []
    sel = st.sidebar.multiselect(label, options=opts, default=opts, key=key)
    return sel

# 3. Station Location Filter
all_stations = df_annotated["station_location"]
sel_stations = sidebar_multiselect("Survey Station / Location", all_stations, "f_station")

# 4. Mode of Travel Filter
all_modes = df_annotated["mode_of_travel"]
sel_modes = sidebar_multiselect("Current Mode of Travel", all_modes, "f_mode")

# 5. PRT Willingness Filter
all_willingness = df_annotated["prt_willingness"]
sel_willingness = sidebar_multiselect("PRT Willingness", all_willingness, "f_prt")

# 6. Surveyor Filter
all_surveyors = df_annotated["surveyor"]
sel_surveyors = sidebar_multiselect("Surveyor", all_surveyors, "f_surveyor")

# 7. Quality Filter Option
quality_opt = st.sidebar.radio(
    "Data Quality Filter",
    options=["All Records", "Clean Entries Only", "Flagged Entries Only"],
    index=0,
    horizontal=True,
)

# Demographics Expander
with st.sidebar.expander("👤 Demographics Filters", expanded=False):
    sel_genders = st.multiselect("Gender", options=sorted(df_annotated["gender"].unique()), default=sorted(df_annotated["gender"].unique()))
    sel_incomes = st.multiselect("Income Level", options=sorted(df_annotated["income"].unique()), default=sorted(df_annotated["income"].unique()))
    sel_purposes = st.multiselect("Trip Purpose", options=sorted(df_annotated["trip_purpose"].unique()), default=sorted(df_annotated["trip_purpose"].unique()))

# ── Apply Filters ──
mask = (
    d_mask
    & time_mask
    & df_annotated["station_location"].isin(sel_stations if sel_stations else ["__NONE__"])
    & df_annotated["mode_of_travel"].isin(sel_modes if sel_modes else ["__NONE__"])
    & df_annotated["prt_willingness"].isin(sel_willingness if sel_willingness else ["__NONE__"])
    & df_annotated["surveyor"].isin(sel_surveyors if sel_surveyors else ["__NONE__"])
    & df_annotated["gender"].isin(sel_genders if sel_genders else ["__NONE__"])
    & df_annotated["income"].isin(sel_incomes if sel_incomes else ["__NONE__"])
    & df_annotated["trip_purpose"].isin(sel_purposes if sel_purposes else ["__NONE__"])
)

if quality_opt == "Clean Entries Only":
    mask = mask & (~df_annotated["is_flagged"])
elif quality_opt == "Flagged Entries Only":
    mask = mask & (df_annotated["is_flagged"])

filtered_df = df_annotated[mask].copy()

# Sidebar Filtered Metric Counter
total_all = len(df_annotated)
total_filt = len(filtered_df)
pct_filt = round((total_filt / total_all * 100), 1) if total_all else 0.0

st.sidebar.markdown("---")
st.sidebar.metric("Filtered Records", f"{total_filt:,}", f"{pct_filt}% of {total_all:,} total")

# ─────────────────────────────────────────────────────────────────────────────
# MAIN DASHBOARD HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.title("🚆 Thane WTP (Personal Rapid Transit) Survey Dashboard")
st.caption(
    f"Survey Dataset: **{file_label}** | Job Code: **{DEFAULT_SURVEY_ID}** | "
    f"Active Sample Count: **{total_filt:,}** records"
)



# ── Survey Site Location Map (Last Sample Coordinate) ──
if "Location" in filtered_df.columns and filtered_df["Location"].notna().any():
    valid_locs = filtered_df["Location"].dropna().astype(str).tolist()
    sample_loc = None
    for loc_str in reversed(valid_locs):
        loc_str = loc_str.strip()
        if "," in loc_str and loc_str.lower() not in ["-", "nan", "none", ""]:
            try:
                lat, lon = map(float, loc_str.split(","))
                sample_loc = (lat, lon)
                break
            except Exception:
                continue

    if sample_loc:
        lat, lon = sample_loc
        with st.expander(f"📍 Show Survey Site Map ({lat:.4f}, {lon:.4f})", expanded=False):
            st.map(pd.DataFrame({"lat": [lat], "lon": [lon]}))


# ─────────────────────────────────────────────────────────────────────────────
# TABS DEFINITION  (Monitoring-first order)
# ─────────────────────────────────────────────────────────────────────────────
tabs = st.tabs(
    [
        " 📊 Summary ",                # tabs[0] — surveyor progress, pace, stations at a glance
        " 👷 Surveyor Activity ",      # tabs[1] — per-enumerator deep dive
        " 🚩 Flagged Entries ",        # tabs[2] — data quality issues to action immediately
        " 📈 KPIs & Mode Share ",      # tabs[3] — overall KPI metrics & travel patterns
        " 🚆 PRT Willingness ",        # tabs[4] — willingness & fare analytics
        " 👥 Demographics ",           # tabs[5] — respondent profile
        " 📄 Raw Data ",               # tabs[6] — full records grid + CSV export
    ]
)



# ─────────────────────────────────────────────────────────────────────────────
# TAB 0: 📊 SUMMARY  — Survey progress, stations, enumerators, pace, alerts
# ─────────────────────────────────────────────────────────────────────────────
with tabs[0]:
    now_ist = datetime.now(IST)
    st.subheader("📊 Survey Progress Summary")
    st.caption(
        f"🕐 Last refreshed: **{now_ist.strftime('%d %b %Y  %I:%M:%S %p IST')}** — "
        f"Upload a new file or click **🔄 Sync Live** in the sidebar to update."
    )

    if filtered_df.empty:
        st.warning("⚠️ No survey records found. Upload an Excel file or sync from TrafficLenz.")
    else:
        # ── Pre-compute key numbers once ──────────────────────────────────────
        total_samples = total_filt
        n_stations    = filtered_df["station_location"].nunique()
        n_surveyors   = filtered_df["surveyor"].nunique()
        avg_dur_min   = round(filtered_df["survey_duration_mins"].mean(), 1) \
                        if filtered_df["survey_duration_mins"].notna().any() else 0.0

        # ── Row 1: Top-line KPI Cards ─────────────────────────────────────────
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("📋 Total Samples",     f"{total_samples:,}")
        k2.metric("📍 Survey Stations",   n_stations)
        k3.metric("👷 Active Surveyors",  n_surveyors)
        k4.metric("⏱️ Avg Entry Duration", f"{avg_dur_min} min")

        st.markdown("---")

        # ── Row 2: Station Breakdown (one metric card per station) ────────────
        st.markdown("### 📍 Samples per Survey Station")

        station_summary = (
            filtered_df.groupby("station_location")
            .agg(
                Samples      =("station_location", "size"),
                Surveyors    =("surveyor", "nunique"),
                First_Sample =("start_time", lambda x: min(x.dropna()) if len(x.dropna()) else "-"),
                Last_Sample  =("end_time",   lambda x: max(x.dropna()) if len(x.dropna()) else "-"),
            )
            .reset_index()
            .rename(columns={"station_location": "Station"})
            .sort_values("Samples", ascending=False)
        )

        # Show as metric cards (one per station) + a compact table below
        if len(station_summary) <= 6:
            st_cols = st.columns(len(station_summary))
            for i, row in station_summary.iterrows():
                st_cols[list(station_summary.index).index(i)].metric(
                    label=str(row["Station"]),
                    value=f"{int(row['Samples']):,}",
                )
        else:
            # Too many stations — just show table
            pass

        station_display = station_summary.copy()
        station_display.columns = [
            "Station", "Total Samples", "Surveyors on Station",
            "First Sample", "Last Sample"
        ]
        st.dataframe(station_display, use_container_width=True, hide_index=True)

        st.markdown("---")

        # ── Row 3: Enumerator Progress Table ─────────────────────────────────
        st.markdown("### 👷 Enumerator Progress Tracker")

        # Compute "minutes since last entry" to detect idle/missing surveyors
        def parse_time_to_today(t_str):
            """Convert a 'HH:MM:SS' string to a today-anchored datetime for idle comparison."""
            if not t_str or t_str == "-":
                return None
            try:
                parts = str(t_str).strip().split(":")
                h, m, s = int(parts[0]), int(parts[1]), int(float(parts[2])) if len(parts) > 2 else 0
                return now_ist.replace(hour=h, minute=m, second=s, microsecond=0, tzinfo=IST)
            except Exception:
                return None

        pace_rows = []
        for surveyor_name, grp in filtered_df.groupby("surveyor"):
            total_s   = len(grp)
            station_s = ", ".join(sorted(grp["station_location"].dropna().unique()))
            first_e   = min(grp["start_time"].dropna()) if grp["start_time"].dropna().size > 0 else "-"
            last_e    = max(grp["end_time"].dropna())   if grp["end_time"].dropna().size > 0   else "-"
            avg_d     = round(grp["survey_duration_mins"].mean(), 1) if grp["survey_duration_mins"].notna().any() else 0.0

            # Idle time: minutes since their last "end_time"
            last_dt = parse_time_to_today(last_e)
            if last_dt:
                idle_min = int((now_ist - last_dt).total_seconds() // 60)
                idle_min = max(idle_min, 0)
                if idle_min >= 60:
                    status = f"🔴 Inactive {idle_min}m"
                elif idle_min >= 30:
                    status = f"🟠 Idle {idle_min}m"
                elif idle_min >= 10:
                    status = f"🟡 Slow {idle_min}m"
                else:
                    status = f"🟢 Active ({idle_min}m ago)"
                idle_label = f"{idle_min} min ago"
            else:
                status     = "⚪ Unknown"
                idle_label = "-"

            pace_rows.append({
                "Surveyor":            surveyor_name,
                "Station(s)":         station_s,
                "Samples Collected":  total_s,
                "First Entry":        first_e,
                "Last Entry":         last_e,
                "Last Seen":          idle_label,
                "Avg Duration (min)": avg_d,
                "Status":             status,
            })


        pace_df = pd.DataFrame(pace_rows).sort_values("Samples Collected", ascending=False)

        # Colour rows by activity status only (Dark & Light theme friendly)
        def colour_pace(row):
            status = row.get("Status", "")
            if "🔴" in str(status):
                # Dark red background with bright readable text for dark & light mode
                return ["background-color: rgba(239, 68, 68, 0.25); color: #fca5a5; font-weight: 500;"] * len(row)
            elif "🟠" in str(status):
                # Dark orange background with bright readable text
                return ["background-color: rgba(249, 115, 22, 0.25); color: #fdba74; font-weight: 500;"] * len(row)
            return [""] * len(row)


        st.dataframe(
            pace_df.style.apply(colour_pace, axis=1),
            use_container_width=True,
            hide_index=True,
        )

        # ── Missing / Inactive Surveyor Alert ────────────────────────────────
        inactive_surveyors = pace_df[pace_df["Status"].str.startswith("🔴") | pace_df["Status"].str.startswith("🟠")]

        if not inactive_surveyors.empty:
            st.warning(
                f"⚠️ **{len(inactive_surveyors)} surveyor(s) have not submitted an entry in the last 30 minutes:** "
                + ", ".join(f"**{r}**" for r in inactive_surveyors["Surveyor"].tolist())
            )

        st.markdown("---")

        # ── Row 4: Hourly Survey Collection Pace ─────────────────────────────
        st.markdown("### 📈 Hourly Survey Collection Pace")

        hourly = (
            filtered_df.dropna(subset=["start_hour"])
            .groupby("start_hour")
            .size()
            .reset_index(name="Count")
            .sort_values("start_hour")
        )

        if not hourly.empty:
            hourly["Hour"] = hourly["start_hour"].apply(lambda h: f"{int(h):02d}:00")

            # Highlight current hour
            current_hour = now_ist.hour
            hourly["colour"] = hourly["start_hour"].apply(
                lambda h: "#ef4444" if int(h) == current_hour else PRIMARY_COLOR
            )

            fig_h = px.bar(
                hourly,
                x="Hour",
                y="Count",
                title="Samples Collected per Hour  (red bar = current hour)",
                color="colour",
                color_discrete_map="identity",
                labels={"Hour": "Hour of Day", "Count": "Samples"},
                text="Count",
            )
            fig_h.update_traces(textposition="outside")
            fig_h.update_layout(
                showlegend=False,
                margin=dict(t=50, b=30, l=20, r=20),
                plot_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(gridcolor="#e2e8f0"),
            )
            st.plotly_chart(fig_h, use_container_width=True)
        else:
            st.info("No start time data available for the hourly chart.")



# ─────────────────────────────────────────────────────────────────────────────
# TAB 1: 👷 SURVEYOR ACTIVITY  (Deep-dive per enumerator)
# ─────────────────────────────────────────────────────────────────────────────
with tabs[1]:
    st.subheader("👷 Surveyor Activity & Productivity")

    if filtered_df.empty:
        st.warning("No records match current filter.")
    else:
        s_sub1, s_sub2 = st.tabs(["📊 Overview", "👤 Individual Surveyor"])

        with s_sub1:
            s_summary = (
                filtered_df.groupby("surveyor")
                .agg(
                    Total_Surveys=("surveyor", "size"),
                    PRT_Yes=("prt_willingness", lambda x: int(x.str.strip().str.lower().eq("yes").sum())),
                    Stations=("station_location", lambda x: ", ".join(sorted(set(x.dropna().astype(str))))),
                    First_Entry=("start_time", lambda x: min(x.dropna()) if len(x.dropna()) else "-"),
                    Last_Entry=("end_time", lambda x: max(x.dropna()) if len(x.dropna()) else "-"),
                    Avg_Duration_Min=("survey_duration_mins", "mean"),
                    Min_Duration_Sec=("entry_duration_sec", "min"),
                    Flagged_Entries=("is_flagged", "sum"),
                )
                .reset_index()
                .rename(
                    columns={
                        "surveyor": "Surveyor",
                        "Total_Surveys": "Total Surveys",
                        "PRT_Yes": "PRT Willing (Yes)",
                        "Stations": "Stations Covered",
                        "First_Entry": "First Entry",
                        "Last_Entry": "Last Entry",
                        "Avg_Duration_Min": "Avg Duration (min)",
                        "Min_Duration_Sec": "Fastest Entry (sec)",
                        "Flagged_Entries": "⚠️ Flagged",
                    }
                )
                .sort_values("Total Surveys", ascending=False)
            )
            s_summary["Avg Duration (min)"] = s_summary["Avg Duration (min)"].round(2)

            st.dataframe(s_summary, use_container_width=True)

            fig_s = px.bar(
                s_summary,
                x="Surveyor",
                y="Total Surveys",
                color="⚠️ Flagged",
                title="Surveys per Enumerator (coloured by Flagged Count)",
                color_continuous_scale="OrRd",
                text="Total Surveys",
            )
            fig_s.update_traces(textposition="outside")
            st.plotly_chart(fig_s, use_container_width=True)

        with s_sub2:
            surveyors_list = sorted(filtered_df["surveyor"].unique())
            sel_s = st.selectbox("Select Surveyor to Inspect", options=surveyors_list, key="s_individual")
            if sel_s:
                s_records = filtered_df[filtered_df["surveyor"] == sel_s]
                s_flagged = s_records[s_records["is_flagged"]]

                sc1, sc2, sc3, sc4 = st.columns(4)
                sc1.metric("Total Surveys", len(s_records))
                sc2.metric("Avg Duration", f"{round(s_records['survey_duration_mins'].mean(), 1) if s_records['survey_duration_mins'].notna().any() else 0} min")
                sc3.metric("Flagged", int(s_records["is_flagged"].sum()))
                sc4.metric("PRT Yes", int(s_records["prt_willingness"].str.strip().str.lower().eq("yes").sum()))

                if not s_flagged.empty:
                    st.warning(f"⚠️ {len(s_flagged)} flagged entries for {sel_s}")
                    st.dataframe(prepare_wtp_display(s_flagged), use_container_width=True)
                    st.markdown("---")

                st.markdown(f"**All Survey Records — {sel_s} ({len(s_records)} total)**")
                s_display = prepare_wtp_display(s_records)
                st.dataframe(s_display, use_container_width=True)
                st.download_button(
                    f"⬇️ Download {sel_s} Records CSV",
                    data=make_download_csv(s_display),
                    file_name=f"{sel_s.lower().replace(' ','_')}_wtp_records.csv",
                    mime="text/csv",
                )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2: 🚩 FLAGGED ENTRIES  (Priority quality audit tab)
# ─────────────────────────────────────────────────────────────────────────────
with tabs[2]:
    st.subheader("🚩 Flagged Entries & Data Quality Audit")
    st.caption(
        f"Active thresholds — Travel Time < **{t_travel_time}m** | "
        f"Travel Cost < **₹{t_travel_cost}** (Walk=₹0) | "
        f"Waiting Time < **{t_waiting_time}m** (Walk=0m) | "
        f"Origin = Destination | Missing OD | Station name must appear in Origin or Destination ({t_auto_stand_scope})"
    )

    flagged_df = filtered_df[filtered_df["is_flagged"]].copy()

    # Ensure quality_flags is always a string Series before .str accessor
    _qf = filtered_df["quality_flags"].fillna("").astype(str)

    tt_flags_cnt        = int(_qf.str.contains("Travel Time <",                  case=False, na=False).sum())
    tc_flags_cnt        = int(_qf.str.contains(r"Travel Cost <|Non-Zero Cost",   case=False, na=False, regex=True).sum())
    wt_flags_cnt        = int(_qf.str.contains(r"Waiting Time <|Non-Zero Wait",  case=False, na=False, regex=True).sum())
    od_eq_cnt           = int(_qf.str.contains("equals Destination",             case=False, na=False).sum())
    missing_od_cnt      = int(_qf.str.contains("Missing Origin",                 case=False, na=False).sum())
    auto_stand_cnt      = int(_qf.str.contains("in Origin or Destination",       case=False, na=False).sum())
    income_mismatch_cnt = int(_qf.str.contains("Income Mismatch",                case=False, na=False).sum())

    q1, q2, q3, q4, q5, q6, q7 = st.columns(7)
    q1.metric("Total Flagged",            len(flagged_df),
              f"{round(len(flagged_df)/total_filt*100,1) if total_filt else 0}%",
              delta_color="inverse")
    q2.metric(f"Time < {t_travel_time}m", tt_flags_cnt)
    q3.metric(f"Cost < ₹{t_travel_cost}", tc_flags_cnt)
    q4.metric(f"Wait < {t_waiting_time}m",wt_flags_cnt)
    q5.metric("OD Errors / Missing",      od_eq_cnt + missing_od_cnt)
    q6.metric("Missing Auto Stand",       auto_stand_cnt)
    q7.metric("Income Mismatch",          income_mismatch_cnt)

    st.markdown("---")

    if flagged_df.empty:
        st.success("🎉 No flagged or suspicious survey entries found at current thresholds!")
    else:
        # ── 1. Flagged by Travel Time, Cost or Waiting Time Table ─────────────
        tcw_mask = _qf.str.contains(
            r"Travel Time <|Travel Cost <|Waiting Time <|Walk Mode with", case=False, na=False, regex=True
        )
        tcw_rows = filtered_df[tcw_mask].copy()

        if not tcw_rows.empty:
            st.markdown(f"### ⏱️ Flagged by Travel Time, Cost or Waiting Time ({len(tcw_rows)} entries)")
            st.caption(
                f"Entries flagged where Travel Time < **{t_travel_time}m**, "
                f"Travel Cost < **₹{t_travel_cost}** (or Walk mode cost > ₹0), "
                f"or Waiting Time < **{t_waiting_time}m** (or Walk mode waiting > 0m)."
            )
            display_cols_tcw = [
                "Date_str", "start_time", "end_time", "surveyor", "station_location",
                "mode_of_travel", "travel_time_min", "travel_cost_rs", "waiting_time_min",
                "travel_distance_km", "origin", "destination", "quality_flags"
            ]
            tcw_display = tcw_rows[[c for c in display_cols_tcw if c in tcw_rows.columns]].copy()
            col_labels_tcw = {
                "Date_str": "Date", "start_time": "Start Time", "end_time": "End Time",
                "surveyor": "Surveyor", "station_location": "Station",
                "mode_of_travel": "Mode", "travel_time_min": "Travel Time (min)",
                "travel_cost_rs": "Travel Cost (₹)", "waiting_time_min": "Waiting Time (min)",
                "travel_distance_km": "Distance (km)",
                "origin": "Origin", "destination": "Destination", "quality_flags": "Flags Triggered",
            }
            tcw_display.rename(columns={k: v for k, v in col_labels_tcw.items() if k in tcw_display.columns}, inplace=True)
            st.dataframe(tcw_display, use_container_width=True, hide_index=True)
            st.markdown("---")

        # ── 2. OD Pair Errors (Origin = Destination or Missing) Table ─────────
        od_err_mask = _qf.str.contains("equals Destination|Missing Origin", case=False, na=False)
        od_err_rows = filtered_df[od_err_mask].copy()

        if not od_err_rows.empty:
            st.markdown(f"### 🔁 Origin = Destination or Missing Location ({len(od_err_rows)} entries)")
            st.caption("Entries where Origin equals Destination or where Origin/Destination is blank.")
            display_cols_od = [
                "Date_str", "start_time", "end_time", "surveyor", "station_location",
                "origin", "destination", "travel_time_min", "travel_cost_rs", "prt_willingness", "quality_flags"
            ]
            od_display = od_err_rows[display_cols_od].copy()
            od_display.columns = [
                "Date", "Start Time", "End Time", "Surveyor", "Station",
                "Origin", "Destination", "Travel Time (min)", "Travel Cost (₹)", "PRT Willingness", "Flags"
            ]
            st.dataframe(od_display, use_container_width=True, hide_index=True)
            st.markdown("---")

        # ── 3. Missing Station Name in Origin / Destination Table ────────────
        auto_stand_mask = _qf.str.contains("in Origin or Destination", case=False, na=False)
        auto_stand_rows = filtered_df[auto_stand_mask].copy()

        if not auto_stand_rows.empty:
            st.markdown(f"### 🛺 Station Name Missing in Origin / Destination ({len(auto_stand_rows)} entries)")
            st.caption(
                "Entries flagged because neither Origin nor Destination contains the **Survey Station name** "
                "(case-insensitive match)."
            )
            display_cols_auto = [
                "Date_str", "start_time", "end_time", "surveyor", "station_location",
                "origin", "destination", "travel_time_min", "travel_cost_rs", "prt_willingness", "quality_flags"
            ]
            auto_display = auto_stand_rows[display_cols_auto].copy()
            auto_display.columns = [
                "Date", "Start Time", "End Time", "Surveyor", "Station",
                "Origin", "Destination", "Travel Time (min)", "Travel Cost (₹)", "PRT Willingness", "Flags"
            ]
            st.dataframe(auto_display, use_container_width=True, hide_index=True)
            st.markdown("---")

        # ── 4. Income Bracket Mismatch Table ─────────────────────────────────
        income_mask = _qf.str.contains("Income Mismatch", case=False, na=False)
        income_rows = filtered_df[income_mask].copy()

        if not income_rows.empty:
            st.markdown(f"### 💰 Income Bracket Mismatch ({len(income_rows)} entries)")
            st.caption(
                "Entries where **Unemployed**, **Student**, or **Housewife** respondents "
                "have an income bracket selected other than **No Income**."
            )
            display_cols_income = [
                "Date_str", "start_time", "end_time", "surveyor", "station_location",
                "occupation", "income", "quality_flags"
            ]
            income_display = income_rows[[c for c in display_cols_income if c in income_rows.columns]].copy()
            col_labels_inc = {
                "Date_str": "Date", "start_time": "Start Time", "end_time": "End Time",
                "surveyor": "Surveyor", "station_location": "Station",
                "occupation": "Occupation", "income": "Income Bracket", "quality_flags": "Flags",
            }
            income_display.rename(columns={k: v for k, v in col_labels_inc.items() if k in income_display.columns}, inplace=True)
            st.dataframe(income_display, use_container_width=True, hide_index=True)
            st.markdown("---")

        # ── Flagged by Surveyor Summary ───────────────────────────────────────
        st.markdown("### 👷 Flagged Count by Surveyor")
        surveyor_flags = (
            flagged_df.groupby("surveyor")
            .agg(
                Flagged_Total    =("surveyor",       "size"),
                Time_Flags       =("quality_flags",  lambda x: sum("Travel Time <"  in str(f) for f in x)),
                Cost_Flags       =("quality_flags",  lambda x: sum("Travel Cost <"  in str(f) for f in x)),
                Wait_Flags       =("quality_flags",  lambda x: sum("Waiting Time <" in str(f) for f in x)),
                OD_Eq_Flags      =("quality_flags",  lambda x: sum("equals Destination" in str(f) or "Missing Origin" in str(f) for f in x)),
                Auto_Stand_Flags =("quality_flags",  lambda x: sum("in Origin or Destination" in str(f) for f in x)),
                Income_Flags     =("quality_flags",  lambda x: sum("Income Mismatch" in str(f) for f in x)),
            )
            .reset_index()
            .rename(columns={
                "surveyor":          "Surveyor",
                "Flagged_Total":     "Total Flagged",
                "Time_Flags":        f"Time < {t_travel_time}m",
                "Cost_Flags":        f"Cost < ₹{t_travel_cost}",
                "Wait_Flags":        f"Wait < {t_waiting_time}m",
                "OD_Eq_Flags":       "OD Errors",
                "Auto_Stand_Flags":  "Missing Terminal",
                "Income_Flags":      "Income Mismatch",
            })
            .sort_values("Total Flagged", ascending=False)
        )

        st.dataframe(surveyor_flags, use_container_width=True, hide_index=True)


        st.markdown(f"---\n### 📋 All Flagged Entries ({len(flagged_df)} records)")
        flagged_display = prepare_wtp_display(flagged_df)
        st.dataframe(flagged_display, use_container_width=True)
        st.download_button(
            "⬇️ Download Flagged Records (CSV)",
            data=make_download_csv(flagged_display),
            file_name="thane_wtp_flagged_entries.csv",
            mime="text/csv",
        )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3: 📊 SURVEY SUMMARY & KPIS
# ─────────────────────────────────────────────────────────────────────────────
with tabs[3]:
    st.subheader("📊 Thane WTP Survey Summary & KPIs")

    if filtered_df.empty:
        st.warning("No survey records match the current filter selection.")
    else:
        prt_yes = int(filtered_df["prt_willingness"].str.strip().str.lower().eq("yes").sum())
        prt_no = int(filtered_df["prt_willingness"].str.strip().str.lower().eq("no").sum())
        prt_maybe = int(filtered_df["prt_willingness"].str.strip().str.lower().str.contains("maybe").sum())
        pct_yes = round((prt_yes / total_filt * 100), 1) if total_filt else 0.0
        pct_no = round((prt_no / total_filt * 100), 1) if total_filt else 0.0
        pct_maybe = round((prt_maybe / total_filt * 100), 1) if total_filt else 0.0

        avg_travel_time = round(filtered_df["travel_time_min"].mean(), 1) if filtered_df["travel_time_min"].notna().any() else 0
        avg_travel_cost = round(filtered_df["travel_cost_rs"].mean(), 1) if filtered_df["travel_cost_rs"].notna().any() else 0
        avg_waiting_time = round(filtered_df["waiting_time_min"].mean(), 1) if filtered_df["waiting_time_min"].notna().any() else 0
        avg_distance = round(filtered_df["travel_distance_km"].mean(), 1) if filtered_df["travel_distance_km"].notna().any() else 0

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Total Surveys", f"{total_filt:,}")
        c2.metric("PRT — Yes", f"{prt_yes}", f"{pct_yes}%")
        c3.metric("PRT — No", f"{prt_no}", f"{pct_no}%")
        c4.metric("PRT — Maybe", f"{prt_maybe}", f"{pct_maybe}%")
        c5.metric("Avg Travel Time", f"{avg_travel_time} min")
        c6.metric("Avg Travel Cost", f"₹{avg_travel_cost}")

        c7, c8, c9, c10, c11, c12 = st.columns(6)
        c7.metric("Avg Waiting Time", f"{avg_waiting_time} min")
        c8.metric("Avg Distance", f"{avg_distance} km")
        c9.metric("Active Surveyors", filtered_df["surveyor"].nunique())
        c10.metric("Survey Stations", filtered_df["station_location"].nunique())
        c11.metric("Flagged Entries", int(filtered_df["is_flagged"].sum()), delta_color="inverse")
        c12.metric("Avg Duration", f"{round(filtered_df['survey_duration_mins'].mean(), 1) if filtered_df['survey_duration_mins'].notna().any() else 0} min")

        st.markdown("---")

        col_ch1, col_ch2 = st.columns(2)

        with col_ch1:
            willingness_counts = filtered_df["prt_willingness"].str.strip().value_counts().reset_index()
            willingness_counts.columns = ["Willingness", "Count"]
            color_map = {"Yes": SUCCESS_COLOR, "No": DANGER_COLOR, "Maybe": WARNING_COLOR, "Not applicable for my journey": GRAY_COLOR}
            fig_w = px.pie(
                willingness_counts, names="Willingness", values="Count", hole=0.45,
                title="PRT Willingness", color="Willingness", color_discrete_map=color_map,
            )
            fig_w.update_traces(textinfo="percent+label")
            fig_w.update_layout(showlegend=False)
            st.plotly_chart(fig_w, use_container_width=True)

        with col_ch2:
            mode_counts = filtered_df["mode_of_travel"].value_counts().reset_index()
            mode_counts.columns = ["Mode", "Count"]
            fig_m = px.bar(
                mode_counts, x="Count", y="Mode", orientation="h",
                title="Current Mode of Travel Share", color_discrete_sequence=[SECONDARY_COLOR],
            )
            fig_m.update_layout(yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig_m, use_container_width=True)

        col_ch3, col_ch4 = st.columns(2)

        with col_ch3:
            purpose_counts = filtered_df["trip_purpose"].value_counts().reset_index()
            purpose_counts.columns = ["Purpose", "Count"]
            fig_p = px.pie(
                purpose_counts, names="Purpose", values="Count",
                title="Trip Purpose", color_discrete_sequence=px.colors.qualitative.Safe,
            )
            fig_p.update_traces(textinfo="percent+label")
            st.plotly_chart(fig_p, use_container_width=True)

        with col_ch4:
            freq_counts = filtered_df["trip_frequency"].value_counts().reset_index()
            freq_counts.columns = ["Frequency", "Count"]
            fig_fr = px.bar(
                freq_counts, x="Frequency", y="Count",
                title="Trip Frequency", color_discrete_sequence=[PRIMARY_COLOR],
            )
            st.plotly_chart(fig_fr, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4: 🚆 PRT WILLINGNESS & FARE SENSITIVITY
# ─────────────────────────────────────────────────────────────────────────────
with tabs[4]:
    st.subheader("🚆 PRT Willingness, Mode Shift & Price Sensitivity")

    if filtered_df.empty:
        st.warning("No records match current filter.")
    else:
        st_sub1, st_sub2, st_sub3 = st.tabs([
            "🔄 Willingness by Current Mode",
            "💰 Willingness by Income Level",
            "🏷️ Acceptable PRT Fare Distribution",
        ])

        with st_sub1:
            st.markdown("### Potential Shift to PRT by Current Mode")
            mode_prt = (
                filtered_df.groupby(["mode_of_travel", "prt_willingness"])
                .size().reset_index(name="Surveys")
            )
            fig_mp = px.bar(
                mode_prt, x="mode_of_travel", y="Surveys", color="prt_willingness",
                title="PRT Shift Willingness by Current Transport Mode",
                barmode="stack",
                labels={"mode_of_travel": "Current Mode", "prt_willingness": "PRT Willingness"},
                color_discrete_map={"Yes": SUCCESS_COLOR, "No": DANGER_COLOR, "Maybe": WARNING_COLOR},
            )
            fig_mp.update_layout(xaxis_tickangle=-30)
            st.plotly_chart(fig_mp, use_container_width=True)
            ct_mode = pd.crosstab(filtered_df["mode_of_travel"], filtered_df["prt_willingness"].str.strip(), margins=True, margins_name="Total")
            st.markdown("#### Mode vs Willingness Cross-Tabulation")
            st.dataframe(ct_mode, use_container_width=True)

        with st_sub2:
            st.markdown("### PRT Willingness across Income Tiers")
            inc_prt = (
                filtered_df.groupby(["income", "prt_willingness"])
                .size().reset_index(name="Surveys")
            )
            fig_ip = px.bar(
                inc_prt, x="income", y="Surveys", color="prt_willingness",
                title="Willingness by Monthly Income", barmode="group",
                labels={"income": "Monthly Income (Rs)", "prt_willingness": "Willingness"},
                color_discrete_map={"Yes": SUCCESS_COLOR, "No": DANGER_COLOR, "Maybe": WARNING_COLOR},
            )
            st.plotly_chart(fig_ip, use_container_width=True)

        with st_sub3:
            st.markdown("### Maximum Acceptable PRT Fare (Rs)")
            st.caption("Only Yes / Maybe respondents.")
            willing_subset = filtered_df[filtered_df["prt_willingness"].str.strip().str.lower().isin(["yes", "maybe"])]
            fare_counts = willing_subset["acceptable_prt_fare"].value_counts().reset_index()
            fare_counts.columns = ["Acceptable Fare Range", "Respondent Count"]
            if not fare_counts.empty:
                fig_f = px.bar(
                    fare_counts, x="Acceptable Fare Range", y="Respondent Count",
                    title="Maximum Acceptable PRT Fare Distribution",
                    color="Acceptable Fare Range",
                    color_discrete_sequence=["#4338ca", "#4f46e5", "#6366f1", "#818cf8", "#a5b4fc"],
                )
                st.plotly_chart(fig_f, use_container_width=True)
                st.dataframe(fare_counts, use_container_width=True)
            else:
                st.info("No acceptable fare data for willing users.")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 5: 👥 DEMOGRAPHICS & PROFILE
# ─────────────────────────────────────────────────────────────────────────────
with tabs[5]:
    st.subheader("👥 Commuter Demographics & Socio-Economic Profile")

    if filtered_df.empty:
        st.warning("No records match current filter.")
    else:
        d_col1, d_col2 = st.columns(2)
        with d_col1:
            age_counts = filtered_df["age"].value_counts().reset_index()
            age_counts.columns = ["Age Group", "Count"]
            fig_age = px.bar(age_counts, x="Age Group", y="Count", title="Age Group Distribution", color_discrete_sequence=[PRIMARY_COLOR])
            st.plotly_chart(fig_age, use_container_width=True)

        with d_col2:
            gender_counts = filtered_df["gender"].value_counts().reset_index()
            gender_counts.columns = ["Gender", "Count"]
            fig_gen = px.pie(gender_counts, names="Gender", values="Count", title="Gender Ratio", color_discrete_sequence=[PRIMARY_COLOR, PURPLE_COLOR, GRAY_COLOR])
            fig_gen.update_traces(textinfo="percent+label")
            st.plotly_chart(fig_gen, use_container_width=True)

        d_col3, d_col4 = st.columns(2)
        with d_col3:
            occ_counts = filtered_df["occupation"].value_counts().reset_index()
            occ_counts.columns = ["Occupation", "Count"]
            fig_occ = px.bar(occ_counts, x="Occupation", y="Count", title="Occupation Breakdown", color_discrete_sequence=[SECONDARY_COLOR])
            st.plotly_chart(fig_occ, use_container_width=True)

        with d_col4:
            income_counts = filtered_df["income"].value_counts().reset_index()
            income_counts.columns = ["Income Level", "Count"]
            fig_inc = px.bar(income_counts, x="Income Level", y="Count", title="Monthly Income Distribution", color_discrete_sequence=[PURPLE_COLOR])
            st.plotly_chart(fig_inc, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 6: 📄 RAW DATA (full grid + CSV export)
# ─────────────────────────────────────────────────────────────────────────────
with tabs[6]:
    st.subheader("📄 Filtered Raw Survey Records")
    st.caption(f"Showing all **{len(filtered_df):,}** records matching active filters.")

    raw_display = prepare_wtp_display(filtered_df)
    st.dataframe(raw_display, use_container_width=True)
    st.download_button(
        "⬇️ Download Filtered Data CSV",
        data=make_download_csv(raw_display),
        file_name="filtered_thane_wtp_survey_data.csv",
        mime="text/csv",
    )

