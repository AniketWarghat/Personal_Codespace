"""
app.py  —  Mumbai Traffic Survey Dashboard (Single-File Combined App)
=======================================================================
Pages
  1. Traffic Survey   – original JJ Junction / Dahisar Toll dashboard
  2. Commuter Survey   – Dharavi Metro commuter intercept survey

Run:
    streamlit run app.py
"""

from __future__ import annotations

# ── Authentication (must be first) ────────────────────────────────────────────
import streamlit as st


def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["APP_PASSWORD"]:
            st.session_state["authenticated"] = True
        else:
            st.session_state["authenticated"] = False

    if "authenticated" not in st.session_state:
        st.text_input("Enter password", type="password",
                       on_change=password_entered, key="password")
        st.stop()
    elif not st.session_state["authenticated"]:
        st.text_input("Enter password", type="password",
                       on_change=password_entered, key="password")
        st.error("Incorrect password")
        st.stop()


check_password()

# ── Imports ───────────────────────────────────────────────────────────────────
import io
import os
import re
from datetime import datetime, time

import pandas as pd
import plotly.express as px
from rapidfuzz import fuzz, process as rfprocess

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Mumbai Traffic Survey Dashboard",
    layout="wide",
    page_icon="🚦",
)

PRIMARY_COLOR = "#0057A8"
SHEET_NAME = "Survey Results"

# Colour palette shared by the Commuter Survey section
SECONDARY = "#00A3E0"
SUCCESS = "#28A745"
WARNING = "#FFC107"
DANGER = "#DC3545"
GREY = "#6C757D"

# ── Sidebar page selector ─────────────────────────────────────────────────────
st.sidebar.title("🚦 Mumbai Survey Dashboard")
st.sidebar.markdown("---")

PAGES = {
    "🚦 Traffic Survey (JJ / Dahisar)": "traffic",
    "🚇 Commuter Survey (Dharavi Metro)": "commuter",
}

selected_page = st.sidebar.radio("Navigate to", list(PAGES.keys()), key="nav_page")
page_key = PAGES[selected_page]

st.sidebar.markdown("---")


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION: COMMUTER SURVEY  — constants & helpers
#  (formerly commuter_survey_page.py, inlined; names prefixed/renamed to avoid
#   collisions with the Traffic Survey section below)
# ══════════════════════════════════════════════════════════════════════════════

# ── Canonical surveyor name map (commuter survey) ─────────────────────────────
COMMUTER_SURVEYOR_NORM: dict[str, str] = {
    # Abdul
    "Abdul": "Abdul",
    "abdul": "Abdul",
    # Shahjahan Shaikh
    "shahjahan shaikh": "Shahjahan Shaikh",
    "shahjahan shaikh ": "Shahjahan Shaikh",
    # Karan
    "karan": "Karan",
    "karan ": "Karan",
    # Amit Mishra
    "amit mishra": "Amit Mishra",
    "amit ": "Amit Mishra",
    "amit": "Amit Mishra",
    # Ramgopal Chaurasiya
    "ramgopal chaurasiya": "Ramgopal Chaurasiya",
    "ramgopal chaurasiya ": "Ramgopal Chaurasiya",
    "Ramgopal chaurasiya ": "Ramgopal Chaurasiya",
    # Rushikesh
    "rushikesh": "Rushikesh",
    "rushikesh ": "Rushikesh",
    # Manas
    "manas": "Manas",
    "manas ": "Manas",
    "Manas ": "Manas",
    # Shariq
    "shariq": "Shariq",
    # Uttkarsh Yadav
    "uttkarsh yadav": "Uttkarsh Yadav",
    "uttkarsh yadav ": "Uttkarsh Yadav",
    "Uttkarsh Yadav ": "Uttkarsh Yadav",
    "uttkarsh ": "Uttkarsh Yadav",
    "uttkarsh": "Uttkarsh Yadav",
    "Uttkarsh": "Uttkarsh Yadav",
    "Uttkarsh ": "Uttkarsh Yadav",
    # Anash Khan
    "anash khan": "Anash Khan",
    "anash ": "Anash Khan",
    "anash": "Anash Khan",
    "Anash": "Anash Khan",
    "Anash ": "Anash Khan",
    "Anash Khan": "Anash Khan",
    # Nirvan Mamidi
    "nirvan ravi mamidi": "Nirvan Mamidi",
    "Nirvan Ravi Mamidi ": "Nirvan Mamidi",
    "Nirvan Ravi Mamidi": "Nirvan Mamidi",
    "nirvan mamidi": "Nirvan Mamidi",
    "Nirvan Mamidi": "Nirvan Mamidi",
    "Nirvan ": "Nirvan Mamidi",
    "nirvan ": "Nirvan Mamidi",
    "Nirvan": "Nirvan Mamidi",
}

# ── Location clean-up helpers (commuter survey) ───────────────────────────────
COMMUTER_LOCATION_NORM: dict[str, str | None] = {
    "dharavi": "Dharavi",
    "dharavi ": "Dharavi",
    "Dharavi ": "Dharavi",
    "dhravi ": "Dharavi",
    "dhravi": "Dharavi",
    "dharvi ": "Dharavi",
    "bkc": "BKC",
    "Bkc": "BKC",
    "midc": "MIDC",
    "t2": "Airport T2",
    "T2": "Airport T2",
    "t1 airport": "Airport T1",
    "t1 airport ": "Airport T1",
    "andheri ": "Andheri",
    "andheri": "Andheri",
    "mahim": "Mahim",
    "dadar": "Dadar",
    "Dadar": "Dadar",
    "koliwada ": "Koliwada",
    "koliwada": "Koliwada",
    "wadala ": "Wadala",
    "shitladevi": "Shitladevi",
    "mahalakshmi": "Mahalaxmi",
    "mahalaxmi": "Mahalaxmi",
    "need ": None,   # junk entry
    "-": None,
}

COMMUTER_INVALID_SET = {"-", "nan", "none", "", "nil", "na"}


def _commuter_clean_loc(val: str | None) -> str | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    if s.lower() in COMMUTER_INVALID_SET:
        return None
    return COMMUTER_LOCATION_NORM.get(s, s.title())


def _commuter_clean_str(val) -> str | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    return None if s.lower() in COMMUTER_INVALID_SET else s


# ── Journey time parsing (1b7.Total Journey Time (Min)) ──────────────────────
# Field-collected values aren't uniformly numeric. Observed shapes in the
# DC513MH05 Dharavi survey export:
#   '10', '20'                  -> bare integer minutes
#   '2min', '20min'             -> integer + 'min'/'mins', no space
#   '20 min', '20 minutes'      -> integer + space + 'min'/'mins'/'minute(s)'
#   '1hr'                       -> hour unit, must be converted (x60), not
#                                   just digit-extracted (would read as 1 min)
#   '35-40', '40-45 mins'       -> dash range, no single correct value;
#                                   left unparsed (NaN) and flagged rather
#                                   than guessed at (e.g. via midpoint)
_JOURNEY_RANGE_RE = re.compile(r"^\s*\d+(\.\d+)?\s*-\s*\d+(\.\d+)?\s*(min|mins|minute|minutes)?\s*$",
                                re.IGNORECASE)
_JOURNEY_HOUR_RE = re.compile(r"^\s*(\d+(\.\d+)?)\s*(hr|hrs|hour|hours)\s*$", re.IGNORECASE)
_JOURNEY_MIN_RE = re.compile(r"^\s*(\d+(\.\d+)?)\s*(min|mins|minute|minutes)?\s*$", re.IGNORECASE)


def parse_journey_time_minutes(val) -> tuple[float | None, str | None]:
    """Parse a raw journey-time string into minutes (float) plus an issue
    label (None if cleanly parsed). Returns (minutes, issue)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None, None
    raw = str(val).strip()
    if not raw or raw.lower() in COMMUTER_INVALID_SET:
        return None, None

    if _JOURNEY_RANGE_RE.match(raw):
        return None, f"Range, not parsed: '{raw}'"

    m = _JOURNEY_HOUR_RE.match(raw)
    if m:
        return float(m.group(1)) * 60.0, None

    m = _JOURNEY_MIN_RE.match(raw)
    if m:
        return float(m.group(1)), None

    return None, f"Unrecognized format: '{raw}'"


def _commuter_parse_time(series: pd.Series) -> pd.Series:
    return pd.to_datetime(
        series.astype(str), format="%H:%M:%S", errors="coerce"
    ).dt.time


@st.cache_data(show_spinner=False)
def load_commuter_data(raw_bytes: bytes) -> tuple[pd.DataFrame, int, list[str]]:
    df = pd.read_excel(io.BytesIO(raw_bytes), sheet_name="Survey Results",
                        engine="openpyxl")

    # ── Location-branch filter ──────────────────────────────────────────────
    # This survey file contains two parallel question blocks selected by
    # "1.Location Name": the Dharavi Metro Station block (1b* columns, which
    # all the parsing below is built around) and a separate LTT block (1c*
    # columns). The 1c* questions aren't equivalent to the 1b* ones (e.g.
    # 1c7 "Mode of Travel" asks current mode, not "mode before metro" like
    # 1b9; 1c12 "Waiting Time" is a free-text range, not a clean number), so
    # rather than guess at a mapping, LTT rows are dropped here and the
    # caller is told how many were excluded.
    dropped_locations: list[str] = []
    if "1.Location Name" in df.columns:
        loc = df["1.Location Name"].astype(str).str.strip()
        is_dharavi = loc.eq("Dharavi Metro Station")
        dropped_locations = sorted(loc[~is_dharavi].unique().tolist())
        n_dropped = int((~is_dharavi).sum())
        df = df[is_dharavi].copy()
    else:
        n_dropped = 0

    # ── Surveyor normalisation ─────────────────────────────────────────────
    if "Remarks1" in df.columns:
        df["surveyor"] = (
            df["Remarks1"].astype(str).str.strip()
            .map(lambda x: COMMUTER_SURVEYOR_NORM.get(
                x, x.title() if x.lower() not in COMMUTER_INVALID_SET else None))
        )
    else:
        df["surveyor"] = None

    # ── Date / time ────────────────────────────────────────────────────────
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], format="%d/%m/%Y", errors="coerce")
    if "start_time" in df.columns:
        df["start_time"] = _commuter_parse_time(df["start_time"])
    if "end_time" in df.columns:
        df["end_time"] = _commuter_parse_time(df["end_time"])

    df["start_hour"] = df["start_time"].apply(
        lambda x: x.hour if x and not pd.isna(x) else None)

    # Survey duration
    def _dur(row):
        s, e = row.get("start_time"), row.get("end_time")
        if s is None or e is None:
            return None
        sd = datetime.combine(datetime.today(), s)
        ed = datetime.combine(datetime.today(), e)
        diff = (ed - sd).total_seconds() / 60
        return diff if diff >= 0 else None
    df["survey_duration_mins"] = df.apply(_dur, axis=1)

    # ── Clean commuter attribute columns ──────────────────────────────────
    def _tidy(col):
        if col not in df.columns:
            return pd.Series([None] * len(df))
        return df[col].apply(_commuter_clean_str)

    df["age"] = _tidy("1b1.Age (years)")
    df["gender"] = _tidy("1b2.Gender")
    df["occupation"] = _tidy("1b3.Occupation")
    df["income"] = _tidy("1b4.Individual Monthly Income (Rs.)")
    df["trip_freq"] = _tidy("1b10.Trip Frequency")
    df["trip_purpose"] = _tidy("1b11. Trip Purpose")
    df["prev_mode"] = df["1b9.Main mode of travel before Dharavi Line\u20113 Metro became operational ?"].apply(_commuter_clean_str) \
        if "1b9.Main mode of travel before Dharavi Line\u20113 Metro became operational ?" in df.columns else None
    df["line11_bandra"] = _tidy("1b12. Will you use Line 11 extended till Bandra Terminus ?")
    df["line8_bkc"] = _tidy("1b13. Will you use Metro Line 8 connection to Dharavi  via BKC ?")

    # Clean locations
    if "1b5.Trip Origin (Start point of the trip before using metro line)" in df.columns:
        df["origin"] = df["1b5.Trip Origin (Start point of the trip before using metro line)"].apply(_commuter_clean_loc)
    if "1b6.Trip Destination (End point of the trip after using metro line)" in df.columns:
        df["destination"] = df["1b6.Trip Destination (End point of the trip after using metro line)"].apply(_commuter_clean_loc)

    # Journey time: free-text in the source data ('10', '20min', '1hr',
    # '35-40', etc.) — see parse_journey_time_minutes() for the full pattern
    # breakdown. Dash-ranges and any unrecognized format come back as NaN
    # with a reason in journey_time_issue rather than being silently dropped.
    jt_col = "1b7.Total Journey Time (Min)"
    if jt_col in df.columns:
        jt_parsed = df[jt_col].apply(parse_journey_time_minutes)
        df["journey_time_min"] = jt_parsed.apply(lambda x: x[0])
        df["journey_time_issue"] = jt_parsed.apply(lambda x: x[1])
    else:
        df["journey_time_min"] = pd.NA
        df["journey_time_issue"] = None
    df["travel_cost_rs"] = pd.to_numeric(df.get("1b8.Total Travel Cost (Rs.)", pd.NA), errors="coerce")

    # Strip leading spaces from categoricals
    for col in ["age", "gender", "occupation", "income", "trip_freq",
                "trip_purpose", "prev_mode", "line11_bandra", "line8_bkc"]:
        if col in df.columns:
            df[col] = df[col].str.strip() if df[col].dtype == object else df[col]

    return df, n_dropped, dropped_locations


def _commuter_sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.markdown("---")
    st.sidebar.subheader("🚇 Commuter Survey Filters")

    # Date
    valid_dates = df["Date"].dropna()
    if valid_dates.empty:
        filtered = df
    else:
        mn, mx = valid_dates.min().date(), valid_dates.max().date()
        sel = st.sidebar.date_input("Survey Date Range", (mn, mx), min_value=mn, max_value=mx)
        if isinstance(sel, tuple) and len(sel) == 2:
            s_date, e_date = sel
        else:
            s_date = e_date = mn
        filtered = df[(df["Date"].dt.date >= s_date) & (df["Date"].dt.date <= e_date)]

    # Surveyor
    surveyors = sorted(filtered["surveyor"].dropna().unique().tolist())
    all_s = st.sidebar.checkbox("All Surveyors", value=True, key="cs_all_s")
    sel_s = st.sidebar.multiselect("Surveyor", surveyors,
                                    default=surveyors if all_s else [], key="cs_surv")
    if sel_s:
        filtered = filtered[filtered["surveyor"].isin(sel_s)]

    # Gender
    genders = sorted(filtered["gender"].dropna().unique().tolist())
    all_g = st.sidebar.checkbox("All Genders", value=True, key="cs_all_g")
    sel_g = st.sidebar.multiselect("Gender", genders,
                                    default=genders if all_g else [], key="cs_gen")
    if sel_g:
        filtered = filtered[filtered["gender"].isin(sel_g)]

    # Occupation
    occs = sorted(filtered["occupation"].dropna().unique().tolist())
    all_o = st.sidebar.checkbox("All Occupations", value=True, key="cs_all_o")
    sel_o = st.sidebar.multiselect("Occupation", occs,
                                    default=occs if all_o else [], key="cs_occ")
    if sel_o:
        filtered = filtered[filtered["occupation"].isin(sel_o)]

    return filtered


def _commuter_kpi(col, label: str, value, delta=None, help_text: str | None = None):
    col.metric(label, value, delta=delta, help=help_text)


def _commuter_tab_overview(df: pd.DataFrame):
    st.subheader("📊 Overview")

    total = len(df)
    male_pct = round(df["gender"].eq("Male").sum() / total * 100, 1) if total else 0
    avg_time = round(df["journey_time_min"].mean(), 1)
    avg_cost = round(df["travel_cost_rs"].mean(), 1)
    surveyors = df["surveyor"].nunique()

    c1, c2, c3, c4, c5 = st.columns(5)
    _commuter_kpi(c1, "Total Responses", total, help_text="Commuter interviews recorded")
    _commuter_kpi(c2, "Male / Female", f"{male_pct}% / {round(100 - male_pct, 1)}%")
    _commuter_kpi(c3, "Avg Journey Time", f"{avg_time} min")
    _commuter_kpi(c4, "Avg Travel Cost", f"₹{avg_cost}")
    _commuter_kpi(c5, "Surveyors Active", surveyors)

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        hr = df["start_hour"].dropna().astype(int).value_counts().sort_index()
        fig = px.bar(x=hr.index, y=hr.values,
                     labels={"x": "Hour of Day", "y": "Responses"},
                     title="Survey Responses by Hour",
                     color_discrete_sequence=[PRIMARY_COLOR])
        fig.update_layout(margin=dict(t=40, b=20), height=300)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        sc = df["surveyor"].value_counts().reset_index()
        sc.columns = ["Surveyor", "Count"]
        fig = px.bar(sc, x="Count", y="Surveyor", orientation="h",
                     title="Responses per Surveyor",
                     color_discrete_sequence=[SECONDARY])
        fig.update_layout(yaxis=dict(autorange="reversed"),
                           margin=dict(t=40, b=20), height=300)
        st.plotly_chart(fig, use_container_width=True)

    jt_clean = df["journey_time_min"].dropna()
    if not jt_clean.empty:
        fig = px.histogram(jt_clean, nbins=20,
                            labels={"value": "Journey Time (min)", "count": "Responses"},
                            title="Journey Time Distribution",
                            color_discrete_sequence=[PRIMARY_COLOR])
        fig.update_layout(showlegend=False, margin=dict(t=40, b=20), height=280)
        st.plotly_chart(fig, use_container_width=True)


def _commuter_tab_demographics(df: pd.DataFrame):
    st.subheader("👥 Traveller Demographics")

    col1, col2 = st.columns(2)

    with col1:
        gd = df["gender"].value_counts().reset_index()
        gd.columns = ["Gender", "Count"]
        fig = px.pie(gd, names="Gender", values="Count", title="Gender Split",
                     color_discrete_sequence=[PRIMARY_COLOR, SECONDARY, GREY])
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(margin=dict(t=40), height=320)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        AGE_ORDER = ["<18", "18-25", "25-44", "45-59", ">60"]
        age_col = df["age"].dropna()
        age_col = age_col.str.strip()
        age_counts = age_col.value_counts().reindex(AGE_ORDER, fill_value=0)
        fig = px.bar(x=age_counts.index, y=age_counts.values,
                     labels={"x": "Age Group", "y": "Count"},
                     title="Age Distribution",
                     color_discrete_sequence=[SECONDARY])
        fig.update_layout(margin=dict(t=40), height=320)
        st.plotly_chart(fig, use_container_width=True)

    col3, col4 = st.columns(2)

    with col3:
        occ = df["occupation"].value_counts().reset_index()
        occ.columns = ["Occupation", "Count"]
        fig = px.bar(occ, x="Count", y="Occupation", orientation="h",
                     title="Occupation Breakdown",
                     color_discrete_sequence=[PRIMARY_COLOR])
        fig.update_layout(yaxis=dict(autorange="reversed"),
                           margin=dict(t=40, b=20), height=300)
        st.plotly_chart(fig, use_container_width=True)

    with col4:
        INCOME_ORDER = ["No Income", "< 10000", "10001-25000", "25001-50000",
                         "50001-75000", "75001-100000", "100000-200000", ">200000"]
        inc = df["income"].str.strip().value_counts().reindex(INCOME_ORDER).dropna()
        fig = px.bar(x=inc.values, y=inc.index, orientation="h",
                     labels={"x": "Count", "y": "Income Range (₹)"},
                     title="Income Distribution",
                     color_discrete_sequence=[SECONDARY])
        fig.update_layout(yaxis=dict(autorange="reversed"),
                           margin=dict(t=40, b=20), height=300)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("##### Gender × Occupation")
    cross = (df.groupby(["occupation", "gender"])
               .size().reset_index(name="Count"))
    fig = px.bar(cross, x="occupation", y="Count", color="gender",
                 barmode="stack",
                 color_discrete_sequence=[PRIMARY_COLOR, SECONDARY, GREY],
                 labels={"occupation": "Occupation"})
    fig.update_layout(margin=dict(t=20, b=20), height=300)
    st.plotly_chart(fig, use_container_width=True)


def _commuter_tab_trip_patterns(df: pd.DataFrame):
    st.subheader("🗺️ Trip Patterns")

    col1, col2 = st.columns(2)

    with col1:
        tp = df["trip_purpose"].str.strip().value_counts().reset_index()
        tp.columns = ["Purpose", "Count"]
        fig = px.pie(tp, names="Purpose", values="Count", title="Trip Purpose",
                     color_discrete_sequence=px.colors.qualitative.Set2)
       urn diff if diff >= 0 else None
    df["survey_duration_mins"] = df.apply(_dur, axis=1)

    # ── Clean commuter attribute columns ──────────────────────────────────
    def _tidy(col):
        if col not in df.columns:
            return pd.Series([None] * len(df))
        return df[col].apply(_commuter_clean_str)

    df["age"] = _tidy("1b1.Age (years)")
    df["gender"] = _tidy("1b2.Gender")
    df["occupation"] = _tidy("1b3.Occupation")
    df["income"] = _tidy("1b4.Individual Monthly Income (Rs.)")
    df["trip_freq"] = _tidy("1b10.Trip Frequency")
    df["trip_purpose"] = _tidy("1b11. Trip Purpose")
    df["prev_mode"] = df["1b9.Main mode of travel before Dharavi Line\u20113 Metro became operational ?"].apply(_commuter_clean_str) \
        if "1b9.Main mode of travel before Dharavi Line\u20113 Metro became operational ?" in df.columns else None
    df["line11_bandra"] = _tidy("1b12. Will you use Line 11 extended till Bandra Terminus ?")
    df["line8_bkc"] = _tidy("1b13. Will you use Metro Line 8 connection to Dharavi  via BKC ?")

    # Clean locations
    if "1b5.Trip Origin (Start point of the trip before using metro line)" in df.columns:
        df["origin"] = df["1b5.Trip Origin (Start point of the trip before using metro line)"].apply(_commuter_clean_loc)
    if "1b6.Trip Destination (End point of the trip after using metro line)" in df.columns:
        df["destination"] = df["1b6.Trip Destination (End point of the trip after using metro line)"].apply(_commuter_clean_loc)

    # Journey time: free-text in the source data ('10', '20min', '1hr',
    # '35-40', etc.) — see parse_journey_time_minutes() for the full pattern
    # breakdown. Dash-ranges and any unrecognized format come back as NaN
    # with a reason in journey_time_issue rather than being silently dropped.
    jt_col = "1b7.Total Journey Time (Min)"
    if jt_col in df.columns:
        jt_parsed = df[jt_col].apply(parse_journey_time_minutes)
        df["journey_time_min"] = jt_parsed.apply(lambda x: x[0])
        df["journey_time_issue"] = jt_parsed.apply(lambda x: x[1])
    else:
        df["journey_time_min"] = pd.NA
        df["journey_time_issue"] = None
    df["travel_cost_rs"] = pd.to_numeric(df.get("1b8.Total Travel Cost (Rs.)", pd.NA), errors="coerce")

    # Strip leading spaces from categoricals
    for col in ["age", "gender", "occupation", "income", "trip_freq",
                "trip_purpose", "prev_mode", "line11_bandra", "line8_bkc"]:
        if col in df.columns:
            df[col] = df[col].str.strip() if df[col].dtype == object else df[col]

    return df, n_dropped, dropped_locations


def _commuter_sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.markdown("---")
    st.sidebar.subheader("🚇 Commuter Survey Filters")

    # Date
    valid_dates = df["Date"].dropna()
    if valid_dates.empty:
        filtered = df
    else:
        mn, mx = valid_dates.min().date(), valid_dates.max().date()
        sel = st.sidebar.date_input("Survey Date Range", (mn, mx), min_value=mn, max_value=mx)
        if isinstance(sel, tuple) and len(sel) == 2:
            s_date, e_date = sel
        else:
            s_date = e_date = mn
        filtered = df[(df["Date"].dt.date >= s_date) & (df["Date"].dt.date <= e_date)]

    # Surveyor
    surveyors = sorted(filtered["surveyor"].dropna().unique().tolist())
    all_s = st.sidebar.checkbox("All Surveyors", value=True, key="cs_all_s")
    sel_s = st.sidebar.multiselect("Surveyor", surveyors,
                                    default=surveyors if all_s else [], key="cs_surv")
    if sel_s:
        filtered = filtered[filtered["surveyor"].isin(sel_s)]

    # Gender
    genders = sorted(filtered["gender"].dropna().unique().tolist())
    all_g = st.sidebar.checkbox("All Genders", value=True, key="cs_all_g")
    sel_g = st.sidebar.multiselect("Gender", genders,
                                    default=genders if all_g else [], key="cs_gen")
    if sel_g:
        filtered = filtered[filtered["gender"].isin(sel_g)]

    # Occupation
    occs = sorted(filtered["occupation"].dropna().unique().tolist())
    all_o = st.sidebar.checkbox("All Occupations", value=True, key="cs_all_o")
    sel_o = st.sidebar.multiselect("Occupation", occs,
                                    default=occs if all_o else [], key="cs_occ")
    if sel_o:
        filtered = filtered[filtered["occupation"].isin(sel_o)]

    return filtered


def _commuter_kpi(col, label: str, value, delta=None, help_text: str | None = None):
    col.metric(label, value, delta=delta, help=help_text)


def _commuter_tab_overview(df: pd.DataFrame):
    st.subheader("📊 Overview")

    total = len(df)
    male_pct = round(df["gender"].eq("Male").sum() / total * 100, 1) if total else 0
    avg_time = round(df["journey_time_min"].mean(), 1)
    avg_cost = round(df["travel_cost_rs"].mean(), 1)
    surveyors = df["surveyor"].nunique()

    c1, c2, c3, c4, c5 = st.columns(5)
    _commuter_kpi(c1, "Total Responses", total, help_text="Commuter interviews recorded")
    _commuter_kpi(c2, "Male / Female", f"{male_pct}% / {round(100 - male_pct, 1)}%")
    _commuter_kpi(c3, "Avg Journey Time", f"{avg_time} min")
    _commuter_kpi(c4, "Avg Travel Cost", f"₹{avg_cost}")
    _commuter_kpi(c5, "Surveyors Active", surveyors)

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        hr = df["start_hour"].dropna().astype(int).value_counts().sort_index()
        fig = px.bar(x=hr.index, y=hr.values,
                     labels={"x": "Hour of Day", "y": "Responses"},
                     title="Survey Responses by Hour",
                     color_discrete_sequence=[PRIMARY_COLOR])
        fig.update_layout(margin=dict(t=40, b=20), height=300)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        sc = df["surveyor"].value_counts().reset_index()
        sc.columns = ["Surveyor", "Count"]
        fig = px.bar(sc, x="Count", y="Surveyor", orientation="h",
                     title="Responses per Surveyor",
                     color_discrete_sequence=[SECONDARY])
        fig.update_layout(yaxis=dict(autorange="reversed"),
                           margin=dict(t=40, b=20), height=300)
        st.plotly_chart(fig, use_container_width=True)

    jt_clean = df["journey_time_min"].dropna()
    if not jt_clean.empty:
        fig = px.histogram(jt_clean, nbins=20,
                            labels={"value": "Journey Time (min)", "count": "Responses"},
                            title="Journey Time Distribution",
                            color_discrete_sequence=[PRIMARY_COLOR])
        fig.update_layout(showlegend=False, margin=dict(t=40, b=20), height=280)
        st.plotly_chart(fig, use_container_width=True)


def _commuter_tab_demographics(df: pd.DataFrame):
    st.subheader("👥 Traveller Demographics")

    col1, col2 = st.columns(2)

    with col1:
        gd = df["gender"].value_counts().reset_index()
        gd.columns = ["Gender", "Count"]
        fig = px.pie(gd, names="Gender", values="Count", title="Gender Split",
                     color_discrete_sequence=[PRIMARY_COLOR, SECONDARY, GREY])
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(margin=dict(t=40), height=320)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        AGE_ORDER = ["<18", "18-25", "25-44", "45-59", ">60"]
        age_col = df["age"].dropna()
        age_col = age_col.str.strip()
        age_counts = age_col.value_counts().reindex(AGE_ORDER, fill_value=0)
        fig = px.bar(x=age_counts.index, y=age_counts.values,
                     labels={"x": "Age Group", "y": "Count"},
                     title="Age Distribution",
                     color_discrete_sequence=[SECONDARY])
        fig.update_layout(margin=dict(t=40), height=320)
        st.plotly_chart(fig, use_container_width=True)

    col3, col4 = st.columns(2)

    with col3:
        occ = df["occupation"].value_counts().reset_index()
        occ.columns = ["Occupation", "Count"]
        fig = px.bar(occ, x="Count", y="Occupation", orientation="h",
                     title="Occupation Breakdown",
                     color_discrete_sequence=[PRIMARY_COLOR])
        fig.update_layout(yaxis=dict(autorange="reversed"),
                           margin=dict(t=40, b=20), height=300)
        st.plotly_chart(fig, use_container_width=True)

    with col4:
        INCOME_ORDER = ["No Income", "< 10000", "10001-25000", "25001-50000",
                         "50001-75000", "75001-100000", "100000-200000", ">200000"]
        inc = df["income"].str.strip().value_counts().reindex(INCOME_ORDER).dropna()
        fig = px.bar(x=inc.values, y=inc.index, orientation="h",
                     labels={"x": "Count", "y": "Income Range (₹)"},
                     title="Income Distribution",
                     color_discrete_sequence=[SECONDARY])
        fig.update_layout(yaxis=dict(autorange="reversed"),
                           margin=dict(t=40, b=20), height=300)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("##### Gender × Occupation")
    cross = (df.groupby(["occupation", "gender"])
               .size().reset_index(name="Count"))
    fig = px.bar(cross, x="occupation", y="Count", color="gender",
                 barmode="stack",
                 color_discrete_sequence=[PRIMARY_COLOR, SECONDARY, GREY],
                 labels={"occupation": "Occupation"})
    fig.update_layout(margin=dict(t=20, b=20), height=300)
    st.plotly_chart(fig, use_container_width=True)


def _commuter_tab_trip_patterns(df: pd.DataFrame):
    st.subheader("🗺️ Trip Patterns")

    col1, col2 = st.columns(2)

    with col1:
        tp = df["trip_purpose"].str.strip().value_counts().reset_index()
        tp.columns = ["Purpose", "Count"]
        fig = px.pie(tp, names="Purpose", values="Count", title="Trip Purpose",
                     color_discrete_sequence=px.colors.qualitative.Set2)
       
# ── Imports ───────────────────────────────────────────────────────────────────
import io
import os
from datetime import datetime, time

import pandas as pd
import plotly.express as px
from rapidfuzz import fuzz, process as rfprocess

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Mumbai Traffic Survey Dashboard",
    layout="wide",
    page_icon="🚦",
)

PRIMARY_COLOR = "#0057A8"
SHEET_NAME = "Survey Results"

# Colour palette shared by the Commuter Survey section
SECONDARY = "#00A3E0"
SUCCESS = "#28A745"
WARNING = "#FFC107"
DANGER = "#DC3545"
GREY = "#6C757D"

# ── Sidebar page selector ─────────────────────────────────────────────────────
st.sidebar.title("🚦 Mumbai Survey Dashboard")
st.sidebar.markdown("---")

PAGES = {
    "🚦 Traffic Survey (JJ / Dahisar)": "traffic",
    "🚇 Commuter Survey (Dharavi Metro)": "commuter",
}

selected_page = st.sidebar.radio("Navigate to", list(PAGES.keys()), key="nav_page")
page_key = PAGES[selected_page]

st.sidebar.markdown("---")


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION: COMMUTER SURVEY  — constants & helpers
#  (formerly commuter_survey_page.py, inlined; names prefixed/renamed to avoid
#   collisions with the Traffic Survey section below)
# ══════════════════════════════════════════════════════════════════════════════

# ── Canonical surveyor name map (commuter survey) ─────────────────────────────
COMMUTER_SURVEYOR_NORM: dict[str, str] = {
    # Abdul
    "Abdul": "Abdul",
    "abdul": "Abdul",
    # Shahjahan Shaikh
    "shahjahan shaikh": "Shahjahan Shaikh",
    "shahjahan shaikh ": "Shahjahan Shaikh",
    # Karan
    "karan": "Karan",
    "karan ": "Karan",
    # Amit Mishra
    "amit mishra": "Amit Mishra",
    "amit ": "Amit Mishra",
    "amit": "Amit Mishra",
    # Ramgopal Chaurasiya
    "ramgopal chaurasiya": "Ramgopal Chaurasiya",
    "ramgopal chaurasiya ": "Ramgopal Chaurasiya",
    "Ramgopal chaurasiya ": "Ramgopal Chaurasiya",
    # Rushikesh
    "rushikesh": "Rushikesh",
    "rushikesh ": "Rushikesh",
    # Manas
    "manas": "Manas",
    "manas ": "Manas",
    "Manas ": "Manas",
    # Shariq
    "shariq": "Shariq",
    # Uttkarsh Yadav
    "uttkarsh yadav": "Uttkarsh Yadav",
    "uttkarsh yadav ": "Uttkarsh Yadav",
    "Uttkarsh Yadav ": "Uttkarsh Yadav",
    "uttkarsh ": "Uttkarsh Yadav",
    # Anash Khan
    "anash khan": "Anash Khan",
    "anash ": "Anash Khan",
    # Nirvan Mamidi
    "nirvan ravi mamidi": "Nirvan Mamidi",
    "Nirvan Ravi Mamidi ": "Nirvan Mamidi",
    "nirvan mamidi": "Nirvan Mamidi",
    "Nirvan Mamidi": "Nirvan Mamidi",
    "Nirvan ": "Nirvan Mamidi",
    "nirvan ": "Nirvan Mamidi",
}

# ── Location clean-up helpers (commuter survey) ───────────────────────────────
COMMUTER_LOCATION_NORM: dict[str, str | None] = {
    "dharavi": "Dharavi",
    "dharavi ": "Dharavi",
    "Dharavi ": "Dharavi",
    "dhravi ": "Dharavi",
    "dhravi": "Dharavi",
    "dharvi ": "Dharavi",
    "bkc": "BKC",
    "Bkc": "BKC",
    "midc": "MIDC",
    "t2": "Airport T2",
    "T2": "Airport T2",
    "t1 airport": "Airport T1",
    "t1 airport ": "Airport T1",
    "andheri ": "Andheri",
    "andheri": "Andheri",
    "mahim": "Mahim",
    "dadar": "Dadar",
    "Dadar": "Dadar",
    "koliwada ": "Koliwada",
    "koliwada": "Koliwada",
    "wadala ": "Wadala",
    "shitladevi": "Shitladevi",
    "mahalakshmi": "Mahalaxmi",
    "mahalaxmi": "Mahalaxmi",
    "need ": None,   # junk entry
    "-": None,
}

COMMUTER_INVALID_SET = {"-", "nan", "none", "", "nil", "na"}


def _commuter_clean_loc(val: str | None) -> str | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    if s.lower() in COMMUTER_INVALID_SET:
        return None
    return COMMUTER_LOCATION_NORM.get(s, s.title())


def _commuter_clean_str(val) -> str | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    return None if s.lower() in COMMUTER_INVALID_SET else s


def _commuter_parse_time(series: pd.Series) -> pd.Series:
    return pd.to_datetime(
        series.astype(str), format="%H:%M:%S", errors="coerce"
    ).dt.time


@st.cache_data(show_spinner=False)
def load_commuter_data(raw_bytes: bytes) -> pd.DataFrame:
    df = pd.read_excel(io.BytesIO(raw_bytes), sheet_name="Survey Results",
                        engine="openpyxl")

    # ── Surveyor normalisation ─────────────────────────────────────────────
    if "Remarks1" in df.columns:
        df["surveyor"] = (
            df["Remarks1"].astype(str).str.strip()
            .map(lambda x: COMMUTER_SURVEYOR_NORM.get(
                x, x.title() if x.lower() not in COMMUTER_INVALID_SET else None))
        )
    else:
        df["surveyor"] = None

    # ── Date / time ────────────────────────────────────────────────────────
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], format="%d/%m/%Y", errors="coerce")
    if "start_time" in df.columns:
        df["start_time"] = _commuter_parse_time(df["start_time"])
    if "end_time" in df.columns:
        df["end_time"] = _commuter_parse_time(df["end_time"])

    df["start_hour"] = df["start_time"].apply(
        lambda x: x.hour if x and not pd.isna(x) else None)

    # Survey duration
    def _dur(row):
        s, e = row.get("start_time"), row.get("end_time")
        if s is None or e is None:
            return None
        sd = datetime.combine(datetime.today(), s)
        ed = datetime.combine(datetime.today(), e)
        diff = (ed - sd).total_seconds() / 60
        return diff if diff >= 0 else None
    df["survey_duration_mins"] = df.apply(_dur, axis=1)

    # ── Clean commuter attribute columns ──────────────────────────────────
    def _tidy(col):
        if col not in df.columns:
            return pd.Series([None] * len(df))
        return df[col].apply(_commuter_clean_str)

    df["age"] = _tidy("1b1.Age (years)")
    df["gender"] = _tidy("1b2.Gender")
    df["occupation"] = _tidy("1b3.Occupation")
    df["income"] = _tidy("1b4.Individual Monthly Income (Rs.)")
    df["trip_freq"] = _tidy("1b10.Trip Frequency")
    df["trip_purpose"] = _tidy("1b11. Trip Purpose")
    df["prev_mode"] = df["1b9.Main mode of travel before Dharavi Line\u20113 Metro became operational ?"].apply(_commuter_clean_str) \
        if "1b9.Main mode of travel before Dharavi Line\u20113 Metro became operational ?" in df.columns else None
    df["line11_bandra"] = _tidy("1b12. Will you use Line 11 extended till Bandra Terminus ?")
    df["line8_bkc"] = _tidy("1b13. Will you use Metro Line 8 connection to Dharavi  via BKC ?")

    # Clean locations
    if "1b5.Trip Origin (Start point of the trip before using metro line)" in df.columns:
        df["origin"] = df["1b5.Trip Origin (Start point of the trip before using metro line)"].apply(_commuter_clean_loc)
    if "1b6.Trip Destination (End point of the trip after using metro line)" in df.columns:
        df["destination"] = df["1b6.Trip Destination (End point of the trip after using metro line)"].apply(_commuter_clean_loc)

    # Numeric journey cols
    df["journey_time_min"] = pd.to_numeric(df.get("1b7.Total Journey Time (Min)", pd.NA), errors="coerce")
    df["travel_cost_rs"] = pd.to_numeric(df.get("1b8.Total Travel Cost (Rs.)", pd.NA), errors="coerce")

    # Strip leading spaces from categoricals
    for col in ["age", "gender", "occupation", "income", "trip_freq",
                "trip_purpose", "prev_mode", "line11_bandra", "line8_bkc"]:
        if col in df.columns:
            df[col] = df[col].str.strip() if df[col].dtype == object else df[col]

    return df


def _commuter_sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.markdown("---")
    st.sidebar.subheader("🚇 Commuter Survey Filters")

    # Date
    valid_dates = df["Date"].dropna()
    if valid_dates.empty:
        filtered = df
    else:
        mn, mx = valid_dates.min().date(), valid_dates.max().date()
        sel = st.sidebar.date_input("Survey Date Range", (mn, mx), min_value=mn, max_value=mx)
        if isinstance(sel, tuple) and len(sel) == 2:
            s_date, e_date = sel
        else:
            s_date = e_date = mn
        filtered = df[(df["Date"].dt.date >= s_date) & (df["Date"].dt.date <= e_date)]

    # Surveyor
    surveyors = sorted(filtered["surveyor"].dropna().unique().tolist())
    all_s = st.sidebar.checkbox("All Surveyors", value=True, key="cs_all_s")
    sel_s = st.sidebar.multiselect("Surveyor", surveyors,
                                    default=surveyors if all_s else [], key="cs_surv")
    if sel_s:
        filtered = filtered[filtered["surveyor"].isin(sel_s)]

    # Gender
    genders = sorted(filtered["gender"].dropna().unique().tolist())
    all_g = st.sidebar.checkbox("All Genders", value=True, key="cs_all_g")
    sel_g = st.sidebar.multiselect("Gender", genders,
                                    default=genders if all_g else [], key="cs_gen")
    if sel_g:
        filtered = filtered[filtered["gender"].isin(sel_g)]

    # Occupation
    occs = sorted(filtered["occupation"].dropna().unique().tolist())
    all_o = st.sidebar.checkbox("All Occupations", value=True, key="cs_all_o")
    sel_o = st.sidebar.multiselect("Occupation", occs,
                                    default=occs if all_o else [], key="cs_occ")
    if sel_o:
        filtered = filtered[filtered["occupation"].isin(sel_o)]

    return filtered


def _commuter_kpi(col, label: str, value, delta=None, help_text: str | None = None):
    col.metric(label, value, delta=delta, help=help_text)


def _commuter_tab_overview(df: pd.DataFrame):
    st.subheader("📊 Overview")

    total = len(df)
    male_pct = round(df["gender"].eq("Male").sum() / total * 100, 1) if total else 0
    avg_time = round(df["journey_time_min"].mean(), 1)
    avg_cost = round(df["travel_cost_rs"].mean(), 1)
    surveyors = df["surveyor"].nunique()

    c1, c2, c3, c4, c5 = st.columns(5)
    _commuter_kpi(c1, "Total Responses", total, help_text="Commuter interviews recorded")
    _commuter_kpi(c2, "Male / Female", f"{male_pct}% / {round(100 - male_pct, 1)}%")
    _commuter_kpi(c3, "Avg Journey Time", f"{avg_time} min")
    _commuter_kpi(c4, "Avg Travel Cost", f"₹{avg_cost}")
    _commuter_kpi(c5, "Surveyors Active", surveyors)

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        hr = df["start_hour"].dropna().astype(int).value_counts().sort_index()
        fig = px.bar(x=hr.index, y=hr.values,
                     labels={"x": "Hour of Day", "y": "Responses"},
                     title="Survey Responses by Hour",
                     color_discrete_sequence=[PRIMARY_COLOR])
        fig.update_layout(margin=dict(t=40, b=20), height=300)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        sc = df["surveyor"].value_counts().reset_index()
        sc.columns = ["Surveyor", "Count"]
        fig = px.bar(sc, x="Count", y="Surveyor", orientation="h",
                     title="Responses per Surveyor",
                     color_discrete_sequence=[SECONDARY])
        fig.update_layout(yaxis=dict(autorange="reversed"),
                           margin=dict(t=40, b=20), height=300)
        st.plotly_chart(fig, use_container_width=True)

    jt_clean = df["journey_time_min"].dropna()
    if not jt_clean.empty:
        fig = px.histogram(jt_clean, nbins=20,
                            labels={"value": "Journey Time (min)", "count": "Responses"},
                            title="Journey Time Distribution",
                            color_discrete_sequence=[PRIMARY_COLOR])
        fig.update_layout(showlegend=False, margin=dict(t=40, b=20), height=280)
        st.plotly_chart(fig, use_container_width=True)


def _commuter_tab_demographics(df: pd.DataFrame):
    st.subheader("👥 Traveller Demographics")

    col1, col2 = st.columns(2)

    with col1:
        gd = df["gender"].value_counts().reset_index()
        gd.columns = ["Gender", "Count"]
        fig = px.pie(gd, names="Gender", values="Count", title="Gender Split",
                     color_discrete_sequence=[PRIMARY_COLOR, SECONDARY, GREY])
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(margin=dict(t=40), height=320)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        AGE_ORDER = ["<18", "18-25", "25-44", "45-59", ">60"]
        age_col = df["age"].dropna()
        age_col = age_col.str.strip()
        age_counts = age_col.value_counts().reindex(AGE_ORDER, fill_value=0)
        fig = px.bar(x=age_counts.index, y=age_counts.values,
                     labels={"x": "Age Group", "y": "Count"},
                     title="Age Distribution",
                     color_discrete_sequence=[SECONDARY])
        fig.update_layout(margin=dict(t=40), height=320)
        st.plotly_chart(fig, use_container_width=True)

    col3, col4 = st.columns(2)

    with col3:
        occ = df["occupation"].value_counts().reset_index()
        occ.columns = ["Occupation", "Count"]
        fig = px.bar(occ, x="Count", y="Occupation", orientation="h",
                     title="Occupation Breakdown",
                     color_discrete_sequence=[PRIMARY_COLOR])
        fig.update_layout(yaxis=dict(autorange="reversed"),
                           margin=dict(t=40, b=20), height=300)
        st.plotly_chart(fig, use_container_width=True)

    with col4:
        INCOME_ORDER = ["No Income", "< 10000", "10001-25000", "25001-50000",
                         "50001-75000", "75001-100000", "100000-200000", ">200000"]
        inc = df["income"].str.strip().value_counts().reindex(INCOME_ORDER).dropna()
        fig = px.bar(x=inc.values, y=inc.index, orientation="h",
                     labels={"x": "Count", "y": "Income Range (₹)"},
                     title="Income Distribution",
                     color_discrete_sequence=[SECONDARY])
        fig.update_layout(yaxis=dict(autorange="reversed"),
                           margin=dict(t=40, b=20), height=300)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("##### Gender × Occupation")
    cross = (df.groupby(["occupation", "gender"])
               .size().reset_index(name="Count"))
    fig = px.bar(cross, x="occupation", y="Count", color="gender",
                 barmode="stack",
                 color_discrete_sequence=[PRIMARY_COLOR, SECONDARY, GREY],
                 labels={"occupation": "Occupation"})
    fig.update_layout(margin=dict(t=20, b=20), height=300)
    st.plotly_chart(fig, use_container_width=True)


def _commuter_tab_trip_patterns(df: pd.DataFrame):
    st.subheader("🗺️ Trip Patterns")

    col1, col2 = st.columns(2)

    with col1:
        tp = df["trip_purpose"].str.strip().value_counts().reset_index()
        tp.columns = ["Purpose", "Count"]
        fig = px.pie(tp, names="Purpose", values="Count", title="Trip Purpose",
                     color_discrete_sequence=px.colors.qualitative.Set2)
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(margin=dict(t=40), height=320)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        FREQ_ORDER = ["Daily", "Alternate Days", "Weekly", "Monthly", "Occasionally"]
        freq = df["trip_freq"].str.strip().value_counts().reindex(FREQ_ORDER).dropna()
        fig = px.bar(x=freq.index, y=freq.values,
                     labels={"x": "Frequency", "y": "Count"},
                     title="Trip Frequency",
                     color_discrete_sequence=[PRIMARY_COLOR])
        fig.update_layout(margin=dict(t=40), height=320)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("##### Mode of Travel Before Dharavi Metro")
    mode = df["prev_mode"].str.strip().value_counts().reset_index()
    mode.columns = ["Mode", "Count"]
    fig = px.bar(mode, x="Count", y="Mode", orientation="h",
                 color_discrete_sequence=[SECONDARY])
    fig.update_layout(yaxis=dict(autorange="reversed"),
                       margin=dict(t=20, b=20), height=350)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("##### Top Origin → Destination Pairs")
    od = (df.dropna(subset=["origin", "destination"])
            .groupby(["origin", "destination"])
            .size().reset_index(name="Trips")
            .sort_values("Trips", ascending=False)
            .head(15))
    od["O-D Pair"] = od["origin"] + " → " + od["destination"]
    fig = px.bar(od, x="Trips", y="O-D Pair", orientation="h",
                 color="Trips", color_continuous_scale="Blues")
    fig.update_layout(yaxis=dict(autorange="reversed"),
                       margin=dict(t=20, b=20), height=420)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("##### Journey Time vs Travel Cost")
    jt_cost = df[["journey_time_min", "travel_cost_rs", "occupation",
                  "trip_purpose"]].dropna(subset=["journey_time_min", "travel_cost_rs"])
    if not jt_cost.empty:
        fig = px.scatter(jt_cost, x="journey_time_min", y="travel_cost_rs",
                          color="occupation",
                          labels={"journey_time_min": "Journey Time (min)",
                                  "travel_cost_rs": "Travel Cost (₹)"},
                          opacity=0.7,
                          color_discrete_sequence=px.colors.qualitative.Set1)
        fig.update_layout(margin=dict(t=20, b=20), height=350)
        st.plotly_chart(fig, use_container_width=True)


def _commuter_tab_metro_opinion(df: pd.DataFrame):
    st.subheader("🚉 Metro Line Expansion Opinions")

    col1, col2 = st.columns(2)

    def _opinion_pie(col, series, title):
        vc = series.str.strip().value_counts().reset_index()
        vc.columns = ["Response", "Count"]
        COLOR_MAP = {
            "Yes": SUCCESS,
            "No": DANGER,
            "Not applicable for my journey": GREY,
        }
        colors = [COLOR_MAP.get(r, "#888") for r in vc["Response"]]
        fig = px.pie(vc, names="Response", values="Count", title=title,
                     color_discrete_sequence=colors)
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(margin=dict(t=40), height=320)
        col.plotly_chart(fig, use_container_width=True)

    _opinion_pie(col1, df["line11_bandra"].dropna(),
                 "Will use Line 11 (Dharavi→Bandra Terminus)?")
    _opinion_pie(col2, df["line8_bkc"].dropna(),
                 "Will use Line 8 (Dharavi via BKC)?")

    st.markdown("##### Line 11 Opinion by Occupation")
    line11_occ = (df.dropna(subset=["line11_bandra", "occupation"])
                    .groupby(["occupation", "line11_bandra"]))

PRIMARY_COLOR = "#0057A8"
SHEET_NAME = "Survey Results"

# --------------------------------------------------
# CANONICAL LOCATIONS & CONSTANTS
# --------------------------------------------------
CANONICAL_LOCATIONS = [
    "Bandra West", "Bandra East", "Bandra Terminus", "Bandra Kurla Complex",
    "CSMT", "Churchgate", "Dadar TT", "Dadar East", "Dadar West",
    "Andheri", "Andheri East", "Andheri West", "Borivali", "Malad",
    "Worli", "Worli Depot", "Lower Parel", "Mahim", "Sion", "Kurla",
    "Dharavi", "Chembur", "Masjid Bandar", "Nagpada", "Byculla",
    "Colaba", "Navy Nagar", "Gateway Of India", "Marine Drive",
    "Mohammad Ali Road", "JJ Hospital", "JJ Flyover", "Mantralaya",
    "Wadala", "Antop Hill", "Mazgaon", "Mumbai Central", "Santacruz",
    "Juhu", "Vile Parle", "Goregaon", "Thane", "Navi Mumbai", "Panvel",
    "Pune", "Nashik", "Alibaug", "Bhindi Bazaar", "Crawford Market",
    "Zaveri Bazaar", "Mahalaxmi", "Grant Road", "Chinchpokli", "Parel",
    "Lal Baug", "Shivaji Nagar", "Pratiksha Nagar", "Antop Hill Bus Stop",
    "Bhaikhala", "Dongri", "Nagpada Chauki", "Pydhonie", "Mazgaon Court",
    "Dhobi Ghat", "Kalbadevi", "Bhendi Bazaar", "Mumbra", "Kalyan",
    "Vasai", "Virar", "Mira Road", "Bhayandar", "Dadar",
    "Dockyard Road", "Sandhurst Road", "Reay Road", "Cotton Green",
    "Sewri", "Masjid", "Marine Lines", "Charni Road", "Mumbai Airport",
    "Sahar", "Kurla Terminus", "Lokmanya Tilak Terminus", "LTT",
    "Mulund", "Ghatkopar", "Vikhroli", "Kanjurmarg", "Bhandup",
    "Nahur", "Dombivli", "Ambernath", "Badlapur",
]

INVALID_LOCATION_VALUES = {
    "-", "none", "not mentioned", "not mention", "reserved",
    "null", "na", "", "n/a", ".", "x", "nil"
}

# --------------------------------------------------
# SCHEMA DETECTION
# Schema A = Mumbai/JJ file  (has "3.Vehicle Type", "2.Arm details")
# Schema B = Dahisar Toll    (has "2.Type of Vehicle", "1.Direction")
# --------------------------------------------------
def detect_schema(df):
    if "3.Vehicle Type" in df.columns:
        return "A"
    if "2.Type of Vehicle" in df.columns:
        return "B"
    return "A"  # fallback


# Vehicle mapping for Schema A (Mumbai/JJ)
VEHICLE_MAPPING_A = {
    "Car": (
        "3a4.Trip Origin",
        "3a5.Trip Destination",
        "3a1.Occupancy (Including driver)"
    ),
    "Taxi/Cab": (
        "3b4.Trip Origin",
        "3b5.Trip Destination",
        "3b1.Occupancy (Including driver)"
    ),
    "Mini Bus - Govt": (
        "3c3.Trip Origin",
        "3c4.Trip Destination",
        "3c5.Mention the Occupancy (In Percentage)"
    ),
    "City Bus - Govt (BEST)": (
        "3d3.Trip Origin",
        "3d4.Trip Destination",
        "3d5.Mention the Occupancy (In Percentage)"
    ),
    "City Bus - Private (Chalo, City flow)": (
        "3e3.Trip Origin",
        "3e4.Trip Destination",
        "3e5.Mention the Occupancy (In Percentage)"
    ),
    "City Bus - Private (Chalo,Cityflow)": (
        "3e3.Trip Origin",
        "3e4.Trip Destination",
        "3e5.Mention the Occupancy (In Percentage)"
    ),
    "Inter city bus - Govt": (
        "3f3.Trip Origin",
        "3f4.Trip Destination",
        "3f5.Mention the Occupancy (In Percentage)"
    ),
    "Inter city bus - Private": (
        "3g3.Trip Origin",
        "3g4.Trip Destination",
        "3g5.Mention the Occupancy (In Percentage)"
    ),
    "Mini Bus - Private": (
        "3h3.Trip Origin",
        "3h4.Trip Destination",
        "3h5.Mention the Occupancy (In Percentage)"
    ),
    "Others": (
        "3i3.Trip Origin",
        "3i4.Trip Destination",
        "3i2.Occupancy (Including Driver)"
    ),
}

BUS_OCC_COLS_A = [
    "3c5.Mention the Occupancy (In Percentage)",
    "3d5.Mention the Occupancy (In Percentage)",
    "3e5.Mention the Occupancy (In Percentage)",
    "3f5.Mention the Occupancy (In Percentage)",
    "3g5.Mention the Occupancy (In Percentage)",
    "3h5.Mention the Occupancy (In Percentage)",
]

# Vehicle mapping for Schema B (Dahisar Toll)
# Passenger sub-types: 2a1a=Car, 2a1b=Taxi, 2a1e/f/g/h=buses
# Goods sub-types: 2b1.Vehicle Type
VEHICLE_MAPPING_B = {
    "Car": (
        "2a1a2.Trip Origin",
        "2a1a3.Trip destination",
        "2a1a1.Occupancy (Including Driver)"
    ),
    "Taxi": (
        "2a1b2.Trip Origin",
        "2a1b3.Trip destination",
        "2a1b1.Occupancy (Including Driver)"
    ),
    "City Bus- Govt (BEST)": (
        "2a1e2.Trip Origin",
        "2a1e3.Trip destination",
        "2a1e1.Mention the Occupancy (In percentage)"
    ),
    "City Bus- private(Chalo, city flow)": (
        "2a1f2.Trip Origin",
        "2a1f3.Trip destination",
        "2a1f1.Mention the Occupancy (In percentage)"
    ),
    "Inter city Bus - Govt": (
        "2a1g2.Trip Origin",
        "2a1g3.Trip destination",
        "2a1g1.Mention the Occupancy (In percentage)"
    ),
    "Inter City Bus - Private": (
        "2a1h2.Trip Origin",
        "2a1h3.Trip destination",
        "2a1h1.Mention the Occupancy (In percentage)"
    ),
    # Goods vehicles
    "LCV": ("2b2.Origin", "2b3.Destination", None),
    "Mini LCV": ("2b2.Origin", "2b3.Destination", None),
    "2-Axle Truck": ("2b2.Origin", "2b3.Destination", None),
    "3-Axle Truck": ("2b2.Origin", "2b3.Destination", None),
    "MAV": ("2b2.Origin", "2b3.Destination", None),
    "OSV": ("2b2.Origin", "2b3.Destination", None),
}

BUS_OCC_COLS_B = [
    "2a1e1.Mention the Occupancy (In percentage)",
    "2a1f1.Mention the Occupancy (In percentage)",
    "2a1g1.Mention the Occupancy (In percentage)",
    "2a1h1.Mention the Occupancy (In percentage)",
]


def normalize_schema_b(df):
    """
    Normalize Schema B (Dahisar) columns into the canonical Schema A column names
    so the rest of the app works unchanged.
    The unified vehicle type is derived from 2a1.Type of Vehicle (passenger)
    or 2b1.Vehicle Type (goods).
    """
    out = df.copy()

    # Derive unified vehicle type column -> "3.Vehicle Type"
    def get_vehicle_type(row):
        vtype = str(row.get("2.Type of Vehicle", "-")).strip()
        if vtype == "Passenger":
            v = str(row.get("2a1.Type of Vehicle", "-")).strip()
            return v if v and v != "-" else pd.NA
        elif vtype == "Goods":
            v = str(row.get("2b1.Vehicle Type", "-")).strip()
            return v if v and v != "-" else pd.NA
        return pd.NA

    out["3.Vehicle Type"] = out.apply(get_vehicle_type, axis=1)

    # Derive arm/direction column -> "2.Arm details"
    out["2.Arm details"] = out.get("1.Direction", pd.NA)

    return out


def get_od_b(row):
    """O-D extractor for Schema B rows (already normalized vehicle type)."""
    vt = row.get("3.Vehicle Type", None)
    if pd.isna(vt):
        return pd.Series([None, None, None])
    vt_clean = " ".join(str(vt).strip().split())
    cols = VEHICLE_MAPPING_B.get(vt_clean)
    if not cols:
        for k, v in VEHICLE_MAPPING_B.items():
            if " ".join(k.strip().split()).lower() == vt_clean.lower():
                cols = v
                break
    if not cols:
        return pd.Series([None, None, None])
    origin_col, dest_col, occ_col = cols
    origin = row.get(origin_col, None)
    destination = row.get(dest_col, None)
    occupancy = row.get(occ_col, None) if occ_col else None
    return pd.Series([origin, destination, occupancy])


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------
def safe_col(df, col):
    return col in df.columns


def parse_time_column(series):
    parsed = pd.to_datetime(series.astype(str), format="%H:%M:%S", errors="coerce")
    return parsed.dt.time


def timedelta_to_minutes(td):
    if pd.isna(td):
        return None
    return td.total_seconds() / 60


def fuzzy_normalize_location(value, canonical_list, threshold=75):
    if pd.isna(value):
        return None, False, "Missing"
    raw = str(value).strip()
    if not raw or raw.lower() in INVALID_LOCATION_VALUES:
        return None, False, "Invalid placeholder"
    if len(raw) < 3:
        return None, False, "Too short"
    if raw.isnumeric():
        return None, False, "Numeric value"

    match = process.extractOne(raw, canonical_list, scorer=fuzz.WRatio)
    if match and match[1] >= threshold:
        return match[0], True, None
    # Return raw value (title-cased) even when no canonical match — don't discard it
    return raw.title(), False, "No canonical match"


def get_od(row, vehicle_mapping=None):
    if vehicle_mapping is None:
        vehicle_mapping = VEHICLE_MAPPING_A
    vt = row.get("3.Vehicle Type", None)
    if pd.isna(vt):
        return pd.Series([None, None, None])
    vt_clean = " ".join(str(vt).strip().split())
    cols = vehicle_mapping.get(vt_clean)
    if not cols:
        for k, v in vehicle_mapping.items():
            if " ".join(k.strip().split()).lower() == vt_clean.lower():
                cols = v
                break
    if not cols:
        return pd.Series([None, None, None])
    origin_col, dest_col, occ_col = cols
    origin = row.get(origin_col, None)
    destination = row.get(dest_col, None)
    occupancy = row.get(occ_col, None) if occ_col else None
    return pd.Series([origin, destination, occupancy])


def clean_location_series(series):
    """Strip, replace placeholders with NaN, title-case."""
    s = series.apply(lambda x: str(x).strip() if pd.notna(x) else x)
    s = s.replace(["-", "", "None", "nan", "NaN"], pd.NA)
    s = s.apply(lambda x: x.title() if isinstance(x, str) else x)
    return s


@st.cache_data(show_spinner=False)
def process_dataframe(raw_bytes):
    df = pd.read_excel(io.BytesIO(raw_bytes), sheet_name=SHEET_NAME, engine="openpyxl")

    # Auto-detect schema and normalise to canonical columns
    schema = detect_schema(df)
    if schema == "B":
        df = normalize_schema_b(df)
        vehicle_mapping = VEHICLE_MAPPING_B
        bus_occ_cols = BUS_OCC_COLS_B
    else:
        vehicle_mapping = VEHICLE_MAPPING_A
        bus_occ_cols = BUS_OCC_COLS_A

    # Ensure canonical columns exist (fallback to NA if missing)
    for col in ["3.Vehicle Type", "2.Arm details"]:
        if col not in df.columns:
            df[col] = pd.NA

    # --------------------------------------------------
    # SURVEYOR NAME NORMALIZATION
    # Maps known spelling variants → canonical name.
    # Each person is counted as ONE individual regardless
    # of capitalisation / typos in the field.
    # --------------------------------------------------
    SURVEYOR_NORM = {
        # Rajesh Jha  (case variants)
        "rajesh jha":          "Rajesh Jha",
        "Rajesh jha":          "Rajesh Jha",
        # Ramesh  (keep separate from Rajesh — verify via Remarks2 if needed)
        "Ramesh":              "Ramesh",
        "rajesh":              "Rajesh",        # treat as distinct until confirmed
        # Brijesh  (typos: brijedh, vrijesh)
        "Brijesh":             "Brijesh",
        "brijesh":             "Brijesh",
        "brijedh":             "Brijesh",
        "vrijesh":             "Brijesh",
        # Krishna Singh  (singj typo, bare "Krishna")
        "Krishna singh":       "Krishna Singh",
        "Krishna Singh":       "Krishna Singh",
        "Krishna singj":       "Krishna Singh",
        "Krishna":             "Krishna Singh",
        # Naitik  (with/without surname Shah)
        "naitik":              "Naitik Shah",
        "naitik shah":         "Naitik Shah",
        "naitik Shah":         "Naitik Shah",
        "Naitik":              "Naitik Shah",
        # Ankit Yadav  (case)
        "Ankit yadav":         "Ankit Yadav",
        "Ankit Yadav":         "Ankit Yadav",
        # Vicky  (case)
        "Vicky":               "Vicky",
        "vicky":               "Vicky",
        # Durgesh  (case)
        "durgesh":             "Durgesh",
        "Durgesh":             "Durgesh",
        # Raj Gaud  (goud typo)
        "Raj gaud":            "Raj Gaud",
        "Raj goud":            "Raj Gaud",
        # Vivek  (case)
        "vivek":               "Vivek",
        "Vivek":               "Vivek",
        # Prathmesh Langade  (Prathamesh spelling variant)
        "Prathmesh langade":   "Prathmesh Langade",
        "Prathamesh langade":  "Prathmesh Langade",
        # Kishan  (trailing garbage "kishan in")
        "kishan":              "Kishan",
        "kishan in":           "Kishan",
        # Trisha  (case)
        "trisha":              "Trisha",
        "Trisha":              "Trisha",
        # Yash Shukla  (bare "Yash")
        "yash shukla":         "Yash Shukla",
        "Yash":                "Yash Shukla",
        # Subhankar Das  (bare "subhankar")
        "subhankar Das":       "Subhankar Das",
        "subhankar":           "Subhankar Das",
        # Clean single-name surveyors (title-case)
        "karan":               "Karan",
        "Ranjit":              "Ranjit",
        "amit":                "Amit",
        "suhani":              "Suhani",
        "Pravin":              "Pravin",
        "Santosh Ingale":      "Santosh Ingale",
        "Udaykumar":           "Udaykumar",
        "sudhanshu Kumar":     "Sudhanshu Kumar",
        "chandan":             "Chandan",
        "krishna Kumar":       "Krishna Kumar",
        "sonu":                "Sonu",
        "kuldeep Rajpoot":     "Kuldeep Rajpoot",
        "Arvind Murkute":      "Arvind Murkute",
    }

    # Surveyor name
    if safe_col(df, "Remarks1"):
        df["Remarks1"] = (
            df["Remarks1"].astype(str)
            .str.strip()
            .replace({"nan": pd.NA, "None": pd.NA, "": pd.NA})
        )
        # Apply explicit normalization map first, then fall back to title-case
        df["Remarks1"] = df["Remarks1"].map(
            lambda x: SURVEYOR_NORM.get(x, x.title() if isinstance(x, str) else x)
            if pd.notna(x) else pd.NA
        )

    # Dates
    if safe_col(df, "Date"):
        df["Date"] = pd.to_datetime(df["Date"], format="%d/%m/%Y", errors="coerce")

    # Times
    if safe_col(df, "start_time"):
        df["start_time"] = parse_time_column(df["start_time"])
    if safe_col(df, "end_time"):
        df["end_time"] = parse_time_column(df["end_time"])

    # Duration
    def compute_duration(row):
        s, e = row.get("start_time"), row.get("end_time")
        if s is None or e is None or pd.isna(s) or pd.isna(e):
            return pd.NaT
        sd = datetime.combine(datetime.today(), s)
        ed = datetime.combine(datetime.today(), e)
        return ed - sd if ed >= sd else pd.NaT

    df["survey_duration"] = df.apply(compute_duration, axis=1)
    df["survey_duration_mins"] = df["survey_duration"].apply(timedelta_to_minutes)

    # Unified O-D
    df[["raw_origin", "raw_destination", "unified_occupancy"]] = df.apply(
        lambda row: get_od(row, vehicle_mapping), axis=1
    )
    df["raw_origin"] = clean_location_series(df["raw_origin"])
    df["raw_destination"] = clean_location_series(df["raw_destination"])

    # Occupancy
    df["unified_occupancy"] = (
        df["unified_occupancy"]
        .astype(str).str.replace("%", "", regex=False).str.strip()
    )
    df["unified_occupancy"] = pd.to_numeric(df["unified_occupancy"], errors="coerce")

    # Fuzzy normalize locations
    origin_results = df["raw_origin"].apply(
        lambda x: fuzzy_normalize_location(x, CANONICAL_LOCATIONS)
    )
    dest_results = df["raw_destination"].apply(
        lambda x: fuzzy_normalize_location(x, CANONICAL_LOCATIONS)
    )

    df["unified_origin"] = origin_results.apply(lambda x: x[0])
    df["origin_clean"] = origin_results.apply(lambda x: x[1])
    df["origin_issue"] = origin_results.apply(lambda x: x[2])

    df["unified_destination"] = dest_results.apply(lambda x: x[0])
    df["destination_clean"] = dest_results.apply(lambda x: x[1])
    df["destination_issue"] = dest_results.apply(lambda x: x[2])

    # Final clean pass
    df["unified_origin"] = clean_location_series(df["unified_origin"])
    df["unified_destination"] = clean_location_series(df["unified_destination"])

    df["location_clean"] = df["origin_clean"] & df["destination_clean"]
    df["bad_location_entry"] = ~df["location_clean"]

    def derive_issue_type(row):
        issues = []
        if not row.get("origin_clean", False):
            issues.append(f"Origin: {row.get('origin_issue', 'Issue')}")
        if not row.get("destination_clean", False):
            issues.append(f"Dest: {row.get('destination_issue', 'Issue')}")
        return " | ".join(issues) if issues else None

    df["location_issue_type"] = df.apply(derive_issue_type, axis=1)

    # Hour
    df["start_hour"] = df["start_time"].apply(
        lambda x: x.hour if pd.notna(x) and x is not None else None
    )

    # Bus sitting %
    df["avg_sitting_pct_source"] = pd.NA
    for col in bus_occ_cols:
        if safe_col(df, col):
            temp = pd.to_numeric(
                df[col].astype(str).str.replace("%", "", regex=False).str.strip(),
                errors="coerce"
            )
            mask = df["avg_sitting_pct_source"].isna() & temp.notna()
            df.loc[mask, "avg_sitting_pct_source"] = temp[mask]
    df["avg_sitting_pct_source"] = pd.to_numeric(df["avg_sitting_pct_source"], errors="coerce")

    return df


def filter_dataframe(df):
    st.sidebar.header("Global Filters")
    total_placeholder = st.sidebar.empty()

    min_date = df["Date"].min().date() if df["Date"].notna().any() else datetime.today().date()
    max_date = df["Date"].max().date() if df["Date"].notna().any() else datetime.today().date()

    selected_dates = st.sidebar.date_input(
        "Date Range", value=(min_date, max_date),
        min_value=min_date, max_value=max_date
    )
    if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
        start_date, end_date = selected_dates
    else:
        start_date = end_date = min_date

    time_from = st.sidebar.time_input("Survey Start Time From", value=time(0, 0))
    time_to = st.sidebar.time_input("Survey Start Time To", value=time(23, 59))

    surveyors = sorted(df["Remarks1"].dropna().unique().tolist())
    sel_all_s = st.sidebar.checkbox("Select All Surveyors", value=True)
    selected_surveyors = st.sidebar.multiselect(
        "Surveyor Name", options=surveyors,
        default=surveyors if sel_all_s else []
    )

    vehicles = sorted(df["3.Vehicle Type"].dropna().unique().tolist())
    sel_all_v = st.sidebar.checkbox("Select All Vehicle Types", value=True)
    selected_vehicles = st.sidebar.multiselect(
        "Vehicle Type", options=vehicles,
        default=vehicles if sel_all_v else []
    )

    arms = sorted(df["2.Arm details"].dropna().unique().tolist())
    sel_all_a = st.sidebar.checkbox("Select All Arms / Directions", value=True)
    selected_arms = st.sidebar.multiselect(
        "Arm / Direction", options=arms,
        default=arms if sel_all_a else []
    )

    filtered = df[
        (df["Date"].dt.date >= start_date) &
        (df["Date"].dt.date <= end_date)
    ].copy()

    filtered = filtered[
        filtered["start_time"].apply(
            lambda x: x is not None and pd.notna(x) and time_from <= x <= time_to
        )
    ]

    filtered = filtered[filtered["Remarks1"].isin(selected_surveyors)] if selected_surveyors else filtered.iloc[0:0]
    filtered = filtered[filtered["3.Vehicle Type"].isin(selected_vehicles)] if selected_vehicles else filtered.iloc[0:0]
    filtered = filtered[filtered["2.Arm details"].isin(selected_arms)] if selected_arms else filtered.iloc[0:0]

    total_placeholder.metric("Filtered Records", len(filtered))
    return filtered


def make_download_csv(df_in):
    return df_in.to_csv(index=False).encode("utf-8")


# --------------------------------------------------
# FILE UPLOAD / LOAD
# --------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.subheader("📂 Upload Survey File")
uploaded_file = st.sidebar.file_uploader(
    "Upload updated Excel survey file",
    type=["xlsx"],
    help="Upload a new version of the survey results Excel file to refresh the dashboard."
)

if uploaded_file is not None:
    file_bytes = uploaded_file.read()
    file_name = uploaded_file.name
    st.sidebar.success(f"✅ Loaded: {file_name}")
else:
    # Fall back to default file path if no upload
    DEFAULT_FILE = "DC513MH04__DC513MH04_Mumbai_2026-05-13_05_04_30__survey_results.xlsx"
    if os.path.exists(DEFAULT_FILE):
        with open(DEFAULT_FILE, "rb") as f:
            file_bytes = f.read()
        file_name = DEFAULT_FILE
    else:
        st.warning("⚠️ No survey file loaded. Please upload an Excel file using the sidebar.")
        st.stop()

with st.spinner("Loading and processing survey data..."):
    df = process_dataframe(file_bytes)

filtered_df = filter_dataframe(df)

# --------------------------------------------------
# HEADER
# --------------------------------------------------
st.title("Mumbai Traffic Survey Dashboard — EEH (JJ Junction)")
last_updated = datetime.now().strftime("%d %b %Y %H:%M:%S")
st.caption(
    f"Survey location: EEH (JJ Junction), Mumbai | "
    f"File: {file_name} | Last updated: {last_updated}"
)

if "Location" in df.columns and df["Location"].notna().any():
    sample_loc = df["Location"].dropna().astype(str).iloc[0]
    try:
        lat, lon = map(float, sample_loc.split(","))
        with st.expander("Show survey site map"):
            st.map(pd.DataFrame({"lat": [lat], "lon": [lon]}))
    except Exception:
        pass

# --------------------------------------------------
# TABS
# --------------------------------------------------
tabs = st.tabs([
    "📊 Summary",
    "👷 Surveyors",
    "🚗 Vehicles",
    "🗺️ Origins & Destinations",
    "🔍 Individual Surveyor",
    "📋 Surveyor Presence",
    "📄 Raw Data",
])

# --------------------------------------------------
# TAB 1 — SUMMARY
# --------------------------------------------------
with tabs[0]:
    total_surveys = len(filtered_df)
    total_surveyors = filtered_df["Remarks1"].nunique()
    most_common_vehicle = (
        filtered_df["3.Vehicle Type"].mode().iloc[0]
        if not filtered_df["3.Vehicle Type"].dropna().empty else "N/A"
    )
    date_range_label = (
        f"{filtered_df['Date'].min().strftime('%d %b')} – "
        f"{filtered_df['Date'].max().strftime('%d %b %Y')}"
        if not filtered_df["Date"].dropna().empty else "N/A"
    )
    peak_hour = "N/A"
    if filtered_df["start_hour"].notna().any():
        peak = int(filtered_df["start_hour"].value_counts().idxmax())
        peak_hour = f"{peak:02d}:00 – {peak:02d}:59"

    data_quality_score = (
        round(filtered_df["location_clean"].mean() * 100, 1) if len(filtered_df) else 0.0
    )

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total Surveys", total_surveys)
    c2.metric("Active Surveyors", total_surveyors)
    c3.metric("Top Vehicle", most_common_vehicle)
    c4.metric("Date Range", date_range_label)
    c5.metric("Peak Hour", peak_hour)
    c6.metric("Data Quality", f"{data_quality_score}%")

    col_l, col_r = st.columns(2)
    with col_l:
        hourly = (
            filtered_df.groupby("start_hour").size()
            .reset_index(name="Survey Count")
        )
        hourly = hourly[hourly["start_hour"].notna()].sort_values("start_hour")
        fig_h = px.bar(
            hourly, x="start_hour", y="Survey Count",
            title="Hourly Survey Distribution",
            labels={"start_hour": "Hour of Day"},
            color_discrete_sequence=[PRIMARY_COLOR]
        )
        fig_h.update_traces(hovertemplate="Hour %{x}:00 — %{y} surveys<extra></extra>")
        st.plotly_chart(fig_h, use_container_width=True)

    with col_r:
        daily = (
            filtered_df.groupby(filtered_df["Date"].dt.date).size()
            .reset_index(name="Survey Count")
        )
        daily.columns = ["Date", "Survey Count"]
        fig_d = px.line(
            daily, x="Date", y="Survey Count",
            title="Daily Survey Trend", markers=True,
        )
        fig_d.update_traces(
            line_color=PRIMARY_COLOR,
            hovertemplate="Date: %{x}<br>Surveys: %{y}<extra></extra>"
        )
        st.plotly_chart(fig_d, use_container_width=True)


 # --------------------------------------------------
# TAB 2 — SURVEYORS
# --------------------------------------------------
with tabs[1]:
    st.subheader("Surveyor Performance Summary")
    sb = filtered_df[filtered_df["Remarks1"].notna()].copy()
    sb = sb[sb["Remarks1"].astype(str).str.strip() != ""]

    if sb.empty:
        st.info("No surveyor data for the selected filters.")
    else:
        summary = (
            sb.groupby("Remarks1", dropna=False)
            .agg(
                **{
                    "Total Surveys": ("Remarks1", "size"),
                    "Arms Covered": (
                        "2.Arm details",
                        lambda x: ", ".join(sorted(set(x.dropna().astype(str))))
                    ),
                    "Vehicle Types Covered": (
                        "3.Vehicle Type",
                        lambda x: ", ".join(sorted(set(x.dropna().astype(str))))
                    ),
                    "First Entry": (
                        "start_time",
                        lambda x: min(t.strftime("%H:%M:%S") for t in x.dropna()) if len(x.dropna()) else None
                    ),
                    "Last Entry": (
                        "end_time",
                        lambda x: max(t.strftime("%H:%M:%S") for t in x.dropna()) if len(x.dropna()) else None
                    ),
                    "Avg Duration (mins)": ("survey_duration_mins", "mean"),
                    "Data Quality (%)": (
                        "location_clean",
                        lambda x: round(x.mean() * 100, 1) if len(x.dropna()) else 0
                    ),
                }
            )
            .reset_index()
            .rename(columns={"Remarks1": "Surveyor Name"})
            .sort_values(["Total Surveys", "Surveyor Name"], ascending=[False, True])
        )
        summary["Avg Duration (mins)"] = summary["Avg Duration (mins)"].round(1)
        summary["First Entry"] = summary["First Entry"].fillna("-")
        summary["Last Entry"] = summary["Last Entry"].fillna("-")

        st.dataframe(summary, use_container_width=True)

        top_s = summary.iloc[0]["Surveyor Name"]
        summary["Highlight"] = summary["Surveyor Name"].apply(
            lambda x: "Top Performer" if x == top_s else "Others"
        )
        fig_sb = px.bar(
            summary.sort_values("Total Surveys", ascending=True),
            x="Total Surveys", y="Surveyor Name", orientation="h",
            color="Highlight", title="Surveys per Surveyor",
            color_discrete_map={"Top Performer": "#FF7F0E", "Others": PRIMARY_COLOR},
            hover_data=["Arms Covered", "Vehicle Types Covered", "Avg Duration (mins)", "Data Quality (%)"]
        )
        fig_sb.update_layout(showlegend=False)
        st.plotly_chart(fig_sb, use_container_width=True)

    # ── FAULTY SURVEYOR TABLE ──────────────────────────
    st.markdown("---")
    st.subheader("⚠️ Faulty Surveyor Entries")
    st.caption(
        "Flags entries where the gap between a surveyor's consecutive entries "
        "is less than the threshold — may indicate rushed or fabricated surveys."
    )

    fc1, fc2, fc3 = st.columns([1, 1, 4])
    with fc1:
        thresh_min = st.number_input(
            "Threshold (min)", min_value=0, max_value=10, value=1, step=1,
            key="faulty_min"
        )
    with fc2:
        thresh_sec = st.number_input(
            "Threshold (sec)", min_value=0, max_value=59, value=0, step=5,
            key="faulty_sec"
        )
    threshold_total_sec = thresh_min * 60 + thresh_sec
    threshold_mins = threshold_total_sec / 60

    with fc3:
        st.markdown(
            f"<div style='padding-top:28px;color:#888;font-size:13px;'>"
            f"Flagging consecutive entries with gap under "
            f"<b>{thresh_min}m {thresh_sec:02d}s</b> "
            f"({threshold_total_sec} sec)</div>",
            unsafe_allow_html=True
        )

    # Compute gap between consecutive entries per surveyor per day
    gap_df = filtered_df[filtered_df["Remarks1"].notna()].copy()
    gap_df = gap_df[gap_df["start_time"].notna()]

    def to_seconds(t):
        return t.hour * 3600 + t.minute * 60 + t.second if t is not None else None

    gap_df["start_sec"] = gap_df["start_time"].apply(to_seconds)
    gap_df["end_sec"] = gap_df["end_time"].apply(to_seconds)
    gap_df = gap_df.sort_values(["Remarks1", "Date", "start_sec"])

    # Shift end_time of previous entry per surveyor per day
    gap_df["prev_end_sec"] = gap_df.groupby(["Remarks1", "Date"])["end_sec"].shift(1)

    # Gap = current entry start − previous entry end (true idle time)
    gap_df["entry_gap_sec"] = gap_df["start_sec"] - gap_df["prev_end_sec"]
    gap_df["entry_gap_mins"] = gap_df["entry_gap_sec"] / 60
 
    faulty_base = gap_df[
        gap_df["entry_gap_sec"].notna() &
        (gap_df["entry_gap_sec"] > 0) &
        (gap_df["entry_gap_sec"] < threshold_total_sec)
    ].copy()

    if faulty_base.empty:
        st.success(
            f"✅ No consecutive entries with gap under "
            f"{thresh_min}m {thresh_sec:02d}s in current filters."
        )
    else:
        # KPI strip
        fk1, fk2, fk3, fk4 = st.columns(4)
        fk1.metric("Total Flagged Entries", len(faulty_base))
        fk2.metric("Surveyors Flagged", faulty_base["Remarks1"].nunique())
        fk3.metric(
            "Shortest Gap",
            f"{int(round(faulty_base['entry_gap_sec'].min()))} sec"
        )
        fk4.metric(
            "Most Flagged",
            faulty_base["Remarks1"].value_counts().idxmax()
        )

        # Summary per surveyor
        faulty_summary = (
            faulty_base.groupby("Remarks1")
            .agg(
                **{
                    "Faulty Entries": ("Remarks1", "size"),
                    "Shortest Gap (sec)": ("entry_gap_sec", lambda x: int(round(x.min()))),
                    "Avg Gap (sec)": ("entry_gap_sec", lambda x: int(round(x.mean()))),
                }
            )
            .reset_index()
            .rename(columns={"Remarks1": "Surveyor"})
            .sort_values("Faulty Entries", ascending=False)
        )
        st.markdown("#### Summary by Surveyor")
        st.dataframe(faulty_summary, use_container_width=True)

        # Detail table
        faulty_display = faulty_base[[
            "Remarks1", "Date", "start_time", "end_time",
            "entry_gap_sec", "entry_gap_mins",
            "3.Vehicle Type", "2.Arm details",
            "unified_origin", "unified_destination"
        ]].copy()

        faulty_display["Gap (sec)"] = faulty_display["entry_gap_sec"].round(0).astype(int)
        faulty_display["Gap (m:ss)"] = faulty_display["entry_gap_mins"].apply(
            lambda x: f"{int(x)}m {int(round((x % 1) * 60)):02d}s" if pd.notna(x) else "-"
        )
        faulty_display["Date"] = pd.to_datetime(faulty_display["Date"]).dt.strftime("%d-%m-%Y")
        faulty_display["start_time"] = faulty_display["start_time"].apply(
            lambda x: x.strftime("%H:%M:%S") if pd.notna(x) and x is not None else "-"
        )
        faulty_display["end_time"] = faulty_display["end_time"].apply(
            lambda x: x.strftime("%H:%M:%S") if pd.notna(x) and x is not None else "-"
        )
        faulty_display = faulty_display.rename(columns={
            "Remarks1": "Surveyor",
            "3.Vehicle Type": "Vehicle Type",
            "2.Arm details": "Arm",
            "unified_origin": "Origin",
            "unified_destination": "Destination",
        }).drop(columns=["entry_gap_sec", "entry_gap_mins"])

        faulty_display = faulty_display[[
            "Surveyor", "Date", "start_time", "end_time",
            "Gap (sec)", "Gap (m:ss)",
            "Vehicle Type", "Arm", "Origin", "Destination"
        ]].sort_values(["Surveyor", "Gap (sec)"])

        st.markdown("#### All Flagged Entries (Detail)")
        st.dataframe(faulty_display, use_container_width=True)

        st.download_button(
            label="⬇️ Download Flagged Entries as CSV",
            data=faulty_display.to_csv(index=False).encode("utf-8"),
            file_name="faulty_surveyor_entries.csv",
            mime="text/csv"
        )


# --------------------------------------------------
# TAB 3 — VEHICLES
# --------------------------------------------------
with tabs[2]:
    st.subheader("Vehicle Type Analysis")

    vs = (
        filtered_df.groupby("3.Vehicle Type")
        .agg(
            Count=("3.Vehicle Type", "size"),
            Avg_Occupancy=("unified_occupancy", "mean"),
            Avg_Sitting_Pct=("avg_sitting_pct_source", "mean"),
        )
        .reset_index()
        .sort_values("Count", ascending=False)
    )
    total_vc = vs["Count"].sum()
    vs["% Share"] = ((vs["Count"] / total_vc) * 100).round(1) if total_vc > 0 else 0
    vs["Avg_Occupancy"] = vs["Avg_Occupancy"].round(1)
    vs["Avg_Sitting_Pct"] = vs["Avg_Sitting_Pct"].round(1)

    col1, col2 = st.columns(2)
    with col1:
        if not vs.empty:
            fig_pie = px.pie(
                vs, names="3.Vehicle Type", values="Count",
                title="Survey Count by Vehicle Type",
                color_discrete_sequence=px.colors.sequential.Blues_r
            )
            fig_pie.update_traces(
                textinfo="percent+label",
                hovertemplate="%{label}<br>Count: %{value}<br>Share: %{percent}<extra></extra>"
            )
            st.plotly_chart(fig_pie, use_container_width=True)

    with col2:
        if not vs.empty:
            fig_vb = px.bar(
                vs, x="3.Vehicle Type", y="Count",
                title="Survey Count by Vehicle Type",
                labels={"3.Vehicle Type": "Vehicle Type", "Count": "Surveys"},
                color_discrete_sequence=[PRIMARY_COLOR]
            )
            fig_vb.update_layout(xaxis_tickangle=-30)
            st.plotly_chart(fig_vb, use_container_width=True)

    st.markdown("### Vehicle Summary Table")
    st.dataframe(
        vs.rename(columns={
            "3.Vehicle Type": "Vehicle Type",
            "Avg_Occupancy": "Avg Occupancy",
            "Avg_Sitting_Pct": "Avg Sitting %"
        }),
        use_container_width=True
    )

    st.markdown("### Vehicle Breakdown per Surveyor")
    sv = filtered_df.groupby(["Remarks1", "3.Vehicle Type"]).size().reset_index(name="Count")
    if not sv.empty:
        fig_sv = px.bar(
            sv, x="Remarks1", y="Count", color="3.Vehicle Type",
            title="Vehicle Type per Surveyor", barmode="stack",
            labels={"Remarks1": "Surveyor", "3.Vehicle Type": "Vehicle Type"}
        )
        fig_sv.update_layout(xaxis_tickangle=-30)
        st.plotly_chart(fig_sv, use_container_width=True)

    st.markdown("### Vehicle Breakdown per Arm / Direction")
    av = filtered_df.groupby(["2.Arm details", "3.Vehicle Type"]).size().reset_index(name="Count")
    if not av.empty:
        fig_av = px.bar(
            av, x="2.Arm details", y="Count", color="3.Vehicle Type",
            title="Vehicle Type per Arm / Direction", barmode="stack",
            labels={"2.Arm details": "Arm / Direction", "3.Vehicle Type": "Vehicle Type"}
        )
        fig_av.update_layout(xaxis_tickangle=-20)
        st.plotly_chart(fig_av, use_container_width=True)


# --------------------------------------------------
# TAB 4 — ORIGINS & DESTINATIONS
# --------------------------------------------------
with tabs[3]:
    st.subheader("Origins & Destinations")

    od = filtered_df.copy()

    # Use raw_origin/raw_destination as fallback if unified is empty
    def best_location(unified, raw):
        if pd.notna(unified) and str(unified).strip() not in ("", "-", "None", "nan"):
            return str(unified).strip().title()
        if pd.notna(raw) and str(raw).strip() not in ("", "-", "None", "nan"):
            return str(raw).strip().title()
        return pd.NA

    od["display_origin"] = od.apply(
        lambda r: best_location(r["unified_origin"], r["raw_origin"]), axis=1
    )
    od["display_destination"] = od.apply(
        lambda r: best_location(r["unified_destination"], r["raw_destination"]), axis=1
    )

    od_valid = od.dropna(subset=["display_origin", "display_destination"]).copy()

    st.markdown(
        f"**{len(od_valid):,}** records have origin & destination data "
        f"out of **{len(od):,}** filtered records."
    )

    # Top O-D pairs
    st.markdown("### Top O-D Pairs")
    od_pairs = (
        od_valid.groupby(["display_origin", "display_destination"])
        .size()
        .reset_index(name="Trip Count")
        .sort_values("Trip Count", ascending=False)
        .head(20)
    )
    if not od_pairs.empty:
        od_pairs["Origin → Destination"] = (
            od_pairs["display_origin"] + " → " + od_pairs["display_destination"]
        )
        col_t, col_c = st.columns([2, 3])
        with col_t:
            st.dataframe(od_pairs[["Origin → Destination", "Trip Count"]], use_container_width=True)
        with col_c:
            fig_od = px.bar(
                od_pairs.sort_values("Trip Count", ascending=True).head(15),
                x="Trip Count", y="Origin → Destination", orientation="h",
                title="Top 15 O-D Pairs",
                color_discrete_sequence=[PRIMARY_COLOR]
            )
            fig_od.update_traces(hovertemplate="%{y}<br>Trips: %{x}<extra></extra>")
            st.plotly_chart(fig_od, use_container_width=True)
    else:
        st.info("No O-D pair data available for the current filters.")

    # Top Origins
    st.markdown("### Top Origins")
    top_orig = (
        od_valid["display_origin"].dropna()
        .value_counts().head(15).reset_index()
    )
    top_orig.columns = ["Origin", "Count"]
    if not top_orig.empty:
        fig_orig = px.bar(
            top_orig.sort_values("Count", ascending=True),
            x="Count", y="Origin", orientation="h",
            title="Top 15 Origins",
            labels={"Count": "Frequency"},
            color_discrete_sequence=[PRIMARY_COLOR]
        )
        fig_orig.update_traces(hovertemplate="Origin: %{y}<br>Count: %{x}<extra></extra>")
        st.plotly_chart(fig_orig, use_container_width=True)
    else:
        st.info("No origin data available.")

    # Top Destinations
    st.markdown("### Top Destinations")
    top_dest = (
        od_valid["display_destination"].dropna()
        .value_counts().head(15).reset_index()
    )
    top_dest.columns = ["Destination", "Count"]
    if not top_dest.empty:
        fig_dest = px.bar(
            top_dest.sort_values("Count", ascending=True),
            x="Count", y="Destination", orientation="h",
            title="Top 15 Destinations",
            labels={"Count": "Frequency"},
            color_discrete_sequence=["#1F77B4"]
        )
        fig_dest.update_traces(hovertemplate="Destination: %{y}<br>Count: %{x}<extra></extra>")
        st.plotly_chart(fig_dest, use_container_width=True)
    else:
        st.info("No destination data available.")

    # Data Quality Report
    st.markdown("### 🚩 Location Data Quality Report")
    bad = filtered_df[filtered_df["bad_location_entry"] == True].copy()
    if bad.empty:
        st.success("No location data issues found in the current filtered data.")
    else:
        bad_pct = round(len(bad) / len(filtered_df) * 100, 1) if len(filtered_df) else 0
        st.warning(
            f"**{len(bad):,}** records ({bad_pct}%) have suspicious or unresolved "
            "origin/destination entries."
        )
        bad_display = bad[[
            "Date", "Remarks1", "3.Vehicle Type",
            "raw_origin", "raw_destination", "location_issue_type"
        ]].copy()
        bad_display["Date"] = pd.to_datetime(bad_display["Date"]).dt.strftime("%d-%m-%Y")
        bad_display = bad_display.rename(columns={
            "Remarks1": "Surveyor",
            "3.Vehicle Type": "Vehicle Type",
            "raw_origin": "Raw Origin",
            "raw_destination": "Raw Destination",
            "location_issue_type": "Issue"
        })
        st.dataframe(bad_display, use_container_width=True)

        st.markdown("#### Bad Entries per Surveyor")
        bad_by_s = (
            bad.groupby("Remarks1").size()
            .reset_index(name="Bad Entries")
            .sort_values("Bad Entries", ascending=False)
            .rename(columns={"Remarks1": "Surveyor"})
        )
        st.dataframe(bad_by_s, use_container_width=True)


# --------------------------------------------------
# TAB 5 — INDIVIDUAL SURVEYOR
# --------------------------------------------------
with tabs[4]:
    st.subheader("Individual Surveyor Deep Dive")

    surveyor_list = sorted(df["Remarks1"].dropna().unique().tolist())
    selected_surveyor = st.selectbox(
        "Select a Surveyor", options=surveyor_list,
        help="Shows all data for this surveyor regardless of global filters."
    )

    if selected_surveyor:
        ind = df[df["Remarks1"] == selected_surveyor].copy()

        # Apply date/time filter from global sidebar to keep consistency
        # but NOT the surveyor filter (we want full view of this surveyor)
        si1, si2, si3, si4, si5 = st.columns(5)
        si1.metric("Total Surveys", len(ind))
        si2.metric(
            "Date Range",
            f"{ind['Date'].min().strftime('%d %b')} – {ind['Date'].max().strftime('%d %b %Y')}"
            if ind["Date"].notna().any() else "N/A"
        )
        si3.metric(
            "Vehicle Types",
            ind["3.Vehicle Type"].dropna().nunique()
        )
        si4.metric(
            "Arms Covered",
            ind["2.Arm details"].dropna().nunique()
        )
        data_q = round(ind["location_clean"].mean() * 100, 1) if len(ind) else 0
        si5.metric("Data Quality", f"{data_q}%")

        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown("#### Daily Survey Count")
            ind_daily = (
                ind.groupby(ind["Date"].dt.date).size()
                .reset_index(name="Count")
            )
            ind_daily.columns = ["Date", "Count"]
            fig_ind_d = px.bar(
                ind_daily, x="Date", y="Count",
                title=f"Daily Surveys — {selected_surveyor}",
                color_discrete_sequence=[PRIMARY_COLOR]
            )
            st.plotly_chart(fig_ind_d, use_container_width=True)

        with col_b:
            st.markdown("#### Vehicle Type Distribution")
            ind_veh = ind["3.Vehicle Type"].value_counts().reset_index()
            ind_veh.columns = ["Vehicle Type", "Count"]
            fig_ind_v = px.pie(
                ind_veh, names="Vehicle Type", values="Count",
                title=f"Vehicle Types — {selected_surveyor}",
                color_discrete_sequence=px.colors.sequential.Blues_r
            )
            st.plotly_chart(fig_ind_v, use_container_width=True)

        st.markdown("#### Hourly Survey Distribution")
        ind_hourly = (
            ind.groupby("start_hour").size()
            .reset_index(name="Count")
        )
        ind_hourly = ind_hourly[ind_hourly["start_hour"].notna()].sort_values("start_hour")
        fig_ind_h = px.bar(
            ind_hourly, x="start_hour", y="Count",
            title=f"Hourly Distribution — {selected_surveyor}",
            labels={"start_hour": "Hour of Day"},
            color_discrete_sequence=[PRIMARY_COLOR]
        )
        st.plotly_chart(fig_ind_h, use_container_width=True)

        st.markdown("#### Top O-D Pairs")
        ind_od = ind.copy()
        ind_od["display_origin"] = ind_od.apply(
            lambda r: best_location(r["unified_origin"], r["raw_origin"]), axis=1
        )
        ind_od["display_destination"] = ind_od.apply(
            lambda r: best_location(r["unified_destination"], r["raw_destination"]), axis=1
        )
        ind_pairs = (
            ind_od.dropna(subset=["display_origin", "display_destination"])
            .groupby(["display_origin", "display_destination"])
            .size()
            .reset_index(name="Trip Count")
            .sort_values("Trip Count", ascending=False)
            .head(15)
        )
        if not ind_pairs.empty:
            ind_pairs["Route"] = ind_pairs["display_origin"] + " → " + ind_pairs["display_destination"]
            st.dataframe(ind_pairs[["Route", "Trip Count"]], use_container_width=True)
        else:
            st.info("No O-D data available for this surveyor.")

        st.markdown("#### All Records for This Surveyor")
        ind_display = ind[[
            "Date", "start_time", "end_time", "3.Vehicle Type",
            "2.Arm details", "unified_origin", "unified_destination",
            "unified_occupancy", "survey_duration_mins"
        ]].copy()
        ind_display["Date"] = pd.to_datetime(ind_display["Date"]).dt.strftime("%d-%m-%Y")
        ind_display["start_time"] = ind_display["start_time"].apply(
            lambda x: x.strftime("%H:%M:%S") if pd.notna(x) and x is not None else "-"
        )
        ind_display["end_time"] = ind_display["end_time"].apply(
            lambda x: x.strftime("%H:%M:%S") if pd.notna(x) and x is not None else "-"
        )
        ind_display["survey_duration_mins"] = ind_display["survey_duration_mins"].round(1)
        ind_display = ind_display.rename(columns={
            "3.Vehicle Type": "Vehicle Type",
            "2.Arm details": "Arm",
            "unified_origin": "Origin",
            "unified_destination": "Destination",
            "unified_occupancy": "Occupancy",
            "survey_duration_mins": "Duration (mins)"
        })
        st.dataframe(ind_display, use_container_width=True)
        st.download_button(
            label=f"Download {selected_surveyor}'s Data as CSV",
            data=make_download_csv(ind_display),
            file_name=f"surveyor_{selected_surveyor.replace(' ', '_')}_data.csv",
            mime="text/csv"
        )


# --------------------------------------------------
# TAB 6 — SURVEYOR PRESENCE
# --------------------------------------------------
with tabs[5]:
    st.subheader("Surveyor Presence")

    pres_base = df[
        df["Date"].notna() &
        df["Remarks1"].notna() &
        df["start_time"].notna() &
        df["end_time"].notna()
    ].copy()
    pres_base = pres_base[pres_base["Remarks1"].astype(str).str.strip() != ""]

    if pres_base.empty:
        st.info("No surveyor presence data available.")
    else:
        records = []
        for _, row in pres_base.iterrows():
            s, e = row["start_time"], row["end_time"]
            if pd.isna(s) or pd.isna(e):
                continue
            if (e.hour, e.minute) < (s.hour, s.minute):
                continue
            date_label = pd.to_datetime(row["Date"]).strftime("%d-%m-%Y")
            for hr in range(s.hour, e.hour + 1):
                records.append({
                    "Surveyor Name": row["Remarks1"],
                    "Date Label": date_label,
                    "Hour": hr,
                    "Half": "First Half" if hr < 13 else "Second Half",
                })

        pres_df = pd.DataFrame(records)

        if pres_df.empty:
            st.info("No hourly presence data could be generated.")
        else:
            half_pres = (
                pres_df.groupby(["Surveyor Name", "Date Label", "Half"])
                .size().reset_index(name="n")
            )
            half_pres["Present"] = "Present"
            pivot = half_pres.pivot_table(
                index="Surveyor Name", columns=["Date Label", "Half"],
                values="Present", aggfunc="first", fill_value=""
            ).sort_index(axis=1).reset_index()

            st.markdown("### Surveyor Presence by Date and Half-Day")
            st.dataframe(pivot, use_container_width=True)

            hourly_s = (
                pres_df.groupby(["Date Label", "Hour"])
                .agg(
                    **{
                        "Surveyors Present": ("Surveyor Name", pd.Series.nunique),
                        "Surveyor Names": (
                            "Surveyor Name",
                            lambda x: ", ".join(sorted(set(x.dropna().astype(str))))
                        ),
                    }
                )
                .reset_index()
                .sort_values(["Date Label", "Hour"])
            )
            hourly_s["Hour Label"] = hourly_s["Hour"].apply(
                lambda x: f"{int(x):02d}:00 – {int(x):02d}:59"
            )
            st.markdown("### Hourly Presence Summary (All Data)")
            st.dataframe(
                hourly_s[["Date Label", "Hour Label", "Surveyors Present", "Surveyor Names"]],
                use_container_width=True
            )

    st.markdown("### Filtered Hourly Presence")
    fpb = filtered_df[
        filtered_df["Date"].notna() &
        filtered_df["Remarks1"].notna() &
        filtered_df["start_time"].notna()
    ].copy()
    fpb = fpb[fpb["Remarks1"].astype(str).str.strip() != ""]

    if fpb.empty:
        st.info("No presence data for the selected filters.")
    else:
        fpb["Date Label"] = pd.to_datetime(fpb["Date"]).dt.strftime("%d-%m-%Y")
        fpb["Hour"] = fpb["start_time"].apply(
            lambda x: x.hour if pd.notna(x) and x is not None else None
        )
        fph = (
            fpb.groupby(["Date Label", "Hour"])
            .agg(
                **{
                    "Surveyors Present": ("Remarks1", pd.Series.nunique),
                    "Surveyor Names": (
                        "Remarks1",
                        lambda x: ", ".join(sorted(set(x.dropna().astype(str))))
                    ),
                    "Total Records": ("Remarks1", "size"),
                }
            )
            .reset_index()
            .sort_values(["Date Label", "Hour"])
        )
        fph["Hour Label"] = fph["Hour"].apply(
            lambda x: f"{int(x):02d}:00 – {int(x):02d}:59" if pd.notna(x) else ""
        )
        st.dataframe(
            fph[["Date Label", "Hour Label", "Surveyors Present", "Surveyor Names", "Total Records"]],
            use_container_width=True
        )


# --------------------------------------------------
# TAB 7 — RAW DATA
# --------------------------------------------------
with tabs[6]:
    st.subheader("Filtered Raw Data")

    raw = filtered_df[[
        "Date", "start_time", "end_time", "Remarks1",
        "3.Vehicle Type", "2.Arm details",
        "unified_origin", "unified_destination",
        "unified_occupancy", "survey_duration_mins"
    ]].copy()

    raw["Date"] = pd.to_datetime(raw["Date"]).dt.strftime("%d-%m-%Y")
    raw["start_time"] = raw["start_time"].apply(
        lambda x: x.strftime("%H:%M:%S") if pd.notna(x) and x is not None else "-"
    )
    raw["end_time"] = raw["end_time"].apply(
        lambda x: x.strftime("%H:%M:%S") if pd.notna(x) and x is not None else "-"
    )
    raw["survey_duration_mins"] = raw["survey_duration_mins"].round(1)
    raw = raw.rename(columns={
        "Remarks1": "Surveyor",
        "3.Vehicle Type": "Vehicle Type",
        "2.Arm details": "Arm",
        "unified_origin": "Origin",
        "unified_destination": "Destination",
        "unified_occupancy": "Occupancy",
        "survey_duration_mins": "Duration (mins)"
    })

    st.dataframe(raw, use_container_width=True)
    st.download_button(
        label="Download Filtered Data as CSV",
        data=make_download_csv(raw),
        file_name="filtered_survey_data.csv",
        mime="text/csv"
    )

# --------------------------------------------------
# FOOTER
# --------------------------------------------------
st.markdown("---")
st.caption(f"File: {file_name} | Dashboard built for DC513MH04 survey — EEH (JJ Junction), Mumbai")
