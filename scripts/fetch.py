#!/usr/bin/env python3
"""Fetch ESA data for the estimate-accuracy analysis.

- Final (post-event, live-amended) Horaro schedules: real-ish lengths.
- Oengus submissions (runner estimates per category) for the 2-year window.
- Probe the donation tracker for actual run start/end times (best truth if open).

Polite pacing: ~1 request/second, sequential.
"""
import json, re, time, urllib.request, pathlib, sys

OUT = pathlib.Path(__file__).parent
UA = {"User-Agent": "esa-crew-corner-estimate-research/1.0 (fredrik@esamarathon.com)", "Accept": "application/json"}

def get(url, headers=None, retries=2):
    h = dict(UA)
    if headers: h.update(headers)
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read().decode("utf-8", "replace"), r.headers.get("Content-Type", "")
        except Exception as e:
            if attempt == retries: raise
            time.sleep(2)

def get_json_following_meta(url):
    text, ctype = get(url)
    hops = 0
    while ("text/html" in ctype or text.lstrip().startswith("<")) and hops < 3:
        m = re.search(r"http-equiv=\"refresh\"[^>]*url='([^']+)'", text, re.I)
        if not m: raise RuntimeError(f"HTML without meta refresh: {url}")
        url = m.group(1) if m.group(1).startswith("http") else urllib.parse.urljoin(url, m.group(1))
        text, ctype = get(url)
        hops += 1
    return json.loads(text)

# ---- Horaro final schedules -------------------------------------------------
HORARO = ["2026-winter1", "2026-winter2", "2025-summer1", "2025-summer2"]
for slug in HORARO:
    p = OUT / f"horaro-{slug}.json"
    if p.exists() and p.stat().st_size > 10000:
        print(f"horaro {slug}: cached"); continue
    d = get_json_following_meta(f"https://horaro.net/-/api/v1/events/esa/schedules/{slug}")
    p.write_text(json.dumps(d))
    items = d["data"]["items"] if "data" in d else d["items"]
    print(f"horaro {slug}: {len(items)} rows")
    time.sleep(1)

# ---- Oengus submissions -----------------------------------------------------
MARATHONS = ["ESA-Sum24", "ESA-Sum25", "ESA-Win26", "ESA-Sum26"]
for slug in MARATHONS:
    p = OUT / f"oengus-{slug}.json"
    if p.exists() and p.stat().st_size > 10000:
        print(f"oengus {slug}: cached"); continue
    pages, page = [], 0
    while True:
        text, _ = get(f"https://oengus.io/api/v1/marathons/{slug}/submissions?page={page}",
                      headers={"Origin": "https://oengus.io", "Referer": "https://oengus.io/"})
        j = json.loads(text)
        content = j.get("content", j if isinstance(j, list) else [])
        if not content: break
        pages.extend(content)
        if j.get("last", True) or page > 200: break
        page += 1
        time.sleep(0.8)
    p.write_text(json.dumps(pages))
    print(f"oengus {slug}: {len(pages)} submissions ({page+1} pages)")
    time.sleep(1)

# ---- Tracker probe (actual run times, if public) ----------------------------
for base in ["https://donations.esamarathon.com"]:
    try:
        text, ctype = get(f"{base}/search/?type=event")
        if text.lstrip().startswith("["):
            events = json.loads(text)
            (OUT / "tracker-events.json").write_text(text)
            print(f"tracker: OPEN — {len(events)} events")
        else:
            print(f"tracker: responds but not JSON ({ctype})")
    except Exception as e:
        print(f"tracker: {e}")
print("DONE")
