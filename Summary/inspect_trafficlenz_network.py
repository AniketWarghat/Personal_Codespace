"""
inspect_trafficlenz_network.py
==============================
Intercepts and logs all network traffic, AJAX requests, WebSocket messages,
and JS function calls on TrafficLenz to uncover the underlying API endpoints.
"""

import json
import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

SESSION_PATH = Path("Summary/data/session.json")
SURVEY_CODE = "DC513DL01"

captured_requests = []

def run_inspection():
    if not SESSION_PATH.exists():
        print(f"❌ Session not found at {SESSION_PATH}")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-web-security", "--ignore-certificate-errors"]
        )
        context = browser.new_context(
            storage_state=str(SESSION_PATH),
            accept_downloads=True,
            ignore_https_errors=True
        )
        page = context.new_page()

        # Listen to all network requests & responses
        def on_request(request):
            url = request.url
            if not any(ext in url for ext in [".png", ".jpg", ".svg", ".woff", ".css", ".ico", "clarity.ms", "google-analytics"]):
                ct = request.headers.get("content-type", "").lower()
                post_data_str = None
                if "json" in ct or "form" in ct or "text" in ct:
                    try:
                        post_data_str = request.post_data
                    except Exception:
                        post_data_str = "[Binary or Gzip]"

                entry = {
                    "method": request.method,
                    "url": url,
                    "headers": request.headers,
                    "post_data": post_data_str,
                }
                captured_requests.append(entry)
                print(f"[REQ] {request.method} -> {url}")
                if post_data_str and post_data_str != "[Binary or Gzip]":
                    print(f"      Data: {post_data_str[:200]}")

        def on_response(response):
            url = response.url
            ct = response.headers.get("content-type", "")
            if "json" in ct or "javascript" in ct or "text" in ct:
                try:
                    # preview text for non-binary
                    if "application/octet" not in ct and "spreadsheetml" not in ct:
                        body_preview = response.text()[:250]
                        print(f"[RESP {response.status}] {url} ({ct})")
                        print(f"       Preview: {body_preview}")
                except Exception:
                    pass

        page.on("request", on_request)
        page.on("response", on_response)

        print("--- Step 1: Navigating to myDashboardView ---")
        page.goto("https://www.trafficlenz.com/Home/myDashboardView", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        print(f"--- Step 2: Searching Survey {SURVEY_CODE} ---")
        page.locator("#job_code").fill(SURVEY_CODE)
        page.locator("#search_jobs").click()
        page.wait_for_timeout(2000)

        print("--- Step 3: Selecting project and submitting ---")
        page.locator(f"text={SURVEY_CODE}").first.click()
        page.wait_for_timeout(1000)

        page.evaluate("""() => {
            const btn = document.querySelector('#submit_job_id');
            if (btn) btn.click();
            else {
                const f = document.querySelector('form');
                if (f) f.submit();
            }
        }""")
        page.wait_for_timeout(5000)

        print("--- Step 4: Inspecting page JavaScript functions on viewgraph ---")
        # Extract JS source code of downloadQuestionnaireReport and related functions
        js_functions = page.evaluate("""() => {
            return {
                downloadQuestionnaireReport_src: typeof downloadQuestionnaireReport === 'function' ? downloadQuestionnaireReport.toString() : 'not_found',
                all_global_functions: Object.keys(window).filter(k => typeof window[k] === 'function' && !k.startsWith('webkit') && !k.startsWith('on')),
                page_forms: Array.from(document.querySelectorAll('form')).map(f => ({ action: f.action, method: f.method, id: f.id, inputs: Array.from(f.elements).map(e => ({ name: e.name, value: e.value, type: e.type })) })),
                ajax_urls_in_scripts: Array.from(document.querySelectorAll('script')).map(s => s.innerText).filter(t => t.includes('downloadQuestionnaireReport') || t.includes('$.ajax') || t.includes('fetch'))
            };
        }""")

        print("\n========================================================")
        print("🔍 JAVASCRIPT SOURCE OF downloadQuestionnaireReport:")
        print("========================================================")
        print(js_functions.get("downloadQuestionnaireReport_src"))
        print("\n🔍 FORMS FOUND ON PAGE:")
        print(json.dumps(js_functions.get("page_forms"), indent=2))

        print("\n--- Step 5: Clicking Map Marker ---")
        page.wait_for_selector(".mapboxgl-marker", state="visible", timeout=20000)
        page.evaluate("""() => {
            const marker = document.querySelector('.mapboxgl-marker');
            if (marker) marker.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
        }""")
        page.wait_for_timeout(2000)

        print("--- Step 6: Expanding + Actions ---")
        page.evaluate("""() => {
            const plus = Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').includes('+'));
            if (plus) plus.click();
        }""")
        page.wait_for_timeout(1500)

        # Inspect the HTML of the popup menu to see the exact href/onclick on the download button
        btn_html = page.evaluate("""() => {
            const btn = document.querySelector('a[onclick*="downloadQuestionnaireReport"]');
            return btn ? { outerHTML: btn.outerHTML, href: btn.href, onclick: btn.getAttribute('onclick') } : 'Button not found';
        }""")
        print("\n🔍 DOWNLOAD BUTTON HTML & ONCLICK:")
        print(json.dumps(btn_html, indent=2))

        print("\n--- Step 7: Triggering download to capture final request ---")
        with page.expect_download(timeout=45000) as dl_info:
            page.evaluate("""() => {
                const dlBtn = document.querySelector('a[onclick*="downloadQuestionnaireReport"]');
                if (dlBtn) dlBtn.click();
            }""")

        dl = dl_info.value
        print(f"✅ Download captured: {dl.suggested_filename}")

        # Save all captured requests to JSON for analysis
        with open("Summary/data/captured_network.json", "w", encoding="utf-8") as f:
            json.dump(captured_requests, f, indent=2)
        print("Saved network log to Summary/data/captured_network.json")

        browser.close()

if __name__ == "__main__":
    run_inspection()
