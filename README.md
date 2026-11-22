# Lari Sehat Bogor

Peta interaktif kelayakan lari per jam untuk 503 desa/kelurahan di Kota dan Kabupaten Bogor, berbasis kualitas udara (PM2.5) dan suhu terasa.

*Hourly running-suitability map for the 503 villages of Bogor City and Regency, combining modelled PM2.5 (CAMS, calibrated against OpenAQ sensors) with elevation-adjusted apparent temperature.*

## Apa yang diperbarui otomatis

| Data | Sumber | Frekuensi | Di mana |
|---|---|---|---|
| Prakiraan PM2.5 dan suhu terasa per desa | Open-Meteo (CAMS global, forecast) | setiap halaman dibuka | langsung dari browser |
| Nilai terakhir sensor PM2.5 | OpenAQ API v3 | tiap jam (GitHub Actions) | `site/data/openaq_latest.json` |
| Faktor kalibrasi CAMS → sensor per jam | OpenAQ + Open-Meteo | tiap Senin 02.41 WIB | `site/data/calibration.json` |
| Pola rata-rata per jam, klaster, hot spot | CAMS 22 Agu–22 Nov 2026 | statis (jalankan ulang `analysis/`) | tertanam di `site/index.html` |

## Struktur

```
site/                     halaman yang di-deploy ke GitHub Pages
  index.html              peta (Leaflet + D3, data tertanam)
  data/                   JSON yang diperbarui workflow
scripts/
  fetch_openaq_latest.py  nilai sensor terbaru (tiap jam)
  update_calibration.py   hitung ulang faktor kalibrasi (mingguan)
analysis/                 analisis spasial dan build halaman
  analysis.py             interpolasi, kelas lari, Moran's I, LISA, Gi*, k-means
  build_web2.py           menyusun site/index.html dari web/template_v2.html
  raw/, processed/        data masukan dan hasil
.github/workflows/update-and-deploy.yml
```

## Pengaturan sekali saja

1. **Secret:** Settings → Secrets and variables → Actions → New repository secret. Nama `OPENAQ_API_KEY`, isi dengan API key OpenAQ (gratis di explore.openaq.org). Key tidak pernah ditulis ke file.
2. **Pages:** Settings → Pages → Build and deployment → Source: **GitHub Actions**.
3. **Jalankan pertama kali:** tab Actions → "Update data and deploy" → Run workflow (centang "Also recompute the OpenAQ calibration" bila perlu).

## Menjalankan ulang analisis

```bash
cd analysis
npm install                 # d3, topojson-client, leaflet (diinline ke halaman)
pip install geopandas libpysal esda scikit-learn
python analysis.py
python build_web2.py        # menulis ../site/index.html
```

## Metode singkat

- **PM2.5:** CAMS global 0,4° (Open-Meteo), 12 titik grid diinterpolasi bilinear ke titik representatif desa, lalu dikalikan faktor kalibrasi per jam = rata-rata sensor OpenAQ / rata-rata CAMS pada sensor di baris grid yang sama dengan Bogor.
- **Suhu terasa:** regresi per jam terhadap ketinggian (Copernicus DEM GLO-90).
- **Kelas lari:** Layak (PM2.5 ≤ 55,4 µg/m³ dan suhu terasa < 32,2 °C), Hindari (PM2.5 > 150,4 atau suhu terasa ≥ 39,4 °C), selain itu Hati-hati. Ambang dari kategori PM2.5 BMKG/ISPU dan heat index NWS.
- **Spasial:** Moran's I, LISA (FDR), Getis-Ord Gi*, k-means (k dipilih dengan silhouette).

## Keterbatasan

- Tidak ada sensor OpenAQ aktif di wilayah Bogor pada periode analisis; kalibrasi memakai sensor murah di Depok. Sensor optik cenderung membaca terlalu tinggi saat lembap.
- Resolusi CAMS ±45 km; sumber lokal tidak terlihat.
- Bukan nasihat medis.

## Atribusi

CAMS / Copernicus Atmosphere Monitoring Service · Open-Meteo · OpenAQ · Copernicus DEM · batas desa: fityannugroho/idn-area-boundary · peta dasar © OpenStreetMap contributors, © CARTO, Esri.
