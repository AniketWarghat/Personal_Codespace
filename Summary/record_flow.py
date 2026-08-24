"""
record_flow.py — Smart Step-by-Step Action & Download Recorder
==============================================================

What this does:
  1. Opens a visible Chrome browser.
  2. Uses your active session (or pre-fills credentials if login needed).
  3. Listens to EVERY click you make as you navigate to the survey and click Download.
  4. Records the exact button/link selectors and the download trigger into `data/flow_config.json`.
  5. On all future runs, `downloader.py` replays these exact clicks automatically in the background!

Run:
    python record_flow.py
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

from downloader import config_from_secrets, config_is_valid, PLAYWRIGHT_AVAILABLE

if not PLAYWRIGHT_AVAILABLE:
    print("❌ Playwright is not installed.")
    print("Run:  pip install playwright && playwright install chromium")
    sys.exit(1)


def record():
    cfg = config_from_secrets()
    ok, reason = config_is_valid(cfg)
    if not ok:
        print(f"❌ Config error: {reason}")
        sys.exit(1)

    save_dir = Path(cfg.save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    session_file = save_dir / "session.json"
    flow_file = save_dir / "flow_config.json"

    print("\n" + "=" * 70)
    print("🎥 TrafficLenz Navigation & Download Flow Recorder")
    print("=" * 70)
    print("1. A browser window will open.")
    print("2. If not logged in, solve the CAPTCHA and click Login.")
    print("3. Click through the website to your survey and click the Download button.")
    print("4. Every click you make will be recorded automatically!")
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

        # Expose Python function to record clicks from JavaScript
        def record_click_event(click_data):
            print(f"  👉 Clicked: [{click_data.get('tag')}] '{click_data.get('text')}' (id='{click_data.get('id')}', cls='{click_data.get('cls')}')")
            recorded_clicks.append(click_data)

        page.expose_function("py_record_click", record_click_event)

        # Inject click listener on every page navigation
        page.add_init_script("""
            document.addEventListener('click', (e) => {
                const el = e.target.closest('button, a, input[type=button], input[type=submit], select, .btn, [onclick], li') || e.target;
                const data = {
                    tag: el.tagName ? el.tagName.toLowerCase() : '',
                    id: el.id || '',
                    cls: el.className || '',
                    name: el.name || '',
                    text: (el.innerText || el.value || el.title || el.getAttribute('aria-label') || '').trim().slice(0, 80),
                    href: el.getAttribute('href') || '',
                    selector: el.id ? '#' + el.id : (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\\s+/).join('.') : '')
                };
                if (window.py_record_click) {
                    window.py_record_click(data);
                }
            }, true);
        """)

        # Listen to download event
        def on_download(download):
            url = download.url
            filename = download.suggested_filename
            print(f"\n📥 DOWNLOAD DETECTED!")
            print(f"   URL      : {url}")
            print(f"   Filename : {filename}")

            test_path = save_dir / "latest_survey.xlsx"
            download.save_as(str(test_path))
            size = test_path.stat().st_size
            print(f"   Saved to : {test_path} ({size:,} bytes)")

            recorded_download_info["download_url"] = url
            recorded_download_info["filename"] = filename
            recorded_download_info["final_url"] = page.url

        page.on("download", on_download)

        try:
            logger.info("Opening TrafficLenz...")
            page.goto(cfg.portal_url, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            # If login page, open modal and pre-fill credentials
            if "/Home/userDashboard" not in page.url and "/Home/viewgraph" not in page.url:
                page.evaluate("""() => {
                    const btn = document.querySelector('#portal_login_btn');
                    if (btn) {
                        btn.removeAttribute('disabled');
                        btn.click();
                    }
                }""")
                page.wait_for_timeout(1000)
                try:
                    page.locator("#loginbox input[name='email'], #email").first.fill(cfg.username)
                    page.locator("#loginbox input[name='password'], #password").first.fill(cfg.password)
                    logger.info("✅ Pre-filled Username & Password into login box.")
                except Exception:
                    pass

            print("\n👉 Please navigate on the page to your survey and click the Download button.")
            print("⏳ Waiting for download... (up to 5 minutes)")

            # Wait until download happens
            start_time = time.time()
            while time.time() - start_time < 300:
                if recorded_download_info.get("filename"):
                    break
                page.wait_for_timeout(1000)

            if recorded_download_info.get("filename"):
                # Save session cookies
                context.storage_state(path=str(session_file))

                # Save flow configuration
                flow_data = {
                    "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "start_url": cfg.portal_url,
                    "final_url": recorded_download_info.get("final_url", page.url),
                    "download_url": recorded_download_info.get("download_url", ""),
                    "clicks": recorded_clicks,
                }
                with open(flow_file, "w", encoding="utf-8") as f:
                    json.dump(flow_data, f, indent=2)

                print("\n" + "=" * 70)
                print("🎉 SUCCESS! Navigation flow and session successfully recorded!")
                print(f"📁 Session saved : {session_file}")
                print(f"📁 Flow config   : {flow_file}")
                print(f"🔢 Total clicks  : {len(recorded_clicks)}")
                print("=" * 70)
                print("\nYou can now click '🔄 Sync Data' in the Streamlit app anytime!")
            else:
                print("\n⚠️ No download was completed within the time limit.")

        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    record()
