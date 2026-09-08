"""
app.py — Delhi OD Passenger / Goods Survey Dashboard
====================================================

Corrected logic:
- Short / suspicious entry check uses entry duration:
      end_time - start_time
  NOT gap from previous entry.

Run:
    streamlit run app.py
"""

from __future__ import annotations

import io
import json
import os
import re
import urllib.parse
from datetime import datetime, time, timezone, timedelta
from typing import Any

IST = timezone(timedelta(hours=5, minutes=30))

import difflib
import functools
from rapidfuzz import fuzz, process
import requests
import pandas as pd
import plotly.express as px
import pydeck as pdk
import xml.etree.ElementTree as ET
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Delhi OD Passenger / Goods Survey Dashboard",
    page_icon="🚦",
    layout="wide",
)


# ─────────────────────────────────────────────────────────────────────────────
# OPTIONAL PASSWORD AUTH
# ─────────────────────────────────────────────────────────────────────────────
def get_app_password() -> str | None:
    try:
        return st.secrets.get("APP_PASSWORD", None)
    except StreamlitSecretNotFoundError:
        return None
    except FileNotFoundError:
        return None


def check_password() -> None:
    app_password = get_app_password()

    if not app_password:
        return

    def password_entered() -> None:
        if st.session_state.get("password") == app_password:
            st.session_state["authenticated"] = True
        else:
            st.session_state["authenticated"] = False

    if "authenticated" not in st.session_state:
        st.text_input(
            "Enter password",
            type="password",
            on_change=password_entered,
            key="password",
        )
        st.stop()

    if not st.session_state["authenticated"]:
        st.text_input(
            "Enter password",
            type="password",
            on_change=password_entered,
            key="password",
        )
        st.error("Incorrect password")
        st.stop()


check_password()


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
PRIMARY_COLOR = "#0057A8"
SECONDARY = "#00A3E0"
SUCCESS = "#28A745"
WARNING = "#FFC107"
DANGER = "#DC3545"
GREY = "#6C757D"

SHEET_NAME = "Survey Results"

DEFAULT_FILE = (
    "DC513DL01 _ Delhi OD_Passenger_ Goods  "
    "OD_2026-08-24 02_42_22__survey_results.xlsx"
)


# ─────────────────────────────────────────────────────────────────────────────
# DELHI COLUMN MAPPING
# ─────────────────────────────────────────────────────────────────────────────
COL_DATE = "Date"
COL_START = "start_time"
COL_END = "end_time"
COL_USERNAME = "Username"
COL_LOCATION = "Location"
COL_SURVEYOR = "Remarks1"
COL_CONTACT = "Remarks2"

COL_DIRECTION = "0.Direction"
COL_SURVEY_TYPE = "1.Survey Type"

# Passenger
COL_PASS_VEHICLE_PRIMARY = "1a1.Vehicle Type"
COL_PASS_VEHICLE_ALT = "1a8.Vehicle Type"
COL_PASS_ORIGIN = "1a2.Trip Origin"
COL_PASS_DESTINATION = "1a3.Trip Destination"
COL_PASS_SHIFT = (
    "1a4.Are you likely to Shift to Proposed Lajpat Nagar - Chirag Delhi - "
    "Khanpur Elevated Corridor?"
)
COL_PASS_FREQUENCY = "1a5.Trip Frequency"
COL_PASS_PURPOSE = "1a6.Trip Purpose"
COL_PASS_OTHER = "1a7.If others please specify"

PASSENGER_OCCUPANCY_COLS = [
    "1a8a1.Occupancy (including Driver)",
    "1a8b1.Occupancy (including Driver)",
    "1a8c1.Occupancy (including Driver)",
    "1a8d1.Occupancy (including Driver)",
    "1a8h1.Occupancy (including Driver)",
    "1a8i1.Occupancy (including Driver)",
]

PASSENGER_BUS_PERCENT_COLS = [
    "1a8e2.Sitting Percentage",
    "1a8e3.Mention the Occupancy (In Percentage)",
    "1a8f2.Sitting Percentage",
    "1a8f3.Mention the Occupancy (In Percentage)",
    "1a8g2.Sitting Percentage",
    "1a8g3.Mention the Occupancy (In Percentage)",
]

# Goods
COL_GOODS_VEHICLE = "1b1.Vehicle Type"
COL_GOODS_ORIGIN = "1b2.Trip Origin"
COL_GOODS_DESTINATION = "1b3.Trip Destination"
COL_GOODS_SHIFT = (
    "1b4.Are you likely to Shift to Proposed Lajpat Nagar - Chirag Delhi - "
    "Khanpur Elevated Corridor?"
)
COL_GOODS_FREQUENCY = "1b5.Trip Frequency"
COL_GOODS_COMMODITY = "1b6.Commodity Type"

INVALID_TEXT = {
    "",
    "-",
    "nan",
    "none",
    "null",
    "na",
    "n/a",
    "nil",
    ".",
}


# ─────────────────────────────────────────────────────────────────────────────
# SUSPICIOUS OD LOGIC
# Only consider Delhi, New Delhi, Gurugram/Gurgaon, Noida
# ─────────────────────────────────────────────────────────────────────────────
SPECIFIC_LOCATION_HINTS = [
    r"\bsector\s*[-]?\s*\d+\b",
    r"\bsec\s*[-]?\s*\d+\b",
    r"\bphase\s*[-]?\s*\d+\b",
    r"\bblock\s+[a-z0-9]+\b",
    r"\b[a-z]+\s+nagar\b",
    r"\b[a-z]+\s+vihar\b",
    r"\b[a-z]+\s+pur\b",
    r"\b[a-z]+\s+puri\b",
    r"\b[a-z]+\s+colony\b",
    r"\b[a-z]+\s+enclave\b",
    r"\b[a-z]+\s+market\b",
    r"\b[a-z]+\s+road\b",
    r"\b[a-z]+\s+gate\b",
    r"\b[a-z]+\s+hospital\b",
    r"\b[a-z]+\s+school\b",
    r"\b[a-z]+\s+metro\b",
    r"\b[a-z]+\s+park\b",
    r"\b[a-z]+\s+place\b",
    r"\b[a-z]+\s+station\b",
    r"\baiims\b",
    r"\bigi\b",
    r"\bisbt\b",
    r"\biit\b",
]


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def safe_get(row: pd.Series, col: str, default: Any = pd.NA) -> Any:
    return row.get(col, default) if col in row.index else default


def clean_text(value: Any, title_case: bool = False) -> Any:
    if value is None or pd.isna(value):
        return pd.NA

    text = str(value).strip()
    text = " ".join(text.split())

    if text.lower() in INVALID_TEXT:
        return pd.NA

    return text.title() if title_case else text


def clean_location(value: Any) -> Any:
    return clean_text(value, title_case=True)


def first_valid(row: pd.Series, columns: list[str], title_case: bool = False) -> Any:
    for col in columns:
        if col in row.index:
            val = clean_text(row.get(col), title_case=title_case)
            if pd.notna(val):
                return val
    return pd.NA


def parse_date_series(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, dayfirst=True, errors="coerce")


def parse_time_value(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None

    if isinstance(value, time):
        return value

    if isinstance(value, datetime):
        return value.time()

    parsed = pd.to_datetime(str(value), errors="coerce")

    if pd.isna(parsed):
        return None

    return parsed.time()


def time_to_seconds(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None

    return value.hour * 3600 + value.minute * 60 + value.second


def duration_seconds(start_t: Any, end_t: Any) -> float | None:
    """
    Correct fraud/sample check duration logic.

    Entry duration = current row end_time - current row start_time.
    """
    start_sec = time_to_seconds(start_t)
    end_sec = time_to_seconds(end_t)

    if start_sec is None or end_sec is None:
        return None

    diff = end_sec - start_sec

    if diff < 0:
        return None

    return diff


def duration_minutes(start_t: Any, end_t: Any) -> float | None:
    sec = duration_seconds(start_t, end_t)

    if sec is None:
        return None

    return round(sec / 60, 2)


def format_seconds(sec: Any) -> str:
    if sec is None or pd.isna(sec):
        return "-"

    sec = int(round(sec))
    mins = sec // 60
    rem = sec % 60

    if mins > 0:
        return f"{mins}m {rem:02d}s"

    return f"{rem}s"


def clean_numeric(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None

    text = str(value).strip()
    text = text.replace("%", "")
    text = text.replace("％", "")
    text = text.replace("℅", "")
    text = text.replace(",", "")

    if text.lower() in INVALID_TEXT:
        return None

    parsed = pd.to_numeric(text, errors="coerce")

    if pd.isna(parsed):
        return None

    return float(parsed)


def safe_unique(series: pd.Series) -> list[str]:
    if series is None or series.empty:
        return []

    return sorted(series.dropna().astype(str).unique().tolist())


def make_download_csv(df_in: pd.DataFrame) -> bytes:
    return df_in.to_csv(index=False).encode("utf-8")


def format_time_value(value: Any) -> str:
    if value is None or pd.isna(value):
        return "-"

    return value.strftime("%H:%M:%S")


def format_date_series(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.strftime("%d-%m-%Y")


def normalize_for_check(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""

    s = str(value).strip().lower()
    s = re.sub(r"[^a-z0-9\s\-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def has_specific_location_detail(value: Any) -> bool:
    s = normalize_for_check(value)

    if not s:
        return False

    for pattern in SPECIFIC_LOCATION_HINTS:
        if re.search(pattern, s):
            return True

    words = [w for w in s.split() if len(w) > 2]

    # If location is only city name, it is not specific
    if s in {"delhi", "new delhi", "gurugram", "gurgaon", "noida"}:
        return False

    # Multi-word localities like "Chirag Delhi", "Lajpat Nagar" are okay
    return len(words) >= 2


def od_quality_flags(origin: Any, destination: Any) -> list[str]:
    """
    Suspicious OD checks ONLY for:
    Delhi, New Delhi, Gurugram/Gurgaon, Noida.
    """
    flags: list[str] = []

    o = normalize_for_check(origin)
    d = normalize_for_check(destination)

    # Origin Delhi/New Delhi only
    if o in {"delhi", "new delhi"}:
        flags.append("Origin Delhi/New Delhi without locality")

    # Destination Delhi/New Delhi only
    if d in {"delhi", "new delhi"}:
        flags.append("Destination Delhi/New Delhi without locality")

    # Origin Gurugram/Gurgaon without locality
    if o in {"gurugram", "gurgaon"}:
        flags.append("Origin Gurugram/Gurgaon without sector/locality")
    elif ("gurugram" in o or "gurgaon" in o) and not has_specific_location_detail(o):
        flags.append("Origin Gurugram/Gurgaon without sector/locality")

    # Destination Gurugram/Gurgaon without locality
    if d in {"gurugram", "gurgaon"}:
        flags.append("Destination Gurugram/Gurgaon without sector/locality")
    elif ("gurugram" in d or "gurgaon" in d) and not has_specific_location_detail(d):
        flags.append("Destination Gurugram/Gurgaon without sector/locality")

    # Origin Noida without sector/locality
    if o == "noida":
        flags.append("Origin Noida without sector/locality")
    elif "noida" in o and not has_specific_location_detail(o):
        flags.append("Origin Noida without sector/locality")

    # Destination Noida without sector/locality
    if d == "noida":
        flags.append("Destination Noida without sector/locality")
    elif "noida" in d and not has_specific_location_detail(d):
        flags.append("Destination Noida without sector/locality")

    return flags


def od_quality_flag_text(origin: Any, destination: Any) -> str | None:
    flags = od_quality_flags(origin, destination)
    return " | ".join(flags) if flags else None


# ─────────────────────────────────────────────────────────────────────────────
# DATA PROCESSING
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def process_dataframe(raw_bytes: bytes) -> pd.DataFrame:
    df = pd.read_excel(
        io.BytesIO(raw_bytes),
        sheet_name=SHEET_NAME,
        engine="openpyxl",
    )

    required_cols = [
        COL_DATE,
        COL_START,
        COL_END,
        COL_USERNAME,
        COL_LOCATION,
        COL_SURVEYOR,
        COL_CONTACT,
        COL_DIRECTION,
        COL_SURVEY_TYPE,
        COL_PASS_VEHICLE_PRIMARY,
        COL_PASS_VEHICLE_ALT,
        COL_PASS_ORIGIN,
        COL_PASS_DESTINATION,
        COL_PASS_SHIFT,
        COL_PASS_FREQUENCY,
        COL_PASS_PURPOSE,
        COL_PASS_OTHER,
        COL_GOODS_VEHICLE,
        COL_GOODS_ORIGIN,
        COL_GOODS_DESTINATION,
        COL_GOODS_SHIFT,
        COL_GOODS_FREQUENCY,
        COL_GOODS_COMMODITY,
    ]

    for col in required_cols:
        if col not in df.columns:
            df[col] = pd.NA

    # Date/time
    df[COL_DATE] = parse_date_series(df[COL_DATE])
    df[COL_START] = df[COL_START].apply(parse_time_value)
    df[COL_END] = df[COL_END].apply(parse_time_value)

    df["start_hour"] = df[COL_START].apply(
        lambda x: x.hour if x is not None and pd.notna(x) else None
    )

    # Correct duration fields
    df["entry_duration_sec"] = df.apply(
        lambda r: duration_seconds(r.get(COL_START), r.get(COL_END)),
        axis=1,
    )

    df["survey_duration_mins"] = df["entry_duration_sec"].apply(
        lambda x: round(x / 60, 2) if pd.notna(x) else None
    )

    # Common fields
    df["surveyor"] = df[COL_SURVEYOR].apply(lambda x: clean_text(x, title_case=True))
    df["contact"] = df[COL_CONTACT].apply(clean_text)
    df["direction"] = df[COL_DIRECTION].apply(clean_text)
    df["survey_type"] = df[COL_SURVEY_TYPE].apply(
        lambda x: clean_text(x, title_case=True)
    )

    # Unified fields
    def derive_vehicle(row: pd.Series) -> Any:
        survey_type = str(row.get("survey_type", "")).strip().lower()

        if survey_type == "passenger":
            return first_valid(
                row,
                [COL_PASS_VEHICLE_PRIMARY, COL_PASS_VEHICLE_ALT],
                title_case=True,
            )

        if survey_type == "goods":
            return first_valid(row, [COL_GOODS_VEHICLE], title_case=True)

        return first_valid(
            row,
            [COL_PASS_VEHICLE_PRIMARY, COL_PASS_VEHICLE_ALT, COL_GOODS_VEHICLE],
            title_case=True,
        )

    def derive_origin(row: pd.Series) -> Any:
        survey_type = str(row.get("survey_type", "")).strip().lower()

        if survey_type == "passenger":
            return clean_location(safe_get(row, COL_PASS_ORIGIN))

        if survey_type == "goods":
            return clean_location(safe_get(row, COL_GOODS_ORIGIN))

        return first_valid(row, [COL_PASS_ORIGIN, COL_GOODS_ORIGIN], title_case=True)

    def derive_destination(row: pd.Series) -> Any:
        survey_type = str(row.get("survey_type", "")).strip().lower()

        if survey_type == "passenger":
            return clean_location(safe_get(row, COL_PASS_DESTINATION))

        if survey_type == "goods":
            return clean_location(safe_get(row, COL_GOODS_DESTINATION))

        return first_valid(
            row,
            [COL_PASS_DESTINATION, COL_GOODS_DESTINATION],
            title_case=True,
        )

    def derive_shift(row: pd.Series) -> Any:
        survey_type = str(row.get("survey_type", "")).strip().lower()

        if survey_type == "passenger":
            return clean_text(safe_get(row, COL_PASS_SHIFT))

        if survey_type == "goods":
            return clean_text(safe_get(row, COL_GOODS_SHIFT))

        return first_valid(row, [COL_PASS_SHIFT, COL_GOODS_SHIFT])

    def derive_frequency(row: pd.Series) -> Any:
        survey_type = str(row.get("survey_type", "")).strip().lower()

        if survey_type == "passenger":
            return clean_text(safe_get(row, COL_PASS_FREQUENCY))

        if survey_type == "goods":
            return clean_text(safe_get(row, COL_GOODS_FREQUENCY))

        return first_valid(row, [COL_PASS_FREQUENCY, COL_GOODS_FREQUENCY])

    def derive_purpose_or_commodity(row: pd.Series) -> Any:
        survey_type = str(row.get("survey_type", "")).strip().lower()

        if survey_type == "passenger":
            purpose = clean_text(safe_get(row, COL_PASS_PURPOSE), title_case=True)
            other = clean_text(safe_get(row, COL_PASS_OTHER), title_case=True)

            if pd.notna(purpose) and str(purpose).lower() == "others" and pd.notna(other):
                return f"Others: {other}"

            return purpose

        if survey_type == "goods":
            return clean_text(safe_get(row, COL_GOODS_COMMODITY), title_case=True)

        return first_valid(
            row,
            [COL_PASS_PURPOSE, COL_GOODS_COMMODITY],
            title_case=True,
        )

    def derive_passenger_occupancy(row: pd.Series) -> float | None:
        for col in PASSENGER_OCCUPANCY_COLS:
            if col in row.index:
                val = clean_numeric(row.get(col))
                if val is not None:
                    return val
        return None

    def derive_bus_sitting_pct(row: pd.Series) -> float | None:
        for col in PASSENGER_BUS_PERCENT_COLS:
            if col in row.index:
                val = clean_numeric(row.get(col))
                if val is not None:
                    return val
        return None

    def derive_occupancy(row: pd.Series) -> str | None:
        for col in PASSENGER_OCCUPANCY_COLS:
            if col in row.index:
                val = str(row.get(col) or "").strip()
                if val and val.lower() not in INVALID_TEXT:
                    try:
                        num = float(val.replace("%", "").replace("℅", "").strip())
                        return str(int(num)) if num.is_integer() else str(num)
                    except Exception:
                        return val

        for col in PASSENGER_BUS_PERCENT_COLS:
            if col in row.index:
                val = str(row.get(col) or "").strip()
                if val and val.lower() not in INVALID_TEXT:
                    clean_val = val.replace("℅", "%").strip()
                    if not clean_val.endswith("%"):
                        try:
                            num = float(clean_val)
                            return f"{int(num)}%" if num.is_integer() else f"{num}%"
                        except Exception:
                            pass
                    return clean_val
        return None

    df["vehicle_type"] = df.apply(derive_vehicle, axis=1)
    df["origin"] = df.apply(derive_origin, axis=1)
    df["destination"] = df.apply(derive_destination, axis=1)
    df["likely_shift"] = df.apply(derive_shift, axis=1)
    df["trip_frequency"] = df.apply(derive_frequency, axis=1)
    df["trip_purpose_or_commodity"] = df.apply(derive_purpose_or_commodity, axis=1)
    df["passenger_occupancy"] = df.apply(derive_passenger_occupancy, axis=1)
    df["bus_sitting_pct"] = df.apply(derive_bus_sitting_pct, axis=1)
    df["occupancy"] = df.apply(derive_occupancy, axis=1)

    # Final cleaning
    df["vehicle_type"] = df["vehicle_type"].apply(lambda x: clean_text(x, title_case=True))
    df["origin"] = df["origin"].apply(clean_location)
    df["destination"] = df["destination"].apply(clean_location)
    df["likely_shift"] = df["likely_shift"].apply(clean_text)
    df["trip_frequency"] = df["trip_frequency"].apply(clean_text)
    df["trip_purpose_or_commodity"] = df["trip_purpose_or_commodity"].apply(
        lambda x: clean_text(x, title_case=True)
    )

    df["has_origin_destination"] = df["origin"].notna() & df["destination"].notna()
    df["bad_od_entry"] = ~df["has_origin_destination"]

    # Suspicious OD only for Delhi/New Delhi/Gurugram/Noida
    df["od_quality_issue"] = df.apply(
        lambda r: od_quality_flag_text(r["origin"], r["destination"]),
        axis=1,
    )

    df["sample_quality_flags"] = df["od_quality_issue"]
    df["sample_quality_suspicious"] = df["sample_quality_flags"].notna()

    return df


# ─────────────────────────────────────────────────────────────────────────────
# FILTERS
# ─────────────────────────────────────────────────────────────────────────────
def filter_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("🔎 Global Filters")

    valid_dates = df[COL_DATE].dropna()

    if not valid_dates.empty:
        min_date = valid_dates.min().date()
        max_date = valid_dates.max().date()

        selected_dates = st.sidebar.date_input(
            "Date Range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )

        if isinstance(selected_dates, (tuple, list)):
            if len(selected_dates) == 2:
                start_date, end_date = selected_dates
            elif len(selected_dates) == 1:
                start_date = end_date = selected_dates[0]
            else:
                start_date = end_date = min_date
        else:
            start_date = end_date = selected_dates
    else:
        start_date = end_date = datetime.today().date()

    # ── Time Dropdown Filters (15-minute intervals from 00:00 to 23:59) ────
    time_options = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 15, 30, 45)]
    if "23:59" not in time_options:
        time_options.append("23:59")

    time_from_str = st.sidebar.selectbox(
        "Survey Start Time From",
        options=time_options,
        index=0,
    )
    time_to_str = st.sidebar.selectbox(
        "Survey Start Time To",
        options=time_options,
        index=len(time_options) - 1,
    )

    h_f, m_f = map(int, time_from_str.split(":"))
    h_t, m_t = map(int, time_to_str.split(":"))
    time_from = time(h_f, m_f)
    time_to = time(h_t, m_t)

    survey_types = safe_unique(df["survey_type"])
    all_types = st.sidebar.checkbox("Select All Survey Types", value=True)
    selected_types = st.sidebar.multiselect(
        "Survey Type",
        options=survey_types,
        default=survey_types if all_types else [],
    )

    directions = safe_unique(df["direction"])
    all_directions = st.sidebar.checkbox("Select All Directions / Arms", value=True)
    selected_directions = st.sidebar.multiselect(
        "Direction / Arm",
        options=directions,
        default=directions if all_directions else [],
    )

    vehicles = safe_unique(df["vehicle_type"])
    all_vehicles = st.sidebar.checkbox("Select All Vehicle Types", value=True)
    selected_vehicles = st.sidebar.multiselect(
        "Vehicle Type",
        options=vehicles,
        default=vehicles if all_vehicles else [],
    )

    surveyors = safe_unique(df["surveyor"])
    all_surveyors = st.sidebar.checkbox("Select All Surveyors", value=True)
    selected_surveyors = st.sidebar.multiselect(
        "Surveyor",
        options=surveyors,
        default=surveyors if all_surveyors else [],
    )

    # ── Apply all filters together ──────────────────────────────────────────
    filtered = df[
        (df[COL_DATE].dt.date >= start_date)
        & (df[COL_DATE].dt.date <= end_date)
    ].copy()

    time_to_cmp = time(time_to.hour, time_to.minute, 59)
    is_full_day = (time_from == time(0, 0)) and (time_to.hour == 23 and time_to.minute >= 59)
    if not is_full_day:
        filtered = filtered[
            filtered[COL_START].apply(
                lambda x: x is not None and pd.notna(x) and time_from <= x <= time_to_cmp
            )
        ]

    if selected_types:
        filtered = filtered[filtered["survey_type"].astype(str).isin(selected_types)]
    else:
        filtered = filtered.iloc[0:0]

    if selected_directions:
        filtered = filtered[filtered["direction"].astype(str).isin(selected_directions)]
    else:
        filtered = filtered.iloc[0:0]

    if selected_vehicles:
        filtered = filtered[filtered["vehicle_type"].astype(str).isin(selected_vehicles)]
    else:
        filtered = filtered.iloc[0:0]

    if selected_surveyors:
        filtered = filtered[filtered["surveyor"].astype(str).isin(selected_surveyors)]
    else:
        filtered = filtered.iloc[0:0]

    st.sidebar.metric("Filtered Records", len(filtered))
    return filtered


# ─────────────────────────────────────────────────────────────────────────────
# DISPLAY HELPER
# ─────────────────────────────────────────────────────────────────────────────
def prepare_display(df_in: pd.DataFrame) -> pd.DataFrame:
    cols = [
        COL_DATE,
        COL_START,
        COL_END,
        "surveyor",
        "contact",
        "survey_type",
        "direction",
        "vehicle_type",
        "occupancy",
        "origin",
        "destination",
        "entry_duration_sec",
        "survey_duration_mins",
        "sample_quality_flags",
    ]

    existing = [c for c in cols if c in df_in.columns]
    out = df_in[existing].copy()

    if COL_DATE in out.columns:
        out[COL_DATE] = format_date_series(out[COL_DATE])

    if COL_START in out.columns:
        out[COL_START] = out[COL_START].apply(format_time_value)

    if COL_END in out.columns:
        out[COL_END] = out[COL_END].apply(format_time_value)

    if "entry_duration_sec" in out.columns:
        out["entry_duration_sec"] = pd.to_numeric(
            out["entry_duration_sec"],
            errors="coerce",
        ).round(0)

        out["Entry Duration"] = out["entry_duration_sec"].apply(format_seconds)

    if "survey_duration_mins" in out.columns:
        out["survey_duration_mins"] = pd.to_numeric(
            out["survey_duration_mins"],
            errors="coerce",
        ).round(2)

    out = out.rename(
        columns={
            COL_DATE: "Date",
            COL_START: "Start Time",
            COL_END: "End Time",
            "surveyor": "Surveyor",
            "contact": "Contact",
            "survey_type": "Survey Type",
            "direction": "Direction",
            "vehicle_type": "Vehicle Type",
            "occupancy": "Occupancy",
            "origin": "Origin",
            "destination": "Destination",
            "entry_duration_sec": "Entry Duration (sec)",
            "survey_duration_mins": "Duration (mins)",
            "sample_quality_flags": "Sample Quality Flags",
        }
    )

    ordered = [
        "Date",
        "Start Time",
        "End Time",
        "Entry Duration (sec)",
        "Entry Duration",
        "Surveyor",
        "Contact",
        "Survey Type",
        "Direction",
        "Vehicle Type",
        "Occupancy",
        "Origin",
        "Destination",
        "Duration (mins)",
        "Sample Quality Flags",
    ]

    ordered = [c for c in ordered if c in out.columns]

    return out[ordered]


# ─────────────────────────────────────────────────────────────────────────────
# DELHI ZONING KML LOADER
# ─────────────────────────────────────────────────────────────────────────────
DELHI_ZONING_KML = os.path.join(os.path.dirname(__file__), "Final_zoning_delhi.kml")

@st.cache_data(show_spinner=False)
def load_delhi_zoning_data(kml_file_path: str):
    if not os.path.exists(kml_file_path):
        return None, [], pd.DataFrame()

    try:
        tree = ET.parse(kml_file_path)
        root = tree.getroot()
        ns = {"kml": "http://www.opengis.net/kml/2.2"}

        features = []
        centroids = []
        table_rows = []
        placemarks = root.findall(".//kml:Placemark", ns)

        for pm in placemarks:
            props = {}
            for sd in pm.findall(".//kml:SimpleData", ns):
                name = sd.attrib.get("name")
                val = sd.text
                if name:
                    props[name] = val
                    props[f"Final_zoning_delhi:{name}"] = val

            zone_no = props.get("Zone_no", "")
            ward_name = props.get("Ward_Name", "")
            ward_no = props.get("Ward_No", "")
            props["zone_no"] = str(zone_no)
            props["ward_name"] = str(ward_name)
            props["ward_no"] = str(ward_no)

            coords_elem = pm.find(".//kml:coordinates", ns)
            if coords_elem is not None and coords_elem.text:
                raw_coords = coords_elem.text.strip().split()
                ring = []
                sum_lng, sum_lat = 0.0, 0.0
                for pt in raw_coords:
                    parts = pt.split(",")
                    if len(parts) >= 2:
                        lng, lat = float(parts[0]), float(parts[1])
                        ring.append([lng, lat])
                        sum_lng += lng
                        sum_lat += lat

                if ring:
                    n_pts = len(ring)
                    c_lng = sum_lng / n_pts
                    c_lat = sum_lat / n_pts

                    features.append({
                        "type": "Feature",
                        "properties": props,
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [ring],
                        },
                    })
                    centroids.append({
                        "zone_no": str(zone_no),
                        "label": f"Zone {zone_no}",
                        "ward": str(ward_name),
                        "coordinates": [c_lng, c_lat],
                    })
                    table_rows.append({
                        "Zone No": zone_no,
                        "Ward Name": ward_name,
                        "Ward No": ward_no,
                        "Center Longitude": round(c_lng, 4),
                        "Center Latitude": round(c_lat, 4),
                    })

        geojson_obj = {
            "type": "FeatureCollection",
            "features": features,
        }
        df_zones = pd.DataFrame(table_rows)
        return geojson_obj, centroids, df_zones
    except Exception as err:
        return None, [], pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# DELHI OD CORRECTION & AI SPATIAL GEOCODING ENGINE
# ─────────────────────────────────────────────────────────────────────────────
OUTSIDE_DELHI_KEYWORDS = [
    "noida", "greater noida", "gr noida", "gurgaon", "gurugram", "grugram", "cyber city",
    "iffco chowk", "manesar", "faridabad", "ghaziabad", "vaishali", "indirapuram",
    "sahibabad", "sonipat", "sonepat", "bahadurgarh", "ballabhgarh", "palwal",
    "rewari", "rohtak", "meerut", "panipat", "kundli", "haryana", "hariyana", "hriyana",
    "uttar pradesh", "up", "rajasthan", "alwar", "dharuhera", "bhiwadi", "modinagar", "hapur",
    "loni", "bhondsi", "mathura", "agra", "jaipur", "kundli border", "karnal", "ambala",
    "punjab", "bihar", "vrindavan", "bulandshahr", "ncr", "maruti kunj", "sarhol",
    "sikandarpur", "huda city", "khekra", "baghpat", "shamli", "muzaffarnagar", "murthal",
    "samalkha", "badli haryana", "jhajjar", "panchgaon", "bilaspur", "bhiwani",
]

STOP_SUFFIXES = [
    "metro station", "metro stn", "metro", "railway station", "rly station", "station", "stn",
    "firni road", "firni", "road", "marg", "terminal", "bus stand", "bus stop", "stand", "stop",
    "market", "bazar", "bajar", "hospital", "hosptal", "mandir", "temple", "village", "vill",
    "chowk", "border", "depot", "extension", "extn", "ext", "pocket", "block", "phase", "sec",
    "sector", "gate", "nagar", "vihar", "enclave", "colony"
]

DELHI_LANDMARK_MAPPINGS: dict[str, tuple[str, str]] = {
    # Moolchand, Lajpat Nagar & South-Central
    "moolchand": ("Moolchand", "3"),
    "mulchand": ("Moolchand", "3"),
    "mool chand": ("Moolchand", "3"),
    "moolchand delhi": ("Moolchand", "3"),
    "mulchand metro station": ("Moolchand", "3"),
    "mulchandar": ("Moolchand", "3"),
    "central market": ("Lajpat Nagar Central Market", "6"),
    "gupta market": ("Lajpat Nagar (Gupta Market)", "6"),
    "lajpat nagar": ("Lajpat Nagar", "6"),
    "lajpat": ("Lajpat Nagar", "6"),
    "lajpat nagar 1": ("Lajpat Nagar I", "3"),
    "lajpat nagar 2": ("Lajpat Nagar II", "3"),
    "lajpat nagar 3": ("Lajpat Nagar III", "6"),
    "lajpat nagar 4": ("Lajpat Nagar IV", "6"),
    "lajpat nagar ring road": ("Lajpat Nagar", "6"),
    "amar colony": ("Amar Colony", "6"),
    "dayanand colony": ("Dayanand Colony", "6"),
    "national park": ("National Park (Lajpat Nagar)", "6"),
    "vikram vihar": ("Vikram Vihar (Lajpat Nagar)", "6"),
    "vinobapuri": ("Vinobapuri", "3"),
    "vinob puri": ("Vinobapuri", "3"),
    "vinoba puri": ("Vinobapuri", "3"),
    "sriniwaspuri": ("Sriniwaspuri", "3"),
    "shiniwas puri": ("Sriniwaspuri", "3"),
    "shiniwaspuri": ("Sriniwaspuri", "3"),
    "defence colony": ("Defence Colony", "14"),
    "south extension": ("South Extension", "12"),
    "south ext": ("South Extension", "12"),
    "south ext 1": ("South Extension I", "12"),
    "south ext 2": ("South Extension II", "12"),
    "south ex": ("South Extension", "12"),
    "kotla mubarakpur": ("Kotla Mubarakpur", "12"),
    "kotla": ("Kotla Mubarakpur", "12"),
    "andrews ganj": ("Andrews Ganj", "12"),

    # Kalkaji, GK, Nehru Place, CR Park
    "kalkaji": ("Kalkaji", "13"),
    "kalka ji": ("Kalkaji", "13"),
    "kalka ji delhi": ("Kalkaji", "13"),
    "kalka ji mandir": ("Kalkaji", "13"),
    "kalika ji": ("Kalkaji", "13"),
    "kalika ji mandir": ("Kalkaji", "13"),
    "kalika devi mandir": ("Kalkaji", "13"),
    "kalak": ("Kalkaji", "13"),
    "kalkaji extension": ("Kalkaji Extension", "15"),
    "govindpuri": ("Govindpuri", "13"),
    "govindpuri delhi": ("Govindpuri", "13"),
    "govind puri": ("Govindpuri", "13"),
    "cr park": ("Chitranjan Park", "15"),
    "c.r. park": ("Chitranjan Park", "15"),
    "chitranjan park": ("Chitranjan Park", "15"),
    "alakananda": ("Alaknanda", "15"),
    "alaknanda": ("Alaknanda", "15"),
    "nehru place": ("Nehru Place", "13"),
    "nehru enclave": ("Nehru Enclave", "15"),
    "nehru enclave east": ("Nehru Enclave East", "15"),
    "nehru enclave west": ("Nehru Enclave West", "15"),
    "nehru nagar": ("Nehru Nagar", "3"),
    "greater kailash": ("Greater Kailash", "9"),
    "greater kailash 1": ("Greater Kailash I", "9"),
    "greater kailash 2": ("Greater Kailash II", "15"),
    "gk": ("Greater Kailash", "9"),
    "gk 1": ("Greater Kailash I", "9"),
    "gk 2": ("Greater Kailash II", "15"),
    "gk1": ("Greater Kailash I", "9"),
    "gk2": ("Greater Kailash II", "15"),
    "kailash colony": ("Kailash Colony", "9"),
    "kailash hills": ("Kailash Hills", "10"),
    "east of kailash": ("East of Kailash", "10"),
    "garhi": ("Garhi (East of Kailash)", "10"),
    "sant nagar": ("Sant Nagar (East of Kailash)", "10"),
    "jamrudpur": ("Zamrudpur", "9"),
    "zamrudpur": ("Zamrudpur", "9"),

    # Madangir, Dakshinpuri, Khanpur, Sangam Vihar
    "madangir": ("Madangir", "18"),
    "madan giri": ("Madangir", "18"),
    "madan gir": ("Madangir", "18"),
    "madangiri": ("Madangir", "18"),
    "madangate": ("Madan Gate (Karol Bagh)", "172"),
    "madan gate": ("Madan Gate (Karol Bagh)", "172"),
    "madhan gate": ("Madan Gate (Karol Bagh)", "172"),
    "dakshinpuri": ("Dakshinpuri", "18"),
    "dhachanpuri": ("Dakshinpuri", "18"),
    "dhachan puri": ("Dakshinpuri", "18"),
    "ambedkar nagar": ("Ambedkar Nagar", "18"),
    "ambedkar": ("Ambedkar Nagar", "18"),
    "khanpur": ("Khanpur", "26"),
    "kanpur": ("Khanpur", "26"),
    "khanpur village": ("Khanpur", "26"),
    "devli": ("Deoli", "26"),
    "deoli": ("Deoli", "26"),
    "tigri": ("Tigri", "26"),
    "sangam vihar": ("Sangam Vihar", "292"),
    "sangham vihar": ("Sangam Vihar", "292"),
    "sangam vihar central": ("Sangam Vihar Central", "291"),
    "talimabad": ("Talimabad", "292"),
    "durga vihar": ("Durga Vihar", "26"),
    "hamdard": ("Hamdard Nagar", "26"),
    "humdard": ("Hamdard Nagar", "26"),
    "hamdard nagar": ("Hamdard Nagar", "26"),
    "humdard nagar": ("Hamdard Nagar", "26"),
    "batra hospital": ("Batra Hospital (Sangam Vihar)", "292"),

    # Sarai Kale Khan, Nizamuddin, Ashram
    "sarai kale khan": ("Sarai Kale Khan", "14"),
    "sarai kale ka": ("Sarai Kale Khan", "14"),
    "sarai kale kha": ("Sarai Kale Khan", "14"),
    "saray kale kha": ("Sarai Kale Khan", "14"),
    "saraikalekhan": ("Sarai Kale Khan", "14"),
    "hazrat nizamuddin": ("Hazrat Nizamuddin", "14"),
    "nizamuddin": ("Hazrat Nizamuddin", "14"),
    "nizamuddin station": ("Hazrat Nizamuddin Railway Station", "14"),
    "nizamuddin railway station": ("Hazrat Nizamuddin Railway Station", "14"),
    "nizamuddin east": ("Nizamuddin East", "14"),
    "nizamuddin west": ("Nizamuddin West", "14"),
    "jungpura": ("Jungpura", "14"),
    "jangpura": ("Jungpura", "14"),
    "jungpura a": ("Jungpura A", "14"),
    "jungpura b": ("Jungpura B", "14"),
    "bhogal": ("Bhogal", "14"),
    "pant nagar": ("Pant Nagar", "14"),
    "ashram": ("Ashram Chowk", "14"),
    "aashram": ("Ashram Chowk", "14"),
    "ashram chowk": ("Ashram Chowk", "14"),
    "hari nagar ashram": ("Hari Nagar Ashram", "14"),
    "kilokri": ("Kilokri (Ashram)", "14"),
    "maharani bagh": ("Maharani Bagh", "14"),
    "friends colony": ("New Friends Colony", "14"),
    "new friends colony": ("New Friends Colony", "14"),
    "nfc": ("New Friends Colony", "14"),
    "friends colony east": ("Friends Colony East", "14"),
    "friends colony west": ("Friends Colony West", "14"),
    "sukhdev vihar": ("Sukhdev Vihar", "14"),
    "sidharth enclave": ("Siddharth Enclave", "14"),
    "sunlight colony": ("Sunlight Colony", "14"),

    # Lado Sarai, Mehrauli, Chhatarpur & South Villages
    "lado sarai": ("Lado Sarai", "280"),
    "ladosarai": ("Lado Sarai", "280"),
    "lado sarai firni road": ("Lado Sarai", "280"),
    "lado sarai firni": ("Lado Sarai", "280"),
    "firni road": ("Lado Sarai (Firni Road)", "280"),
    "firani road": ("Lado Sarai (Firni Road)", "280"),
    "mehrauli": ("Mehrauli", "278"),
    "mahrauli": ("Mehrauli", "278"),
    "mahroli": ("Mehrauli", "278"),
    "mahrawli": ("Mehrauli", "278"),
    "mahorli": ("Mehrauli", "278"),
    "mehrauli terminal": ("Mehrauli", "278"),
    "mahrauli terminal": ("Mehrauli", "278"),
    "qutub minar": ("Mehrauli (Qutub Minar)", "278"),
    "chhatarpur": ("Chhatarpur", "282"),
    "chattarpur": ("Chhatarpur", "282"),
    "chhatarpur enclave": ("Chhatarpur Enclave", "282"),
    "sultanpur": ("Sultanpur (Mehrauli)", "282"),
    "ghitorni": ("Ghitorni", "282"),
    "aya nagar": ("Aya Nagar", "282"),
    "fatehpur beri": ("Fatehpur Beri", "282"),
    "fatehpur": ("Fatehpur Beri", "282"),
    "mandi gaon": ("Mandi Village", "282"),
    "mandi village": ("Mandi Village", "282"),
    "sainik farm": ("Sainik Farm", "282"),
    "saini farm": ("Sainik Farm", "282"),
    "neb sarai": ("Neb Sarai", "282"),
    "meb sarai": ("Neb Sarai", "282"),
    "neb sarai village": ("Neb Sarai", "282"),
    "meb sarai village": ("Neb Sarai", "282"),
    "adhchini": ("Adhchini", "8"),
    "adhchini village": ("Adhchini", "8"),
    "adchini": ("Adhchini", "8"),
    "rajokri": ("Rajokri", "275"),
    "rajokari": ("Rajokri", "275"),
    "rajokri village": ("Rajokri", "275"),
    "masudpur": ("Masoodpur (Vasant Kunj)", "274"),
    "masoodpur": ("Masoodpur (Vasant Kunj)", "274"),
    "masudpur village": ("Masoodpur (Vasant Kunj)", "274"),
    "masoodpur village": ("Masoodpur (Vasant Kunj)", "274"),
    "city forest": ("City Forest (Tajpur)", "283"),

    # Saket, Malviya Nagar, Hauz Khas, IIT
    "saket": ("Saket", "16"),
    "select citywalk": ("Saket (Select Citywalk)", "16"),
    "saket select city": ("Saket (Select Citywalk)", "16"),
    "pushp vihar": ("Pushp Vihar", "16"),
    "pushpa bhavan": ("Pushp Vihar (Pushpa Bhawan)", "16"),
    "pushpa bhawan": ("Pushp Vihar (Pushpa Bhawan)", "16"),
    "pushp bhavan": ("Pushp Vihar (Pushpa Bhawan)", "16"),
    "malviya nagar": ("Malviya Nagar", "11"),
    "chirag delhi": ("Chirag Delhi", "11"),
    "delhi chirag": ("Chirag Delhi", "11"),
    "chirag": ("Chirag Delhi", "11"),
    "sheikh sarai": ("Sheikh Sarai", "11"),
    "sheikh sarai phase 1": ("Sheikh Sarai Phase I", "11"),
    "sheikh sarai phase 2": ("Sheikh Sarai Phase II", "11"),
    "panchsheel park": ("Panchsheel Park", "11"),
    "panchsheel enclave": ("Panchsheel Enclave", "15"),
    "panchsheel": ("Panchsheel Park", "11"),
    "panchil": ("Panchsheel Park", "11"),
    "sarvodaya enclave": ("Sarvodaya Enclave", "11"),
    "khirki extension": ("Khirki Extension", "11"),
    "khirki ext": ("Khirki Extension", "11"),
    "siri fort": ("Siri Fort", "8"),
    "neeti bagh": ("Niti Bagh", "8"),
    "niti bagh": ("Niti Bagh", "8"),
    "shahpur jat": ("Shahpur Jat", "8"),
    "hauz khas": ("Hauz Khas", "8"),
    "hauz khas village": ("Hauz Khas Village", "8"),
    "hauz rani": ("Hauz Rani", "16"),
    "green park": ("Green Park", "8"),
    "green park main": ("Green Park Main", "8"),
    "green park extension": ("Green Park Extension", "8"),
    "green park ext": ("Green Park Extension", "8"),
    "safdarjung enclave": ("Safdarjung Enclave", "7"),
    "safdarjung": ("Safdarjung Hospital / Enclave", "218"),
    "safdarganj": ("Safdarjung Hospital", "218"),
    "sabdarjan": ("Safdarjung Hospital", "218"),
    "safdarjung development area": ("SDA (Safdarjung Dev Area)", "8"),
    "sda": ("SDA (Safdarjung Dev Area)", "8"),
    "iit": ("IIT Delhi", "8"),
    "iit delhi": ("IIT Delhi", "8"),
    "iit gate": ("IIT Gate Junction", "8"),
    "iit gate junction": ("IIT Gate Junction", "8"),
    "aiims": ("AIIMS (Ansari Nagar)", "218"),
    "aiims hospital": ("AIIMS (Ansari Nagar)", "218"),
    "safdarjung hospital": ("Safdarjung Hospital", "218"),
    "sarojini nagar": ("Sarojini Nagar", "213"),
    "sarojni": ("Sarojini Nagar", "213"),
    "sarojani market": ("Sarojini Nagar Market", "213"),
    "sarojni market": ("Sarojini Nagar Market", "213"),
    "nauroji nagar": ("Nauroji Nagar", "213"),
    "laxmibai nagar": ("Laxmibai Nagar", "213"),
    "kidwai nagar": ("Kidwai Nagar", "213"),
    "ina": ("INA Colony / Market", "213"),
    "ina colony": ("INA Colony", "213"),
    "dilli haat": ("Dilli Haat (INA)", "213"),
    "lodhi colony": ("Lodhi Colony", "212"),
    "lodhi road": ("Lodhi Road", "212"),
    "lodhi garden": ("Lodhi Garden", "212"),
    "jln stadium": ("JLN Stadium", "212"),
    "jawaharlal nehru stadium": ("JLN Stadium", "212"),
    "chidiyaghar": ("National Zoological Park", "212"),
    "chidiya ghar": ("National Zoological Park", "212"),
    "delhi zoo": ("National Zoological Park", "212"),
    "khan market": ("Khan Market", "212"),
    "jor bagh": ("Jor Bagh", "212"),
    "golf links": ("Golf Links", "212"),
    "sunder nagar": ("Sunder Nagar", "212"),
    "india gate": ("India Gate", "212"),
    "high court": ("Delhi High Court (Tilak Marg)", "211"),
    "supreme court": ("Supreme Court (Pragati Maidan)", "211"),
    "pragati maidan": ("Pragati Maidan", "211"),
    "mandi house": ("Mandi House", "211"),
    "patel chowk": ("Patel Chowk", "211"),
    "kendriya terminal": ("Kendriya Terminal (Central Secretariat)", "211"),
    "central secretariat": ("Central Secretariat", "211"),
    # Additional Colloquial & Landmarks
    "gaziyabad": ("Ghaziabad", "Outside"),
    "faribad": ("Faridabad", "Outside"),
    "gudgaon": ("Gurugram", "Outside"),
    "dehradun": ("Dehradun", "Outside"),
    "bisrakh jalalpur": ("Greater Noida (Bisrakh)", "Outside"),
    "badkhal mod": ("Faridabad (Badkhal)", "Outside"),
    "rajghat": ("Rajghat", "167"),
    "rajeev gandi": ("Rajiv Gandhi Hospital (Tahirpur)", "236"),
    "karkardooma court": ("Karkardooma", "227"),
    "karkardooma": ("Karkardooma", "227"),
    "nagloi": ("Nangloi", "164"),
    "nangloi": ("Nangloi", "164"),
    "shivaji": ("Shivaji Stadium (CP)", "211"),
    "shivaji stadium": ("Shivaji Stadium (CP)", "211"),
    "okhala mandi": ("Okhla Mandi", "287"),
    "bhikaji cama": ("Bhikaji Cama Place", "213"),
    "bhikaji cama place": ("Bhikaji Cama Place", "213"),
    "janpath": ("Janpath", "211"),
    "ip state": ("IP Estate", "192"),
    "ip estate": ("IP Estate", "192"),
    "cgo complex": ("CGO Complex (Lodhi Road)", "212"),
    "palika kendra": ("Palika Kendra (CP)", "211"),
    "karni singh shooting range": ("Dr. Karni Singh Range (Asola)", "287"),
    "dr karni singh shooting range": ("Dr. Karni Singh Range (Asola)", "287"),
    "hoskhas": ("Hauz Khas", "8"),
    "basant lok": ("Vasant Lok (Vasant Vihar)", "269"),
    "basant gaon": ("Vasant Gaon", "269"),
    "bhawani kunj": ("Bhawani Kunj (Vasant Kunj)", "274"),
    "arsd college": ("ARSD College (Dhaula Kuan)", "215"),
    "indra inclave": ("Indra Enclave (Neb Sarai)", "282"),
    "ghadi": ("Garhi (East of Kailash)", "10"),
    "kushak nallah depo": ("Kushak Nallah Depot", "212"),
    "kushak nallah": ("Kushak Nallah", "212"),
    "archani": ("Archna Cinema (GK I)", "9"),
    "archana": ("Archna Cinema (GK I)", "9"),
    "bas stand": ("Nill", "-"),

    # Central Delhi & NDMC
    "cp": ("Connaught Place", "211"),
    "c.p.": ("Connaught Place", "211"),
    "c p": ("Connaught Place", "211"),
    "connaught place": ("Connaught Place", "211"),
    "connaught circus": ("Connaught Place", "211"),
    "rajiv chowk": ("Connaught Place (Rajiv Chowk)", "211"),
    "minto road": ("Minto Road", "192"),
    "ito": ("ITO", "192"),
    "indraprastha": ("Indraprastha", "192"),
    "daryaganj": ("Daryaganj", "167"),
    "chandni chowk": ("Chandni Chowk", "153"),
    "lal kila": ("Red Fort (Lal Qila)", "153"),
    "red fort": ("Red Fort (Lal Qila)", "153"),
    "jama masjid": ("Jama Masjid", "177"),
    "chawri bazar": ("Chawri Bazar", "177"),
    "sadar bazar": ("Sadar Bazar", "177"),
    "sadar bajar": ("Sadar Bazar", "177"),
    "kashmere gate": ("ISBT Kashmere Gate", "153"),
    "kashmiri gate": ("ISBT Kashmere Gate", "153"),
    "isbt": ("ISBT Kashmere Gate", "153"),
    "isbt kashmere gate": ("ISBT Kashmere Gate", "153"),
    "kashmiri gate terminal": ("ISBT Kashmere Gate", "153"),
    "mori gate": ("Mori Gate", "153"),
    "new delhi railway station": ("New Delhi Railway Station", "182"),
    "ndls": ("New Delhi Railway Station", "182"),
    "old delhi railway station": ("Old Delhi Railway Station", "153"),
    "pahar ganj": ("Paharganj", "182"),
    "paharganj": ("Paharganj", "182"),
    "karol bagh": ("Karol Bagh", "172"),
    "jhandewalan": ("Jhandewalan", "172"),
    "patel nagar": ("Patel Nagar", "182"),
    "rajendra nagar": ("Rajendra Nagar", "179"),
    "pusa road": ("Pusa Road", "179"),
    "indralok": ("Inderlok", "73"),
    "inderlok": ("Inderlok", "73"),
    "inderpuri": ("Inderpuri", "178"),
    "indrapuri": ("Inderpuri", "178"),
    "inderpuri krishi": ("Inderpuri (Krishi Kunj)", "178"),
    "inderpuri krishi kunj": ("Inderpuri (Krishi Kunj)", "178"),
    "indrapuri krishi kunj": ("Inderpuri (Krishi Kunj)", "178"),
    "krishi kunj": ("Inderpuri (Krishi Kunj)", "178"),

    # Airport, Cantt, Vasant Kunj, West Delhi
    "airport": ("IGI Airport", "258"),
    "airport delhi": ("IGI Airport", "258"),
    "igi airport": ("IGI Airport", "258"),
    "indira gandhi airport": ("IGI Airport", "258"),
    "igi airport terminal 2": ("IGI Airport Terminal 2", "258"),
    "t3 airport": ("IGI Airport Terminal 3", "258"),
    "t1 airport": ("IGI Airport Terminal 1", "258"),
    "delhi cantt": ("Delhi Cantonment", "215"),
    "cantt": ("Delhi Cantonment", "215"),
    "dhaula kuan": ("Dhaula Kuan", "215"),
    "rk puram": ("R.K. Puram", "216"),
    "r k puram": ("R.K. Puram", "216"),
    "rk puram sector 1": ("R.K. Puram Sector 1", "216"),
    "motibagh": ("Moti Bagh", "217"),
    "moti bagh": ("Moti Bagh", "217"),
    "chanakyapuri": ("Chanakyapuri", "217"),
    "anand niketan": ("Anand Niketan", "269"),
    "vasant vihar": ("Vasant Vihar", "269"),
    "munirka": ("Munirka", "269"),
    "ber sarai": ("Ber Sarai", "269"),
    "katwaria sarai": ("Katwaria Sarai", "269"),
    "jnu": ("JNU (Jawaharlal Nehru University)", "269"),
    "vasant kunj": ("Vasant Kunj", "274"),
    "vasant kunj sector a": ("Vasant Kunj Sector A", "274"),
    "vasant kunj sector b": ("Vasant Kunj Sector B", "274"),
    "vasant kunj sector c": ("Vasant Kunj Sector C", "274"),
    "vasant kunj sector d": ("Vasant Kunj Sector D", "274"),
    "mahipalpur": ("Mahipalpur", "277"),
    "kapashera": ("Kapashera", "275"),
    "kapashera border": ("Kapashera Border", "275"),
    "janakpuri": ("Janakpuri", "205"),
    "vikaspuri": ("Vikaspuri", "210"),
    "tilak nagar": ("Tilak Nagar", "203"),
    "subhash nagar": ("Subhash Nagar", "197"),
    "tagore garden": ("Tagore Garden", "198"),
    "raja garden": ("Raja Garden", "198"),
    "punjabi bagh": ("Punjabi Bagh", "164"),
    "paschim vihar": ("Paschim Vihar", "154"),
    "mayapuri": ("Mayapuri", "199"),
    "mayapur": ("Mayapuri", "199"),
    "dwarka": ("Dwarka", "246"),
    "dwarka sec 1": ("Dwarka Sector 1", "246"),
    "dwarka sec 6": ("Dwarka Sector 6", "246"),
    "dwarka sec 10": ("Dwarka Sector 10", "246"),
    "dwarka sec 12": ("Dwarka Sector 12", "246"),
    "dwarka sec 21": ("Dwarka Sector 21", "258"),
    "dwarka mor": ("Dwarka Mor", "246"),
    "shahbad mohammad": ("Shahbad Mohammadpur", "246"),
    "uttam nagar": ("Uttam Nagar", "225"),
    "najafgarh": ("Najafgarh", "252"),
    "qamruddin nagar": ("Qamruddin Nagar", "154"),
    "qamruddin nagar terminal": ("Qamruddin Nagar", "154"),

    # North Delhi
    "rohini": ("Rohini", "44"),
    "rohini sec 3": ("Rohini Sector 3", "44"),
    "rohini sec 7": ("Rohini Sector 7", "44"),
    "rohini sec 8": ("Rohini Sector 8", "44"),
    "pitampura": ("Pitampura", "66"),
    "shalimar bagh": ("Shalimar Bagh", "57"),
    "ashok vihar": ("Ashok Vihar", "74"),
    "model town": ("Model Town", "63"),
    "mukherjee nagar": ("Mukherjee Nagar", "62"),
    "gtb nagar": ("GTB Nagar", "62"),
    "vishwavidyalay": ("Vishwa Vidyalaya (DU)", "62"),
    "vishwa vidyalaya": ("Vishwa Vidyalaya (DU)", "62"),
    "civil lines": ("Civil Lines", "71"),
    "timarpur": ("Timarpur", "71"),
    "azadpur": ("Azadpur", "59"),
    "azadpur mandi": ("Azadpur Mandi", "59"),
    "azadpur metro station": ("Azadpur", "59"),
    "burari": ("Burari", "26"),
    "narela": ("Narela", "17"),
    "bawana": ("Bawana", "20"),
    "badli": ("Badli", "32"),
    "badli industrial area": ("Badli Industrial Area", "32"),
    "samaypur badli": ("Samaypur Badli", "32"),
    "samaypur": ("Samaypur Badli", "32"),

    # East Delhi
    "anand vihar": ("Anand Vihar", "151"),
    "aandh vihar": ("Anand Vihar", "151"),
    "anand vihar isbt": ("Anand Vihar ISBT", "151"),
    "mayur vihar": ("Mayur Vihar", "234"),
    "mayur vihar phase 1": ("Mayur Vihar Phase I", "234"),
    "mayur vihar phase 2": ("Mayur Vihar Phase II", "214"),
    "mayur vihar phase 3": ("Mayur Vihar Phase III", "223"),
    "trilokpuri": ("Trilokpuri", "223"),
    "ghazipur": ("Ghazipur", "223"),
    "gazipur": ("Ghazipur", "223"),
    "gazipur mandi": ("Ghazipur Mandi", "223"),
    "patparganj": ("Patparganj", "234"),
    "ip extension": ("IP Extension", "234"),
    "laxmi nagar": ("Laxmi Nagar", "228"),
    "preet vihar": ("Preet Vihar", "227"),
    "nirman vihar": ("Nirman Vihar", "227"),
    "shakarpur": ("Shakarpur", "228"),
    "shahdara": ("Shahdara", "232"),
    "dilshad garden": ("Dilshad Garden", "236"),
    "seelampur": ("Seelampur", "240"),

    # South-East Delhi
    "sarita vihar": ("Sarita Vihar", "273"),
    "jasola": ("Jasola Vihar", "273"),
    "jasola vihar": ("Jasola Vihar", "273"),
    "jamia": ("Jamia Nagar", "273"),
    "jamia nagar": ("Jamia Nagar", "273"),
    "batla house": ("Batla House", "273"),
    "zakir nagar": ("Zakir Nagar", "273"),
    "abul fazal enclave": ("Abul Fazal Enclave", "273"),
    "shaheen bagh": ("Shaheen Bagh", "273"),
    "kalindi kunj": ("Kalindi Kunj", "273"),
    "okhla": ("Okhla", "287"),
    "okhla phase 1": ("Okhla Industrial Area Phase I", "287"),
    "okhla phase 2": ("Okhla Industrial Area Phase II", "287"),
    "okhla phase 3": ("Okhla Industrial Area Phase III", "287"),
    "okhla industrial area": ("Okhla Industrial Area", "287"),
    "okhla vihar": ("Okhla Vihar", "273"),
    "badarpur": ("Badarpur", "283"),
    "badarpur border": ("Badarpur Border", "283"),
    "mohan estate": ("Mohan Estate (Badarpur)", "283"),
    "meethapur": ("Meethapur", "283"),
    "jaitpur": ("Jaitpur", "283"),
    "molarband": ("Molarband", "283"),
    "ali village": ("Ali Village", "283"),
    "tajpur": ("Tajpur Pahadi", "283"),
    "pul pehlad": ("Pul Pehladpur", "287"),
    "pul pehladpur": ("Pul Pehladpur", "287"),
}

@functools.lru_cache(maxsize=1)
def get_clean_wards_dict() -> dict[str, tuple[str, str]]:
    if not os.path.exists(DELHI_ZONING_KML):
        return {}
    try:
        tree = ET.parse(DELHI_ZONING_KML)
        root = tree.getroot()
        ns = {"kml": "http://www.opengis.net/kml/2.2"}
        wards = {}
        for pm in root.findall(".//kml:Placemark", ns):
            z_no = ""
            w_name = ""
            for sd in pm.findall(".//kml:SimpleData", ns):
                attr = sd.attrib.get("name")
                if attr == "Zone_no":
                    z_no = sd.text or ""
                elif attr == "Ward_Name":
                    w_name = sd.text or ""
            if w_name and z_no:
                cw = re.sub(r"[^a-zA-Z0-9\s]", " ", w_name).strip().lower()
                cw = re.sub(r"\s+", " ", cw)
                if cw:
                    wards[cw] = (w_name.title(), str(z_no))
        return wards
    except Exception:
        return {}

@functools.lru_cache(maxsize=1)
def get_delhi_polygons_cached() -> list[tuple[str, str, list[tuple[float, float]]]]:
    """Loads polygon rings for 295 Delhi zones from KML for Point-in-Polygon checks."""
    if not os.path.exists(DELHI_ZONING_KML):
        return []
    try:
        tree = ET.parse(DELHI_ZONING_KML)
        root = tree.getroot()
        ns = {"kml": "http://www.opengis.net/kml/2.2"}
        polys = []
        for pm in root.findall(".//kml:Placemark", ns):
            props = {}
            for sd in pm.findall(".//kml:SimpleData", ns):
                if sd.attrib.get("name"):
                    props[sd.attrib.get("name")] = sd.text
            z_no = str(props.get("Zone_no", ""))
            w_name = str(props.get("Ward_Name", "")).title()
            coords_elem = pm.find(".//kml:coordinates", ns)
            if coords_elem is not None and coords_elem.text:
                raw = coords_elem.text.strip().split()
                ring = []
                for pt in raw:
                    parts = pt.split(",")
                    if len(parts) >= 2:
                        ring.append((float(parts[0]), float(parts[1])))
                if ring:
                    polys.append((z_no, w_name, ring))
        return polys
    except Exception:
        return []

def point_in_polygon(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    """Ray casting point-in-polygon algorithm."""
    n = len(poly)
    inside = False
    p1x, p1y = poly[0]
    for i in range(n + 1):
        p2x, p2y = poly[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside

def find_delhi_zone_by_lat_lng(lng: float, lat: float) -> tuple[str, str]:
    """Finds exact Delhi Zone No for coordinates using KML polygons."""
    polys = get_delhi_polygons_cached()
    for z_no, w_name, poly in polys:
        if point_in_polygon(lng, lat, poly):
            return z_no, w_name
    return "Outside", "Outside Delhi"

@functools.lru_cache(maxsize=1024)
def geocode_location_spatial(
    location_query: str,
    provider: str = "LocationIQ",
    api_key: str | None = None
) -> tuple[str, str, str]:
    """Geocodes location name via LocationIQ / Geoapify / OSM / Google and matches into Delhi zoning polygons."""
    import urllib.parse
    q = clean_location_str(location_query)
    if not q or len(q) < 2:
        return "Nill", "-", "Invalid"

    q_encoded = urllib.parse.quote_plus(f"{q} Delhi NCR India")

    # 1. LocationIQ (5,000 free requests/day)
    if (provider.startswith("LocationIQ") or provider == "LocationIQ") and api_key and len(api_key.strip()) >= 10:
        try:
            url = f"https://us1.locationiq.com/v1/search.php?key={api_key.strip()}&q={q_encoded}&format=json&limit=1"
            headers = {"User-Agent": "DelhiODSurveyDashboard/2.0"}
            resp = requests.get(url, headers=headers, timeout=4)
            if resp.status_code == 200:
                data = resp.json()
                if data and isinstance(data, list) and len(data) > 0:
                    lat = float(data[0]["lat"])
                    lng = float(data[0]["lon"])
                    z_no, w_name = find_delhi_zone_by_lat_lng(lng, lat)
                    disp_name = data[0].get("display_name", q.title()).split(",")[0].strip()
                    return disp_name, z_no, "LocationIQ Spatial"
        except Exception:
            pass

    # 2. Geoapify (3,000 free credits/day)
    if (provider.startswith("Geoapify") or provider == "Geoapify") and api_key and len(api_key.strip()) >= 10:
        try:
            url = f"https://api.geoapify.com/v1/geocode/search?text={q_encoded}&apiKey={api_key.strip()}&limit=1"
            headers = {"User-Agent": "DelhiODSurveyDashboard/2.0"}
            resp = requests.get(url, headers=headers, timeout=4)
            if resp.status_code == 200:
                data = resp.json()
                features = data.get("features", [])
                if features:
                    props = features[0].get("properties", {})
                    lat = float(props.get("lat"))
                    lng = float(props.get("lon"))
                    z_no, w_name = find_delhi_zone_by_lat_lng(lng, lat)
                    disp_name = props.get("name") or props.get("formatted", q.title()).split(",")[0].strip()
                    return disp_name, z_no, "Geoapify Spatial"
        except Exception:
            pass

    # 3. Google Maps Geocoding
    if (provider.startswith("Google") or provider == "Google Maps") and api_key and len(api_key.strip()) >= 10:
        try:
            url = f"https://maps.googleapis.com/maps/api/geocode/json?address={q_encoded}&key={api_key.strip()}"
            resp = requests.get(url, timeout=4)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("results"):
                    loc = data["results"][0]["geometry"]["location"]
                    lat, lng = loc["lat"], loc["lng"]
                    z_no, w_name = find_delhi_zone_by_lat_lng(lng, lat)
                    disp_name = data["results"][0].get("formatted_address", q.title()).split(",")[0].strip()
                    return disp_name, z_no, "Google Maps Spatial"
        except Exception:
            pass

    # 4. OpenStreetMap Nominatim (Free, No Key required)
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={q_encoded}&format=json&limit=1"
        headers = {"User-Agent": "DelhiODSurveyDashboard/2.0 (systragroup-survey-research)"}
        resp = requests.get(url, headers=headers, timeout=3)
        if resp.status_code == 200:
            results = resp.json()
            if results:
                lat = float(results[0]["lat"])
                lng = float(results[0]["lon"])
                z_no, w_name = find_delhi_zone_by_lat_lng(lng, lat)
                disp_name = results[0].get("display_name", q.title()).split(",")[0].strip()
                return disp_name, z_no, "OSM Spatial Match"
    except Exception:
        pass

    return "Nill", "-", "Unmatched"

def resolve_od_batch_with_llm(
    raw_locations: list[str],
    provider: str = "Google Gemini",
    api_key: str = "",
    endpoint_url: str = "http://localhost:11434",
    model_name: str = "gemini-1.5-flash",
) -> dict[str, tuple[str, str, str]]:
    """Resolves noisy survey OD locations using semantic LLMs (Gemini / Ollama / OpenAI) with context-grounded Delhi zoning."""
    if not raw_locations:
        return {}

    wards = get_clean_wards_dict()
    # List of official Delhi administrative wards & zones
    ward_names = [f"{name} (Zone {z})" for name, z in list(wards.values())]
    ward_context_str = ", ".join(ward_names)

    prompt = f"""ROLE:
You are an expert Delhi-NCR Urban Geography and Transport Survey Data Cleaner.
You specialize in matching noisy, hand-typed field-survey location names to
official Delhi administrative ward/zone records.

REFERENCE DATA:
You are given the official list of 295 Delhi wards with their Zone Numbers,
extracted from Final_zoning_delhi.kml:
{ward_context_str}

TASK:
For each raw input location string, find the single best-matching official
ward name and return its zone number — using human-level judgment, not just
exact or near-exact string matching.

MATCHING METHODOLOGY (apply in order):
1. Normalize the raw string: lowercase, strip extra spaces, expand common
   survey abbreviations (Vill./Vilage -> Village, Ind. -> Industrial,
   Sec -> Sector, Jn./Junc -> Junction, Nr -> Near, Rd -> Road).
2. Check for phonetic/spelling variants of an official ward name (e.g.
   transposed letters, dropped/doubled letters, colloquial Hindi-English
   transliteration spellings like "Devoli"/"Devolli" for "Deoli").
3. Check for partial or landmark-based matches — a survey point may name a
   junction, market, metro station, or road that sits inside/adjacent to an
   official ward (e.g. "IIT Gate Junc" -> falls within Hauz Khas ward). Use
   the nearest containing ward, not a literal name match.
4. If the location clearly belongs to another NCR city/district (Noida,
   Gurgaon/Gurugram, Faridabad, Ghaziabad, Sonipat, Bahadurgarh, Greater
   Noida, etc.) — including sector/village names typical of those cities —
   mark it Outside Delhi, even if no exact match is found in the reference list.
5. If two or more official wards are plausible matches and the raw string
   gives no way to disambiguate, choose the closer/more common match but
   flag it with "confidence": "low".
6. Only mark a location "Nill" / zone "-" if it is truly unintelligible
   gibberish, blank, or contains no locational signal at all (e.g. "asdfgh",
   "xxx", "123", a single stray character).

DO NOT:
- Force-fit an unrelated ward just to avoid "Outside" or "Nill".
- Invent a ward name that isn't in the reference list.
- Treat every unfamiliar string as gibberish — try steps 1–4 first.

OUTPUT FORMAT:
Respond ONLY with a valid JSON array, no markdown, no commentary, in this schema:
[
  {{
    "raw": "<original input string>",
    "corrected_od": "<official ward name, or 'Nill'>",
    "zone_no": "<zone number as string, 'Outside', or '-'>",
    "confidence": "<'high' | 'medium' | 'low'>"
  }}
]

FEW-SHOT EXAMPLES:
"Great Kailash" -> {{"raw": "Great Kailash", "corrected_od": "Greater Kailash", "zone_no": "9", "confidence": "high"}}
"Devolli Village" -> {{"raw": "Devolli Village", "corrected_od": "Deoli", "zone_no": "26", "confidence": "high"}}
"Badli Ind Area" -> {{"raw": "Badli Ind Area", "corrected_od": "Badli Industrial Area", "zone_no": "32", "confidence": "high"}}
"Hauz Khas Vilage" -> {{"raw": "Hauz Khas Vilage", "corrected_od": "Hauz Khas", "zone_no": "8", "confidence": "high"}}
"IIT Gate Junc" -> {{"raw": "IIT Gate Junc", "corrected_od": "Hauz Khas", "zone_no": "8", "confidence": "medium"}}
"Noida Sec 62" -> {{"raw": "Noida Sec 62", "corrected_od": "Noida Sector 62", "zone_no": "Outside", "confidence": "high"}}
"asdfghjk" -> {{"raw": "asdfghjk", "corrected_od": "Nill", "zone_no": "-", "confidence": "high"}}

INPUT LOCATION NAMES:
{json.dumps(raw_locations)}
"""

    response_text = ""
    # 1. Google Gemini API
    if "Gemini" in provider and api_key and len(api_key.strip()) >= 10:
        key_clean = api_key.strip()
        m_req = model_name.split(" ")[0].strip().lower()
        if not m_req:
            m_req = "gemini-3.7-flash"

        candidate_models = [
            m_req,
            "gemini-3.7-flash",
            "gemini-3.5-flash-lite",
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-3.1-pro",
            "gemini-1.5-pro",
        ]
        candidate_models = list(dict.fromkeys(candidate_models))

        # Try modern google-genai Client first (Official Google GenAI SDK)
        try:
            from google import genai
            client = genai.Client(api_key=key_clean)
            for c_model in candidate_models:
                try:
                    res = client.models.generate_content(
                        model=c_model,
                        contents=prompt,
                    )
                    if res and hasattr(res, "text") and res.text:
                        response_text = res.text
                        break
                except Exception as sdk_err:
                    st.session_state["llm_api_last_error"] = f"GenAI SDK ({c_model}): {str(sdk_err)[:200]}"
                    continue
        except Exception:
            pass

        # Try legacy google.generativeai SDK
        if not response_text:
            try:
                import google.generativeai as legacy_genai
                legacy_genai.configure(api_key=key_clean)
                for c_model in candidate_models:
                    try:
                        m_obj = legacy_genai.GenerativeModel(c_model)
                        res = m_obj.generate_content(
                            prompt,
                            generation_config={"temperature": 0.1, "response_mime_type": "application/json"}
                        )
                        if res and res.text:
                            response_text = res.text
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        # Fallback to multi-version REST API
        if not response_text:
            for c_model in candidate_models:
                for api_ver in ["v1beta", "v1"]:
                    try:
                        url = f"https://generativelanguage.googleapis.com/{api_ver}/models/{c_model}:generateContent?key={key_clean}"
                        payload = {
                            "contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}
                        }
                        resp = requests.post(url, json=payload, timeout=25)
                        if resp.status_code == 200:
                            data = resp.json()
                            if data.get("candidates") and data["candidates"][0].get("content"):
                                response_text = data["candidates"][0]["content"]["parts"][0]["text"]
                                break
                        elif resp.status_code in [400, 403, 404]:
                            st.session_state["llm_api_last_error"] = f"Google API ({c_model}/{api_ver}): HTTP {resp.status_code} - {resp.text[:200]}"
                    except Exception as ex:
                        st.session_state["llm_api_last_error"] = f"Network Error: {str(ex)[:200]}"
                if response_text:
                    break

    # 2. Ollama Local / Offline
    elif "Ollama" in provider:
        try:
            base_url = endpoint_url.strip().rstrip("/") if endpoint_url and len(endpoint_url.strip()) > 5 else "http://localhost:11434"
            m = model_name.strip() if model_name and len(model_name.strip()) > 1 else "llama3.2"
            url = f"{base_url}/api/chat"
            payload = {
                "model": m,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "format": "json"
            }
            resp = requests.post(url, json=payload, timeout=45)
            if resp.status_code == 200:
                response_text = resp.json().get("message", {}).get("content", "")
        except Exception:
            pass

    # 3. OpenAI / Custom Endpoint
    elif "OpenAI" in provider and api_key and len(api_key.strip()) >= 10:
        try:
            m = model_name.strip() if model_name and len(model_name.strip()) > 3 else "gpt-4o-mini"
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"}
            payload = {
                "model": m,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "temperature": 0.1
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=25)
            if resp.status_code == 200:
                response_text = resp.json()["choices"][0]["message"]["content"]
        except Exception:
            pass

    # Parse JSON
    result_map = {}
    if response_text:
        try:
            clean_json = re.sub(r"^```json\s*|\s*```$", "", response_text.strip(), flags=re.MULTILINE)
            parsed = json.loads(clean_json)
            if isinstance(parsed, dict):
                for val in parsed.values():
                    if isinstance(val, list):
                        parsed = val
                        break
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        r = item.get("raw", "").strip()
                        c = item.get("corrected_od", "Nill").strip()
                        z = str(item.get("zone_no", "-")).strip()
                        conf = str(item.get("confidence", "high")).strip()
                        if r and c != "Nill" and z != "-":
                            result_map[r] = (c, z, f"AI Semantic ({conf})")
        except Exception:
            pass

    return result_map

def clean_location_str(text: str) -> str:
    if not text:
        return ""
    t = re.sub(r"[^a-zA-Z0-9\s]", " ", str(text)).strip().lower()
    return re.sub(r"\s+", " ", t)

GENERIC_STOPWORDS = {
    "village", "vill", "gaon", "nagar", "vihar", "enclave", "colony", "park",
    "road", "rd", "marg", "block", "sector", "sec", "phase", "pocket", "pkt",
    "market", "mkt", "mandir", "temple", "station", "stn", "stand", "terminal", "gate",
    "dehli", "delhi", "east", "west", "north", "south", "central", "old", "new",
    "puri", "mor", "chowk", "extn", "extension", "ext", "area", "ind",
    "industrial", "near", "opp", "opposite",
}

def clean_core_proper_noun(text: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9\s]", " ", str(text)).lower()
    words = [w for w in clean.split() if w not in GENERIC_STOPWORDS and len(w) > 1]
    return " ".join(words)

@functools.lru_cache(maxsize=1)
def get_all_target_cores_dict() -> dict[str, tuple[str, str, str]]:
    all_targets = {**DELHI_LANDMARK_MAPPINGS, **(get_clean_wards_dict() or {})}
    core_map = {}
    for k, (name, z) in all_targets.items():
        c = clean_core_proper_noun(k)
        if c and c not in core_map:
            core_map[c] = (name, str(z), k)
    return core_map

@functools.lru_cache(maxsize=8192)
def suggest_corrected_od_and_zone(raw_text: str) -> tuple[str, str, str]:
    raw_str = str(raw_text).strip()
    if not raw_str or raw_str.lower() in INVALID_TEXT:
        return "Nill", "-", "Invalid"

    cleaned = clean_location_str(raw_str)
    if not cleaned or len(cleaned) < 2 or cleaned in ["test", "bus stand", "bus stop"]:
        return "Nill", "-", "Invalid"

    # 1. Check Outside Delhi keywords
    for out_key in OUTSIDE_DELHI_KEYWORDS:
        if cleaned == out_key or cleaned.startswith(out_key + " ") or cleaned.endswith(" " + out_key) or f" {out_key} " in f" {cleaned} ":
            clean_title = " ".join([w.capitalize() for w in cleaned.split()])
            return clean_title, "Outside", "Outside Delhi"

    clean_wards = get_clean_wards_dict()
    all_targets = {**DELHI_LANDMARK_MAPPINGS, **(clean_wards or {})}

    # 2. Strict Exact match in landmark / ward dictionary
    if cleaned in all_targets:
        corr, z_no = all_targets[cleaned]
        return corr, str(z_no), "Exact Match"

    # 3. Compressed spaces match (e.g. "kalka ji" -> "kalkaji", "madan giri" -> "madangir")
    compressed = cleaned.replace(" ", "")
    for k, (corr, z_no) in all_targets.items():
        if k.replace(" ", "") == compressed:
            return corr, str(z_no), "Exact Match"

    # 4. Strip noise suffixes and re-test against landmarks & wards
    q_stripped = cleaned
    for suf in STOP_SUFFIXES:
        if q_stripped.endswith(" " + suf):
            q_stripped = q_stripped[:-len(suf)-1].strip()
            break

    if q_stripped in all_targets:
        corr, z_no = all_targets[q_stripped]
        return corr, str(z_no), "Exact Match"

    # If not an exact match or known alias, return Nill (NO AI FUZZY GUESSING)
    return "Nill", "-", "Unmatched"


# ─────────────────────────────────────────────────────────────────────────────
# FILE LOAD
# ─────────────────────────────────────────────────────────────────────────────
st.sidebar.title("🚦 Delhi OD Dashboard")
st.sidebar.markdown("---")

# ── TrafficLenz Auto-Download ─────────────────────────────────────────────
st.sidebar.subheader("🔄 Live Data from TrafficLenz")

_downloader_available = False
try:
    from downloader import (
        config_from_secrets,
        config_is_valid,
        download_excel_bytes,
        has_saved_session,
        perform_interactive_login,
    )
    _tl_config = config_from_secrets()
    _tl_ok, _tl_reason = config_is_valid(_tl_config)
    _downloader_available = _tl_ok
except Exception as _dl_import_err:
    _tl_ok = False
    _tl_reason = str(_dl_import_err)

if _downloader_available:
    _has_session = has_saved_session(_tl_config)
    import sys
    _is_cloud = sys.platform.startswith("linux") and not os.environ.get("DISPLAY")
    
    if _has_session:
        st.sidebar.success("🟢 TrafficLenz Connected")
    else:
        st.sidebar.warning("🟠 One-time login required")

    sync_clicked = False

    if _is_cloud:
        # On Cloud: only show Sync button if session exists, otherwise show secret guidance
        if _has_session:
            sync_clicked = st.sidebar.button("🔄 Sync Data", use_container_width=True, help="Fetch latest survey report directly into memory")
        else:
            st.sidebar.info("💡 To enable sync on Streamlit Cloud, add your `TL_SESSION_JSON` into App Secrets.")
    else:
        # On Local Desktop: show both 1-Click Login and Sync Data buttons
        col_btn1, col_btn2 = st.sidebar.columns(2)
        with col_btn1:
            if st.button("🔑 Login / Connect", use_container_width=True, help="Opens browser to complete 1-time CAPTCHA login"):
                with st.spinner("Opening browser for login... Please check the 'I am not a robot' CAPTCHA."):
                    try:
                        success = perform_interactive_login(_tl_config)
                        if success:
                            st.sidebar.success("✅ Logged in & session saved!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.sidebar.error("❌ Login was not completed.")
                    except Exception as _login_err:
                        st.sidebar.error(f"Login error: {_login_err}")

        with col_btn2:
            sync_clicked = st.button("🔄 Sync Data", use_container_width=True, help="Fetch latest survey report directly into memory")

    if sync_clicked:
        with st.spinner("🌐 Syncing latest survey data from TrafficLenz..."):
            try:
                _raw_bytes, _ts = download_excel_bytes(_tl_config)
                st.session_state["tl_data_bytes"] = _raw_bytes
                st.session_state["tl_sync_time"] = _ts
                st.sidebar.success(f"✅ Synced at {_ts}")
                process_dataframe.clear()
                st.rerun()
            except Exception as _sync_err:
                st.sidebar.error(f"❌ Sync failed: {_sync_err}")
                if _is_cloud:
                    st.sidebar.info("💡 If your session expired, update `TL_SESSION_JSON` in your Streamlit Cloud Secrets.")
                else:
                    st.sidebar.info("💡 If your session expired or captcha is required, click '🔑 Login / Connect' above.")

    if "tl_sync_time" in st.session_state:
        st.sidebar.caption(f"Last synced: **{st.session_state['tl_sync_time']}**")
else:
    if _tl_reason:
        st.sidebar.info(f"ℹ️ Auto-download not configured:\n{_tl_reason}")

st.sidebar.markdown("---")

# ── Manual Upload (always available as fallback) ──────────────────────────
st.sidebar.subheader("📂 Or Upload File Manually")

uploaded_file = st.sidebar.file_uploader(
    "Upload Delhi OD Excel file",
    type=["xlsx"],
)

# ── Resolve which file to use (priority: uploaded > live sync > default) ──
if uploaded_file is not None:
    file_bytes = uploaded_file.read()
    file_name = uploaded_file.name
    st.sidebar.success(f"✅ Loaded: {file_name}")
elif "tl_data_bytes" in st.session_state and st.session_state["tl_data_bytes"]:
    file_bytes = st.session_state["tl_data_bytes"]
    _last_ts = st.session_state.get("tl_sync_time", "")
    file_name = f"TrafficLenz Live Report ({_last_ts})"
    st.sidebar.info(f"📊 Using live synced data ({_last_ts})")
elif os.path.exists(DEFAULT_FILE):
    with open(DEFAULT_FILE, "rb") as f:
        file_bytes = f.read()
    file_name = DEFAULT_FILE
    st.sidebar.info(f"Using default file: {DEFAULT_FILE}")
else:
    st.warning("⚠️ No survey file loaded. Click **🔄 Sync Data** or upload a file manually.")
    st.stop()


with st.spinner("Loading and processing Delhi OD survey data..."):
    df = process_dataframe(file_bytes)

filtered_df = filter_dataframe(df)


# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.title("Delhi OD Passenger / Goods Survey Dashboard")

st.caption(
    f"File: {file_name} | Last updated: "
    f"{datetime.now(IST).strftime('%d %b %Y %I:%M:%S %p')} IST"
)

if COL_LOCATION in df.columns and df[COL_LOCATION].notna().any():
    valid_locs = df[COL_LOCATION].dropna().astype(str).tolist()
    sample_loc = None
    for loc_str in reversed(valid_locs):
        loc_str = loc_str.strip()
        if "," in loc_str and loc_str.lower() not in INVALID_TEXT:
            try:
                lat, lon = map(float, loc_str.split(","))
                sample_loc = loc_str
                break
            except Exception:
                continue

    if sample_loc:
        try:
            lat, lon = map(float, sample_loc.split(","))
            with st.expander(f"📍 Show Survey Site Map ({lat:.4f}, {lon:.4f})"):
                st.map(pd.DataFrame({"lat": [lat], "lon": [lon]}))
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────
tabs = st.tabs(
    [
        "📊 Summary",
        "👷 Surveyors",
        "🚗 Vehicles",
        "🚩 Suspicious OD",
        "🔁 Shift / Frequency / Purpose",
        "📄 Raw Data",
        "🗺️ Output",
    ]
)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
with tabs[0]:
    st.subheader("📊 Survey Summary")

    total_records = len(filtered_df)

    passenger_count = int(
        filtered_df["survey_type"].astype(str).str.lower().eq("passenger").sum()
    )
    goods_count = int(
        filtered_df["survey_type"].astype(str).str.lower().eq("goods").sum()
    )
    active_surveyors = filtered_df["surveyor"].nunique()

    top_vehicle = (
        filtered_df["vehicle_type"].mode().iloc[0]
        if not filtered_df["vehicle_type"].dropna().empty
        else "N/A"
    )

    od_completeness = (
        round(filtered_df["has_origin_destination"].mean() * 100, 1)
        if total_records
        else 0.0
    )

    suspicious_count = int(filtered_df["sample_quality_suspicious"].sum())
    suspicious_pct = (
        round(suspicious_count / total_records * 100, 1)
        if total_records
        else 0.0
    )

    avg_duration = (
        round(filtered_df["survey_duration_mins"].mean(), 2)
        if filtered_df["survey_duration_mins"].notna().any()
        else 0
    )

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total Surveys", total_records)
    c2.metric("Passenger", passenger_count)
    c3.metric("Goods", goods_count)
    c4.metric("Active Surveyors", active_surveyors)
    c5.metric("Top Vehicle", top_vehicle)
    c6.metric("OD Completeness", f"{od_completeness}%")

    c7, c8, c9 = st.columns(3)
    c7.metric("Avg Entry Duration", f"{avg_duration} min")
    c8.metric("Suspicious OD Records", suspicious_count)
    c9.metric("Suspicious OD %", f"{suspicious_pct}%")

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        hourly = (
            filtered_df.dropna(subset=["start_hour"])
            .groupby("start_hour")
            .size()
            .reset_index(name="Survey Count")
            .sort_values("start_hour")
        )

        if not hourly.empty:
            fig = px.bar(
                hourly,
                x="start_hour",
                y="Survey Count",
                title="Hourly Survey Distribution",
                labels={"start_hour": "Hour of Day"},
                color_discrete_sequence=[PRIMARY_COLOR],
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No hourly data available.")

    with col2:
        daily = (
            filtered_df.dropna(subset=[COL_DATE])
            .groupby(filtered_df[COL_DATE].dt.date)
            .size()
            .reset_index(name="Survey Count")
        )

        daily.columns = ["Date", "Survey Count"]

        if not daily.empty:
            fig = px.line(
                daily,
                x="Date",
                y="Survey Count",
                markers=True,
                title="Daily Survey Trend",
            )
            fig.update_traces(line_color=PRIMARY_COLOR)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No daily data available.")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — SURVEYORS
# ─────────────────────────────────────────────────────────────────────────────
with tabs[1]:
    st.subheader("👷 Surveyor Performance & Activity Monitoring")

    surveyor_base = filtered_df[filtered_df["surveyor"].notna()].copy()

    if surveyor_base.empty:
        st.info("No surveyor data available.")
    else:
        subtab_s1, subtab_s2, subtab_s3 = st.tabs(
            [
                "📊 Overview & Performance",
                "👤 Individual Surveyor Activity",
                "⏱️ Short Entry Duration",
            ]
        )

        # ── SUBTAB S1: Overview & Performance ────────────────────────────────
        with subtab_s1:
            summary = (
                surveyor_base.groupby("surveyor")
                .agg(
                    Total_Surveys=("surveyor", "size"),
                    Passenger_Surveys=(
                        "survey_type",
                        lambda x: int(x.astype(str).str.lower().eq("passenger").sum()),
                    ),
                    Goods_Surveys=(
                        "survey_type",
                        lambda x: int(x.astype(str).str.lower().eq("goods").sum()),
                    ),
                    Directions=(
                        "direction",
                        lambda x: ", ".join(sorted(set(x.dropna().astype(str)))),
                    ),
                    Vehicle_Types=(
                        "vehicle_type",
                        lambda x: ", ".join(sorted(set(x.dropna().astype(str)))),
                    ),
                    First_Entry=(
                        COL_START,
                        lambda x: min(t.strftime("%H:%M:%S") for t in x.dropna())
                        if len(x.dropna())
                        else "-",
                    ),
                    Last_Entry=(
                        COL_END,
                        lambda x: max(t.strftime("%H:%M:%S") for t in x.dropna())
                        if len(x.dropna())
                        else "-",
                    ),
                    Avg_Duration_Mins=("survey_duration_mins", "mean"),
                    Suspicious_OD=("sample_quality_suspicious", "sum"),
                )
                .reset_index()
                .rename(
                    columns={
                        "surveyor": "Surveyor",
                        "Total_Surveys": "Total Surveys",
                        "Passenger_Surveys": "Passenger Surveys",
                        "Goods_Surveys": "Goods Surveys",
                        "Vehicle_Types": "Vehicle Types",
                        "Avg_Duration_Mins": "Avg Duration (mins)",
                        "Suspicious_OD": "Suspicious OD",
                    }
                )
                .sort_values("Total Surveys", ascending=False)
            )

            summary["Avg Duration (mins)"] = summary["Avg Duration (mins)"].round(2)
            summary["Suspicious OD"] = summary["Suspicious OD"].astype(int)

            st.dataframe(summary, use_container_width=True)

            fig = px.bar(
                summary.sort_values("Total Surveys", ascending=True),
                x="Total Surveys",
                y="Surveyor",
                orientation="h",
                title="Surveys per Surveyor",
                color_discrete_sequence=[PRIMARY_COLOR],
            )
            st.plotly_chart(fig, use_container_width=True)

        # ── SUBTAB S2: Individual Surveyor Activity ──────────────────────────
        with subtab_s2:
            st.markdown("### 👤 Individual Surveyor Activity Monitoring")
            surveyor_names = sorted(surveyor_base["surveyor"].dropna().unique().tolist())

            sel_surveyor = st.selectbox(
                "Select Surveyor to Inspect",
                options=surveyor_names,
                key="surveyor_activity_select",
            )

            if sel_surveyor:
                s_df = surveyor_base[surveyor_base["surveyor"] == sel_surveyor].copy()
                s_total = len(s_df)
                s_pass = int(s_df["survey_type"].astype(str).str.lower().eq("passenger").sum())
                s_goods = int(s_df["survey_type"].astype(str).str.lower().eq("goods").sum())
                s_susp = int(s_df["sample_quality_suspicious"].sum())
                s_avg_dur = round(s_df["survey_duration_mins"].mean(), 2) if s_df["survey_duration_mins"].notna().any() else 0.0
                s_min_dur = round(s_df["entry_duration_sec"].min(), 0) if s_df["entry_duration_sec"].notna().any() else 0
                s_max_dur = round(s_df["entry_duration_sec"].max(), 0) if s_df["entry_duration_sec"].notna().any() else 0

                # Metric cards
                m1, m2, m3, m4, m5, m6 = st.columns(6)
                m1.metric("Total Surveys", s_total)
                m2.metric("Passenger", s_pass)
                m3.metric("Goods", s_goods)
                m4.metric("Avg Entry Time", f"{s_avg_dur} min")
                m5.metric("Fastest Entry", format_seconds(s_min_dur))
                m6.metric("Suspicious ODs", s_susp)

                st.markdown("---")

                # Activity Charts
                col_c1, col_c2 = st.columns(2)

                with col_c1:
                    # Hourly Timeline
                    if "start_hour" in s_df.columns and s_df["start_hour"].notna().any():
                        s_hourly = (
                            s_df.groupby("start_hour")
                            .size()
                            .reset_index(name="Count")
                            .sort_values("start_hour")
                        )
                        fig_sh = px.bar(
                            s_hourly,
                            x="start_hour",
                            y="Count",
                            title=f"Hourly Activity ({sel_surveyor})",
                            labels={"start_hour": "Hour of Day", "Count": "Surveys"},
                            color_discrete_sequence=[PRIMARY_COLOR],
                        )
                        st.plotly_chart(fig_sh, use_container_width=True)
                    else:
                        st.info("No hourly start time data.")

                with col_c2:
                    # Vehicle Types Breakdown
                    s_vtype = s_df["vehicle_type"].value_counts().reset_index()
                    s_vtype.columns = ["Vehicle Type", "Count"]
                    if not s_vtype.empty:
                        fig_sv = px.pie(
                            s_vtype,
                            names="Vehicle Type",
                            values="Count",
                            title=f"Vehicle Types Surveyed ({sel_surveyor})",
                            color_discrete_sequence=px.colors.sequential.Blues_r,
                        )
                        fig_sv.update_traces(textinfo="percent+label")
                        st.plotly_chart(fig_sv, use_container_width=True)
                    else:
                        st.info("No vehicle type data.")

                # Detailed table of this surveyor's entries
                st.markdown(f"### 📋 Detailed Survey Log — {sel_surveyor} ({s_total} records)")
                s_display = prepare_display(s_df)
                st.dataframe(s_display, use_container_width=True)

                st.download_button(
                    f"⬇️ Download {sel_surveyor} Records (CSV)",
                    data=make_download_csv(s_display),
                    file_name=f"{sel_surveyor.replace(' ', '_').lower()}_survey_log.csv",
                    mime="text/csv",
                )

        # ── SUBTAB S3: Short Entry Duration ──────────────────────────────────
        with subtab_s3:
            st.markdown("### ⏱️ Short Entry Duration Check")
            st.caption(
                "Corrected logic: this uses each row's entry duration "
                "`end_time - start_time`. It does not use previous entry gap."
            )

            t1, t2, t3 = st.columns([1, 1, 4])

            with t1:
                duration_min = st.number_input(
                    "Threshold minutes",
                    min_value=0,
                    max_value=60,
                    value=4,
                    step=1,
                    key="duration_threshold_min",
                )

            with t2:
                duration_sec = st.number_input(
                    "Threshold seconds",
                    min_value=0,
                    max_value=59,
                    value=0,
                    step=5,
                    key="duration_threshold_sec",
                )

            threshold_sec = duration_min * 60 + duration_sec

            with t3:
                st.markdown(
                    f"<div style='padding-top:28px;color:#666;'>"
                    f"Flagging entries with duration below "
                    f"<b>{duration_min}m {duration_sec:02d}s</b> "
                    f"({threshold_sec} seconds)"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            duration_df = filtered_df[
                filtered_df["entry_duration_sec"].notna()
                & (filtered_df["entry_duration_sec"] >= 0)
                & (filtered_df["entry_duration_sec"] < threshold_sec)
            ].copy()

            if duration_df.empty:
                st.success("No short-duration entries found for selected threshold.")
            else:
                k1, k2, k3, k4 = st.columns(4)

                k1.metric("Short Entries", len(duration_df))
                k2.metric("Surveyors Flagged", duration_df["surveyor"].nunique())
                k3.metric(
                    "Shortest Entry",
                    format_seconds(duration_df["entry_duration_sec"].min()),
                )
                k4.metric(
                    "Most Flagged Surveyor",
                    duration_df["surveyor"].value_counts().idxmax(),
                )

                st.markdown("### Summary by Surveyor")

                duration_summary = (
                    duration_df.groupby("surveyor")
                    .agg(
                        Short_Entries=("surveyor", "size"),
                        Shortest_Duration_Sec=("entry_duration_sec", "min"),
                        Avg_Duration_Sec=("entry_duration_sec", "mean"),
                    )
                    .reset_index()
                    .rename(columns={"surveyor": "Surveyor"})
                    .sort_values("Short_Entries", ascending=False)
                )

                duration_summary["Shortest Duration"] = duration_summary[
                    "Shortest_Duration_Sec"
                ].apply(format_seconds)

                duration_summary["Avg Duration"] = duration_summary[
                    "Avg_Duration_Sec"
                ].apply(format_seconds)

                duration_summary = duration_summary[
                    [
                        "Surveyor",
                        "Short_Entries",
                        "Shortest Duration",
                        "Avg Duration",
                    ]
                ].rename(columns={"Short_Entries": "Short Entries"})

                st.dataframe(duration_summary, use_container_width=True)

                st.markdown("### Flagged Entry Details")

                duration_display = prepare_display(duration_df)
                st.dataframe(duration_display, use_container_width=True)

                st.download_button(
                    "⬇️ Download Short Entry Duration Records CSV",
                    data=make_download_csv(duration_display),
                    file_name="short_entry_duration_records.csv",
                    mime="text/csv",
                )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — VEHICLES
# ─────────────────────────────────────────────────────────────────────────────
with tabs[2]:
    st.subheader("🚗 Vehicle Type Analysis")

    vehicle_summary = (
        filtered_df.dropna(subset=["vehicle_type"])
        .groupby(["survey_type", "vehicle_type"])
        .agg(
            Count=("vehicle_type", "size"),
            Avg_Passenger_Occupancy=("passenger_occupancy", "mean"),
            Avg_Bus_Sitting_Pct=("bus_sitting_pct", "mean"),
        )
        .reset_index()
        .sort_values("Count", ascending=False)
    )

    if vehicle_summary.empty:
        st.info("No vehicle data available.")
    else:
        total_v = vehicle_summary["Count"].sum()
        vehicle_summary["Share (%)"] = (
            vehicle_summary["Count"] / total_v * 100
        ).round(1)

        vehicle_summary["Avg_Passenger_Occupancy"] = vehicle_summary[
            "Avg_Passenger_Occupancy"
        ].round(1)

        vehicle_summary["Avg_Bus_Sitting_Pct"] = vehicle_summary[
            "Avg_Bus_Sitting_Pct"
        ].round(1)

        col1, col2 = st.columns(2)

        with col1:
            fig = px.pie(
                vehicle_summary,
                names="vehicle_type",
                values="Count",
                title="Vehicle Type Share",
                color_discrete_sequence=px.colors.sequential.Blues_r,
            )
            fig.update_traces(textinfo="percent+label")
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            fig = px.bar(
                vehicle_summary,
                x="vehicle_type",
                y="Count",
                color="survey_type",
                title="Vehicle Count by Survey Type",
                labels={
                    "vehicle_type": "Vehicle Type",
                    "survey_type": "Survey Type",
                },
            )
            fig.update_layout(xaxis_tickangle=-30)
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            vehicle_summary.rename(
                columns={
                    "survey_type": "Survey Type",
                    "vehicle_type": "Vehicle Type",
                    "Avg_Passenger_Occupancy": "Avg Passenger Occupancy",
                    "Avg_Bus_Sitting_Pct": "Avg Bus Sitting %",
                }
            ),
            use_container_width=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — SUSPICIOUS OD
# ─────────────────────────────────────────────────────────────────────────────
with tabs[3]:
    st.subheader("🚩 Suspicious OD Records")

    st.caption(
        "Suspicious OD records only consider Delhi, New Delhi, Gurugram/Gurgaon, "
        "and Noida when entered without adequate locality/sector detail."
    )

    suspicious = filtered_df[filtered_df["sample_quality_suspicious"] == True].copy()

    total_records = len(filtered_df)
    suspicious_count = len(suspicious)
    suspicious_pct = (
        round(suspicious_count / total_records * 100, 1)
        if total_records
        else 0.0
    )

    k1, k2, k3 = st.columns(3)
    k1.metric("Filtered Records", total_records)
    k2.metric("Suspicious OD Records", suspicious_count)
    k3.metric("Suspicious OD %", f"{suspicious_pct}%")

    if suspicious.empty:
        st.success("No suspicious OD records found.")
    else:
        flags_series = suspicious["sample_quality_flags"].fillna("").astype(str)

        origin_delhi_mask = flags_series.str.contains(
            "Origin Delhi/New Delhi without locality",
            case=False,
            regex=False,
            na=False,
        )

        destination_delhi_mask = flags_series.str.contains(
            "Destination Delhi/New Delhi without locality",
            case=False,
            regex=False,
            na=False,
        )

        origin_gurugram_mask = flags_series.str.contains(
            "Origin Gurugram/Gurgaon without sector/locality",
            case=False,
            regex=False,
            na=False,
        )

        destination_gurugram_mask = flags_series.str.contains(
            "Destination Gurugram/Gurgaon without sector/locality",
            case=False,
            regex=False,
            na=False,
        )

        origin_noida_mask = flags_series.str.contains(
            "Origin Noida without sector/locality",
            case=False,
            regex=False,
            na=False,
        )

        destination_noida_mask = flags_series.str.contains(
            "Destination Noida without sector/locality",
            case=False,
            regex=False,
            na=False,
        )

        table_specs = [
            (
                "1. Origin: Delhi / New Delhi without locality",
                suspicious[origin_delhi_mask],
                "origin_delhi_without_locality.csv",
            ),
            (
                "2. Destination: Delhi / New Delhi without locality",
                suspicious[destination_delhi_mask],
                "destination_delhi_without_locality.csv",
            ),
            (
                "3. Origin: Gurugram/Gurgaon without sector/locality",
                suspicious[origin_gurugram_mask],
                "origin_gurugram_without_locality.csv",
            ),
            (
                "4. Destination: Gurugram/Gurgaon without sector/locality",
                suspicious[destination_gurugram_mask],
                "destination_gurugram_without_locality.csv",
            ),
            (
                "5. Origin: Noida without sector/locality",
                suspicious[origin_noida_mask],
                "origin_noida_without_locality.csv",
            ),
            (
                "6. Destination: Noida without sector/locality",
                suspicious[destination_noida_mask],
                "destination_noida_without_locality.csv",
            ),
        ]

        for title, subset, filename in table_specs:
            st.markdown(f"### {title}")

            if subset.empty:
                st.success("No records found.")
            else:
                display_df = prepare_display(subset)
                st.dataframe(display_df, use_container_width=True)

                st.download_button(
                    f"⬇️ Download {title} CSV",
                    data=make_download_csv(display_df),
                    file_name=filename,
                    mime="text/csv",
                )

        with st.expander("Show all suspicious OD records"):
            all_display = prepare_display(suspicious)
            st.dataframe(all_display, use_container_width=True)

            st.download_button(
                "⬇️ Download All Suspicious OD Records CSV",
                data=make_download_csv(all_display),
                file_name="all_suspicious_od_records.csv",
                mime="text/csv",
            )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 5 — SHIFT / FREQUENCY / PURPOSE
# ─────────────────────────────────────────────────────────────────────────────
with tabs[4]:
    st.subheader("🔁 Shift, Frequency, Purpose and Commodity")

    col1, col2 = st.columns(2)

    with col1:
        shift_counts = filtered_df["likely_shift"].value_counts().reset_index()
        shift_counts.columns = ["Response", "Count"]

        if not shift_counts.empty:
            fig = px.pie(
                shift_counts,
                names="Response",
                values="Count",
                title="Likely to Shift to Proposed Corridor?",
                color_discrete_sequence=[SUCCESS, DANGER, GREY, WARNING],
            )
            fig.update_traces(textinfo="percent+label")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No shift response data available.")

    with col2:
        freq_counts = filtered_df["trip_frequency"].value_counts().reset_index()
        freq_counts.columns = ["Frequency", "Count"]

        if not freq_counts.empty:
            fig = px.bar(
                freq_counts,
                x="Frequency",
                y="Count",
                title="Trip Frequency",
                color_discrete_sequence=[PRIMARY_COLOR],
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No frequency data available.")

    col3, col4 = st.columns(2)

    with col3:
        st.markdown("### Passenger Purpose")

        purpose = (
            filtered_df[
                filtered_df["survey_type"].astype(str).str.lower() == "passenger"
            ]["trip_purpose_or_commodity"]
            .value_counts()
            .reset_index()
        )
        purpose.columns = ["Purpose", "Count"]

        if not purpose.empty:
            fig = px.bar(
                purpose,
                x="Purpose",
                y="Count",
                color_discrete_sequence=[PRIMARY_COLOR],
            )
            fig.update_layout(xaxis_tickangle=-30)
            st.plotly_chart(fig, use_container_width=True)

    with col4:
        st.markdown("### Goods Commodity")

        commodity = (
            filtered_df[
                filtered_df["survey_type"].astype(str).str.lower() == "goods"
            ]["trip_purpose_or_commodity"]
            .value_counts()
            .reset_index()
        )
        commodity.columns = ["Commodity", "Count"]

        if not commodity.empty:
            fig = px.bar(
                commodity,
                x="Commodity",
                y="Count",
                color_discrete_sequence=[SECONDARY],
            )
            fig.update_layout(xaxis_tickangle=-30)
            st.plotly_chart(fig, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 6 — RAW DATA
# ─────────────────────────────────────────────────────────────────────────────
with tabs[5]:
    st.subheader("📄 Filtered Raw Data")

    raw = prepare_display(filtered_df)

    st.dataframe(raw, use_container_width=True)

    st.download_button(
        "⬇️ Download Filtered Data CSV",
        data=make_download_csv(raw),
        file_name="filtered_delhi_od_survey_data.csv",
        mime="text/csv",
    )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 7 — OUTPUT & SPATIAL ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────
with tabs[6]:
    st.subheader("🗺️ Output & Spatial Analysis")

    subtab_o1, subtab_o2, subtab_o3 = st.tabs(
        [
            "🗺️ Delhi Zoning Map",
            "🛠️ OD Correction",
            "📊 Origin–Destination Analysis",
        ]
    )

    # ── SUBTAB O1: Delhi Zoning Map ──────────────────────────────────────────
    with subtab_o1:
        st.markdown("### 🗺️ Delhi Zoning Map Layer")
        geojson_data, centroids_data, df_zones = load_delhi_zoning_data(DELHI_ZONING_KML)

        if not geojson_data or not geojson_data.get("features"):
            st.warning(f"⚠️ Could not load Delhi Zoning KML file from `{DELHI_ZONING_KML}`.")
        else:
            # Fast vectorized zone aggregation (mapping unique strings only)
            zone_od_counts: dict[str, dict[str, int]] = {}

            if "origin" in filtered_df.columns:
                unique_origs = filtered_df["origin"].dropna().unique()
                orig_map = {str(o): suggest_corrected_od_and_zone(str(o)) for o in unique_origs}
                for orig_val, o_count in filtered_df["origin"].value_counts().items():
                    c_od, z_no, _ = orig_map.get(str(orig_val), ("Nill", "-", ""))
                    if c_od.lower() != "nill" and z_no and z_no != "-" and z_no != "Outside":
                        z_key = str(z_no)
                        if z_key not in zone_od_counts:
                            zone_od_counts[z_key] = {"origins": 0, "destinations": 0, "total": 0}
                        zone_od_counts[z_key]["origins"] += int(o_count)
                        zone_od_counts[z_key]["total"] += int(o_count)

            if "destination" in filtered_df.columns:
                unique_dests = filtered_df["destination"].dropna().unique()
                dest_map = {str(d): suggest_corrected_od_and_zone(str(d)) for d in unique_dests}
                for dest_val, d_count in filtered_df["destination"].value_counts().items():
                    c_od, z_no, _ = dest_map.get(str(dest_val), ("Nill", "-", ""))
                    if c_od.lower() != "nill" and z_no and z_no != "-" and z_no != "Outside":
                        z_key = str(z_no)
                        if z_key not in zone_od_counts:
                            zone_od_counts[z_key] = {"origins": 0, "destinations": 0, "total": 0}
                        zone_od_counts[z_key]["destinations"] += int(d_count)
                        zone_od_counts[z_key]["total"] += int(d_count)

            # Calculate max total for true relative sizing
            max_sample_vol = max([s["total"] for s in zone_od_counts.values()] or [1])

            # Also attach sample count to GeoJSON polygon features for seamless tooltip
            for feat in geojson_data.get("features", []):
                z_id = str(feat.get("properties", {}).get("zone_no", feat.get("properties", {}).get("Zone_no", "")))
                tot_z = zone_od_counts.get(z_id, {}).get("total", 0)
                feat["properties"]["total_od_count"] = f"{tot_z} samples" if tot_z > 0 else "0 samples"

            # Match pointer coordinates with centroids
            centroid_map = {str(c["zone_no"]): c for c in centroids_data}
            pointer_data = []
            for z_no_str, stats in zone_od_counts.items():
                if z_no_str in centroid_map:
                    c_info = centroid_map[z_no_str]
                    tot = stats["total"]
                    w_name = str(c_info.get("ward", "")).title()
                    # Relative sqrt scaling: from 180m up to 1000m based on sample volume
                    scaled_radius = 180 + ((tot / max_sample_vol) ** 0.5) * 820
                    pointer_data.append({
                        "zone_no": z_no_str,
                        "ward_name": w_name,
                        "ward_no": str(z_no_str),
                        "dot_label": f"{w_name}\n({tot} samples)",
                        "label": f"Zone {z_no_str}: {w_name} ({tot} samples)",
                        "total_od_count": f"{tot} samples",
                        "origins_count": stats["origins"],
                        "destinations_count": stats["destinations"],
                        "coordinates": c_info["coordinates"],
                        "radius": int(scaled_radius),
                    })

            # Controls Row
            ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4, ctrl_col5 = st.columns([1.6, 1.4, 1.1, 1.1, 1.0])

            with ctrl_col1:
                all_zones_list = sorted(
                    [str(z) for z in df_zones["Zone No"].dropna().unique().tolist() if z],
                    key=lambda x: int(x) if x.isdigit() else x,
                )
                selected_zone_filter = st.multiselect(
                    "Filter Specific Zones",
                    options=all_zones_list,
                    default=[],
                    help="Select one or more zones to highlight on the map (leave empty to view all 295 zones)",
                    key="zoning_multiselect_filter",
                )

            with ctrl_col2:
                map_theme = st.selectbox(
                    "Background Map Style",
                    options=[
                        "Light (Clean)",
                        "Roads / Streets",
                        "Dark",
                    ],
                    index=0,
                    key="zoning_map_theme_select",
                )

            with ctrl_col3:
                show_labels = st.checkbox(
                    "🏷️ Zone Labels",
                    value=True,
                    help="Display Zone_no text labels on top of each shape",
                    key="zoning_show_labels_chk",
                )

            with ctrl_col4:
                show_od_pointers = st.checkbox(
                    "📍 OD Pointers",
                    value=True,
                    help="Display small pointers for zones with corrected OD trips",
                    key="zoning_show_od_pointers_chk",
                )

            with ctrl_col5:
                opacity_val = st.slider(
                    "Fill Opacity",
                    min_value=10,
                    max_value=200,
                    value=65,
                    step=5,
                    key="zoning_opacity_slider",
                )

            # Theme style mapping
            theme_map = {
                "Light (Clean)": "light",
                "Roads / Streets": "road",
                "Dark": "dark",
            }
            selected_style = theme_map.get(map_theme, "light")

            # Filter features/centroids/pointers if selected
            if selected_zone_filter:
                display_features = [
                    f for f in geojson_data["features"]
                    if str(f["properties"].get("Zone_no", "")) in selected_zone_filter
                    or str(f["properties"].get("zone_no", "")) in selected_zone_filter
                ]
                display_centroids = [
                    c for c in centroids_data
                    if str(c["zone_no"]) in selected_zone_filter
                ]
                display_pointers = [
                    p for p in pointer_data
                    if str(p["zone_no"]) in selected_zone_filter
                ]
                display_geojson = {
                    "type": "FeatureCollection",
                    "features": display_features,
                }
            else:
                display_geojson = geojson_data
                display_centroids = centroids_data
                display_pointers = pointer_data

            # Build Pydeck layers
            layers = []

            # 1. GeoJSON Zoning Polygons Layer
            zoning_layer = pdk.Layer(
                "GeoJsonLayer",
                data=display_geojson,
                stroked=True,
                filled=True,
                get_fill_color=[33, 150, 243, opacity_val],
                get_line_color=[15, 76, 129, 220],
                get_line_width=20,
                line_width_min_pixels=1,
                pickable=True,
                auto_highlight=True,
                highlight_color=[255, 179, 0, 160],
            )
            layers.append(zoning_layer)

            # 2. Text Labels Layer (Zone_no on shape)
            if show_labels and display_centroids:
                text_layer = pdk.Layer(
                    "TextLayer",
                    data=display_centroids,
                    get_position="coordinates",
                    get_text="zone_no",
                    get_size=12,
                    get_color=[10, 25, 47, 240],
                    get_angle=0,
                    get_text_anchor="'middle'",
                    get_alignment_baseline="'center'",
                    pickable=False,
                )
                layers.append(text_layer)

            # 3. OD Density Pointer Layer (clean circular dots; details shown on hover)
            if show_od_pointers and display_pointers:
                od_pointer_layer = pdk.Layer(
                    "ScatterplotLayer",
                    data=display_pointers,
                    get_position="coordinates",
                    get_radius="radius",
                    get_fill_color=[233, 30, 99, 200],
                    get_line_color=[255, 255, 255, 255],
                    get_line_width=2,
                    pickable=True,
                    auto_highlight=True,
                    highlight_color=[255, 235, 59, 255],
                )
                layers.append(od_pointer_layer)

            # 4. Survey Station Green Pins Layer (OD-1, OD-2... based on last sample per day >= 100 samples)
            survey_site_pins = []
            if COL_LOCATION in df.columns and df[COL_LOCATION].notna().any():
                # Check for date column
                date_col_name = COL_DATE if COL_DATE in df.columns else "date"
                if date_col_name in df.columns:
                    unique_dates = sorted([d for d in df[date_col_name].dropna().unique() if str(d).strip()])
                    station_idx = 1
                    for d_val in unique_dates:
                        day_records = df[df[date_col_name] == d_val]
                        day_count = len(day_records)
                        # Skip days with very few samples (< 100)
                        if day_count < 100:
                            continue

                        # Extract lat/long from the last sample of that day
                        loc_series = day_records[COL_LOCATION].dropna().astype(str).tolist()
                        day_last_loc = None
                        for l_str in reversed(loc_series):
                            if "," in l_str and l_str.lower() not in INVALID_TEXT:
                                try:
                                    s_lat, s_lon = map(float, l_str.split(","))
                                    day_last_loc = (s_lat, s_lon)
                                    break
                                except Exception:
                                    pass

                        if day_last_loc:
                            s_lat, s_lon = day_last_loc
                            z_found, w_found = find_delhi_zone_by_lat_lng(s_lon, s_lat)
                            
                            station_code_str = f"OD-{station_idx}"
                            survey_site_pins.append({
                                "lat": s_lat,
                                "lon": s_lon,
                                "coordinates": [s_lon, s_lat],
                                "name": station_code_str,
                                "station_code": station_code_str,
                                "ward_name": w_found if w_found and w_found != "Outside Delhi" else "-",
                                "zone_no": z_found,
                                "survey_date": str(d_val),
                                "day_samples": f"{day_count:,} samples",
                                "total_od_count": f"{day_count:,} samples",
                            })
                            station_idx += 1

                # Fallback if single location
                if not survey_site_pins:
                    loc_list = df[COL_LOCATION].dropna().astype(str).tolist()
                    for l_str in reversed(loc_list):
                        if "," in l_str and l_str.lower() not in INVALID_TEXT:
                            try:
                                s_lat, s_lon = map(float, l_str.split(","))
                                z_found, w_found = find_delhi_zone_by_lat_lng(s_lon, s_lat)
                                survey_site_pins.append({
                                    "lat": s_lat,
                                    "lon": s_lon,
                                    "coordinates": [s_lon, s_lat],
                                    "name": "OD-1",
                                    "station_code": "OD-1",
                                    "ward_name": w_found if w_found and w_found != "Outside Delhi" else "-",
                                    "zone_no": z_found,
                                    "survey_date": "Active Survey Day",
                                    "day_samples": f"{len(df):,} samples",
                                    "total_od_count": f"{len(df):,} samples",
                                })
                                break
                            except Exception:
                                pass

            if survey_site_pins:
                # Green Circle Marker
                survey_pin_layer = pdk.Layer(
                    "ScatterplotLayer",
                    data=survey_site_pins,
                    get_position=["lon", "lat"],
                    get_radius=360,
                    get_fill_color=[46, 125, 50, 240],
                    get_line_color=[255, 255, 255, 255],
                    get_line_width=3,
                    pickable=True,
                    auto_highlight=True,
                    highlight_color=[0, 230, 118, 255],
                )
                layers.append(survey_pin_layer)

                # Station Label (only OD-1, OD-2, etc.)
                survey_pin_text_layer = pdk.Layer(
                    "TextLayer",
                    data=survey_site_pins,
                    get_position=["lon", "lat"],
                    get_text="station_code",
                    get_size=14,
                    get_color=[27, 94, 32, 255],
                    get_angle=0,
                    get_text_anchor="'middle'",
                    get_alignment_baseline="'bottom'",
                    get_pixel_offset=[0, -14],
                    pickable=False,
                )
                layers.append(survey_pin_text_layer)

            # Pydeck ViewState centered on Delhi (or active station)
            init_lat = survey_site_pins[0]["lat"] if survey_site_pins else 28.6139
            init_lon = survey_site_pins[0]["lon"] if survey_site_pins else 77.2090

            view_state = pdk.ViewState(
                latitude=init_lat,
                longitude=init_lon,
                zoom=10.5,
                pitch=0,
            )

            tooltip = {
                "html": """
                    <div style="font-family: sans-serif; padding: 6px 10px; font-size: 13px; line-height: 1.4;">
                        <b style="color: #2E7D32; font-size: 15px;">📍 {name}</b><br/>
                        <b>Zone:</b> {zone_no}<br/>
                        <hr style="margin: 4px 0; border: 0; border-top: 1px solid #ddd;"/>
                        <b>Total Samples:</b> <span style="color: #D81B60; font-weight: bold;">{total_od_count}</span>
                    </div>
                """,
                "style": {
                    "backgroundColor": "rgba(255, 255, 255, 0.96)",
                    "color": "#222",
                    "borderRadius": "6px",
                    "boxShadow": "0 2px 8px rgba(0,0,0,0.25)",
                    "border": "1px solid #B0BEC5",
                },
            }

            deck = pdk.Deck(
                layers=layers,
                initial_view_state=view_state,
                map_style=selected_style,
                tooltip=tooltip,
            )

            st.pydeck_chart(deck, use_container_width=True)

            st.caption(
                "ℹ️ **Delhi Zoning Map**: Blue polygons show Delhi administrative zones. "
                "🟢 **Green Pins** mark daily survey stations (**OD-1**, **OD-2**, etc.) from the last sample coordinate of each day ($>100$ samples). "
                "🔴 **Pink-Red Pointers** show zone trip density (hover over any dot or shape to view sample details)."
            )

            # Expandable zone reference table
            with st.expander("📋 View Delhi Zones Reference Table (295 Zones)"):
                st.dataframe(df_zones, use_container_width=True, hide_index=True)
                st.download_button(
                    "⬇️ Download Delhi Zones List (CSV)",
                    data=df_zones.to_csv(index=False).encode("utf-8"),
                    file_name="delhi_zoning_list.csv",
                    mime="text/csv",
                )

    # ── SUBTAB O2: OD Correction ─────────────────────────────────────────────
    with subtab_o2:
        st.markdown("### 🛠️ Origin–Destination Spelling Correction & Zone Assignment")
        st.caption(
            "Compiles all unique locations entered across Origins and Destinations in the survey, "
            "standardizes abbreviations and spelling (e.g. `cp` ➔ `Connaught Place`, `gk` ➔ `Greater Kailash`), "
            "maps verified Delhi locations to their **Zone No**, marks NCR locations as **Outside**, "
            "and sets unverified/unmatched locations to **Nill**."
        )

        geojson_data, centroids_data, df_zones = load_delhi_zoning_data(DELHI_ZONING_KML)

        # 1. Compilation Controls
        c_scope_col, c_search_col, c_min_count_col = st.columns([1.5, 2, 1.2])

        with c_scope_col:
            od_scope = st.radio(
                "Scope of Locations",
                options=["All Locations (Origin + Destination)", "Origins Only", "Destinations Only"],
                index=0,
                horizontal=True,
                key="od_correction_scope",
            )

        with c_search_col:
            od_search_query = st.text_input(
                "🔍 Search Location / Zone",
                placeholder="Type location name (e.g. Lajpat, CP, GK, Noida)...",
                key="od_correction_search",
            )

        with c_min_count_col:
            min_count = st.number_input(
                "Min Occurrence Count",
                min_value=1,
                max_value=1000,
                value=1,
                step=1,
                key="od_correction_min_count",
            )

        # 2. Extract series according to scope
        loc_series_list = []
        if od_scope in ["All Locations (Origin + Destination)", "Origins Only"]:
            if "origin" in filtered_df.columns:
                loc_series_list.append(filtered_df["origin"].dropna().astype(str))
        if od_scope in ["All Locations (Origin + Destination)", "Destinations Only"]:
            if "destination" in filtered_df.columns:
                loc_series_list.append(filtered_df["destination"].dropna().astype(str))

        if not loc_series_list:
            st.info("No OD location data available.")
        else:
            combined_locs = pd.concat(loc_series_list, ignore_index=True)
            # Filter out invalid text
            valid_locs = combined_locs[
                combined_locs.str.strip().str.lower().apply(lambda x: x not in INVALID_TEXT and len(x) > 1)
            ]

            if valid_locs.empty:
                st.info("No valid OD locations found.")
            else:
                # Value counts table
                od_counts = valid_locs.value_counts().reset_index()
                od_counts.columns = ["OD", "Count"]

                if min_count > 1:
                    od_counts = od_counts[od_counts["Count"] >= min_count]

                # Filter by search
                if od_search_query.strip():
                    q_lower = od_search_query.strip().lower()
                    od_counts = od_counts[od_counts["OD"].str.lower().str.contains(q_lower, na=False)]

                # Session state for manual / AI geocoded overrides
                if "od_custom_mappings" not in st.session_state:
                    st.session_state["od_custom_mappings"] = {}

                # AI & Geocoding Resolver Panel
                with st.expander("🌐 External Spatial Geocoding & AI LLM Semantic Resolution", expanded=False):
                    tab_geo, tab_llm = st.tabs(["🌐 Spatial Polygon Geocoding (Google/LocationIQ/OSM)", "🧠 AI LLM Semantic Resolver (Gemini/Ollama/OpenAI)"])
                    
                    with tab_geo:
                        g_col1, g_col2, g_col3 = st.columns([1.5, 1.8, 1.8])
                        with g_col1:
                            geo_provider = st.selectbox(
                                "Geocoding Provider",
                                options=[
                                    "Google Maps",
                                    "LocationIQ (5,000 free/day)",
                                    "Geoapify (3,000 free/day)",
                                    "OpenStreetMap (Free, No Key)",
                                ],
                                index=0,
                                key="od_geocoding_provider_select",
                            )
                        with g_col2:
                            custom_geo_key = st.text_input(
                                f"{geo_provider.split(' ')[0]} API Key",
                                type="password",
                                placeholder="Enter your API key...",
                                help="Enter your Google Maps / LocationIQ / Geoapify API key.",
                                key="od_custom_geo_api_key_input",
                            )
                        with g_col3:
                            st.write("")
                            st.write("")
                            btn_c1, btn_c2 = st.columns(2)
                            with btn_c1:
                                run_geocoding = st.button(
                                    "🌐 Run Spatial Search",
                                    key="btn_run_geocoding_spatial",
                                    help="Queries coordinates for unmapped locations and finds their exact Delhi Zone number from the zoning polygons.",
                                )
                            with btn_c2:
                                reset_mappings = st.button(
                                    "🔄 Reset AI Matches",
                                    key="btn_reset_od_mappings",
                                    help="Clears cached session overrides and applies the expanded 600+ Delhi master AI gazetteer.",
                                )

                    with tab_llm:
                        st.caption("🧠 **AI LLM Semantic Correction**: Uses powerful language models (Gemini / Ollama / OpenAI) to understand real semantic intent (e.g. *'Great Kailash'* ➔ *'Greater Kailash'*, *'Devoli Village'* ➔ *'Deoli'*).")
                        l_col1, l_col2, l_col3, l_col4 = st.columns([1.5, 1.2, 1.8, 1.3])
                        with l_col1:
                            llm_provider = st.selectbox(
                                "LLM Provider",
                                options=["Google Gemini", "Ollama (Local / Offline)", "OpenAI"],
                                index=0,
                                key="od_llm_provider_select",
                            )
                        with l_col2:
                            if llm_provider == "Google Gemini":
                                model_options = [
                                    "gemini-3.7-flash",
                                    "gemini-3.5-flash-lite",
                                    "gemini-2.5-flash",
                                    "gemini-2.0-flash",
                                    "gemini-1.5-flash",
                                    "gemini-3.1-pro",
                                    "gemini-1.5-pro",
                                ]
                            elif llm_provider == "Ollama (Local / Offline)":
                                model_options = ["llama3.2", "mistral", "qwen2.5", "phi3"]
                            else:
                                model_options = ["gpt-4o-mini", "gpt-4o"]
                            llm_model = st.selectbox("Model Name", options=model_options, index=0, key="od_llm_model_name")
                        with l_col3:
                            if "Ollama" in llm_provider:
                                llm_key_or_url = st.text_input("Ollama Base URL", value="http://localhost:11434", key="od_llm_ollama_url")
                            else:
                                llm_key_or_url = st.text_input(f"{llm_provider.split(' ')[0]} API Key", type="password", placeholder="Paste Gemini / OpenAI API key...", key="od_llm_api_key")
                        with l_col4:
                            st.write("")
                            st.write("")
                            run_llm_resolver = st.button("🤖 Run AI LLM Batch", key="btn_run_llm_semantic_batch", help="Sends unmapped locations in semantic batches to the LLM for context-aware Delhi zone assignment.")

                if "reset_mappings" in locals() and reset_mappings:
                    st.session_state["od_custom_mappings"] = {}
                    st.success("✅ Applied expanded Master AI Gazetteer! Locations re-matched.")
                    st.rerun()

                # If LLM batch button clicked, process unmapped items with LLM
                if "run_llm_resolver" in locals() and run_llm_resolver:
                    st.session_state["llm_api_last_error"] = None
                    unmapped_llm_items = []
                    for raw_od in od_counts["OD"]:
                        if raw_od not in st.session_state["od_custom_mappings"]:
                            c_od, z_no, _ = suggest_corrected_od_and_zone(raw_od)
                            if c_od == "Nill" or z_no == "-":
                                unmapped_llm_items.append(raw_od)

                    if not unmapped_llm_items:
                        st.info("🎉 All displayed locations are already resolved!")
                    elif "Gemini" in llm_provider and (not llm_key_or_url or len(llm_key_or_url.strip()) < 10):
                        st.warning("⚠️ Please enter your Google Gemini API key above to run AI Semantic Resolution.")
                    elif "OpenAI" in llm_provider and (not llm_key_or_url or len(llm_key_or_url.strip()) < 10):
                        st.warning("⚠️ Please enter your OpenAI API key above to run AI Semantic Resolution.")
                    else:
                        batch_size = 20
                        total_batches = (len(unmapped_llm_items) + batch_size - 1) // batch_size
                        p_bar = st.progress(0, text=f"Starting AI LLM Semantic Resolution for {len(unmapped_llm_items)} locations across {total_batches} batches...")
                        status_box = st.empty()
                        
                        resolved_llm_count = 0
                        for b_idx in range(total_batches):
                            chunk = unmapped_llm_items[b_idx * batch_size : (b_idx + 1) * batch_size]
                            p_bar.progress((b_idx + 1) / total_batches, text=f"🧠 [Batch {b_idx+1}/{total_batches}] Asking {llm_provider} ({llm_model}) to resolve {len(chunk)} locations...")
                            
                            batch_results = resolve_od_batch_with_llm(
                                raw_locations=chunk,
                                provider=llm_provider,
                                api_key=llm_key_or_url if "Ollama" not in llm_provider else "",
                                endpoint_url=llm_key_or_url if "Ollama" in llm_provider else "http://localhost:11434",
                                model_name=llm_model,
                            )
                            
                            for raw_k, (corr_val, z_val, stat_val) in batch_results.items():
                                if corr_val != "Nill" and z_val != "-":
                                    st.session_state["od_custom_mappings"][raw_k] = (corr_val, z_val, stat_val)
                                    resolved_llm_count += 1
                                    
                            status_box.markdown(f"📊 **AI LLM Progress**: Processed `{min((b_idx+1)*batch_size, len(unmapped_llm_items))} / {len(unmapped_llm_items)}` | ✅ **Resolved**: `{resolved_llm_count}`")
                        
                        p_bar.empty()
                        status_box.empty()
                        if resolved_llm_count > 0:
                            st.success(f"🎉 **AI LLM Semantic Resolution Complete!** Successfully mapped **{resolved_llm_count}** noisy survey locations to official Delhi Zones.")
                            st.rerun()
                        else:
                            err_msg = st.session_state.get("llm_api_last_error", "No response returned from model.")
                            st.error(f"⚠️ **AI Resolution Failed**: {err_msg}. Please check your API Key and Model Selection.")

                # Compute auto-corrections and zone numbers instantaneously
                corrected_list = []
                zone_list = []
                match_status_list = []

                # If geocoding button clicked, process unmapped items with rich live progress feedback
                if "run_geocoding" in locals() and run_geocoding:
                    unmapped_items = []
                    for raw_od in od_counts["OD"]:
                        if raw_od not in st.session_state["od_custom_mappings"]:
                            c_od, z_no, _ = suggest_corrected_od_and_zone(raw_od)
                            if c_od == "Nill" or z_no == "-":
                                unmapped_items.append(raw_od)

                    if not unmapped_items:
                        st.info("🎉 All displayed locations are already resolved and assigned!")
                    elif "Google" in geo_provider and (not custom_geo_key or len(custom_geo_key.strip()) < 10):
                        st.warning("⚠️ Please enter your Google Maps API key above to run Google Maps spatial search.")
                    elif "LocationIQ" in geo_provider and (not custom_geo_key or len(custom_geo_key.strip()) < 10):
                        st.warning("⚠️ Please enter your LocationIQ API key above to run LocationIQ spatial search (or select OpenStreetMap for free keyless search).")
                    elif "Geoapify" in geo_provider and (not custom_geo_key or len(custom_geo_key.strip()) < 10):
                        st.warning("⚠️ Please enter your Geoapify API key above to run Geoapify spatial search (or select OpenStreetMap for free keyless search).")
                    else:
                        import time
                        progress_container = st.container()
                        with progress_container:
                            p_bar = st.progress(0, text=f"Starting spatial polygon geocoding for {len(unmapped_items)} locations...")
                            status_box = st.empty()
                            
                            new_delhi_count = 0
                            new_outside_count = 0
                            unresolved_count = 0
                            
                            for idx, raw_loc in enumerate(unmapped_items):
                                current_step = idx + 1
                                fraction = current_step / len(unmapped_items)
                                p_bar.progress(fraction, text=f"🔍 [{current_step}/{len(unmapped_items)}] Resolving: **{raw_loc}** via {geo_provider.split(' ')[0]}...")
                                
                                geo_od, geo_z, geo_m = geocode_location_spatial(raw_loc, geo_provider, custom_geo_key)
                                if geo_od != "Nill" and geo_z != "-":
                                    st.session_state["od_custom_mappings"][raw_loc] = (geo_od, geo_z, geo_m)
                                    if geo_z == "Outside":
                                        new_outside_count += 1
                                    else:
                                        new_delhi_count += 1
                                else:
                                    unresolved_count += 1
                                
                                status_box.markdown(
                                    f"📊 **Progress**: **{current_step} / {len(unmapped_items)}** checked | "
                                    f"✅ **Resolved**: `{new_delhi_count + new_outside_count}` *(📍 Delhi: {new_delhi_count} | 🏢 Outside NCR: {new_outside_count})* | "
                                    f"⚠️ **Nill**: `{unresolved_count}`"
                                )
                                time.sleep(0.04)
                            
                            p_bar.empty()
                            status_box.empty()
                            st.success(
                                f"🎉 **Geocoding Complete!** Resolved **{new_delhi_count + new_outside_count}** new locations "
                                f"(📍 **{new_delhi_count}** mapped to Delhi Zones, 🏢 **{new_outside_count}** Outside Delhi, ⚠️ **{unresolved_count}** remained Nill)."
                            )

                for raw_od in od_counts["OD"]:
                    if raw_od in st.session_state["od_custom_mappings"]:
                        corr_od, z_no, m_type = st.session_state["od_custom_mappings"][raw_od]
                    else:
                        corr_od, z_no, m_type = suggest_corrected_od_and_zone(raw_od)
                    corrected_list.append(corr_od)
                    zone_list.append(z_no)
                    match_status_list.append(m_type)

                od_table = pd.DataFrame({
                    "Sr. No.": range(1, len(od_counts) + 1),
                    "OD": od_counts["OD"].tolist(),
                    "Count": od_counts["Count"].tolist(),
                    "Corrected OD": corrected_list,
                    "Zone No": zone_list,
                    "Match Status": match_status_list,
                })

                # Summary Metric Cards
                total_unique_ods = len(od_table)
                total_volume = od_table["Count"].sum()
                delhi_mapped_count = ((od_table["Zone No"] != "-") & (od_table["Zone No"] != "Outside")).sum()
                outside_count = (od_table["Zone No"] == "Outside").sum()
                nill_count = (od_table["Corrected OD"] == "Nill").sum()

                m_col1, m_col2, m_col3, m_col4 = st.columns(4)
                m_col1.metric("Unique OD Locations", total_unique_ods)
                m_col2.metric("Delhi Zones Mapped", delhi_mapped_count)
                m_col3.metric("Outside Delhi Locations", outside_count)
                m_col4.metric("Unmatched (Nill)", nill_count)

                st.markdown("---")
                st.markdown("#### 📝 Editable OD Mapping Table")
                st.caption("You can directly click and edit **Corrected OD** or **Zone No** cells in the table below to adjust any mapping:")

                # Interactive editable table
                edited_od_table = st.data_editor(
                    od_table,
                    use_container_width=True,
                    disabled=["Sr. No.", "OD", "Count", "Match Status"],
                    hide_index=True,
                    num_rows="fixed",
                    key="od_correction_data_editor",
                )

                # Download Buttons
                d_col1, d_col2 = st.columns(2)
                with d_col1:
                    st.download_button(
                        "⬇️ Download OD Correction Mapping (CSV)",
                        data=edited_od_table.to_csv(index=False).encode("utf-8"),
                        file_name="od_correction_zone_mapping.csv",
                        mime="text/csv",
                    )

                with d_col2:
                    # Create enriched survey data with corrected OD columns
                    mapping_dict_od = dict(zip(edited_od_table["OD"], edited_od_table["Corrected OD"]))
                    mapping_dict_zone = dict(zip(edited_od_table["OD"], edited_od_table["Zone No"]))

                    enriched_df = filtered_df.copy()
                    if "origin" in enriched_df.columns:
                        enriched_df["Corrected_Origin"] = enriched_df["origin"].map(mapping_dict_od).fillna("Nill")
                        enriched_df["Origin_Zone"] = enriched_df["origin"].map(mapping_dict_zone).fillna("-")
                    if "destination" in enriched_df.columns:
                        enriched_df["Corrected_Destination"] = enriched_df["destination"].map(mapping_dict_od).fillna("Nill")
                        enriched_df["Destination_Zone"] = enriched_df["destination"].map(mapping_dict_zone).fillna("-")

                    st.download_button(
                        "⬇️ Download Full Enriched Survey Data with Zones (CSV)",
                        data=enriched_df.to_csv(index=False).encode("utf-8"),
                        file_name="delhi_survey_data_with_corrected_zones.csv",
                        mime="text/csv",
                    )

    # ── SUBTAB O3: Origin-Destination Analysis ───────────────────────────────
    with subtab_o3:
        st.markdown("### 📊 Origin–Destination Pairs & Flows")
        od_valid = filtered_df.dropna(subset=["origin", "destination"]).copy()

        st.markdown(
            f"**{len(od_valid):,}** records have valid Origin and Destination "
            f"out of **{len(filtered_df):,}** filtered records."
        )

        if od_valid.empty:
            st.info("No valid OD records.")
        else:
            od_pairs = (
                od_valid.groupby(["origin", "destination"])
                .size()
                .reset_index(name="Trip Count")
                .sort_values("Trip Count", ascending=False)
            )

            od_pairs["OD Pair"] = od_pairs["origin"] + " → " + od_pairs["destination"]

            col1, col2 = st.columns([2, 3])

            with col1:
                st.markdown("### Top OD Pairs")
                st.dataframe(
                    od_pairs[["OD Pair", "Trip Count"]].head(25),
                    use_container_width=True,
                )

            with col2:
                top_od = od_pairs.head(15).sort_values("Trip Count", ascending=True)

                fig = px.bar(
                    top_od,
                    x="Trip Count",
                    y="OD Pair",
                    orientation="h",
                    title="Top 15 OD Pairs",
                    color_discrete_sequence=[PRIMARY_COLOR],
                )
                st.plotly_chart(fig, use_container_width=True)

            col3, col4 = st.columns(2)

            with col3:
                top_origins = filtered_df["origin"].value_counts().head(15).reset_index()
                top_origins.columns = ["Origin", "Count"]

                fig = px.bar(
                    top_origins.sort_values("Count", ascending=True),
                    x="Count",
                    y="Origin",
                    orientation="h",
                    title="Top Origins",
                    color_discrete_sequence=[PRIMARY_COLOR],
                )
                st.plotly_chart(fig, use_container_width=True)

            with col4:
                top_destinations = (
                    filtered_df["destination"].value_counts().head(15).reset_index()
                )
                top_destinations.columns = ["Destination", "Count"]

                fig = px.bar(
                    top_destinations.sort_values("Count", ascending=True),
                    x="Count",
                    y="Destination",
                    orientation="h",
                    title="Top Destinations",
                    color_discrete_sequence=[SECONDARY],
                )
                st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        st.subheader("Missing OD Entries")

        bad_od = filtered_df[filtered_df["bad_od_entry"] == True].copy()

        if bad_od.empty:
            st.success("No missing OD entries.")
        else:
            st.warning(f"{len(bad_od):,} records have missing Origin or Destination.")
            st.dataframe(prepare_display(bad_od), use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    "Dashboard built for Delhi OD Passenger / Goods Survey — "
)