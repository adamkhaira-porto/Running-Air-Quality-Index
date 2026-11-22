"""Air quality x running suitability, Kota & Kabupaten Bogor (503 desa/kelurahan).

Inputs (raw/):
  cams_nodes_summary.json  CAMS global 0.4 deg nodes (via Open-Meteo): hour-of-day means, daily means, forecast
  elevation_desa.json      Copernicus DEM elevation at desa representative points
  apparent_temp_fit.json   per-hour regression of apparent temperature on elevation
  desa_bogor_full.geojson  village polygons (fityannugroho/idn-area-boundary)
Outputs (processed/): desa_metrics.csv, desa_analysis.geojson, analysis_summary.json, web_payload.json
"""
import json
import numpy as np
import pandas as pd
import geopandas as gpd
from libpysal.weights import Queen, KNN
from esda.moran import Moran, Moran_Local
from esda.getisord import G_Local
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

np.random.seed(42)
cams = json.load(open("raw/cams_nodes_summary.json"))
elev = np.array(json.load(open("raw/elevation_desa.json"))["elev"], dtype=float)
atfit = json.load(open("raw/apparent_temp_fit.json"))["fit"]
desa = gpd.read_file("raw/desa_bogor_full.geojson")
cent = pd.read_csv("processed/desa_centroid.csv")
assert (desa.code.values == cent.code.values).all()
desa["elev_m"] = elev

LATS = [-6.0, -6.4, -6.8]
LONS = [106.4, 106.8, 107.2, 107.6]
nodes = cams["n"]
idx = {(round(n[0], 1), round(n[1], 1)): i for i, n in enumerate(nodes)}

def arr(k):
    return np.array([[np.nan if v is None else v for v in n[k]] for n in nodes], dtype=float)

HOD_PM, HOD_O3, HOD_NO2, HOD_OK, HOD_GOOD, DAILY, FC = (arr(k) for k in range(2, 9))

# --- bilinear weights from the 4 surrounding CAMS nodes ---
W_IDX, W_VAL = [], []
for la, lo in zip(cent.lat, cent.lon):
    i0 = 0 if la >= LATS[1] else 1          # lat rows descend: -6.0, -6.4, -6.8
    j0 = max(0, min(2, int((lo - LONS[0]) // 0.4)))
    la_a, la_b = LATS[i0], LATS[i0 + 1]
    lo_a, lo_b = LONS[j0], LONS[j0 + 1]
    ty = (la_a - la) / (la_a - la_b)
    tx = (lo - lo_a) / (lo_b - lo_a)
    ty, tx = min(max(ty, 0), 1), min(max(tx, 0), 1)
    corners = [(la_a, lo_a, (1 - ty) * (1 - tx)), (la_a, lo_b, (1 - ty) * tx),
               (la_b, lo_a, ty * (1 - tx)), (la_b, lo_b, ty * tx)]
    W_IDX.append([idx[(round(a, 1), round(b, 1))] for a, b, _ in corners])
    W_VAL.append([w for *_, w in corners])
W_IDX, W_VAL = np.array(W_IDX), np.array(W_VAL)

def interp(A):
    return np.einsum("dk,dkt->dt", W_VAL, A[W_IDX])

# OpenAQ calibration: CAMS overstates the diurnal swing (night x1.8-2.0, midday x0.8) against the two
# low-cost sensors nearest Bogor on the same CAMS grid row (Depok, Griya Tugu Asri). Multiply by the
# hour-of-day ratio of means (processed/openaq_calibration.json, built from raw/openaq/).
CF = np.array(json.load(open("processed/openaq_calibration.json"))["cf"])
pm_raw = interp(HOD_PM)
pm = pm_raw * CF[None, :]  # (503, 24) calibrated mean PM2.5 by hour of day, ug/m3
o3 = interp(HOD_O3)
no2 = interp(HOD_NO2)
okp = interp(HOD_OK)      # % of hours with PM2.5 <= 55.4 (ISPU 'sedang' or better)
daily = interp(DAILY)
fc = interp(FC)

a = np.array([f[1] for f in atfit]); b = np.array([f[2] for f in atfit])
at = a[None, :] + b[None, :] * (elev[:, None] / 1000.0)   # apparent temp by hour

# --- categories ---
def pm_cat(x):  # BMKG / ISPU PM2.5 bands
    return np.select([x <= 15.5, x <= 55.4, x <= 150.4, x <= 250.4], [0, 1, 2, 3], 4)

def heat_cat(t):  # NWS heat index classes in degC
    return np.select([t < 26.7, t < 32.2, t < 39.4, t < 51.1], [0, 1, 2, 3], 4)

RUN_HOURS = list(range(5, 21))   # 05:00-20:59 realistic outdoor running hours
pc, hc = pm_cat(pm), heat_cat(at)
# run class: 2 = layak, 1 = hati-hati, 0 = hindari
# Hindari only when one factor reaches its severe tier (ISPU 'sangat tidak sehat' > 150.4,
# NWS 'danger' >= 39.4 C); every other non-layak hour is hati-hati, matching the official advice
# for ISPU 'tidak sehat' and NWS 'extreme caution' (reduce strenuous/prolonged activity).
run = np.where((pc <= 1) & (hc <= 1), 2, np.where((pc >= 3) | (hc >= 3), 0, 1))

best_h, best_pm, n_layak, n_hati = [], [], [], []
for d in range(len(desa)):
    # Heat safety first (acute risk), then lowest PM2.5 (cumulative risk):
    # 1) hours with apparent temp below NWS 'extreme caution' (32.2 C); 2) else below 'danger' (39.4 C)
    tier1 = [h for h in RUN_HOURS if at[d, h] < 32.2]
    tier2 = [h for h in RUN_HOURS if at[d, h] < 39.4]
    pool = tier1 or tier2 or RUN_HOURS
    h_best = min(pool, key=lambda h: pm[d, h])
    best_h.append(h_best); best_pm.append(pm[d, h_best])
    n_layak.append(int(sum(run[d, h] == 2 for h in RUN_HOURS)))
    n_hati.append(int(sum(run[d, h] == 1 for h in RUN_HOURS)))

desa["pm_mean"] = pm.mean(1)
desa["pm_pagi_05_07"] = pm[:, 5:8].mean(1)
desa["pm_siang_13_16"] = pm[:, 13:17].mean(1)
desa["pm_sore_17_19"] = pm[:, 17:20].mean(1)
desa["o3_puncak"] = o3.max(1)
desa["no2_mean"] = no2.mean(1)
desa["at_06"] = at[:, 6]
desa["at_16"] = at[:, 16]
desa["jam_terbaik"] = best_h
desa["pm_jam_terbaik"] = best_pm
desa["n_jam_layak"] = n_layak
desa["n_jam_hati"] = n_hati
desa["rasio_pagi_vs_siang"] = desa.pm_pagi_05_07 / desa.pm_siang_13_16

# --- spatial statistics on mean PM2.5 ---
dm = desa.to_crs(32748)
wq = Queen.from_dataframe(dm, use_index=False, silence_warnings=True)
islands = list(wq.islands)
wk = KNN.from_dataframe(dm.set_geometry(dm.representative_point()), k=6)
for w in (wq, wk):
    w.transform = "r"
y = desa.pm_mean.values
mi_q = Moran(y, wq, permutations=999)
mi_k = Moran(y, wk, permutations=999)
lisa = Moran_Local(y, wk, permutations=999, seed=42)
# FDR (Benjamini-Hochberg) on pseudo p-values
p = lisa.p_sim; order = np.argsort(p); m = len(p)
thr = 0.05 * (np.arange(1, m + 1) / m)
passed = p[order] <= thr
k_max = np.max(np.where(passed)[0]) + 1 if passed.any() else 0
fdr_cut = p[order][k_max - 1] if k_max else 0
sig = p <= fdr_cut
lab = np.array(["Tidak signifikan"] * m, dtype=object)
qmap = {1: "Tinggi-Tinggi", 2: "Rendah-Tinggi", 3: "Rendah-Rendah", 4: "Tinggi-Rendah"}
for i in range(m):
    if sig[i]:
        lab[i] = qmap[lisa.q[i]]
desa["lisa"] = lab
gi = G_Local(y, wk, star=True, permutations=999, seed=42)
desa["gi_z"] = gi.Zs

# Run-suitability Moran (mixes air + terrain heat)
mi_run = Moran(desa.n_jam_layak.values.astype(float), wk, permutations=999)

# --- k-means typology on air + heat profile ---
feat_cols = ["pm_pagi_05_07", "pm_siang_13_16", "pm_sore_17_19", "o3_puncak", "at_06", "at_16"]
X = StandardScaler().fit_transform(desa[feat_cols])
sil = {}
for k in range(3, 7):   # 3-6 clusters keeps the typology readable
    km = KMeans(n_clusters=k, n_init=20, random_state=42).fit(X)
    sil[k] = float(silhouette_score(X, km.labels_))
k_best = max(sil, key=sil.get)
km = KMeans(n_clusters=k_best, n_init=20, random_state=42).fit(X)
desa["klaster"] = km.labels_
# stable cluster ids for the web page: 0 highland, 2 morning-spike east, 3 northern lowland, 1 the rest
_p = desa.groupby("klaster")[["elev_m", "pm_pagi_05_07", "pm_mean"]].mean()
_hi = _p.elev_m.idxmax(); _rest = _p.drop(_hi)
_ms = (_rest.pm_pagi_05_07 - _rest.pm_mean).idxmax(); _rest = _rest.drop(_ms)
_lo = _rest.pm_mean.idxmax(); _mid = _rest.drop(_lo).index[0]
desa["klaster"] = desa.klaster.map({_hi: 0, _mid: 1, _ms: 2, _lo: 3})
prof = desa.groupby("klaster")[feat_cols + ["elev_m", "n_jam_layak", "pm_mean"]].mean().round(1)
prof["n_desa"] = desa.groupby("klaster").size()
prof["luas_km2"] = desa.groupby("klaster").luas_km2.sum().round(0)

# --- save ---
cols = ["code", "name", "kecamatan", "wilayah", "jenis", "luas_km2", "elev_m", "pm_mean", "pm_pagi_05_07",
        "pm_siang_13_16", "pm_sore_17_19", "rasio_pagi_vs_siang", "o3_puncak", "no2_mean", "at_06", "at_16",
        "jam_terbaik", "pm_jam_terbaik", "n_jam_layak", "n_jam_hati", "lisa", "gi_z", "klaster"]
desa[cols].round(3).to_csv("processed/desa_metrics.csv", index=False)
desa[cols + ["geometry"]].to_file("processed/desa_analysis.geojson", driver="GeoJSON")

summary = {
    "n_desa": int(len(desa)),
    "moran_pm_queen": {"I": round(float(mi_q.I), 3), "p": float(mi_q.p_sim), "islands": len(islands)},
    "moran_pm_knn6": {"I": round(float(mi_k.I), 3), "p": float(mi_k.p_sim)},
    "moran_jam_layak_knn6": {"I": round(float(mi_run.I), 3), "p": float(mi_run.p_sim)},
    "lisa_fdr_cut": float(fdr_cut),
    "lisa_counts": desa.lisa.value_counts().to_dict(),
    "silhouette": {k: round(v, 3) for k, v in sil.items()},
    "k_best": int(k_best),
    "cluster_profile": prof.reset_index().to_dict(orient="records"),
    "pm_mean_range": [round(float(y.min()), 1), round(float(y.max()), 1)],
    "pm_hod_region_mean": [round(float(v), 1) for v in pm.mean(0)],
    "pm_hod_region_mean_raw": [round(float(v), 1) for v in pm_raw.mean(0)],
    "o3_hod_region_mean": [round(float(v), 1) for v in o3.mean(0)],
    "at_hod_region_mean": [round(float(v), 1) for v in at.mean(0)],
    "best_hour_counts": pd.Series(best_h).value_counts().sort_index().to_dict(),
    "n_jam_layak_dist": pd.Series(n_layak).describe().round(2).to_dict(),
    "desa_zero_layak": int(sum(np.array(n_layak) == 0)),
}
json.dump(summary, open("processed/analysis_summary.json", "w"), indent=1, default=int)

payload = {
    "nodes": [[n[0], n[1]] for n in nodes],
    "hod_pm": HOD_PM.round(0).tolist(), "hod_o3": HOD_O3.round(0).tolist(), "hod_ok": HOD_OK.round(0).tolist(),
    "daily": np.nan_to_num(DAILY, nan=-1).round(0).tolist(), "fc": np.nan_to_num(FC, nan=-1).round(0).tolist(),
    "t0": cams["t0"], "now": cams["now"], "at_a": a.tolist(), "at_b": b.tolist(),
    "desa": [{"c": r.code, "n": r["name"], "k": r.kecamatan, "w": "Kota" if r.wilayah == "Kota Bogor" else "Kab",
              "e": int(r.elev_m), "wi": W_IDX[i].tolist(), "wv": [round(v, 3) for v in W_VAL[i]],
              "cl": int(r.klaster), "li": r.lisa, "gz": round(float(r.gi_z), 2), "bh": int(r.jam_terbaik),
              "nl": int(r.n_jam_layak), "pm": round(float(r.pm_mean), 1)}
             for i, (_, r) in enumerate(desa.iterrows())],
}
json.dump(payload, open("processed/web_payload.json", "w"), separators=(",", ":"))
print(json.dumps({k: v for k, v in summary.items() if k != "cluster_profile"}, indent=1, default=int))
print(prof.to_string())
