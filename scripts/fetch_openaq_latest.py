"""Hourly job: latest PM2.5 from every OpenAQ location around Bogor/Jabodetabek.

Writes site/data/openaq_latest.json, read by the web page. Needs the OPENAQ_API_KEY
environment variable (a GitHub Actions secret); the key never goes into any file.
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.openaq.org/v3"
BBOX = "106.30,-6.95,107.35,-6.00"          # Jabodetabek + Bogor (minLon,minLat,maxLon,maxLat)
ACTIVE_HOURS = 6                            # a sensor counts as active if it reported in the last 6 h
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "site", "data", "openaq_latest.json")
CAL = os.path.join(ROOT, "site", "data", "calibration.json")


def get(path, key, params=None, tries=6):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    for i in range(tries):
        req = urllib.request.Request(url, headers={"X-API-Key": key, "Accept": "application/json",
                                                   "User-Agent": "lari-sehat-bogor/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                sys.exit("OpenAQ rejected the API key (401). Check the OPENAQ_API_KEY secret.")
            if e.code in (408, 429, 500, 502, 503, 504):
                time.sleep(5 * (i + 1))
                continue
            raise
        except urllib.error.URLError:
            time.sleep(5 * (i + 1))
    sys.exit(f"Giving up on {path}")


def main():
    key = os.environ.get("OPENAQ_API_KEY", "").strip()
    if not key:
        sys.exit("OPENAQ_API_KEY is not set.")
    used = set(json.load(open(CAL)).get("sensors", [])) if os.path.exists(CAL) else set()
    now = dt.datetime.now(dt.timezone.utc)

    locs, page = [], 1
    while True:
        r = get("/locations", key, {"bbox": BBOX, "parameters_id": 2, "limit": 1000, "page": page})
        locs += r.get("results", [])
        if len(r.get("results", [])) < 1000:
            break
        page += 1

    out = []
    for L in locs:
        pm = [s["id"] for s in L.get("sensors", []) if (s.get("parameter") or {}).get("name") == "pm25"]
        if not pm:
            continue
        latest = {}
        r = get(f"/locations/{L['id']}/latest", key)
        for x in r.get("results", []):
            if x.get("sensorsId") in pm and x.get("value") is not None and x["value"] >= 0:
                latest[x["sensorsId"]] = (x["value"], (x.get("datetime") or {}).get("utc"))
        time.sleep(1.1)  # stay well under the OpenAQ rate limit
        # one marker per location: the PM2.5 sensor with the freshest reading
        best = max(latest.items(), key=lambda kv: kv[1][1] or "", default=None)
        sid, (val, t) = best if best else (pm[0], (None, (L.get("datetimeLast") or {}).get("utc")))
        act = False
        if val is not None and t:
            age = now - dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
            act = age <= dt.timedelta(hours=ACTIVE_HOURS)
        out.append({
            "n": (L.get("name") or "").strip(), "la": round(L["coordinates"]["latitude"], 5),
            "lo": round(L["coordinates"]["longitude"], 5), "p": (L.get("provider") or {}).get("name"),
            "mon": bool(L.get("isMonitor")), "act": act, "v": None if val is None else round(val, 1),
            "t": t, "used": sid in used or any(s in used for s in pm), "sensor": sid, "location": L["id"],
        })

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "bbox": BBOX, "stations": out},
              open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"{len(out)} locations, {sum(s['act'] for s in out)} active")


if __name__ == "__main__":
    main()
