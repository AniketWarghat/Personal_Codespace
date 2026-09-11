"""
record_flow.py -- Smart Step-by-Step Action & Download Recorder
==============================================================
Records your navigation to the survey download, saves fresh session cookies,
and auto-updates secrets.toml with the new TL_SESSION_JSON.

Run:
    python record_flow.py
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

from downloader import config_from_secrets, config_is_valid, PLAYWRIGHT_AVAILABLE

if not PLAYWRIGHT_AVAILABLE:
    print("[ERROR] Playwright is not installed.")
    print("Run:  pip install playwright && playwright install chromium")
    sys.exit(1)


def update_secrets_toml(session_json: str):
    """Inject/replace TL_SESSION_JSON in .streamlit/secrets.toml."""
    secrets_path = Path(__file__).parent / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        print(f"[WARN] secrets.toml not found at {secrets_path} - skipping auto-update.")
        return

    content = secrets_path.read_text(encoding="utf-8")

    # Escape backslashes and quotes for TOML multiline string
    toml_value = f'"""{session_json}"""'

    if "TL_SESSION_JSON" in content:
        # Replace existing value (handles both single-line and multiline)
        content = re.sub(
            r'TL_SESSION_JSON\s*=\s*""".*?"""',
            f'TL_SESSION_JSON = {toml_value}',
            content,
            flags=re.DOTALL,
        )
        content = re.sub(
            r'TL_SESSION_JSON\s*=\s*"[^"]*"',
            f'TL_SESSION_JSON = {toml_value}',
            content,
        )
    else:
        content += f"\nTL_SESSION_JSON = {toml_value}\n"

    secrets_path.write_text(content, encoding="utf-8")
    print(f"[OK] secrets.toml updated with new TL_SESSION_JSON at: {secrets_path}")


def record():
    cfg = config_from_secrets()
    ok, reason = config_is_valid(cfg)
    if not ok:
        print(f"[ERROR] Config error: {reason}")
        sys.exit(1)

    save_dir = Path(cfg.save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    session_file = save_dir / "session.json"
    flow_file = save_dir / "flow_config.json"

    print("\n" + "=" * 70)
    print("[RECORD] TrafficLenz Navigation & Download Flow Recorder")
    print("=" * 70)
    print("1. A browser window will open.")
    print("2. If not logged in, solve the CAPTCHA and click Login.")
    print("3. Navigate to your survey and click the Download button.")
    print("4. Every click will be recorded. Session will be auto-saved.")
    print("=" * 70 + "\n")

    recorded_clicks = []
    recorded_download_info = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--ignore-certificate-errors", "--disable-web-security"],
        )

        context_kwargs = {"accept_downloads": True, "ignore_https_errors": True}
        if session_file.exists():
            context_kwargs["storage_state"] = str(session_file)

        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        def record_click_event(click_data):
            tag  = click_data.get("tag", "")
            text = click_data.get("text", "")
            eid  = click_data.get("id", "")
            print(f"  [CLICK] <{tag}> '{text}' id='{eid}'")
            recorded_clicks.append(click_data)

        page.expose_function("py_record_click", record_click_event)

        page.add_init_script("""
            document.addEventListener('click', (e) => {
                const el = e.target.closest('button, a, input[type=button], input[type=submit], select, .btn, [onclick], li') || e.target;
                const data = {
                    tag:  el.tagName ? el.tagName.toLowerCase() : '',
                    id:   el.id || '',
                    cls:  el.className || '',
                    name: el.name || '',
                    text: (el.innerText || el.value || el.title || el.getAttribute('aria-label') || '').trim().slice(0, 80),
                    href: el.getAttribute('href') || '',
                    selector: el.id ? '#' + el.id : (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).join('.') : '')
                };
                if (window.py_record_click) window.py_record_click(data);
            }, true);
        """)

        def on_download(download):
            url      = download.url
            filename = download.suggested_filename
            print(f"\n[DOWNLOAD] Detected!")
            print(f"  URL      : {url}")
            print(f"  Filename : {filename}")

            test_path = save_dir / "latest_survey.xlsx"
            download.save_as(str(test_path))
            size = test_path.stat().st_size
            print(f"  Saved to : {test_path} ({size:,} bytes)")

            recorded_download_info["download_url"] = url
            recorded_download_info["filename"]     = filename
            recorded_download_info["final_url"]    = page.url

        page.on("download", on_download)

        try:
            logger.info("Opening TrafficLenz...")
            page.goto(cfg.portal_url, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            # If not on dashboard, try to open login modal & pre-fill
            if "/Home/userDashboard" not in page.url and "/Home/viewgraph" not in page.url and "/Home/myDashboardView" not in page.url:
                page.evaluate("""() => {
                    const btn = document.querySelector('#portal_login_btn');
                    if (btn) { btn.removeAttribute('disabled'); btn.click(); }
                }""")
                page.wait_for_timeout(1000)
                try:
                    page.locator("#loginbox input[name='email'], #email").first.fill(cfg.username)
                    page.locator("#loginbox input[name='password'], #password").first.fill(cfg.password)
                    logger.info("[OK] Pre-filled Username & Password.")
                except Exception:
                    pass

            print("\n>>> Navigate in the browser to your survey and click Download.")
            print(">>> Waiting up to 5 minutes for a download event...")

            start_time = time.time()
            while time.time() - start_time < 300:
                if recorded_download_info.get("filename"):
                    break
                page.wait_for_timeout(1000)

            # Always save session cookies (even if download timed out)
            context.storage_state(path=str(session_file))
            logger.info("Session saved to %s", session_file)

            if recorded_download_info.get("filename"):
                flow_data = {
                    "recorded_at":  time.strftime("%Y-%m-%d %H:%M:%S"),
                    "start_url":    cfg.portal_url,
                    "final_url":    recorded_download_info.get("final_url", page.url),
                    "download_url": recorded_download_info.get("download_url", ""),
                    "clicks":       recorded_clicks,
                }
                with open(flow_file, "w", encoding="utf-8") as f:
                    json.dump(flow_data, f, indent=2)

                print("\n" + "=" * 70)
                print("[SUCCESS] Flow and session recorded!")
                print(f"  Session : {session_file}")
                print(f"  Flow    : {flow_file}")
                print(f"  Clicks  : {len(recorded_clicks)}")
                print("=" * 70)
            else:
                print("\n[WARN] No download detected — but session was still saved.")

            # Auto-update secrets.toml with new session
            with open(session_file, "r", encoding="utf-8") as f:
                session_data = json.load(f)
            session_json_str = json.dumps(session_data)

            update_secrets_toml(session_json_str)

            print("\n" + "=" * 70)
            print("[NEXT STEPS] To refresh Streamlit Cloud:")
            print("  1. The local secrets.toml has been updated automatically.")
            print("  2. Also paste the JSON below into Streamlit Cloud Secrets")
            print("     (App Settings -> Secrets -> TL_SESSION_JSON = <paste>)")
            print("=" * 70)
            print(session_json_str)
            print("=" * 70 + "\n")

        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    record()
