# Lari Sehat Bogor & Jakarta

**Live:** https://adamkhaira-porto.github.io/Running-Air-Quality-Index/

Peta interaktif kelayakan lari per jam untuk 764 wilayah: 503 desa/kelurahan di Kota dan Kabupaten Bogor serta 261 kelurahan daratan DKI Jakarta (tanpa Kepulauan Seribu), berbasis kualitas udara (PM2.5) dan suhu terasa.

*Hourly running-suitability map for 764 villages of Bogor and Jakarta, combining modelled PM2.5 (CAMS, calibrated against OpenAQ sensors) with elevation-adjusted apparent temperature.*

## Apa yang diperbarui otomatis

| Data | Sumber | Frekuensi | Di mana |
|---|---|---|---|
| Prakiraan PM2.5 (12 titik grid CAMS) dan model suhu terasa per jam (30 desa, regresi terhadap ketinggian) | Open-Meteo | tiap jam (GitHub Actions) | `site/data/forecast.json` |
| Nilai terakhir sensor PM2.5 | OpenAQ API v3 | tiap jam (GitHub Actions) | `site/data/openaq_latest.json` |
| Faktor kalibrasi CAMS → sensor per jam, per baris sel grid (−6,0° Jakarta; −6,4° Depok/Bogor) | OpenAQ + Open-Meteo | tiap Senin 02.41 WIB | `site/data/calibration.json` |
| Pola rata-rata per jam, klaster, hot spot | CAMS 22 Agu–22 Nov 2026 | statis (jalankan ulang `analysis/`) | tertanam di `site/index.html` |

## Struktur

```
site/                     halaman yang di-deploy ke GitHub Pages
  index.html              peta (Leaflet + D3, data tertanam)
  data/                   JSON yang diperbarui workflow
scripts/
  fetch_forecast.py       prakiraan PM2.5 + suhu terasa (tiap jam)
  fetch_openaq_latest.py  nilai sensor terbaru (tiap jam)
  update_calibration.py   hitung ulang faktor kalibrasi per sel grid (mingguan)
  prepare_jakarta.py      sekali jalan: ketinggian + sampel suhu terasa Jakarta
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

- **PM2.5:** CAMS global 0,4° (Open-Meteo) di 12 titik grid. Tiap titik grid dikalikan faktor kalibrasi per jam (rata-rata sensor OpenAQ ÷ rata-rata CAMS) dari sensor di dalam sel gridnya: baris −6,0° memakai sensor Jakarta, −6,4° sensor Depok, −6,8° meminjam −6,4°. Lalu diinterpolasi bilinear ke titik representatif desa/kelurahan.
- **Suhu terasa:** regresi per jam terhadap ketinggian (Copernicus DEM GLO-90), plus koreksi per jam untuk Jakarta dari 30 kelurahan sampel (kota pesisir: sekitar +1,8 °C subuh, −1,3 °C siang).
- **Kelas lari:** Layak (PM2.5 ≤ 55,4 µg/m³ dan suhu terasa < 32,2 °C), Hindari (PM2.5 > 150,4 atau suhu terasa ≥ 39,4 °C), selain itu Hati-hati. Ambang dari kategori PM2.5 BMKG/ISPU dan heat index NWS.
- **Spasial:** Moran's I, LISA (FDR), Getis-Ord Gi*, k-means (k dipilih dengan silhouette).

## Keterbatasan

- Tidak ada sensor OpenAQ aktif di wilayah Bogor pada periode analisis; kalibrasi memakai sensor murah di Depok (Bogor) dan Jakarta. Sensor optik cenderung membaca terlalu tinggi saat lembap.
- Versi Jakarta belum memakai jaringan SPKU milik DKI (tidak ada API publik); rencana tahap berikutnya.
- Resolusi CAMS ±45 km; sumber lokal tidak terlihat.
- Bukan nasihat medis.

## Atribusi

CAMS / Copernicus Atmosphere Monitoring Service · Open-Meteo · OpenAQ · Copernicus DEM · batas desa: fityannugroho/idn-area-boundary · peta dasar Esri (Light Gray, Dark Gray, World Imagery) dan © OpenStreetMap contributors.
