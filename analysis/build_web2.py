import json
import pandas as pd

s = json.load(open("processed/analysis_summary.json"))
d = pd.read_csv("processed/desa_metrics.csv")
prof = pd.DataFrame(s["cluster_profile"]).set_index("klaster")

f = lambda x, n=1: f"{x:.{n}f}".replace(".", ",")
pmh, ath = s["pm_hod_region_mean"], s["at_hod_region_mean"]
kota = d[d.wilayah == "Kota Bogor"]
br, jr = s["by_region"]["bgr"], s["by_region"]["jkt"]
calf = json.load(open("processed/openaq_calibration.json"))
CJ, CB = calf["rows"]["-6.0"], calf["rows"]["-6.4"]
bgr = d[d.region == "bgr"]; jkt = d[d.region == "jkt"]
rep = {
    "__JAT05__": f(jr["at_hod"][5]), "__JPM05__": f(jr["pm_hod"][5], 0), "__JPM17__": f(jr["pm_hod"][17], 0), "__JAT17__": f(jr["at_hod"][17]),
    "__JB05__": str(int((jkt.jam_terbaik == 5).sum())),
    "__CB06__": f(CB["cams_hod"][6], 0), "__OB06__": f(CB["obs_hod"][6], 0), "__CJ12__": f(CJ["cams_hod"][12], 0), "__OJ12__": f(CJ["obs_hod"][12], 0),
    "__BMIN__": f(min(br["pm_hod"]), 0), "__BMAX__": f(max(br["pm_hod"]), 0), "__AT05__": f(br["at_hod"][5]), "__AT12__": f(br["at_hod"][12]),
    "__B05__": str(int((bgr.jam_terbaik == 5).sum())), "__B1820__": str(int(bgr.jam_terbaik.isin([18, 19, 20]).sum())),
    "__OJ05__": f(CJ["obs_hod"][5], 0), "__OJ16__": f(CJ["obs_hod"][16], 0),
    "__C0N__": str(int(prof.loc[0, "n_desa"])), "__C0A__": f"{prof.loc[0, 'luas_km2']:.0f}", "__C0L__": f(prof.loc[0, "n_jam_layak"]),
    "__ZERO__": str(s["desa_zero_layak"]), "__ZEROP__": f"{100 * s['desa_zero_layak'] / s['n_desa']:.0f}",
    "__KB__": str(s["k_best"]), "__SIL__": "; ".join(f"k={k}: {f(v, 3)}" for k, v in s["silhouette"].items()),
    "__MORAN__": f(s["moran_pm_knn6"]["I"], 2),
    "__HH__": str(s["lisa_counts"].get("Tinggi-Tinggi", 0)), "__LL__": str(s["lisa_counts"].get("Rendah-Rendah", 0)),
}
html = open("web/template_v2.html").read()
for k, v in rep.items():
    html = html.replace(k, v)
html = html.replace("__D3__", open("node_modules/d3/dist/d3.min.js").read())
html = html.replace("__TOPO__", open("node_modules/topojson-client/dist/topojson-client.min.js").read())
html = html.replace("__TOPOJSON__", open("processed/desa.topo.json").read())
html = html.replace("__KECLINES__", open("processed/kec_lines.json").read())
html = html.replace("__REGLINES__", open("processed/reg_lines.json").read())
pl = json.load(open("processed/web_payload.json"))
html = html.replace("__LEAFLETCSS__", open("node_modules/leaflet/dist/leaflet.css").read())
html = html.replace("__LEAFLETJS__", open("node_modules/leaflet/dist/leaflet.js").read())
html = html.replace("__KECLABELS__", open("processed/kec_labels.json").read())
cal = json.load(open("processed/openaq_calibration.json"))
pl["cf"] = cal["cf"]
pl["calrows"] = cal["rows"]
_fp = json.load(open("processed/forecast_points.json"))
pl["atp"] = _fp["at_points"]
pl["atpj"] = _fp["at_points_jkt"]
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
