import os
import time
from pathlib import Path
import pandas as pd

from db import init_db, save_dataframe, log_sync

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

def find_latest_file():
    files = list(DOWNLOAD_DIR.glob("*.xlsx"))
    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_mtime)

def import_latest_download():
    latest_file = find_latest_file()
    if latest_file is None:
        log_sync("failed", 0, "No downloaded report found")
        return

    try:
        df = pd.read_excel(latest_file, sheet_name="Survey Results", engine="openpyxl")
        save_dataframe(df, latest_file.name)
        log_sync("success", len(df), f"Imported {latest_file.name}")

        os.remove(latest_file)
    except Exception as e:
        log_sync("failed", 0, str(e))
        raise

if __name__ == "__main__":
    init_db()

    # TODO: Add Selenium login + download logic here
    # After download completes:
    import_latest_download()