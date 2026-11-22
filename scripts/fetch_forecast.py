"""Hourly job: forecast inputs for the web page (no API key needed).

- PM2.5: CAMS global forecast at the 12 grid nodes used for interpolation (Open-Meteo air-quality API).
- Apparent temperature: Open-Meteo forecast at 30 Bogor villages spread across the elevation range plus
  30 Jakarta kelurahan; for every forecast hour fit AT = a + b * elevation_km + c * [Jakarta], the same
  model as the analysis (c = coastal-city offset).
  The page applies a/b to each village's elevation, so visitors never call the API for 503 points.

Writes site/data/forecast.json. Points come from site/data/forecast_points.json.
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PTS = os.path.join(ROOT, "site", "data", "forecast_points.json")
OUT = os.path.join(ROOT, "site", "data", "forecast.json")
COMMON = {"past_days": 1, "forecast_days": 4, "timezone": "Asia/Jakarta"}


def fetch(base, lats, lons, extra):
    q = urllib.parse.urlencode({"latitude": ",".join(map(str, lats)), "longitude": ",".join(map(str, lons)),
                                **COMMON, **extra})
    for i in range(6):
        try:
            with urllib.request.urlopen(f"{base}?{q}", timeout=90) as r:
                j = json.load(r)
                return j if isinstance(j, list) else [j]
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(20 * (i + 1)); continue
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(20 * (i + 1))
    sys.exit(f"Open-Meteo unreachable: {base}")


def main():
    pts = json.load(open(PTS))
    nodes = pts["nodes"]
    atp = [p + [0] for p in pts["at_points"]] + [p + [1] for p in pts.get("at_points_jkt", [])]
    pm = fetch("https://air-quality-api.open-meteo.com/v1/air-quality", [n[0] for n in nodes], [n[1] for n in nodes],
               {"hourly": "pm2_5", "domains": "cams_global"})
    at = fetch("https://api.open-meteo.com/v1/forecast", [p[0] for p in atp], [p[1] for p in atp],
               {"hourly": "apparent_temperature"})
    times = pm[0]["hourly"]["time"]
    if at[0]["hourly"]["time"][:len(times)] != times[:len(at[0]["hourly"]["time"])]:
        sys.exit("time axes differ between the two APIs")
    n = min(len(times), len(at[0]["hourly"]["time"]))

    elev = [p[2] / 1000 for p in atp]
    jk = [p[3] for p in atp]
    a_s, b_s, c_s, r2s = [], [], [], []
    for t in range(n):
        rows = [(1.0, e, j, loc["hourly"]["apparent_temperature"][t]) for e, j, loc in zip(elev, jk, at)
                if loc["hourly"]["apparent_temperature"][t] is not None]
        if len(rows) < 15:
            a_s.append(None); b_s.append(None); c_s.append(None); continue
        # normal equations for y = a + b*elev + c*jkt
        X = [r[:3] for r in rows]; Y = [r[3] for r in rows]
        A = [[sum(x[i] * x[k] for x in X) for k in range(3)] for i in range(3)]
        v = [sum(x[i] * y for x, y in zip(X, Y)) for i in range(3)]
        M = [A[i] + [v[i]] for i in range(3)]
        for i in range(3):
            piv = max(range(i, 3), key=lambda r: abs(M[r][i])); M[i], M[piv] = M[piv], M[i]
            for r in range(3):
                if r != i:
                    f = M[r][i] / M[i][i]
                    M[r] = [M[r][q] - f * M[i][q] for q in range(4)]
        a, b, c = (M[i][3] / M[i][i] for i in range(3))
        my = sum(Y) / len(Y); ss = sum((y - my) ** 2 for y in Y)
        r2s.append(1 - sum((y - a - b * x[1] - c * x[2]) ** 2 for x, y in zip(X, Y)) / ss if ss else 1)
        a_s.append(round(a, 2)); b_s.append(round(b, 2)); c_s.append(round(c, 2))

    out = {"generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "time0": times[0], "hours": n,
           "pm": [[None if v is None else round(v, 1) for v in node["hourly"]["pm2_5"][:n]] for node in pm],
           "at_a": a_s, "at_b": b_s, "at_c": c_s,
           "at_r2_median": round(sorted(r2s)[len(r2s) // 2], 3) if r2s else None}
    json.dump(out, open(OUT, "w"), separators=(",", ":"))
    print(f"{n} hours from {times[0]}, AT fit median R2 {out['at_r2_median']}")


if __name__ == "__main__":
    main()
