"""One-off job: inputs for adding Jakarta (261 kelurahan) to the analysis.

Reads analysis/raw/jakarta/points.json and writes, next to it:
  elevation_jakarta.json   Copernicus DEM elevation (m) per kelurahan point (Open-Meteo Elevation API)
  at_sample_hod.json       hour-of-day mean apparent temperature (deg C), 22 Aug-22 Nov 2026 WIB,
                           at 30 Bogor + 30 Jakarta sample points (Open-Meteo historical forecast API)
No API key needed.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "analysis", "raw", "jakarta")
START, END = "2026-08-22", "2026-11-22"


def get(url, params):
    q = urllib.parse.urlencode(params)
    for i in range(6):
        try:
            with urllib.request.urlopen(f"{url}?{q}", timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(30 * (i + 1)); continue
            print(e.read()[:300]); raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(30 * (i + 1))
    sys.exit(f"unreachable: {url}")


def main():
    pts = json.load(open(os.path.join(DIR, "points.json")))

    elev = {}
    J = pts["jakarta"]
    for i in range(0, len(J), 100):
        b = J[i:i + 100]
        r = get("https://api.open-meteo.com/v1/elevation",
                {"latitude": ",".join(str(p[1]) for p in b), "longitude": ",".join(str(p[2]) for p in b)})
        for p, e in zip(b, r["elevation"]):
            elev[p[0]] = e
        time.sleep(2)
    json.dump(elev, open(os.path.join(DIR, "elevation_jakarta.json"), "w"), separators=(",", ":"))
    print(f"elevation: {len(elev)} points, min {min(elev.values())} max {max(elev.values())}")

    samples = [("jkt", p[0], p[1], p[2]) for p in pts["sample_jakarta"]] + \
              [("bgr", p[0], p[1], p[2]) for p in pts["sample_bogor"]]
    out = []
    for i in range(0, len(samples), 10):
        b = samples[i:i + 10]
        r = get("https://historical-forecast-api.open-meteo.com/v1/forecast",
                {"latitude": ",".join(str(s[2]) for s in b), "longitude": ",".join(str(s[3]) for s in b),
                 "hourly": "apparent_temperature", "start_date": START, "end_date": END,
                 "timezone": "Asia/Jakarta"})
        r = r if isinstance(r, list) else [r]
        for s, loc in zip(b, r):
            sums, n = [0.0] * 24, [0] * 24
            for t, v in zip(loc["hourly"]["time"], loc["hourly"]["apparent_temperature"]):
                if v is None:
                    continue
                h = int(t[11:13]); sums[h] += v; n[h] += 1
            out.append({"region": s[0], "id": s[1], "lat": s[2], "lon": s[3], "model_elev": loc.get("elevation"),
                        "hod": [round(sums[h] / n[h], 3) if n[h] else None for h in range(24)], "n": sum(n)})
        time.sleep(10)
    json.dump(out, open(os.path.join(DIR, "at_sample_hod.json"), "w"), separators=(",", ":"))
    print(f"apparent temperature: {len(out)} points, hours per point {[o['n'] for o in out][:5]}...")


if __name__ == "__main__":
    main()
