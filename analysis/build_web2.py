import json
import pandas as pd

s = json.load(open("processed/analysis_summary.json"))
d = pd.read_csv("processed/desa_metrics.csv")
prof = pd.DataFrame(s["cluster_profile"]).set_index("klaster")

# guard: cluster order must match the names hard-coded in the page
assert prof.elev_m.idxmax() == 0, "cluster 0 must be the highland cluster"
assert prof.pm_pagi_05_07.idxmax() == 2, "cluster 2 must be the morning-spike cluster"
assert prof.pm_mean.drop(2).idxmax() == 3, "cluster 3 must be the northern lowland cluster"

f = lambda x, n=1: f"{x:.{n}f}".replace(".", ",")
pmh, ath = s["pm_hod_region_mean"], s["at_hod_region_mean"]
kota = d[d.wilayah == "Kota Bogor"]
rep = {
    "__PM06__": f(pmh[6], 0), "__PM11__": f(pmh[11], 0), "__RATIO__": f(pmh[6] / pmh[11], 1),
    "__AT12__": f(ath[12]), "__PM17__": f(pmh[17], 0), "__AT17__": f(ath[17]),
    "__KOTA1718__": str(int(kota.jam_terbaik.isin([17, 18]).sum())),
    "__C0N__": str(int(prof.loc[0, "n_desa"])), "__C0A__": f"{prof.loc[0, 'luas_km2']:.0f}",
    "__C0L__": f(prof.loc[0, "n_jam_layak"]),
    "__ZERO__": str(s["desa_zero_layak"]), "__ZEROP__": f"{100 * s['desa_zero_layak'] / s['n_desa']:.0f}",
    "__SIL__": "; ".join(f"k={k}: {f(v, 3)}" for k, v in s["silhouette"].items()),
    "__MORAN__": f(s["moran_pm_knn6"]["I"], 2),
    "__HH__": str(s["lisa_counts"].get("Tinggi-Tinggi", 0)), "__LL__": str(s["lisa_counts"].get("Rendah-Rendah", 0)),
    "__NOWLBL__": "22 November 2026 pukul 12.00 WIB",
    "__RAW06__": f(s["pm_hod_region_mean_raw"][6], 0), "__RAW12__": f(s["pm_hod_region_mean_raw"][12], 0),
    "__CALMIN__": f(min(pmh), 0), "__CALMAX__": f(max(pmh), 0),
    "__AT05__": f(ath[5]), "__B05__": str(int((d.jam_terbaik == 5).sum())), "__B1820__": str(int(d.jam_terbaik.isin([18, 19, 20]).sum())),
    "__KOTA05__": str(int((kota.jam_terbaik == 5).sum())), "__C3L__": f(prof.loc[3, "n_jam_layak"]),
}
cal0 = json.load(open("processed/openaq_calibration.json"))
rep.update({"__OBS06__": f(cal0["obs_hod"][6], 0), "__OBS12__": f(cal0["obs_hod"][12], 0), "__OBS23__": f(cal0["obs_hod"][23], 0),
    "__OBS15__": f(cal0["obs_hod"][15], 0), "__CALDAYS__": str(cal0["n_days"]), "__OBSM__": f(cal0["obs_mean"]), "__CAMSM__": f(cal0["cams_mean"]),
    "__CFMIN__": f(min(cal0["cf"]), 2), "__CFMAX__": f(max(cal0["cf"]), 2), "__CALR__": f(cal0["daily_r"], 2)})
html = open("web/template_v2.html").read()
for k, v in rep.items():
    html = html.replace(k, v)
html = html.replace("__D3__", open("node_modules/d3/dist/d3.min.js").read())
html = html.replace("__TOPO__", open("node_modules/topojson-client/dist/topojson-client.min.js").read())
html = html.replace("__TOPOJSON__", open("processed/desa.topo.json").read())
html = html.replace("__KECLINES__", open("processed/kec_lines.json").read())
html = html.replace("__REGLINES__", open("processed/reg_lines.json").read())
pl = json.load(open("processed/web_payload.json"))
g = json.load(open("raw/desa_bogor_full.geojson"))
ll = {f["properties"]["code"]: (f["properties"]["lat"], f["properties"]["lon"]) for f in g["features"]}
for x in pl["desa"]:
    x["la"], x["lo"] = round(ll[x["c"]][0], 4), round(ll[x["c"]][1], 4)
html = html.replace("__LEAFLETCSS__", open("node_modules/leaflet/dist/leaflet.css").read())
html = html.replace("__LEAFLETJS__", open("node_modules/leaflet/dist/leaflet.js").read())
html = html.replace("__KECLABELS__", open("processed/kec_labels.json").read())
cal = json.load(open("processed/openaq_calibration.json"))
pl["cf"] = cal["cf"]
pl["calib"] = {"obs_hod": cal["obs_hod"], "cams_hod": cal["cams_hod"]}
st = pd.read_csv("raw/openaq/pm25_terbaru.csv")
st["has"] = st.pm25_terbaru.notna() & (st.pm25_terbaru >= 0)
st = st.sort_values(["has", "jam_tersedia"], ascending=False).drop_duplicates("location_id")
def wib(u):
    if not isinstance(u, str): return ""
    x = pd.Timestamp(u) + pd.Timedelta(hours=7)
    return f"{x.day} {['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des'][x.month-1]} {x.year}, {x.hour:02d}.00 WIB"
NOW = pd.Timestamp("2026-11-22T05:00:00Z")
pl["oaq"] = [{"n": r.nama.strip(), "la": round(r.lat, 5), "lo": round(r.lon, 5), "p": r.penyedia, "mon": bool(r.monitor_resmi),
              "act": bool(r.has and isinstance(r.waktu_terbaru_utc, str) and pd.Timestamp(r.waktu_terbaru_utc) >= NOW - pd.Timedelta(days=2)),
              "v": None if not r.has else round(float(r.pm25_terbaru), 1), "t": (r.waktu_terbaru_utc if r.has else r.terakhir) if isinstance(r.waktu_terbaru_utc if r.has else r.terakhir, str) else None,
              "used": int(r.sensor_id) in cal["sensors"]} for r in st.itertuples()]
html = html.replace("__PAYLOAD__", json.dumps(pl, separators=(",", ":")))
assert "__" not in html.replace("__proto__", "").split("<script>")[0], "unfilled placeholder in markup"
open("../site/index.html", "w").write(html)
print({k: v for k, v in rep.items()})
print(len(html) / 1e6, "MB")
