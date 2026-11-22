"""Weekly job: re-derive the hour-of-day CAMS -> OpenAQ calibration factors.

1. Find OpenAQ PM2.5 sensors in the Jabodetabek box with >= 10 days of hourly data in the last 92 days.
2. Fetch CAMS PM2.5 (Open-Meteo, cams_global) at each sensor for the same window.
3. Group sensors by the CAMS grid row whose native 0.4 deg cell they sit in (-6.0 = Jakarta, -6.4 = Depok /
   north Bogor). Row -6.8 (south Bogor) has no sensors and borrows -6.4.
4. Per row, pair hour by hour; factor for local hour h = mean(sensor) / mean(CAMS) over all pairs at h.

Writes site/data/calibration.json. If there is not enough data, the previous file is kept.
Needs OPENAQ_API_KEY (GitHub Actions secret).
"""
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

from fetch_openaq_latest import BBOX, get  # same API helper and search box

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "site", "data", "calibration.json")
DAYS = 92
MIN_SENSOR_HOURS = 240
MIN_PAIRS_PER_HOUR = 40
ROW_OF_NODE_LAT = {"-6.0": "-6.0", "-6.4": "-6.4", "-6.8": "-6.4"}


def open_meteo(lats, lons, start, end):
    q = urllib.parse.urlencode({"latitude": ",".join(f"{x:.5f}" for x in lats),
                                "longitude": ",".join(f"{x:.5f}" for x in lons),
                                "hourly": "pm2_5", "start_date": start, "end_date": end,
                                "timezone": "GMT", "domains": "cams_global"})
    for i in range(5):
        try:
            with urllib.request.urlopen("https://air-quality-api.open-meteo.com/v1/air-quality?" + q, timeout=120) as r:
                j = json.load(r)
                return j if isinstance(j, list) else [j]
        except (urllib.error.URLError, TimeoutError):
            time.sleep(10 * (i + 1))
    sys.exit("Open-Meteo unreachable")


def corr(a, b):
    n = len(a)
    if n < 5:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a)); sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    return None if sa == 0 or sb == 0 else sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)


def main():
    key = os.environ.get("OPENAQ_API_KEY", "").strip()
    if not key:
        sys.exit("OPENAQ_API_KEY is not set.")
    now = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    t0 = now - dt.timedelta(days=DAYS)

    locs = get("/locations", key, {"bbox": BBOX, "parameters_id": 2, "limit": 1000}).get("results", [])
    sensors = []
    for L in locs:
        for s in L.get("sensors", []):
            if (s.get("parameter") or {}).get("name") != "pm25":
                continue
            obs, page = {}, 1
            while True:
                r = get(f"/sensors/{s['id']}/hours", key, {"datetime_from": t0.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "datetime_to": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "limit": 1000, "page": page})
                rows = r.get("results", [])
                for x in rows:
                    t = ((x.get("period") or {}).get("datetimeFrom") or {}).get("utc")
                    v = x.get("value")
                    if t and v is not None and 0 <= v < 1000:
                        obs[t[:13]] = v           # key: "YYYY-MM-DDTHH"
                if len(rows) < 1000:
                    break
                page += 1
                time.sleep(1.1)
            time.sleep(1.1)
            if len(obs) >= MIN_SENSOR_HOURS:
                sensors.append({"id": s["id"], "name": (L.get("name") or "").strip(),
                                "lat": L["coordinates"]["latitude"], "lon": L["coordinates"]["longitude"], "obs": obs})
    print(f"{len(sensors)} sensors with >= {MIN_SENSOR_HOURS} h")
    if not sensors:
        print("No usable sensors; keeping previous calibration."); return

    cams = open_meteo([s["lat"] for s in sensors], [s["lon"] for s in sensors],
                      t0.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d"))
    prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
    rows = dict(prev.get("rows", {}))
    groups = defaultdict(list)
    for s, c in zip(sensors, cams):
        groups[f"{round(s['lat'] / 0.4) * 0.4:.1f}"].append((s, c))
    for key, members in sorted(groups.items()):
        so, sc, n = [0.0] * 24, [0.0] * 24, [0] * 24
        used, daily_o, daily_c = [], [], []
        for s, c in members:
            series = {t[:13]: v for t, v in zip(c["hourly"]["time"], c["hourly"]["pm2_5"]) if v is not None}
            day = defaultdict(lambda: [0.0, 0.0, 0])
            k = 0
            for t, o in s["obs"].items():
                if t not in series:
                    continue
                u = dt.datetime.fromisoformat(t + ":00:00+00:00") + dt.timedelta(hours=7)
                so[u.hour] += o; sc[u.hour] += series[t]; n[u.hour] += 1; k += 1
                d = day[u.date()]; d[0] += o; d[1] += series[t]; d[2] += 1
            for d in day.values():
                if d[2] >= 20:
                    daily_o.append(d[0] / d[2]); daily_c.append(d[1] / d[2])
            if k:
                used.append({"id": s["id"], "name": s["name"], "pairs": k})
        print(f"row {key}: {len(used)} sensors, pairs per hour min {min(n)}")
        if min(n) < MIN_PAIRS_PER_HOUR:
            print(f"  not enough pairs; keeping previous factors for row {key}"); continue
        obs_hod = [so[h] / n[h] for h in range(24)]; cams_hod = [sc[h] / n[h] for h in range(24)]
        r = corr(daily_o, daily_c)
        rows[key] = {"cf": [round(o / c, 3) for o, c in zip(obs_hod, cams_hod)],
                     "sensors": [u["id"] for u in used], "names": [u["name"] for u in used], "pairs": sum(n),
                     "obs_hod": [round(x, 1) for x in obs_hod], "cams_hod": [round(x, 1) for x in cams_hod],
                     "obs_mean": round(sum(so) / sum(n), 1), "cams_mean": round(sum(sc) / sum(n), 1),
                     "daily_r": None if r is None else round(r, 2), "n_days": len(daily_o)}
    if "-6.0" not in rows or "-6.4" not in rows:
        print("A needed row is missing; keeping previous calibration."); return
    out = {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "period": {"from": t0.strftime("%Y-%m-%d"), "to": now.strftime("%Y-%m-%d")},
           "rows": rows, "row_of_node_lat": ROW_OF_NODE_LAT,
           # flat copy of the -6.4 row for older pages
           **{k: rows["-6.4"][k] for k in ("cf", "obs_hod", "cams_hod", "obs_mean", "cams_mean", "daily_r", "n_days", "names")},
           "sensors": sorted({x for r in rows.values() for x in r["sensors"]})}
    json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: (v["obs_mean"], v["cams_mean"], v["daily_r"]) for k, v in rows.items()}))

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
