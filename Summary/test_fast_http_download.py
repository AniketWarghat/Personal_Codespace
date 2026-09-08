"""
test_fast_http_download.py
==========================
Tests direct HTTP POST to TrafficLenz downloadQuestionnaireReport
using session cookies without launching Playwright.
"""

import json
import os
import time
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

with open("Summary/data/session.json", "r", encoding="utf-8") as f:
    session_data = json.load(f)

s = requests.Session()
cookies_dict = {}
for c in session_data.get("cookies", []):
    s.cookies.set(c["name"], c["value"], domain=c.get("domain", "www.trafficlenz.com"))
    cookies_dict[c["name"]] = c["value"]

csrf_token = cookies_dict.get("csrftoken", "")
print(f"Loaded {len(cookies_dict)} cookies. CSRF: {csrf_token}")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.trafficlenz.com/Home/viewgraph",
    "Origin": "https://www.trafficlenz.com",
    "X-CSRFToken": csrf_token,
    "X-Requested-With": "XMLHttpRequest",
}

# 1. Test getJobSiteDetails
url_details = "https://www.trafficlenz.com/Home/getJobSiteDetails"
r_details = s.post(
    url_details,
    data={
        "csrfmiddlewaretoken": csrf_token,
        "job_id": "7676D2",
        "job_code": "DC513DL01",
        "job_name": "DC513DL01 - Delhi OD",
        "page_no": "1"
    },
    headers=headers,
    verify=False,
    timeout=15
)
print(f"\n1. getJobSiteDetails: {r_details.status_code}")
try:
    print("   JSON response preview:", json.dumps(r_details.json(), indent=2)[:300])
except Exception:
    print("   Text preview:", r_details.text[:200])

# 2. Test direct downloadQuestionnaireReport via multipart POST
url_dl = "https://www.trafficlenz.com/Home/downloadQuestionnaireReport"
t0 = time.time()
r_dl = s.post(
    url_dl,
    data={
        "site_id": "93A8309C",
        "task_id": "642AD95B",
        "csrfmiddlewaretoken": csrf_token,
    },
    headers=headers,
    verify=False,
    timeout=30
)
t_elapsed = time.time() - t0
print(f"\n2. downloadQuestionnaireReport: {r_dl.status_code} in {t_elapsed:.2f}s")
print(f"   Content-Type: {r_dl.headers.get('Content-Type')}")
print(f"   Content-Length: {len(r_dl.content):,} bytes")

if len(r_dl.content) > 10000 and "spreadsheetml" in r_dl.headers.get("Content-Type", ""):
    print("   🎉 SUCCESS! Direct HTTP download works! No Playwright browser required!")
    with open("Summary/data/test_fast_survey.xlsx", "wb") as f_out:
        f_out.write(r_dl.content)
    print("   Saved to Summary/data/test_fast_survey.xlsx")
else:
    print("   Response text preview:", r_dl.text[:300])

