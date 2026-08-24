"""
export_cookies.py
─────────────────
Run this ONCE manually on your local machine to grab your trafficlenz.com
session cookies after you log in normally in Chrome.

Steps:
    1.  pip install selenium webdriver-manager
    2.  python export_cookies.py
    3.  Log in manually in the Chrome window that opens (solve CAPTCHA yourself)
    4.  Press ENTER in this terminal when you're fully logged in
    5.  cookies.json is saved — copy it to the server

You only need to redo this when your session expires (usually 7–30 days).
"""

import json
import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

PORTAL_URL  = "https://www.trafficlenz.com"
COOKIE_FILE = Path(__file__).resolve().parent / "cookies.json"


def main():
    # Open a VISIBLE (non-headless) Chrome so you can log in manually
    opts = Options()
    opts.add_argument("--start-maximized")

    service = Service(ChromeDriverManager().install())
    driver  = webdriver.Chrome(service=service, options=opts)

    driver.get(PORTAL_URL)
    print("\n" + "="*55)
    print("  Browser opened at trafficlenz.com")
    print("  → Log in normally (solve the CAPTCHA yourself)")
    print("  → Once you are fully inside the portal, come back here")
    print("="*55)
    input("\n  Press ENTER when you are logged in …\n")

    cookies = driver.get_cookies()
    driver.quit()

    COOKIE_FILE.write_text(json.dumps(cookies, indent=2))
    print(f"✓ {len(cookies)} cookies saved to: {COOKIE_FILE}")
    print("  Copy cookies.json to your server's survey_app/ folder.")


if __name__ == "__main__":
    main()
