# SummaryV2 — TrafficLenz Survey Data Web App (Next.js)

A high-performance Next.js application for exploring Delhi OD passenger & goods survey data, featuring direct Neon PostgreSQL integration, comprehensive global filters, and TanStack Table data grid with CSV export.

---

## 🌟 Key Features

- **Raw Data Tab**: Displays all raw & derived survey columns matching `app-2.py` (`Date`, `Start Time`, `End Time`, `Entry Duration`, `Surveyor`, `Contact`, `Survey Type`, `Direction`, `Vehicle Type`, `Occupancy`, `Origin`, `Destination`, `Sample Quality Flags`).
- **Global Filters Sidebar**:
  - Date Range Picker (`dateFrom`, `dateTo`).
  - 15-Minute Survey Start Time Dropdowns (`00:00` to `23:45`).
  - Multi-Select Dropdowns with "Select All" / "Deselect All" for Survey Type, Direction / Arm, Vehicle Type, and Surveyor.
  - Real-time "Filtered Records" metric counter.
- **TanStack Table Data Grid**:
  - Full client/server column sorting.
  - Pagination controls (`25`, `50`, `100`, `250` rows per page).
  - Suspicious OD and short duration highlight badges.
- **CSV Export**: One-click download of filtered records matching Streamlit format.
- **Dual-Mode Database Layer**: Connects to **Neon PostgreSQL** via `DATABASE_URL`, with seamless fallback to an included local seed dataset for instant offline development.
- **Sync Worker (`sync_worker/sync_to_neon.py`)**: Python worker for upserting TrafficLenz survey records into NeonDB.

---

## 🚀 Quickstart

### 1. Install Node Dependencies

```bash
cd SummaryV2
npm install
```

### 2. Configure Environment (Optional for NeonDB)

Copy `.env.example` to `.env.local`:

```bash
cp .env.example .env.local
```

Add your Neon PostgreSQL connection string:

```env
DATABASE_URL=postgresql://username:password@ep-cool-fog-123456.us-east-2.aws.neon.tech/neondb?sslmode=require
```

*(If `DATABASE_URL` is omitted, the app will run in local mock mode seeded with 2,410 real survey records).*

### 3. Run Development Server

```bash
npm run dev
```

Open **[http://localhost:3000](http://localhost:3000)** in your browser.

---

## 🏗️ Building for Production

```bash
npm run build
npm start
```

