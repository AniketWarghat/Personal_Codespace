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

import io
import os
from datetime import datetime, time

import pandas as pd
import plotly.express as px
import streamlit as st
from rapidfuzz import fuzz, process

# --------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------
st.set_page_config(
    page_title="Mumbai Traffic Survey Dashboard — EEH (JJ Junction)",
    layout="wide"
)

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

# FIXED: Use exact column names from the Excel file
VEHICLE_MAPPING = {
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

BUS_OCC_COLS = [
    "3c5.Mention the Occupancy (In Percentage)",
    "3d5.Mention the Occupancy (In Percentage)",
    "3e5.Mention the Occupancy (In Percentage)",
    "3f5.Mention the Occupancy (In Percentage)",
    "3g5.Mention the Occupancy (In Percentage)",
    "3h5.Mention the Occupancy (In Percentage)",
]


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


def get_od(row):
    vt = row.get("3.Vehicle Type", None)
    if pd.isna(vt):
        return pd.Series([None, None, None])
    vt_clean = " ".join(str(vt).strip().split())
    cols = VEHICLE_MAPPING.get(vt_clean)
    if not cols:
        for k, v in VEHICLE_MAPPING.items():
            if " ".join(k.strip().split()).lower() == vt_clean.lower():
                cols = v
                break
    if not cols:
        return pd.Series([None, None, None])
    origin_col, dest_col, occ_col = cols
    origin = row.get(origin_col, None)
    destination = row.get(dest_col, None)
    occupancy = row.get(occ_col, None)
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

    # Surveyor name
    if safe_col(df, "Remarks1"):
        df["Remarks1"] = (
            df["Remarks1"].astype(str)
            .str.strip()
            .replace({"nan": pd.NA, "None": pd.NA, "": pd.NA})
        )
        df["Remarks1"] = df["Remarks1"].str.title()

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
    df[["raw_origin", "raw_destination", "unified_occupancy"]] = df.apply(get_od, axis=1)
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
    for col in BUS_OCC_COLS:
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
