"""
scheduler.py
────────────
Runs every 5 minutes between 08:00 and 21:00 (local time).
Each tick: download the Datacorp report → load into SQLite DB.

Start once on the server:
    python scheduler.py

Or run as a systemd service (see README.md).

Dependencies:
    pip install schedule python-dotenv
"""

import logging
import time
from datetime import datetime
from pathlib import Path

import schedule
from dotenv import load_dotenv

# Load .env file if present (DATACORP_URL, DATACORP_USER, etc.)
load_dotenv(Path(__file__).resolve().parent / ".env")

from db import init_db, save_dataframe, log_sync
from downloader import download_report

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scheduler.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

SYNC_START_HOUR = 8   # 08:00
SYNC_END_HOUR   = 21  # 21:00  (last sync runs before 21:00)
SHEET_NAME      = "Survey Results"


def is_within_window() -> bool:
    now = datetime.now()
    return SYNC_START_HOUR <= now.hour < SYNC_END_HOUR


def sync_job():
    """Download → parse → save to DB.  Runs on every scheduled tick."""
    if not is_within_window():
        logger.info("Outside sync window (08:00–21:00) — skipping.")
        return

    logger.info("═" * 55)
    logger.info("Sync started")

    try:
        # 1. Download from Datacorp
        file_path = download_report()

        # 2. Parse the Excel sheet
        df = pd.read_excel(file_path, sheet_name=SHEET_NAME, engine="openpyxl")
        logger.info(f"Parsed {len(df)} rows from {file_path.name}")

        # 3. Save to SQLite
        save_dataframe(df, file_path.name)

        # 4. Log success
        log_sync("success", len(df), f"Imported {file_path.name}")
        logger.info(f"Sync SUCCESS — {len(df)} rows saved.")

        # 5. Remove the downloaded file to keep the folder clean
        file_path.unlink(missing_ok=True)

    except Exception as exc:
        log_sync("failed", 0, str(exc))
        logger.exception(f"Sync FAILED: {exc}")


def main():
    init_db()
    logger.info("Scheduler starting up …")
    logger.info(f"Sync window : {SYNC_START_HOUR:02d}:00 – {SYNC_END_HOUR:02d}:00")
    logger.info("Interval    : every 5 minutes")

    # Schedule every 5 minutes
    schedule.every(5).minutes.do(sync_job)

    # Run once immediately at startup (if within window)
    sync_job()

    while True:
        schedule.run_pending()
        time.sleep(30)   # check every 30 s so we don't burn CPU


if __name__ == "__main__":
    main()
