"""
downloader.py — TrafficLenz Automated Survey Downloader
========================================================

Complete automated workflow:
  1. Uses saved session from `data/session.json`.
  2. Opens `myDashboardView`.
  3. Searches for the configured Survey / Job code (e.g. `DC513DL01`).
  4. Opens project map on `viewgraph`.
  5. Clicks map marker.
  6. Expands task actions (+).
  7. Triggers `downloadQuestionnaireReport` export.
  8. Streams raw Excel bytes directly into memory for Streamlit (no stray files left on disk).
"""

from __future__ import annotations

import io
import os
import time
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
@dataclass
class TrafficLenzConfig:
    """Settings needed to automate the TrafficLenz download."""

    portal_url: str = "https://www.trafficlenz.com/"
    username: str = ""
    password: str = ""
    survey_id: str = "DC513DL01"
    save_dir: str = "data"
    save_filename: str = "latest_survey.xlsx"
    headless: bool = True
    timeout_ms: int = 45_000

    @property
    def session_path(self) -> Path:
        return Path(self.save_dir) / "session.json"


# ---------------------------------------------------------------------------
# SESSION CHECK & INTERACTIVE LOGIN
# ---------------------------------------------------------------------------
# CLOUD DEPLOYMENT & SESSION HELPERS
# ---------------------------------------------------------------------------
def _ensure_cloud_session(config: TrafficLenzConfig) -> None:
    """If running on Streamlit Cloud and TL_SESSION_JSON is in secrets, write to disk."""
    if not config.session_path.exists():
        try:
            import streamlit as st
            import json
            session_val = st.secrets.get("TL_SESSION_JSON")
            if session_val:
                Path(config.save_dir).mkdir(parents=True, exist_ok=True)
                with open(config.session_path, "w", encoding="utf-8") as f:
                    if isinstance(session_val, (dict, list)):
                        json.dump(session_val, f, indent=2)
                    else:
                        f.write(str(session_val).strip("'\""))
                logger.info("Restored session from Streamlit Secrets (TL_SESSION_JSON).")
        except Exception as e:
            logger.warning("Could not restore cloud session: %s", e)


def _ensure_chromium_installed() -> None:
    """Automatically install Chromium on Linux cloud containers if missing."""
    if not PLAYWRIGHT_AVAILABLE:
        return
    import subprocess
    import sys
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            b.close()
    except Exception as e:
        logger.info("Playwright Chromium browser binary not found (%s). Installing now...", e)
        try:
            cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info("Playwright Chromium installed successfully: %s", res.stdout)
        except Exception as install_err:
            logger.error("Failed to auto-install chromium: %s", install_err)


# Run check on import in cloud environments
if PLAYWRIGHT_AVAILABLE:
    import sys
    if sys.platform.startswith("linux"):
        _ensure_chromium_installed()


def has_saved_session(config: TrafficLenzConfig) -> bool:
    """Return True if session.json exists or is provided in secrets."""
    _ensure_cloud_session(config)
    return config.session_path.exists()


def perform_interactive_login(config: TrafficLenzConfig, wait_timeout_sec: int = 180) -> bool:
    """
    Open visible browser for one-time manual login (to solve reCAPTCHA).
    Saves session cookies to `data/session.json` upon successful login.
    """
    if not PLAYWRIGHT_AVAILABLE:
        raise ImportError("Playwright is not installed. Run: pip install playwright && playwright install chromium")

    _ensure_chromium_installed()

    # Cloud environment check: No GUI display on headless Linux servers
    import sys
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        raise EnvironmentError(
            "Interactive login cannot open a popup window on a cloud server without a display.\n"
            "👉 Please run 'python login.py' on your local computer once, then paste the contents of 'data/session.json' into Streamlit Cloud Secrets under TL_SESSION_JSON."
        )

    Path(config.save_dir).mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,  # Visible browser for human captcha solving
            args=["--ignore-certificate-errors", "--disable-web-security"],
        )
        context = browser.new_context(accept_downloads=True, ignore_https_errors=True)
        page = context.new_page()

        try:
            logger.info("Opening login page: %s", config.portal_url)
            page.goto(config.portal_url, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            # Open modal
            page.evaluate("""() => {
                const btn = document.querySelector('#portal_login_btn');
                if (btn) {
                    btn.removeAttribute('disabled');
                    btn.click();
                }
            }""")
            page.wait_for_timeout(1000)

            # Pre-fill credentials
            try:
                page.locator("#loginbox input[name='email'], #email").first.fill(config.username)
                page.locator("#loginbox input[name='password'], #password").first.fill(config.password)
                logger.info("Pre-filled credentials into login modal.")
            except Exception as e:
                logger.warning("Could not prefill credentials: %s", e)

            logger.info("Waiting for user to solve CAPTCHA and log in...")

            # Wait for successful login (URL changes away from login page)
            logged_in = False
            iterations = max(1, wait_timeout_sec // 2)
            for _ in range(iterations):
                page.wait_for_timeout(2000)
                current_url = page.url
                if "/Home/" in current_url or "/dashboard" in current_url:
                    logged_in = True
                    break

            if logged_in:
                context.storage_state(path=str(config.session_path))
                logger.info("Session saved successfully to %s", config.session_path)
                return True
            else:
                logger.warning("Login timeout reached without detecting logged-in state.")
                return False

        finally:
            context.close()
            browser.close()


# ---------------------------------------------------------------------------
# AUTOMATED DOWNLOAD (USES SAVED SESSION & TARGET SURVEY CODE)
# ---------------------------------------------------------------------------
def download_excel_bytes(config: TrafficLenzConfig) -> Tuple[bytes, str]:
    """
    Download latest Excel file into memory (bytes) using the saved session.
    Automatically navigates: myDashboardView -> search survey_id -> map marker -> export report.

    Returns:
        (file_bytes, timestamp_str)
    """
    if not PLAYWRIGHT_AVAILABLE:
        raise ImportError("Playwright is not installed. Run: pip install playwright && playwright install chromium")

    Path(config.save_dir).mkdir(parents=True, exist_ok=True)
    _ensure_cloud_session(config)
    _ensure_chromium_installed()

    temp_file = Path(config.save_dir) / f"temp_{int(time.time())}.xlsx"

    with sync_playwright() as p:
        launch_kwargs = {
            "headless": config.headless,
            "args": [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--ignore-certificate-errors",
                "--disable-web-security",
            ],
        }
        for exe in ["/usr/bin/chromium", "/usr/bin/chromium-browser"]:
            if os.path.exists(exe):
                launch_kwargs["executable_path"] = exe
                logger.info("Using system Chromium at %s", exe)
                break

        browser = p.chromium.launch(**launch_kwargs)

        context_kwargs = {"accept_downloads": True, "ignore_https_errors": True}
        if config.session_path.exists():
            context_kwargs["storage_state"] = str(config.session_path)

        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        page.set_default_timeout(config.timeout_ms)

        try:
            survey_code = config.survey_id or "DC513DL01"

            # ── Step 1: Open myDashboardView ──────────────────────────────
            logger.info("1. Opening dashboard...")
            page.goto("https://www.trafficlenz.com/Home/myDashboardView", wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            # Check if redirected to login (session expired)
            if "/Home/userDashboard" not in page.url and "/Home/myDashboardView" not in page.url:
                raise PermissionError("Session expired or not logged in. Please click '🔑 Login / Connect' to re-authenticate.")

            # ── Step 2: Search for survey job code ────────────────────────
            logger.info("2. Searching survey job code: %s", survey_code)
            page.locator("#job_code").fill(survey_code)
            page.locator("#search_jobs").click()
            page.wait_for_timeout(2000)

            # ── Step 3: Click project item and submit view ────────────────
            logger.info("3. Selecting project...")
            page.locator(f"text={survey_code}").first.click()
            page.wait_for_timeout(1000)

            page.evaluate("""() => {
                const btn = document.querySelector('#submit_job_id');
                if (btn) {
                    btn.click();
                } else {
                    const f = document.querySelector('form');
                    if (f) f.submit();
                }
            }""")
            page.wait_for_timeout(5000)

            # ── Step 4: Click Map Marker on viewgraph ─────────────────────
            logger.info("4. Clicking Map Marker...")
            page.wait_for_selector(".mapboxgl-marker", state="visible", timeout=20000)
            page.evaluate("""() => {
                const marker = document.querySelector('.mapboxgl-marker');
                if (marker) {
                    marker.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                }
            }""")
            page.wait_for_timeout(2000)

            # ── Step 5: Expand task actions (+) ───────────────────────────
            logger.info("5. Expanding task actions (+)...")
            page.evaluate("""() => {
                const plus = Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('+'));
                if (plus) plus.click();
            }""")
            page.wait_for_timeout(1500)

            # ── Step 6: Trigger download ───────────────────────────────────
            logger.info("6. Triggering questionnaire report download...")
            with page.expect_download(timeout=config.timeout_ms) as dl_info:
                page.evaluate("""() => {
                    const dlBtn = document.querySelector('a[onclick*="downloadQuestionnaireReport"]');
                    if (dlBtn) {
                        dlBtn.click();
                    } else if (typeof downloadQuestionnaireReport === 'function') {
                        downloadQuestionnaireReport('93A8309C', '642AD95B');
                    }
                }""")

            download = dl_info.value
            download.save_as(str(temp_file))

            # Read into memory
            with open(temp_file, "rb") as f:
                file_bytes = f.read()

            logger.info("Successfully fetched %d bytes into memory.", len(file_bytes))

        finally:
            if temp_file.exists():
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
            context.close()
            browser.close()

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return file_bytes, timestamp


def download_latest_excel(config: TrafficLenzConfig) -> Tuple[str, str]:
    """
    Download and save latest survey Excel to data/latest_survey.xlsx.
    """
    file_bytes, timestamp = download_excel_bytes(config)
    save_path = Path(config.save_dir) / config.save_filename
    with open(save_path, "wb") as f:
        f.write(file_bytes)
    return str(save_path.resolve()), timestamp


# ---------------------------------------------------------------------------
# FACTORY FROM SECRETS
# ---------------------------------------------------------------------------
def _load_toml_secrets() -> dict:
    import tomllib
    script_dir = Path(__file__).parent
    toml_path = script_dir / ".streamlit" / "secrets.toml"
    if toml_path.exists():
        try:
            with open(toml_path, "rb") as f:
                return tomllib.load(f)
        except Exception:
            pass
    return {}


def config_from_secrets() -> TrafficLenzConfig:
    toml_data = _load_toml_secrets()

    def _get(key: str, default: str = "") -> str:
        try:
            import streamlit as st
            val = st.secrets.get(key)
            if val:
                return str(val)
        except Exception:
            pass
        if key in toml_data:
            return str(toml_data[key])
        return os.environ.get(key, default)

    return TrafficLenzConfig(
        portal_url=_get("TL_PORTAL_URL", "https://www.trafficlenz.com/"),
        username=_get("TL_USERNAME"),
        password=_get("TL_PASSWORD"),
        survey_id=_get("TL_SURVEY_ID", "DC513DL01"),
        headless=True,
        save_dir=str(Path(__file__).parent / _get("TL_SAVE_DIR", "data")),
        save_filename=_get("TL_SAVE_FILENAME", "latest_survey.xlsx"),
    )


def config_is_valid(config: TrafficLenzConfig) -> Tuple[bool, str]:
    if not config.portal_url:
        return False, "TL_PORTAL_URL is not set in secrets.toml"
    if not config.username:
        return False, "TL_USERNAME is not set in secrets.toml"
    if not config.password:
        return False, "TL_PASSWORD is not set in secrets.toml"
    if not PLAYWRIGHT_AVAILABLE:
        return False, "Playwright not installed. Run: pip install playwright && playwright install chromium"
    return True, ""


# ---------------------------------------------------------------------------
# CLI TEST
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = config_from_secrets()
    ok, reason = config_is_valid(cfg)
    if not ok:
        print(f"❌ Config error: {reason}")
        sys.exit(1)

    if not has_saved_session(cfg):
        print("No saved session found. Performing interactive login...")
        success = perform_interactive_login(cfg)
        if not success:
            print("❌ Login failed or was cancelled.")
            sys.exit(1)

    print(f"Fetching latest survey data for '{cfg.survey_id}' from TrafficLenz...")
    data_bytes, ts = download_excel_bytes(cfg)
    print(f"✅ SUCCESS! Downloaded {len(data_bytes):,} bytes at {ts}")
