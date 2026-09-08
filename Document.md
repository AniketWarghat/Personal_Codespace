# Document.md — TrafficLenz Survey Data Web App (Next.js)

## Goal (v1 scope)
Build a Next.js website that reads survey data from NeonDB (populated by the existing Python sync worker) and shows **one tab: Raw Data**, with **Global Filters** matching the logic already proven in the reference Streamlit app (`app-2.py`, Delhi OD Passenger/Goods Survey Dashboard). Later phases will add the other tabs (Summary, Surveyors, Vehicles, OD Analysis, Suspicious OD, etc.) that already exist in `app-2.py` — build the schema and filter layer so those can be added without rework.

**Reference file:** `app-2.py` is the source of truth for column names, cleaning rules, and derived-field logic. Port its logic faithfully — don't reinvent field derivation.

## Architecture

```
[TrafficLenz downloadQuestionnaireReport] 
        │ (Python session-based downloader, existing)
        ▼
[Sync worker: process_dataframe() logic, every 30s]
        │ (upsert via psycopg2/SQLAlchemy)
        ▼
[NeonDB: Postgres — stores RAW + DERIVED columns]
        │
        ▼
[Next.js API route: /api/survey-data]  (Route Handler, server-side pg query)
        │
        ▼
[Next.js frontend: Raw Data tab + Global Filters sidebar]
```

Next.js Route Handlers talk to Neon directly (server-side, using a read-only DB role) — no separate FastAPI layer needed for v1, since Next.js already runs server-side code.

## Data model (Neon table: `survey_records`)

Port these columns from `app-2.py`'s `process_dataframe()` output. Raw columns first, then derived:

**Raw (as downloaded):**
| Column | Source field in app-2.py |
|---|---|
| `date` | `Date` |
| `start_time` | `start_time` |
| `end_time` | `end_time` |
| `username` | `Username` |
| `location` | `Location` (lat,lon string) |
| `remarks1` (surveyor raw) | `Remarks1` |
| `remarks2` (contact raw) | `Remarks2` |
| `direction_raw` | `0.Direction` |
| `survey_type_raw` | `1.Survey Type` |
| ...plus all passenger/goods question columns (`1a1..1a8`, `1b1..1b6`) — store as-is; see `app-2.py` lines ~108–160 for the full list |

**Derived (computed by the sync worker, mirroring `process_dataframe()`):**
| Column | Derivation logic (see app-2.py) |
|---|---|
| `surveyor` | title-cased `remarks1` |
| `contact` | cleaned `remarks2` |
| `direction` | cleaned `direction_raw` |
| `survey_type` | title-cased `survey_type_raw` |
| `vehicle_type` | `derive_vehicle()` |
| `origin` | `derive_origin()` |
| `destination` | `derive_destination()` |
| `likely_shift` | `derive_shift()` |
| `trip_frequency` | `derive_frequency()` |
| `trip_purpose_or_commodity` | `derive_purpose_or_commodity()` |
| `occupancy` | `derive_occupancy()` |
| `entry_duration_sec` | `duration_seconds(start_time, end_time)` |
| `survey_duration_mins` | `entry_duration_sec / 60` |
| `has_origin_destination` | bool |
| `bad_od_entry` | bool |
| `sample_quality_flags` | `od_quality_flag_text()` |
| `sample_quality_suspicious` | bool |
| `last_synced_at` | sync timestamp (new column, not in app-2.py) |

Add a unique key (e.g. hash of raw row content, or `username` + `date` + `start_time` if that's unique per entry) so the sync worker can upsert without duplicating rows.

## Raw Data tab — columns to display (v1)
Mirror `prepare_display()` in `app-2.py`, in this order:
`Date, Start Time, End Time, Entry Duration (sec), Entry Duration, Surveyor, Contact, Survey Type, Direction, Vehicle Type, Occupancy, Origin, Destination, Duration (mins), Sample Quality Flags`

Use a data table component (TanStack Table recommended) with sorting and a CSV export button (mirrors the `⬇️ Download Filtered Data CSV` button in `app-2.py`).

## Global Filters (sidebar, mirrors `filter_dataframe()` in app-2.py)
1. **Date Range** — min/max from data, date-range picker.
2. **Survey Start Time From / To** — dropdowns, 15-minute increments, 00:00–23:59.
3. **Survey Type** — multi-select, "Select All" toggle, default all.
4. **Direction / Arm** — multi-select, "Select All" toggle, default all.
5. **Vehicle Type** — multi-select, "Select All" toggle, default all.
6. **Surveyor** — multi-select, "Select All" toggle, default all.

Filter logic: all filters AND together. If a multi-select has zero options selected, the result is empty (matches `app-2.py` behavior — don't silently ignore an empty selection).

Show a "Filtered Records: N" counter, same as `st.sidebar.metric("Filtered Records", ...)`.

## API route: `GET /api/survey-data`
Query params mirror the filters above:
- `dateFrom`, `dateTo`
- `timeFrom`, `timeTo`
- `surveyType` (repeatable or comma-separated)
- `direction` (repeatable or comma-separated)
- `vehicleType` (repeatable or comma-separated)
- `surveyor` (repeatable or comma-separated)

Returns: `{ records: [...], totalCount: number, lastSyncedAt: string }`

Apply filtering in the SQL query (`WHERE` clauses), not by fetching everything and filtering client-side — dataset will grow over time.

## Tech stack
- Next.js (App Router, TypeScript)
- Tailwind CSS for styling
- `pg` or `postgres.js` for the Neon connection (server-side only, in Route Handlers — never expose the DB connection string to the client)
- TanStack Table for the Raw Data grid
- A date-range and multi-select component (e.g. from `shadcn/ui`, which pairs well with Tailwind)

## Build order for the AI IDE
1. Scaffold Next.js app (App Router, TypeScript, Tailwind).
2. Set up Neon connection in a server-only module (env var for connection string, read-only role).
3. Build `/api/survey-data` Route Handler with the filter query params above, querying `survey_records`.
4. Build the Global Filters sidebar (client component), fetching distinct filter option values (survey types, directions, vehicle types, surveyors) either from a small `/api/filter-options` route or from the initial data load.
5. Build the Raw Data table (TanStack Table) wired to `/api/survey-data`, re-fetching when filters change.
6. Add the CSV export button (client-side, from the currently filtered rows).
7. Add a "Last synced: {lastSyncedAt}" indicator, matching the `st.caption(f"Last updated: ...")` in app-2.py.
8. (Optional, later) Add auto-refresh every 30s to match the sync cadence — same pattern discussed for the Streamlit dashboard.

## Explicitly out of scope for v1
Summary, Surveyors, Short Entry Duration, Vehicles, OD Analysis, Suspicious OD, and Shift/Frequency/Purpose tabs — these exist in `app-2.py` and should be ported later using the same derived columns already in the Neon schema, so no schema changes should be needed to add them.
