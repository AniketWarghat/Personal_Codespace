"""
downloader.py  (cookie-based — no login form, no CAPTCHA)
──────────────────────────────────────────────────────────
Loads saved cookies from cookies.json, injects them into a headless Chrome
session, then navigates directly to the report and downloads it.

Prerequisites:
    1. Run export_cookies.py on your local machine once to create cookies.json
    2. Copy cookies.json to the server next to this file
    3. Re-run export_cookies.py whenever the session expires

Environment variables (set in .env):
    DATACORP_URL      – https://www.trafficlenz.com  (no trailing slash)
    DATACORP_JOB_ID   – e.g. DC513MH04
"""

import json
import logging
import os
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)

BASE_DIR     = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
COOKIE_FILE  = BASE_DIR / "cookies.json"
DOWNLOAD_DIR.mkdir(exist_ok=True)


def _build_driver() -> webdriver.Chrome:
    prefs = {
        "download.default_directory": str(DOWNLOAD_DIR),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_experimental_option("prefs", prefs)

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)


def _load_cookies(driver: webdriver.Chrome):
    """Inject saved cookies into the browser session."""
    if not COOKIE_FILE.exists():
        raise FileNotFoundError(
            f"cookies.json not found at {COOKIE_FILE}\n"
            "Run export_cookies.py on your local machine first."
        )

    cookies = json.loads(COOKIE_FILE.read_text())
    portal_url = os.environ.get("DATACORP_URL", "https://www.trafficlenz.com")

    # Must visit the domain before setting cookies
    driver.get(portal_url)
    time.sleep(2)

    for cookie in cookies:
        cookie.pop("sameSite", None)
        try:
            driver.add_cookie(cookie)
        except Exception as e:
            logger.debug(f"Skipped cookie '{cookie.get('name')}': {e}")

    logger.info(f"Injected {len(cookies)} cookies")


def _wait_for_download(timeout: int = 120) -> Path:
    deadline = time.time() + timeout
    while time.time() < deadline:
        xlsx_files = [
            f for f in DOWNLOAD_DIR.glob("*.xlsx")
            if not f.name.endswith(".crdownload")
        ]
        if xlsx_files:
            time.sleep(1)
            return max(xlsx_files, key=lambda f: f.stat().st_mtime)
        time.sleep(2)
    raise TimeoutError(
        f"No .xlsx file appeared in {DOWNLOAD_DIR} within {timeout}s"
    )


def _is_session_valid(driver: webdriver.Chrome) -> bool:
    """
    After injecting cookies and refreshing, check we're actually logged in.
    ⚠️  Replace the CSS selector with something only visible when logged in
        (e.g. a dashboard nav, user avatar, or sidebar element).
    """
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "nav.dashboard-nav, .user-menu, #dashboard")
            )
        )
        return True
    except Exception:
        return False


class SessionExpiredError(Exception):
    """Raised when cookies.json exists but the session is no longer valid."""
    pass


def download_report() -> Path:
    """
    Main entry point called by scheduler.py.
    Returns the path of the downloaded .xlsx file.
    """
    portal_url = os.environ.get("DATACORP_URL", "https://www.trafficlenz.com")
    job_id     = os.environ["DATACORP_JOB_ID"]

    driver = _build_driver()
    wait   = WebDriverWait(driver, 30)

    try:
        # ── 1. Inject saved cookies ─────────────────────────────────────
        _load_cookies(driver)

        # ── 2. Reload so cookies take effect ────────────────────────────
        driver.refresh()
        time.sleep(3)

        # ── 3. Verify session is still alive ────────────────────────────
        if not _is_session_valid(driver):
            raise SessionExpiredError(
                "Session cookie has expired. "
                "Re-run export_cookies.py on your local machine and "
                "copy the new cookies.json to the server."
            )

        logger.info("Session valid — navigating to report …")

        # ── 4. Navigate to the job report page ──────────────────────────
        # ⚠️  Inspect the URL when you open a job report manually in Chrome
        #     and replace this pattern with the real one.
        driver.get(f"{portal_url}/jobs/{job_id}/report")
        time.sleep(3)

        # ── 5. Click the Export / Download button ───────────────────────
        # ⚠️  Right-click the Export button in DevTools → Copy → Copy selector
        #     and replace the selector below.
        export_btn = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR,
                 "button.export-excel, a[data-action='export'], .btn-download")
            )
        )
        export_btn.click()
        logger.info("Export clicked — waiting for download …")

        # ── 6. Wait for file ─────────────────────────────────────────────
        path = _wait_for_download(timeout=120)
        logger.info(f"Downloaded: {path.name}")
        return path

    finally:
        driver.quit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    p = download_report()
    print(f"File saved to: {p}")
