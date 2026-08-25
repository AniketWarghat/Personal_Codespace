"""
scheduler.py — Standalone 15-Minute Background Auto-Sync Worker
================================================================
Runs continuously in the background (or as a Windows Service / Cron job).
Every 15 minutes between 6:00 AM and 11:00 PM Indian Standard Time (IST):
  1. Downloads the latest Excel survey report from TrafficLenz.
  2. Saves it to `data/latest_survey.xlsx`.
  3. Logs the status with timestamp.

Usage:
  python scheduler.py
"""

import logging
import time
from datetime import datetime, time as dtime, timezone, timedelta
from pathlib import Path

from downloader import config_from_secrets, config_is_valid, download_latest_excel, has_saved_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("data/sync_scheduler.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("Scheduler")

IST = timezone(timedelta(hours=5, minutes=30))
START_TIME = dtime(6, 0)   # 6:00 AM IST
END_TIME = dtime(23, 0)    # 11:00 PM IST
INTERVAL_SECONDS = 15 * 60 # 15 minutes


def is_active_hours() -> bool:
    """Check if current time is within 6:00 AM to 11:00 PM IST."""
    now_ist = datetime.now(IST).time()
    return START_TIME <= now_ist <= END_TIME


def run_sync_job() -> None:
    cfg = config_from_secrets()
    ok, reason = config_is_valid(cfg)
    if not ok:
        logger.error("Configuration error: %s", reason)
        return

    if not has_saved_session(cfg):
        logger.error("No active session found in %s. Please login first.", cfg.session_path)
        return

    logger.info("🚀 Starting 15-minute sync for survey %s...", cfg.survey_id)
    try:
        saved_file, ts = download_latest_excel(cfg)
        size_bytes = Path(saved_file).stat().st_size
        logger.info("✅ SUCCESS! Downloaded %s (%d bytes) at %s IST", saved_file, size_bytes, ts)
    except Exception as e:
        logger.error("❌ Sync failed: %s", e)


def main():
    logger.info("=== TrafficLenz Auto-Sync Scheduler Started ===")
    logger.info("Active Window: 06:00 AM – 11:00 PM IST (every 15 minutes)")

    while True:
        try:
            if is_active_hours():
                run_sync_job()
            else:
                now_ist_str = datetime.now(IST).strftime("%H:%M:%S")
                logger.info("🌙 Outside survey window (%s IST). Sleeping until next check...", now_ist_str)

        except Exception as e:
            logger.error("Unexpected error in scheduler loop: %s", e)

        # Sleep for 15 minutes
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
