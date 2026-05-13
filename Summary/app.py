import io
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
FILE_NAME = "Input/DC513MH04 _DC513MH04 Mumbai_2026-05-13 11_03_12__survey_results.xlsx"
SHEET_NAME = "Survey Results"

# --------------------------------------------------
# HELPERS
# --------------------------------------------------
CANONICAL_LOCATIONS = [
    "Bandra West", "Bandra East", "Bandra Terminus", "Bandra Kurla Complex",
    "CSMT", "Churchgate", "Dadar TT", "Dadar East", "Dadar West",
    "Andheri", "Andheri East", "Andheri West", "Borivali", "Malad",
    "Worli", "Worli Depot", "Lower Parel", "Mahim", "Sion", "Kurla",
    "Dharavi", "Chembur", "Masjid Bandar", "Nagpada", "Byculla",
    "Colaba", "Navy Nagar", "Gateway of India", "Marine Drive",
    "Mohammad Ali Road", "JJ Hospital", "JJ Flyover", "Mantralaya",
    "Wadala", "Antop Hill", "Mazgaon", "Mumbai Central", "Santacruz",
    "Juhu", "Vile Parle", "Goregaon", "Thane", "Navi Mumbai", "Panvel",
    "Pune", "Nashik", "Alibaug", "Bhindi Bazaar", "Crawford Market",
    "Zaveri Bazaar", "Mahalaxmi", "Grant Road", "Chinchpokli", "Parel",
    "Lal Baug", "Shivaji Nagar", "Pratiksha Nagar", "Antop Hill Bus Stop",
    "Bhaikhala", "Dongri", "Nagpada Chauki", "Pydhonie", "Mazgaon Court"
]

INVALID_LOCATION_VALUES = {
    "-", "none", "not mentioned", "not mention", "reserved", "null", "na", ""
}

BUS_TYPES = {
    "Mini Bus - Govt",
    "Mini Bus - Private",
    "City Bus - Govt (BEST)",
    "City Bus - Private (Chalo, City flow)",
    "City Bus - Private (Chalo,Cityflow)",
    "Inter city bus - Govt",
    "Inter city bus - Private",
}

VEHICLE_MAPPING = {
    "Car": ("3a4.Trip Origin", "3a5.Trip Dest", "3a1.Occupancy (Incl. driver)"),
    "Taxi/Cab": ("3b4.Trip Origin", "3b5.Trip Dest", "3b1.Occupancy (Incl. driver)"),
    "Mini Bus - Govt": ("3c3.Trip Origin", "3c4.Trip Dest", "3c5.Mention the Occupancy (%)"),
    "City Bus - Govt (BEST)": ("3d3.Trip Origin", "3d4.Trip Dest", "3d5.Mention the Occupancy (%)"),
    "City Bus - Private (Chalo,Cityflow)": ("3e3.Trip Origin", "3e4.Trip Dest", "3e5.Mention the Occupancy (%)"),
    "City Bus - Private (Chalo, City flow)": ("3e3.Trip Origin", "3e4.Trip Dest", "3e5.Mention the Occupancy (%)"),
    "Inter city bus - Govt": ("3f3.Trip Origin", "3f4.Trip Dest", "3f5.Mention the Occupancy (%)"),
    "Inter city bus - Private": ("3g3.Trip Origin", "3g4.Trip Dest", "3g5.Mention the Occupancy (%)"),
    "Mini Bus - Private": ("3h3.Trip Origin", "3h4.Trip Dest", "3h5.Mention the Occupancy (%)"),
    "Others": ("3i3.Trip Origin", "3i4.Trip Dest", "3i2.Occupancy (Incl. Driver)")
}


def safe_col(df, col):
    return col in df.columns


def parse_time_column(series):
    parsed = pd.to_datetime(series.astype(str), format="%H:%M:%S", errors="coerce")
    return parsed.dt.time


def time_to_minutes(t):
    if pd.isna(t) or t is None:
        return None
    return t.hour * 60 + t.minute + t.second / 60


def timedelta_to_minutes(td):
    if pd.isna(td):
        return None
    return td.total_seconds() / 60


def normalize_text(value):
    if pd.isna(value):
        return None
    value = str(value).strip()
    if not value:
        return None
    return value


def is_suspicious_location(value):
    if pd.isna(value):
        return True
    raw = str(value).strip()
    low = raw.lower()

    if low in INVALID_LOCATION_VALUES:
        return True
    if len(raw) < 3:
        return True
    if len(raw) == 1:
        return True
    if raw.isnumeric():
        return True
    if raw.replace(".", "", 1).isdigit():
        return True
    return False


def fuzzy_normalize_location(value, canonical_list, threshold=80):
    if pd.isna(value):
        return None, False, "Missing"
    raw = str(value).strip()
    if not raw:
        return None, False, "Blank"
    if raw.lower() in INVALID_LOCATION_VALUES:
        return raw, False, "Invalid placeholder"
    if len(raw) < 3:
        return raw, False, "Too short"
    if raw.isnumeric():
        return raw, False, "Numeric value"

    match = process.extractOne(
        raw,
        canonical_list,
        scorer=fuzz.WRatio
    )

    if match and match[1] >= threshold:
        return match[0], True, None

    return raw, False, "No reliable fuzzy match"


def get_od(row):
    vt = row.get("3.Vehicle Type", None)
    if pd.isna(vt):
        return pd.Series([None, None, None])

    vt = " ".join(str(vt).strip().split())

    cols = VEHICLE_MAPPING.get(vt)

    if not cols:
        for k, v in VEHICLE_MAPPING.items():
            if " ".join(k.strip().split()).lower() == vt.lower():
                cols = v
                break

    if not cols:
        return pd.Series([None, None, None])

    origin_col, dest_col, occ_col = cols
    origin = row.get(origin_col, None)
    destination = row.get(dest_col, None)
    occupancy = row.get(occ_col, None)

    return pd.Series([origin, destination, occupancy])


@st.cache_data(show_spinner=False)
def load_and_process_data():
    df = pd.read_excel(FILE_NAME, sheet_name=SHEET_NAME, engine="openpyxl")

    # Clean surveyor names
    if safe_col(df, "Remarks1"):
        df["Remarks1"] = df["Remarks1"].astype(str).str.strip()
        df["Remarks1"] = df["Remarks1"].replace({"nan": pd.NA, "None": pd.NA})
        df["Remarks1"] = df["Remarks1"].str.title()

    # Parse dates
    if safe_col(df, "Date"):
        df["Date"] = pd.to_datetime(df["Date"], format="%d/%m/%Y", errors="coerce")

    # Parse times
    if safe_col(df, "start_time"):
        df["start_time"] = parse_time_column(df["start_time"])
    if safe_col(df, "end_time"):
        df["end_time"] = parse_time_column(df["end_time"])

    # Compute duration
    def compute_duration(row):
        stime = row.get("start_time")
        etime = row.get("end_time")
        if stime is None or etime is None or pd.isna(stime) or pd.isna(etime):
            return pd.NaT
        start_dt = datetime.combine(datetime.today(), stime)
        end_dt = datetime.combine(datetime.today(), etime)
        if end_dt < start_dt:
            return pd.NaT
        return end_dt - start_dt

    df["survey_duration"] = df.apply(compute_duration, axis=1)
    df["survey_duration_mins"] = df["survey_duration"].apply(timedelta_to_minutes)

    # Unified origin / destination / occupancy
    df[["raw_origin", "raw_destination", "unified_occupancy"]] = df.apply(get_od, axis=1)
    df["raw_origin"] = df["raw_origin"].apply(lambda x: str(x).strip() if pd.notna(x) else x)
    df["raw_destination"] = df["raw_destination"].apply(lambda x: str(x).strip() if pd.notna(x) else x)

    # Normalize occupancy if possible
        # Normalize occupancy if possible
    df["unified_occupancy"] = (
        df["unified_occupancy"]
        .astype(str)
        .str.replace("%", "", regex=False)
        .str.strip()
    )
    df["unified_occupancy"] = pd.to_numeric(df["unified_occupancy"], errors="coerce")

    # Location normalization

    # Location normalization
    origin_results = df["raw_origin"].apply(lambda x: fuzzy_normalize_location(x, CANONICAL_LOCATIONS, threshold=80))
    dest_results = df["raw_destination"].apply(lambda x: fuzzy_normalize_location(x, CANONICAL_LOCATIONS, threshold=80))

    df["unified_origin"] = origin_results.apply(lambda x: x[0])
    df["origin_clean"] = origin_results.apply(lambda x: x[1])
    df["origin_issue"] = origin_results.apply(lambda x: x[2])

    df["unified_destination"] = dest_results.apply(lambda x: x[0])
    df["destination_clean"] = dest_results.apply(lambda x: x[1])
    df["destination_issue"] = dest_results.apply(lambda x: x[2])

    df["unified_origin"] = (
    df["unified_origin"]
    .apply(lambda x: x.strip() if isinstance(x, str) else x)
    .replace("-", pd.NA)
    .replace("", pd.NA)
    .replace("None", pd.NA)
    )

    df["unified_destination"] = (
    df["unified_destination"]
    .apply(lambda x: x.strip() if isinstance(x, str) else x)
    .replace("-", pd.NA)
    .replace("", pd.NA)
    .replace("None", pd.NA)
    )

    df["unified_origin"] = df["unified_origin"].apply(lambda x: x.title() if isinstance(x, str) else x)
    df["unified_destination"] = df["unified_destination"].apply(lambda x: x.title() if isinstance(x, str) else x)

    df["location_clean"] = df["origin_clean"] & df["destination_clean"]
    df["bad_location_entry"] = ~df["location_clean"]

    def derive_issue_type(row):
        issues = []
        if not row.get("origin_clean", False):
            issues.append(f"Origin: {row.get('origin_issue', 'Issue')}")
        if not row.get("destination_clean", False):
            issues.append(f"Destination: {row.get('destination_issue', 'Issue')}")
        return " | ".join(issues) if issues else None

    df["location_issue_type"] = df.apply(derive_issue_type, axis=1)

    # Hour extraction
    df["start_hour"] = df["start_time"].apply(lambda x: x.hour if pd.notna(x) and x is not None else None)

        # Avg sitting % / source occupancy for vehicle summary
    df["avg_sitting_pct_source"] = pd.NA

    bus_occ_cols = [
        "3c5.Mention the Occupancy (%)",
        "3d5.Mention the Occupancy (%)",
        "3e5.Mention the Occupancy (%)",
        "3f5.Mention the Occupancy (%)",
        "3g5.Mention the Occupancy (%)",
        "3h5.Mention the Occupancy (%)"
    ]

    for col in bus_occ_cols:
        if safe_col(df, col):
            temp = (
                df[col]
                .astype(str)
                .str.replace("%", "", regex=False)
                .str.strip()
            )
            temp = pd.to_numeric(temp, errors="coerce")
            mask = df["avg_sitting_pct_source"].isna() & temp.notna()
            df.loc[mask, "avg_sitting_pct_source"] = temp[mask]

    # fallback from generic Sitting column if available
    if safe_col(df, "Sitting"):
        sitting_clean = pd.to_numeric(df["Sitting"], errors="coerce")
        mask = df["avg_sitting_pct_source"].isna() & sitting_clean.notna()
        df.loc[mask, "avg_sitting_pct_source"] = sitting_clean[mask]

    df["avg_sitting_pct_source"] = pd.to_numeric(df["avg_sitting_pct_source"], errors="coerce")

    return df


def filter_dataframe(df):
    st.sidebar.header("Global Filters")

    total_records_placeholder = st.sidebar.empty()

    min_date = df["Date"].min().date() if df["Date"].notna().any() else datetime.today().date()
    max_date = df["Date"].max().date() if df["Date"].notna().any() else datetime.today().date()

    selected_dates = st.sidebar.date_input(
        "Date Range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )

    if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
        start_date, end_date = selected_dates
    else:
        start_date = min_date
        end_date = max_date

    time_from = st.sidebar.time_input("Survey Start Time From", value=time(0, 0))
    time_to = st.sidebar.time_input("Survey Start Time To", value=time(23, 59))

    surveyors = sorted([x for x in df["Remarks1"].dropna().unique().tolist()])
    select_all_surveyors = st.sidebar.checkbox("Select All Surveyors", value=True)
    selected_surveyors = st.sidebar.multiselect(
        "Surveyor Name",
        options=surveyors,
        default=surveyors if select_all_surveyors else []
    )

    vehicle_types = sorted([x for x in df["3.Vehicle Type"].dropna().unique().tolist()])
    select_all_vehicles = st.sidebar.checkbox("Select All Vehicle Types", value=True)
    selected_vehicles = st.sidebar.multiselect(
        "Vehicle Type",
        options=vehicle_types,
        default=vehicle_types if select_all_vehicles else []
    )

    arms = sorted([x for x in df["2.Arm details"].dropna().unique().tolist()])
    select_all_arms = st.sidebar.checkbox("Select All Arms / Directions", value=True)
    selected_arms = st.sidebar.multiselect(
        "Arm / Direction",
        options=arms,
        default=arms if select_all_arms else []
    )

    filtered = df.copy()

    filtered = filtered[
        (filtered["Date"].dt.date >= start_date) &
        (filtered["Date"].dt.date <= end_date)
    ]

    filtered = filtered[
        filtered["start_time"].apply(
            lambda x: x is not None and pd.notna(x) and time_from <= x <= time_to
        )
    ]

    if selected_surveyors:
        filtered = filtered[filtered["Remarks1"].isin(selected_surveyors)]
    else:
        filtered = filtered.iloc[0:0]

    if selected_vehicles:
        filtered = filtered[filtered["3.Vehicle Type"].isin(selected_vehicles)]
    else:
        filtered = filtered.iloc[0:0]

    if selected_arms:
        filtered = filtered[filtered["2.Arm details"].isin(selected_arms)]
    else:
        filtered = filtered.iloc[0:0]

    total_records_placeholder.metric("Filtered Records", len(filtered))

    return filtered


def make_download_csv(df):
    return df.to_csv(index=False).encode("utf-8")


# --------------------------------------------------
# LOAD DATA
# --------------------------------------------------
with st.spinner("Loading and processing survey data..."):
    df = load_and_process_data()

filtered_df = filter_dataframe(df)

with st.expander("Debug O-D Check"):
    st.write("Total filtered rows:", len(filtered_df))
    st.write("Rows with origin:", filtered_df["unified_origin"].notna().sum())
    st.write("Rows with destination:", filtered_df["unified_destination"].notna().sum())
    st.write(
        filtered_df[
            [
                "3.Vehicle Type",
                "2.Arm details",
                "raw_origin",
                "raw_destination",
                "unified_origin",
                "unified_destination",
                "location_issue_type"
            ]
        ].head(50)
    )

with st.expander("Debug Vehicle Fields"):
    st.write(
        filtered_df[
            [
                "3.Vehicle Type",
                "unified_occupancy",
                "avg_sitting_pct_source",
                "raw_origin",
                "raw_destination"
            ]
        ].head(20)
    )

# --------------------------------------------------
# HEADER
# --------------------------------------------------
st.title("Mumbai Traffic Survey Dashboard — EEH (JJ Junction)")
last_updated = datetime.now().strftime("%d %b %Y %H:%M:%S")
st.caption(f"Survey location: EEH (JJ Junction), Mumbai | File: {FILE_NAME} | Last updated: {last_updated}")

# Optional fixed survey location map
if "Location" in df.columns and df["Location"].notna().any():
    sample_loc = df["Location"].dropna().astype(str).iloc[0]
    try:
        lat, lon = map(float, sample_loc.split(","))
        map_df = pd.DataFrame({"lat": [lat], "lon": [lon]})
        with st.expander("Show survey site map"):
            st.map(map_df)
    except Exception:
        pass

tabs = st.tabs([
    "Summary",
    "Surveyors",
    "Vehicles",
    "Origins & Destinations",
    "Surveyor Presenty",
    "Raw Data"
])

# --------------------------------------------------
# TAB 1 — SUMMARY
# --------------------------------------------------
with tabs[0]:
    total_surveys = len(filtered_df)
    total_surveyors = filtered_df["Remarks1"].nunique() if "Remarks1" in filtered_df.columns else 0

    most_common_vehicle = (
        filtered_df["3.Vehicle Type"].mode().iloc[0]
        if not filtered_df["3.Vehicle Type"].dropna().empty
        else "N/A"
    )

    if not filtered_df["Date"].dropna().empty:
        date_range_label = f"{filtered_df['Date'].min().strftime('%d %b')} – {filtered_df['Date'].max().strftime('%d %b %Y')}"
    else:
        date_range_label = "N/A"

    peak_hour = "N/A"
    if filtered_df["start_hour"].notna().any():
        peak = filtered_df["start_hour"].value_counts().idxmax()
        peak_hour = f"{int(peak):02d}:00 – {int(peak):02d}:59"

    data_quality_score = round(filtered_df["location_clean"].mean() * 100, 1) if len(filtered_df) else 0.0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total Surveys", total_surveys)
    c2.metric("Total Active Surveyors", total_surveyors)
    c3.metric("Most Common Vehicle Type", most_common_vehicle)
    c4.metric("Date Range", date_range_label)
    c5.metric("Peak Survey Hour", peak_hour)
    c6.metric("Data Quality Score", f"{data_quality_score}%")

    hourly = filtered_df.groupby("start_hour").size().reset_index(name="Survey Count")
    hourly["start_hour"] = hourly["start_hour"].fillna(-1)
    hourly = hourly[hourly["start_hour"] >= 0].sort_values("start_hour")

    fig_hourly = px.bar(
        hourly,
        x="start_hour",
        y="Survey Count",
        title="Hourly Survey Distribution",
        labels={"start_hour": "Hour of Day", "Survey Count": "Number of Surveys"},
        color_discrete_sequence=[PRIMARY_COLOR]
    )
    fig_hourly.update_traces(hovertemplate="Hour: %{x}:00<br>Surveys: %{y}<extra></extra>")
    st.plotly_chart(fig_hourly, use_container_width=True)

    daily = filtered_df.groupby(filtered_df["Date"].dt.date).size().reset_index(name="Survey Count")
    daily.columns = ["Date", "Survey Count"]

    fig_daily = px.line(
        daily,
        x="Date",
        y="Survey Count",
        title="Daily Survey Trend",
        markers=True,
        labels={"Date": "Date", "Survey Count": "Number of Surveys"}
    )
    fig_daily.update_traces(line_color=PRIMARY_COLOR, hovertemplate="Date: %{x}<br>Surveys: %{y}<extra></extra>")
    st.plotly_chart(fig_daily, use_container_width=True)

# --------------------------------------------------
# TAB 2 — SURVEYORS
# --------------------------------------------------
# --------------------------------------------------
# TAB 2 — SURVEYORS
# --------------------------------------------------
with tabs[1]:
    st.subheader("Surveyor Performance Summary")

    surveyor_base = filtered_df.copy()

    surveyor_base = surveyor_base[surveyor_base["Remarks1"].notna()]
    surveyor_base = surveyor_base[surveyor_base["Remarks1"].astype(str).str.strip() != ""]

    if surveyor_base.empty:
        st.info("No surveyor data available for the selected global filters.")
    else:
        surveyor_summary = (
            surveyor_base.groupby("Remarks1", dropna=False)
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
                        lambda x: min([t.strftime("%H:%M:%S") for t in x.dropna()]) if len(x.dropna()) else None
                    ),
                    "Last Entry": (
                        "end_time",
                        lambda x: max([t.strftime("%H:%M:%S") for t in x.dropna()]) if len(x.dropna()) else None
                    ),
                    "Avg Duration (mins)": ("survey_duration_mins", "mean"),
                    "Data Quality Score (%)": (
                        "location_clean",
                        lambda x: round(x.mean() * 100, 1) if len(x.dropna()) else 0
                    )
                }
            )
            .reset_index()
            .rename(columns={"Remarks1": "Surveyor Name"})
            .sort_values(["Total Surveys", "Surveyor Name"], ascending=[False, True])
        )

        surveyor_summary["Avg Duration (mins)"] = surveyor_summary["Avg Duration (mins)"].round(1)
        surveyor_summary["First Entry"] = surveyor_summary["First Entry"].fillna("-")
        surveyor_summary["Last Entry"] = surveyor_summary["Last Entry"].fillna("-")
        surveyor_summary["Vehicle Types Covered"] = surveyor_summary["Vehicle Types Covered"].replace("", "-")
        surveyor_summary["Arms Covered"] = surveyor_summary["Arms Covered"].replace("", "-")

        st.dataframe(surveyor_summary, use_container_width=True)

        top_surveyor = surveyor_summary.iloc[0]["Surveyor Name"]
        surveyor_summary["Highlight"] = surveyor_summary["Surveyor Name"].apply(
            lambda x: "Top Performer" if x == top_surveyor else "Others"
        )

        fig_surveyor_bar = px.bar(
            surveyor_summary.sort_values("Total Surveys", ascending=True),
            x="Total Surveys",
            y="Surveyor Name",
            orientation="h",
            color="Highlight",
            title="Surveys per Surveyor",
            labels={
                "Total Surveys": "Number of Surveys",
                "Surveyor Name": "Surveyor"
            },
            color_discrete_map={
                "Top Performer": "#FF7F0E",
                "Others": PRIMARY_COLOR
            },
            hover_data=["Arms Covered", "Vehicle Types Covered", "Avg Duration (mins)", "Data Quality Score (%)"]
        )
        fig_surveyor_bar.update_layout(showlegend=False)
        st.plotly_chart(fig_surveyor_bar, use_container_width=True)

# --------------------------------------------------
# TAB 3 — VEHICLES
# --------------------------------------------------
with tabs[2]:
    st.subheader("Vehicle Type Analysis")

    vehicle_summary = (
        filtered_df.groupby("3.Vehicle Type")
        .agg(
            Count=("3.Vehicle Type", "size"),
            Avg_Occupancy=("unified_occupancy", "mean"),
            Avg_Sitting_Pct=("avg_sitting_pct_source", "mean")
        )
        .reset_index()
        .sort_values("Count", ascending=False)
    )

    total_vehicle_count = vehicle_summary["Count"].sum()
    vehicle_summary["% Share"] = (
        (vehicle_summary["Count"] / total_vehicle_count) * 100
        if total_vehicle_count > 0 else 0
    )
    vehicle_summary["% Share"] = vehicle_summary["% Share"].round(1)
    vehicle_summary["Avg_Occupancy"] = vehicle_summary["Avg_Occupancy"].round(1)
    vehicle_summary["Avg_Sitting_Pct"] = vehicle_summary["Avg_Sitting_Pct"].round(1)

    vehicle_summary["Avg_Occupancy"] = vehicle_summary["Avg_Occupancy"].where(
        vehicle_summary["Avg_Occupancy"].notna(), "-"
    )
    vehicle_summary["Avg_Sitting_Pct"] = vehicle_summary["Avg_Sitting_Pct"].where(
        vehicle_summary["Avg_Sitting_Pct"].notna(), "-"
    )

    col1, col2 = st.columns(2)

    with col1:
        if not vehicle_summary.empty:
            fig_pie = px.pie(
                vehicle_summary,
                names="3.Vehicle Type",
                values="Count",
                title="Survey Count by Vehicle Type",
                color_discrete_sequence=px.colors.sequential.Blues
            )
            fig_pie.update_traces(textinfo="percent+label", hovertemplate="%{label}<br>Count: %{value}<br>Share: %{percent}<extra></extra>")
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("No vehicle data available for the selected filters.")

    with col2:
        if not vehicle_summary.empty:
            fig_vehicle_bar = px.bar(
                vehicle_summary,
                x="3.Vehicle Type",
                y="Count",
                title="Survey Count by Vehicle Type",
                labels={
                    "3.Vehicle Type": "Vehicle Type",
                    "Count": "Number of Surveys"
                },
                color_discrete_sequence=[PRIMARY_COLOR]
            )
            fig_vehicle_bar.update_traces(hovertemplate="Vehicle Type: %{x}<br>Count: %{y}<extra></extra>")
            fig_vehicle_bar.update_layout(xaxis_tickangle=-30)
            st.plotly_chart(fig_vehicle_bar, use_container_width=True)

    st.markdown("### Vehicle Summary Table")

    if not vehicle_summary.empty:
        display_vehicle_summary = vehicle_summary.rename(columns={
            "3.Vehicle Type": "Vehicle Type",
            "Avg_Occupancy": "Avg Occupancy",
            "Avg_Sitting_Pct": "Avg Sitting %"
        })
        st.dataframe(display_vehicle_summary, use_container_width=True)
    else:
        st.info("No summary data available.")

    st.markdown("### Vehicle Type Breakdown per Surveyor")
    surveyor_vehicle = (
        filtered_df.groupby(["Remarks1", "3.Vehicle Type"])
        .size()
        .reset_index(name="Count")
    )

    if not surveyor_vehicle.empty:
        fig_surveyor_vehicle = px.bar(
            surveyor_vehicle,
            x="Remarks1",
            y="Count",
            color="3.Vehicle Type",
            title="Vehicle Type Breakdown per Surveyor",
            labels={
                "Remarks1": "Surveyor",
                "Count": "Survey Count",
                "3.Vehicle Type": "Vehicle Type"
            },
            barmode="stack"
        )
        fig_surveyor_vehicle.update_layout(xaxis_tickangle=-30)
        st.plotly_chart(fig_surveyor_vehicle, use_container_width=True)
    else:
        st.info("No surveyor vehicle breakdown available.")

    st.markdown("### Vehicle Type Breakdown per Arm / Direction")
    arm_vehicle = (
        filtered_df.groupby(["2.Arm details", "3.Vehicle Type"])
        .size()
        .reset_index(name="Count")
    )

    if not arm_vehicle.empty:
        fig_arm_vehicle = px.bar(
            arm_vehicle,
            x="2.Arm details",
            y="Count",
            color="3.Vehicle Type",
            title="Vehicle Type Breakdown per Arm / Direction",
            labels={
                "2.Arm details": "Arm / Direction",
                "Count": "Survey Count",
                "3.Vehicle Type": "Vehicle Type"
            },
            barmode="stack"
        )
        fig_arm_vehicle.update_layout(xaxis_tickangle=-20)
        st.plotly_chart(fig_arm_vehicle, use_container_width=True)
    else:
        st.info("No arm-wise vehicle breakdown available.")

# --------------------------------------------------
# TAB 4 — ORIGINS & DESTINATIONS
# --------------------------------------------------
with tabs[3]:
    st.subheader("Origins & Destinations")

    od_base = filtered_df.copy()



    od_base["unified_origin"] = od_base["unified_origin"].apply(lambda x: x.strip() if isinstance(x, str) else x)
    od_base["unified_destination"] = od_base["unified_destination"].apply(lambda x: x.strip() if isinstance(x, str) else x)

    od_base = od_base.copy()
    od_base["unified_origin"] = od_base["unified_origin"].apply(lambda x: x.strip() if isinstance(x, str) else x)
    od_base["unified_destination"] = od_base["unified_destination"].apply(lambda x: x.strip() if isinstance(x, str) else x)

    od_base["unified_origin"] = od_base["unified_origin"].replace("-", pd.NA).replace("", pd.NA)
    od_base["unified_destination"] = od_base["unified_destination"].replace("-", pd.NA).replace("", pd.NA)

    od_base["unified_origin"] = od_base["unified_origin"].apply(lambda x: x.title() if isinstance(x, str) else x)
    od_base["unified_destination"] = od_base["unified_destination"].apply(lambda x: x.title() if isinstance(x, str) else x)

    od_pairs = (
        od_base.dropna(subset=["unified_origin", "unified_destination"])
        .groupby(["unified_origin", "unified_destination"])
        .size()
        .reset_index(name="Trip Count")
        .sort_values("Trip Count", ascending=False)
        .head(20)
    )

    st.markdown("### Top O-D Pairs")
    if not od_pairs.empty:
        od_pairs["Origin → Destination"] = od_pairs["unified_origin"] + " → " + od_pairs["unified_destination"]
        st.dataframe(
            od_pairs[["Origin → Destination", "Trip Count"]],
            use_container_width=True
        )
    else:
        st.info("No O-D pair data available.")

    top_origins = (
        od_base["unified_origin"]
        .dropna()
        .value_counts()
        .head(15)
        .reset_index()
    )
    top_origins.columns = ["Origin", "Count"]

    st.markdown("### Top Origins")
    if not top_origins.empty:
        fig_origins = px.bar(
            top_origins.sort_values("Count", ascending=True),
            x="Count",
            y="Origin",
            orientation="h",
            title="Top 15 Origins",
            labels={"Count": "Frequency", "Origin": "Origin"},
            color_discrete_sequence=[PRIMARY_COLOR]
        )
        fig_origins.update_traces(hovertemplate="Origin: %{y}<br>Count: %{x}<extra></extra>")
        st.plotly_chart(fig_origins, use_container_width=True)
    else:
        st.info("No origin data available.")

    top_destinations = (
        od_base["unified_destination"]
        .dropna()
        .value_counts()
        .head(15)
        .reset_index()
    )
    top_destinations.columns = ["Destination", "Count"]

    st.markdown("### Top Destinations")
    if not top_destinations.empty:
        fig_destinations = px.bar(
            top_destinations.sort_values("Count", ascending=True),
            x="Count",
            y="Destination",
            orientation="h",
            title="Top 15 Destinations",
            labels={"Count": "Frequency", "Destination": "Destination"},
            color_discrete_sequence=["#1F77B4"]
        )
        fig_destinations.update_traces(hovertemplate="Destination: %{y}<br>Count: %{x}<extra></extra>")
        st.plotly_chart(fig_destinations, use_container_width=True)
    else:
        st.info("No destination data available.")

# --------------------------------------------------
# TAB 5 — SURVEYOR PRESENTY
# --------------------------------------------------

with tabs[4]:
    st.subheader("Surveyor Presence")

    # IMPORTANT: use full df, not filtered_df
    presence_base = df.copy()

    presence_base = presence_base[
        presence_base["Date"].notna() &
        presence_base["Remarks1"].notna() &
        presence_base["start_time"].notna() &
        presence_base["end_time"].notna()
    ].copy()

    presence_base = presence_base[presence_base["Remarks1"].astype(str).str.strip() != ""]

    if presence_base.empty:
        st.info("No surveyor presence data available.")
    else:
        presence_records = []

        for _, row in presence_base.iterrows():
            surveyor = row["Remarks1"]
            survey_date = pd.to_datetime(row["Date"]).strftime("%d-%m-%Y")
            start_t = row["start_time"]
            end_t = row["end_time"]

            if pd.isna(start_t) or pd.isna(end_t):
                continue

            start_hour = start_t.hour
            end_hour = end_t.hour

            if (end_t.hour, end_t.minute, end_t.second) < (start_t.hour, start_t.minute, start_t.second):
                continue

            for hour in range(start_hour, end_hour + 1):
                half = "First Half" if hour < 13 else "Second Half"
                presence_records.append({
                    "Surveyor Name": surveyor,
                    "Date Label": survey_date,
                    "Hour": hour,
                    "Half": half,
                    "Present": "Present"
                })

        presence_hourly = pd.DataFrame(presence_records)

        if presence_hourly.empty:
            st.info("No hourly surveyor presence could be generated.")
        else:
            half_presence = (
                presence_hourly.groupby(["Surveyor Name", "Date Label", "Half"])
                .agg({"Present": "first"})
                .reset_index()
            )

            presence_pivot = half_presence.pivot_table(
                index="Surveyor Name",
                columns=["Date Label", "Half"],
                values="Present",
                aggfunc="first",
                fill_value=""
            )

            presence_pivot = presence_pivot.sort_index(axis=1)
            presence_pivot = presence_pivot.reset_index()

            st.markdown("### Surveyor Presence by Date and Half")
            st.dataframe(presence_pivot, use_container_width=True)

            hourly_summary = (
                presence_hourly.groupby(["Date Label", "Hour"])
                .agg(
                    **{
                        "Surveyors Present": ("Surveyor Name", pd.Series.nunique),
                        "Surveyor Names": (
                            "Surveyor Name",
                            lambda x: ", ".join(sorted(set(x.dropna().astype(str))))
                        )
                    }
                )
                .reset_index()
                .sort_values(["Date Label", "Hour"])
            )

            hourly_summary["Hour Label"] = hourly_summary["Hour"].apply(lambda x: f"{int(x):02d}:00")

            st.markdown("### Hourly Surveyor Presence")
            st.dataframe(
                hourly_summary[["Date Label", "Hour Label", "Surveyors Present", "Surveyor Names"]],
                use_container_width=True
            )
            st.markdown("### Hourly Surveyor Presence Filtered")

    filtered_presence_base = filtered_df.copy()

    filtered_presence_base = filtered_presence_base[
    filtered_presence_base["Date"].notna() &
    filtered_presence_base["Remarks1"].notna() &
    filtered_presence_base["start_time"].notna()
    ].copy()

    filtered_presence_base = filtered_presence_base[
    filtered_presence_base["Remarks1"].astype(str).str.strip() != ""
    ]

    if filtered_presence_base.empty:
        st.info("No hourly surveyor presence data available for the selected filters.")
    else:
        filtered_presence_base["Date Label"] = pd.to_datetime(
        filtered_presence_base["Date"]
        ).dt.strftime("%d-%m-%Y")

        filtered_presence_base["Hour"] = filtered_presence_base["start_time"].apply(
        lambda x: x.hour if pd.notna(x) and x is not None else None
        )

        hourly_surveyor_presence_filtered = (
            filtered_presence_base.groupby(["Date Label", "Hour"])
            .agg(
            **{
                "Surveyors Present": ("Remarks1", pd.Series.nunique),
                "Surveyor Names": (
                    "Remarks1",
                    lambda x: ", ".join(sorted(set(x.dropna().astype(str))))
                ),
                "Total Records": ("Remarks1", "size")
                }
            )
            .reset_index()
            .sort_values(["Date Label", "Hour"])
        )

        hourly_surveyor_presence_filtered["Hour Label"] = (
            hourly_surveyor_presence_filtered["Hour"]
            .apply(lambda x: f"{int(x):02d}:00 - {int(x):02d}:59" if pd.notna(x) else "")
        )

        st.dataframe(
            hourly_surveyor_presence_filtered[
            ["Date Label", "Hour Label", "Surveyors Present", "Surveyor Names", "Total Records"]
            ],
            use_container_width=True
        )

# --------------------------------------------------
# TAB 6 — RAW DATA
# --------------------------------------------------
with tabs[5]:
    st.subheader("Filtered Raw Data")

    raw_display = filtered_df.copy()

    columns_to_show = [
        "Date",
        "start_time",
        "end_time",
        "Remarks1",
        "3.Vehicle Type",
        "2.Arm details",
        "unified_origin",
        "unified_destination",
        "unified_occupancy",
        "survey_duration"
    ]

    available_columns = [col for col in columns_to_show if col in raw_display.columns]
    raw_display = raw_display[available_columns].copy()

    raw_display = raw_display.rename(columns={
        "Remarks1": "Surveyor",
        "3.Vehicle Type": "Vehicle Type",
        "2.Arm details": "Arm"
    })

    if "Date" in raw_display.columns:
        raw_display["Date"] = pd.to_datetime(raw_display["Date"]).dt.strftime("%d-%m-%Y")

    if "start_time" in raw_display.columns:
        raw_display["start_time"] = raw_display["start_time"].apply(
            lambda x: x.strftime("%H:%M:%S") if pd.notna(x) and x is not None else None
        )

    if "end_time" in raw_display.columns:
        raw_display["end_time"] = raw_display["end_time"].apply(
            lambda x: x.strftime("%H:%M:%S") if pd.notna(x) and x is not None else None
        )

    if "survey_duration" in raw_display.columns:
        raw_display["survey_duration"] = raw_display["survey_duration"].apply(
            lambda x: str(x) if pd.notna(x) else None
        )

    st.dataframe(raw_display, use_container_width=True)

    csv_data = make_download_csv(raw_display)
    st.download_button(
        label="Download Filtered Data as CSV",
        data=csv_data,
        file_name="filtered_survey_data.csv",
        mime="text/csv"
    )



# --------------------------------------------------
# FOOTER
# --------------------------------------------------
st.markdown("---")
st.caption(f"Data file: {FILE_NAME} | Dashboard built for DC513MH04 survey")