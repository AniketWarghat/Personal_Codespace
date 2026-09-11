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
import json
import re
import urllib.request
import urllib.parse

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
    survey_id: str = "DC513MH06"
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
    """Restore session cookies from Streamlit Secrets to disk.

    Always called before each sync. Preferred approach:
        TL_SESSIONID = "o0rvfmtu1v7ewpy6lfq28r9bwuecnn53"
        TL_CSRFTOKEN = "7wQnfq95xSDIJX2KKaotkCfunXeeGXGZ"

    These are plain short strings — zero TOML/JSON encoding issues.
    If present in secrets they ALWAYS overwrite any existing session file
    (ensures stale or corrupt files are replaced on every sync).
    """
    import re as _re

    try:
        try:
            import streamlit as st
        except ImportError:
            st = None

        if st is not None:
            # ── Preferred: two simple plain strings ──────────────────────────────
            sessionid = str(st.secrets.get("TL_SESSIONID", "")).strip()
            csrftoken = str(st.secrets.get("TL_CSRFTOKEN", "")).strip()

            if sessionid and csrftoken:
                # Always write fresh — don't trust whatever is on disk
                Path(config.save_dir).mkdir(parents=True, exist_ok=True)
                minimal_session = {
                    "cookies": [
                        {
                            "name": "sessionid",
                            "value": sessionid,
                            "domain": "www.trafficlenz.com",
                            "path": "/",
                            "expires": -1,
                            "httpOnly": True,
                            "secure": False,
                            "sameSite": "Lax",
                        },
                        {
                            "name": "csrftoken",
                            "value": csrftoken,
                            "domain": "www.trafficlenz.com",
                            "path": "/",
                            "expires": -1,
                            "httpOnly": False,
                            "secure": False,
                            "sameSite": "Lax",
                        },
                    ],
                    "origins": [],
                }
                with open(config.session_path, "w", encoding="utf-8") as f:
                    json.dump(minimal_session, f, indent=2)
                logger.info("Session written from TL_SESSIONID + TL_CSRFTOKEN secrets.")
                return

        # ── If session file already exists and is valid JSON, use it ─────────
        if config.session_path.exists():
            try:
                with open(config.session_path, "r", encoding="utf-8") as f:
                    json.load(f)  # validate
                logger.info("Using existing valid session file.")
                return
            except (json.JSONDecodeError, ValueError):
                logger.warning("Existing session file is corrupt — deleting and regenerating.")
                config.session_path.unlink(missing_ok=True)

        if st is not None:
            # ── Fallback: TL_SESSION_JSON large blob ─────────────────────────────
            session_val = st.secrets.get("TL_SESSION_JSON")
            if not session_val:
                return  # Nothing to do

            Path(config.save_dir).mkdir(parents=True, exist_ok=True)
            if isinstance(session_val, (dict, list)):
                with open(config.session_path, "w", encoding="utf-8") as f:
                    json.dump(session_val, f, indent=2)
                logger.info("Session written from TL_SESSION_JSON (dict/list).")
                return

            raw = str(session_val).strip()
            # Validate; if TOML-corrupted, extract sessionid+csrftoken via regex
            try:
                json.loads(raw)
                with open(config.session_path, "w", encoding="utf-8") as f:
                    f.write(raw)
                logger.info("Session written from TL_SESSION_JSON (valid JSON string).")
            except json.JSONDecodeError:
                logger.warning("TL_SESSION_JSON is TOML-corrupted — extracting cookies via regex.")
                sid_m  = _re.search(r'"name"\s*:\s*"sessionid"\s*,\s*"value"\s*:\s*"([^"]+)"', raw)
                csrf_m = _re.search(r'"name"\s*:\s*"csrftoken"\s*,\s*"value"\s*:\s*"([^"]+)"', raw)
                if sid_m and csrf_m:
                    minimal = {
                        "cookies": [
                            {"name": "sessionid", "value": sid_m.group(1),
                             "domain": "www.trafficlenz.com", "path": "/",
                             "expires": -1, "httpOnly": True, "secure": False, "sameSite": "Lax"},
                            {"name": "csrftoken", "value": csrf_m.group(1),
                             "domain": "www.trafficlenz.com", "path": "/",
                             "expires": -1, "httpOnly": False, "secure": False, "sameSite": "Lax"},
                        ],
                        "origins": [],
                    }
                    with open(config.session_path, "w", encoding="utf-8") as f:
                        json.dump(minimal, f, indent=2)
                    logger.info("Session recovered from corrupt TL_SESSION_JSON via regex.")
                else:
                    raise ValueError(
                        "TL_SESSION_JSON is corrupt and sessionid/csrftoken could not be "
                        "extracted. Please add TL_SESSIONID and TL_CSRFTOKEN to Streamlit Secrets."
                    )

    except Exception as e:
        logger.warning("Could not restore cloud session: %s", e)
        if not config.session_path.exists():
            raise


def _ensure_chromium_installed() -> None:
    """Automatically install Chromium on Linux cloud containers if missing.

    NOTE: On Streamlit Cloud / headless Linux, Playwright's bundled Chromium shell
    requires system libraries (libglib-2.0.so.0, etc.) that are NOT installed.
    This function must NEVER try to launch a browser on those environments.
    """
    import sys
    # Hard guard: never attempt a browser launch on headless Linux (Streamlit Cloud)
    if sys.platform.startswith("linux") or not os.environ.get("DISPLAY"):
        raise RuntimeError(
            "Cannot launch Chromium on headless Linux / Streamlit Cloud. "
            "Use direct HTTP sync instead."
        )
    if not PLAYWRIGHT_AVAILABLE:
        return
    import subprocess
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            b.close()
    except Exception as e:
        logger.info("Playwright Chromium browser binary not found (%s). Installing now...", e)
        try:
            cmd = [sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info("Playwright Chromium & dependencies installed successfully: %s", res.stdout)
        except Exception as install_err:
            logger.error("Failed to auto-install chromium: %s", install_err)
            try:
                cmd_fallback = [sys.executable, "-m", "playwright", "install", "chromium"]
                subprocess.run(cmd_fallback, capture_output=True, text=True, check=True)
            except Exception:
                pass


# Do not eagerly launch or install Chromium on import
# Direct HTTP session download is used on cloud containers.


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
# AUTOMATED DOWNLOAD (DIRECT HTTP API)
# ---------------------------------------------------------------------------
def _direct_http_download(config: TrafficLenzConfig) -> Tuple[bytes, str]:
    """
    Downloads survey questionnaire report directly via HTTP session requests.
    Fast, reliable, and requires 0 browser / Chromium dependencies.
    """
    if not config.session_path.exists():
        raise FileNotFoundError(
            "Session file not found. Please paste TL_SESSION_JSON or TL_SESSIONID into Streamlit Secrets."
        )

    with open(config.session_path, "r", encoding="utf-8") as sf:
        s_data = json.load(sf)
    cookies_dict = {c["name"]: c["value"] for c in s_data.get("cookies", [])}
    cookie_hdr = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())
    csrf = cookies_dict.get("csrftoken", "")
    survey_code = config.survey_id or "DC513MH06"

    # 1. Fetch dashboard to find matching jobs
    dash_req = urllib.request.Request(
        "https://www.trafficlenz.com/Home/myDashboardView",
        headers={
            "Cookie": cookie_hdr,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        }
    )
    dash_html = urllib.request.urlopen(dash_req, timeout=25).read().decode("utf-8", errors="ignore")

    # Check for session expiration
    if "/portal_login_btn" in dash_html or "portal_login" in dash_html:
        raise PermissionError("TrafficLenz session expired. Please re-authenticate and update TL_SESSION_JSON / TL_SESSIONID.")

    # 2. Parse all candidate jobs matching survey_code
    rows = re.findall(r"<tr>(.*?)</tr>", dash_html, re.DOTALL)
    candidate_jobs = []
    for r in rows:
        m_id = re.search(r"submitThisJob\('([A-Za-z0-9]+)'\)", r)
        if m_id:
            jid = m_id.group(1)
            cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td.*?>(.*?)</td>", r, re.DOTALL)]
            cells = [c for c in cells if c]
            row_text = " ".join(cells)
            if survey_code.lower() in row_text.lower():
                score = 0
                if any(w in row_text.lower() for w in ["wtp", "questionnaire"]):
                    score += 20
                if "survey" in row_text.lower():
                    score += 5
                candidate_jobs.append((score, jid, row_text))

    candidate_jobs.sort(key=lambda x: x[0], reverse=True)
    if not candidate_jobs:
        raise ValueError(f"Job code '{survey_code}' not found in TrafficLenz dashboard.")

    logger.info("Direct HTTP: Found candidate jobs for %s: %s", survey_code, candidate_jobs)

    best_download = None  # (byte_length, dl_bytes, timestamp)

    # 3. For each candidate job, inspect sites and tasks
    for score, jid, row_text in candidate_jobs:
        logger.info("Checking job %s (%s)...", jid, row_text)
        sites_post = urllib.parse.urlencode({
            "job_id": jid,
            "csrfmiddlewaretoken": csrf,
        }).encode("utf-8")
        sites_req = urllib.request.Request(
            "https://www.trafficlenz.com/Home/getSitesOrTasks/",
            data=sites_post,
            headers={
                "Cookie": cookie_hdr,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Referer": "https://www.trafficlenz.com/Home/viewgraph",
                "X-CSRFToken": csrf,
                "X-Requested-With": "XMLHttpRequest",
            }
        )
        try:
            sites_res = urllib.request.urlopen(sites_req, timeout=15).read().decode("utf-8", errors="ignore")
            sites_data = json.loads(sites_res)
        except Exception as se:
            logger.warning("Failed to fetch sites for job %s: %s", jid, se)
            continue

        sites = sites_data.get("data", {}).get("sites", [])

        # Priority: Prioritize "WTP Survey" over empty sites like "RNI"
        def site_score(s):
            sn = s.get("site_name", "").lower()
            sc = 0
            if "wtp" in sn: sc += 20
            if "survey" in sn: sc += 10
            if "rni" in sn: sc -= 10
            return sc

        sites.sort(key=site_score, reverse=True)

        for site in sites:
            site_id = site.get("site_id")
            site_name = site.get("site_name", "")
            # Check tasks for this site
            task_post = urllib.parse.urlencode({
                "job_id": jid,
                "select_dropdown_sites": site_id,
                "csrfmiddlewaretoken": csrf,
            }).encode("utf-8")
            task_req = urllib.request.Request(
                "https://www.trafficlenz.com/Home/getSitesOrTasks/",
                data=task_post,
                headers={
                    "Cookie": cookie_hdr,
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Referer": "https://www.trafficlenz.com/Home/viewgraph",
                    "X-CSRFToken": csrf,
                    "X-Requested-With": "XMLHttpRequest",
                }
            )
            try:
                task_res = urllib.request.urlopen(task_req, timeout=15).read().decode("utf-8", errors="ignore")
                task_data = json.loads(task_res)
            except Exception as te:
                logger.warning("Failed to fetch tasks for site %s: %s", site_id, te)
                continue

            tasks = task_data.get("data", {}).get("task_types", [])

            # Prioritize task 86FE4915 or Questionnaire
            def task_score(t):
                tid = t.get("task_id", "")
                ttype = t.get("task_type", "").lower()
                sc = 0
                if tid == "86FE4915": sc += 30
                if "questionnaire" in ttype: sc += 15
                if "survey" in ttype: sc += 5
                return sc

            tasks.sort(key=task_score, reverse=True)

            for task in tasks:
                t_type = task.get("task_type", "")
                t_id = task.get("task_id", "")
                if "questionnaire" in t_type.lower() or "survey" in t_type.lower():
                    logger.info("Found Questionnaire Report: site=%s (%s), task=%s (%s). Downloading...",
                                site_id, site_name, t_id, t_type)
                    dl_post = urllib.parse.urlencode({
                        "site_id": site_id,
                        "task_id": t_id,
                        "csrfmiddlewaretoken": csrf,
                    }).encode("utf-8")
                    dl_req = urllib.request.Request(
                        "https://www.trafficlenz.com/Home/downloadQuestionnaireReport",
                        data=dl_post,
                        headers={
                            "Cookie": cookie_hdr,
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                            "Referer": "https://www.trafficlenz.com/Home/viewgraph",
                            "X-CSRFToken": csrf,
                            "X-Requested-With": "XMLHttpRequest",
                        }
                    )
                    try:
                        dl_bytes = urllib.request.urlopen(dl_req, timeout=90).read()
                    except Exception as de:
                        logger.warning("Failed to download report for task %s: %s", t_id, de)
                        continue

                    if dl_bytes.startswith(b"PK") and len(dl_bytes) > 2000:
                        from datetime import timezone, timedelta
                        ist = timezone(timedelta(hours=5, minutes=30))
                        timestamp = datetime.now(ist).strftime("%d-%m-%Y %I:%M:%S %p")
                        logger.info("Direct HTTP download candidate: site=%s (%s), task=%s -> %d bytes",
                                    site_id, site_name, t_id, len(dl_bytes))

                        # If file contains substantial survey data (>50KB), return immediately!
                        if len(dl_bytes) > 50000:
                            logger.info("Direct HTTP download successful with substantial data (%d bytes).", len(dl_bytes))
                            return dl_bytes, timestamp

                        if best_download is None or len(dl_bytes) > best_download[0]:
                            best_download = (len(dl_bytes), dl_bytes, timestamp)

    if best_download and best_download[0] > 2000:
        logger.info("Returning best download found (%d bytes).", best_download[0])
        return best_download[1], best_download[2]

    raise RuntimeError(f"Could not find an active Questionnaire export task for {survey_code}.")


def download_excel_bytes(config: TrafficLenzConfig) -> Tuple[bytes, str]:
    """
    Download latest Excel file into memory (bytes) using the saved session.
    Uses fast direct HTTP API calls (0 browser dependencies, 100% cloud-compatible).
    Falls back to Playwright only on desktop environments.

    Returns:
        (file_bytes, timestamp_str)
    """
    Path(config.save_dir).mkdir(parents=True, exist_ok=True)
    _ensure_cloud_session(config)

    # ── Attempt 1: Direct Fast HTTP Session Download (Instant, 0 RAM, 0 browser dependencies) ──
    try:
        return _direct_http_download(config)
    except (PermissionError, FileNotFoundError) as user_err:
        raise user_err
    except Exception as http_err:
        logger.warning("Direct HTTP session download failed: %s", http_err)
        import sys
        # On Linux/headless cloud containers (e.g. Streamlit Cloud), Playwright cannot launch without C libraries
        if sys.platform.startswith("linux") or not os.environ.get("DISPLAY"):
            raise RuntimeError(
                f"Direct HTTP sync failed: {http_err}. "
                "Please verify your session is valid by running 'python login.py' locally and updating TL_SESSION_JSON in Streamlit Secrets."
            )

    # ── Attempt 2: Full Headless Playwright Browser ────────────────────────────
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("Direct HTTP sync failed and Playwright is not available.")

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
            survey_code = config.survey_id or "DC513MH06"

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
            flow_file = Path(config.save_dir) / "flow_config.json"
            rec_btn_id = None
            if flow_file.exists():
                try:
                    with open(flow_file, "r", encoding="utf-8") as ff:
                        f_data = json.load(ff)
                        for c in f_data.get("clicks", []):
                            cid = c.get("id", "")
                            if cid.startswith("button_"):
                                rec_btn_id = cid
                                break
                except Exception:
                    pass

            page.evaluate("""(btnId) => {
                if (btnId) {
                    const b = document.getElementById(btnId);
                    if (b) { b.click(); return; }
                }
                const plus = Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('+'));
                if (plus) plus.click();
            }""", rec_btn_id)
            page.wait_for_timeout(1500)

            # ── Step 6: Trigger download ───────────────────────────────────
            logger.info("6. Triggering questionnaire report download...")
            with page.expect_download(timeout=config.timeout_ms) as dl_info:
                page.evaluate("""() => {
                    const dlBtn = document.querySelector('a[onclick*="downloadQuestionnaireReport"], button[onclick*="downloadQuestionnaireReport"]');
                    if (dlBtn) {
                        dlBtn.click();
                    } else {
                        const anyDl = Array.from(document.querySelectorAll('a, button')).find(
                            el => (el.innerText || '').toLowerCase().includes('download') || (el.getAttribute('onclick') || '').includes('download')
                        );
                        if (anyDl) anyDl.click();
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

    from datetime import timezone, timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    timestamp = datetime.now(ist).strftime("%d-%m-%Y %I:%M:%S %p")
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
    if not PLAYWRIGHT_AVAILABLE and not config.session_path.exists():
        return False, "Playwright not installed and no session cookies found. Please provide TL_SESSION_JSON in secrets or install playwright."
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
