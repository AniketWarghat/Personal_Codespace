from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger(__name__)

from downloader import config_from_secrets, config_is_valid, PLAYWRIGHT_AVAILABLE

if not PLAYWRIGHT_AVAILABLE:
    print('[ERROR] Playwright is not installed.')
    print('Run:  pip install playwright && playwright install chromium')
    sys.exit(1)

from playwright.sync_api import sync_playwright


def interactive_login():
    cfg = config_from_secrets()
    ok, reason = config_is_valid(cfg)
    if not ok:
        print(f'[ERROR] Config error: {reason}')
        print('Please check .streamlit/secrets.toml')
        sys.exit(1)

    save_dir = Path(cfg.save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    session_file = save_dir / 'session.json'

    print('=' * 65)
    print('[LOGIN] TrafficLenz Interactive Login Helper')
    print('=' * 65)
    print(f'Portal URL : {cfg.portal_url}')
    print(f'Username   : {cfg.username}')
    print(f'Saving to  : {session_file}')
    print()
    print('>>> A browser window is opening now.')
    print('>>> Username & Password will be filled automatically.')
    print(">>> Solve the CAPTCHA and click Login in the browser.")
    print('=' * 65)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=['--ignore-certificate-errors', '--disable-web-security'],
        )
        context = browser.new_context(accept_downloads=True, ignore_https_errors=True)
        page = context.new_page()

        try:
            logger.info('Opening %s...', cfg.portal_url)
            page.goto(cfg.portal_url, wait_until='domcontentloaded')
            page.wait_for_timeout(2000)

            page.evaluate("""() => {
                const btn = document.querySelector('#portal_login_btn');
                if (btn) { btn.removeAttribute('disabled'); btn.click(); }
            }""")
            page.wait_for_timeout(1000)

            try:
                page.locator("#loginbox input[name='email'], #email").first.fill(cfg.username)
                page.locator("#loginbox input[name='password'], #password").first.fill(cfg.password)
                logger.info('[OK] Pre-filled Username and Password.')
            except Exception as e:
                logger.warning('Could not auto-fill credentials: %s', e)

            print('\n[WAITING] Solve the CAPTCHA and click Login. You have 3 minutes...')

            logged_in = False
            for _ in range(90):
                page.wait_for_timeout(2000)
                current_url = page.url
                if '/Home/' in current_url or '/dashboard' in current_url or current_url.rstrip('/') != cfg.portal_url.rstrip('/'):
                    logged_in = True
                    break

            if logged_in:
                context.storage_state(path=str(session_file))
                print('\n' + '=' * 65)
                print(f'[SUCCESS] Session saved to: {session_file}')
                print('=' * 65)
                print('\nCopy the JSON below into Streamlit Secrets as TL_SESSION_JSON:')
                print('-' * 65)
                with open(session_file, 'r', encoding='utf-8') as f:
                    print(json.dumps(json.load(f)))
                print('-' * 65 + '\n')
            else:
                print('\n[WARNING] Login timed out.')

        finally:
            context.close()
            browser.close()


if __name__ == '__main__':
    interactive_login()
