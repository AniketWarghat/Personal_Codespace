"""
login.py — One-Time Interactive Login & Session Saver for TrafficLenz
=====================================================================

Since TrafficLenz uses Google reCAPTCHA ("I am not a robot"), an automated
headless script cannot solve the captcha on its own.

This script:
  1. Opens a visible Chrome browser window.
  2. Opens the TrafficLenz portal and login modal.
  3. Pre-fills your Username and Password automatically.
  4. Waits for YOU to check the "I'm not a robot" captcha and click "Login".
  5. As soon as you're logged in, saves the session cookies to `data/session.json`.

After running this ONCE:
  All future downloads from the Streamlit dashboard (and downloader.py) will
  reuse `data/session.json` in the background with NO captcha and NO login prompts!

Run:
    python login.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

from downloader import config_from_secrets, config_is_valid, PLAYWRIGHT_AVAILABLE

if not PLAYWRIGHT_AVAILABLE:
    print("❌ Playwright is not installed.")
    print("Run:  pip install playwright && playwright install chromium")
    sys.exit(1)

from playwright.sync_api import sync_playwright


def interactive_login():
    cfg = config_from_secrets()
    ok, reason = config_is_valid(cfg)
    if not ok:
        print(f"❌ Config error: {reason}")
        print("Please check .streamlit/secrets.toml")
        sys.exit(1)

    save_dir = Path(cfg.save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    session_file = save_dir / "session.json"

    print("=" * 65)
    print("🔑 TrafficLenz Interactive Login Helper")
    print("=" * 65)
    print(f"Portal URL : {cfg.portal_url}")
    print(f"Username   : {cfg.username}")
    print(f"Saving to  : {session_file}")
    print()
    print("👉 A browser window is opening now.")
    print("👉 Username & Password will be filled automatically.")
    print("👉 Simply click the 'I am not a robot' reCAPTCHA and click Login.")
    print("=" * 65)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,  # Visible browser for human captcha solving
            args=[
                "--ignore-certificate-errors",
                "--disable-web-security",
            ],
        )
        context = browser.new_context(
            accept_downloads=True,
            ignore_https_errors=True,
        )
        page = context.new_page()

        try:
            logger.info("Opening %s...", cfg.portal_url)
            page.goto(cfg.portal_url, wait_until="domcontentloaded")
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

            # Auto-fill credentials
            try:
                page.locator("#loginbox input[name='email'], #email").first.fill(cfg.username)
                page.locator("#loginbox input[name='password'], #password").first.fill(cfg.password)
                logger.info("✅ Pre-filled Username and Password into the login box.")
            except Exception as e:
                logger.warning("Could not auto-fill credentials: %s", e)

            print("\n⏳ Waiting for you to solve the CAPTCHA and click Login...")

            # Wait for successful login (URL changes away from login page or session cookies set)
            # Max wait 3 minutes
            logged_in = False
            for _ in range(90):  # 90 * 2s = 180s
                page.wait_for_timeout(2000)
                current_url = page.url
                
                # Check if URL changed to dashboard/viewgraph or user is logged in
                if cfg.login_success_url_fragment and cfg.login_success_url_fragment in current_url:
                    logged_in = True
                    break
                elif "/Home/" in current_url or "/dashboard" in current_url or current_url.rstrip("/") != cfg.portal_url.rstrip("/"):
                    logged_in = True
                    break

            if logged_in:
                # Save session cookies
                context.storage_state(path=str(session_file))
                print("\n" + "=" * 65)
                print(f"🎉 LOGIN SUCCESSFUL! Session saved to: {session_file}")
                print("All future downloads in Streamlit will now run automatically!")
                print("=" * 65)
            else:
                print("\n⚠️ Login timed out or was not completed.")

        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    interactive_login()

