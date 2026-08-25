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
import os
import re
from datetime import datetime, time, timezone, timedelta
from typing import Any

IST = timezone(timedelta(hours=5, minutes=30))

import pandas as pd
import plotly.express as px
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

    df["vehicle_type"] = df.apply(derive_vehicle, axis=1)
    df["origin"] = df.apply(derive_origin, axis=1)
    df["destination"] = df.apply(derive_destination, axis=1)
    df["likely_shift"] = df.apply(derive_shift, axis=1)
    df["trip_frequency"] = df.apply(derive_frequency, axis=1)
    df["trip_purpose_or_commodity"] = df.apply(derive_purpose_or_commodity, axis=1)
    df["passenger_occupancy"] = df.apply(derive_passenger_occupancy, axis=1)
    df["bus_sitting_pct"] = df.apply(derive_bus_sitting_pct, axis=1)

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
        "Origin",
        "Destination",
        "Duration (mins)",
        "Sample Quality Flags",
    ]

    ordered = [c for c in ordered if c in out.columns]

    return out[ordered]


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
    sample_loc = df[COL_LOCATION].dropna().astype(str).iloc[0]

    try:
        lat, lon = map(float, sample_loc.split(","))
        with st.expander("Show Survey Site Map"):
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
        "⏱️ Short Entry Duration",
        "🚗 Vehicles",
        "🗺️ OD Analysis",
        "🚩 Suspicious OD",
        "🔁 Shift / Frequency / Purpose",
        "📄 Raw Data",
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
    st.subheader("👷 Surveyor Performance")

    surveyor_base = filtered_df[filtered_df["surveyor"].notna()].copy()

    if surveyor_base.empty:
        st.info("No surveyor data available.")
    else:
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


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — SHORT ENTRY DURATION
# ─────────────────────────────────────────────────────────────────────────────
with tabs[2]:
    st.subheader("⏱️ Short Entry Duration Check")

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
# TAB 4 — VEHICLES
# ─────────────────────────────────────────────────────────────────────────────
with tabs[3]:
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
# TAB 5 — OD ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────
with tabs[4]:
    st.subheader("🗺️ Origin–Destination Analysis")

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
# TAB 6 — SUSPICIOUS OD
# ─────────────────────────────────────────────────────────────────────────────
with tabs[5]:
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
# TAB 7 — SHIFT / FREQUENCY / PURPOSE
# ─────────────────────────────────────────────────────────────────────────────
with tabs[6]:
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
# TAB 8 — RAW DATA
# ─────────────────────────────────────────────────────────────────────────────
with tabs[7]:
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
# FOOTER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    "Dashboard built for Delhi OD Passenger / Goods Survey — "
    "Entry-duration fraud check uses end_time minus start_time."
)