# TAHAP 4 — DESAIN MULTIMODAL GEOMORPHIC CHANGE DAS BATANG KURANJI

## 1. Keputusan Metodologis

Audit sumber publik menunjukkan bahwa **wall-to-wall post-event DEM tidak tersedia** untuk DAS Batang Kuranji pada periode pascabanjir Siklon Senyar 2025. Oleh karena itu, Tahap 4 tidak diposisikan sebagai true DEM-of-Difference (DoD) atau full DeltaDEM analysis.

Tahap 4 menggunakan pendekatan **multimodal geomorphic change evidence** yang menggabungkan:

1. **ICESat-2 ATL08 repeat-track elevation evidence** untuk membandingkan elevasi sepanjang lintasan yang sama sebelum dan sesudah kejadian;
2. **Sentinel-1 GRD event-change mapping** untuk mendeteksi perubahan permukaan/backscatter pada koridor banjir menggunakan acquisition geometry yang konsisten;
3. hasil Tahap 1–3 sebagai baseline topografi, GFI, hazard candidate, dan observed flood reference.

NISAR tidak digunakan karena corrected BETA science-product query tidak menemukan GCOV, GSLC, GUNW, atau RSLC yang menutup DAS Kuranji pada window yang diuji.

---

## 2. Evidence Stream A — ICESat-2 ATL08

Audit NASA CMR menemukan repeat-track candidate:

- RGT: **0453**
- region: **14**
- PRE: **14 Oktober 2025 06:44:26 UTC**
- POST: **13 Januari 2026 02:24:01 UTC**
- separation: sekitar **90.8 hari**

OpenAltimetry berhasil mengembalikan ATL08 subset untuk kedua tanggal.

Interpretasi yang diperbolehkan:

- perubahan elevasi sepanjang lintasan laser yang sama/berdekatan;
- indikasi erosi, deposisi, atau perubahan permukaan jika positional and quality control mendukung;
- comparison terhadap koridor sungai, observed flood extent, dan P175 hazard domain.

Interpretasi yang tidak diperbolehkan:

- menganggap ATL08 sebagai DEM penuh;
- menginterpolasi perubahan lintasan menjadi perubahan elevasi seluruh DAS tanpa validasi tambahan;
- mengatribusikan seluruh perubahan antara Oktober 2025 dan Januari 2026 hanya kepada kejadian 21–27 November, karena interval POST juga mencakup proses pascakejadian dan kemungkinan kejadian susulan/intervensi.

---

## 3. Evidence Stream B — Sentinel-1 GRD

Refined ASF audit menemukan satu group dengan acquisition geometry yang konsisten:

- flight direction: **ASCENDING**
- relative orbit: **142**
- polarization: **VV+VH**
- PRE: **16 November 2025 11:40:34 UTC**
- EVENT: **22 November 2025 11:41:17 UTC**
- POST: **28 November 2025 11:40:04 UTC**

Triplet ini sangat sesuai untuk event-change analysis karena:

- PRE hanya 5 hari sebelum event window;
- EVENT berada di dalam periode 21–27 November;
- POST hanya 1 hari setelah event window;
- orbit direction, relative orbit, dan polarization sama sehingga geometric/radiometric comparability lebih baik daripada scene acak.

Produk yang dianalisis:

- VV backscatter PRE/EVENT/POST;
- VH backscatter PRE/EVENT/POST;
- log-ratio atau dB difference EVENT minus PRE;
- POST minus PRE;
- optional EVENT minus POST;
- thresholded change masks setelah speckle/noise/terrain masking yang sesuai.

Tujuan utama adalah evidence of surface change / inundation-related backscatter response, bukan rekonstruksi elevasi.

---

## 4. Integrasi dengan Tahap 1–3

Evidence Stage 4 dibandingkan terhadap:

- DAS dan drainage network Tahap 1;
- GFI/WD/P175 baseline candidate Tahap 2;
- observed BIG/BRIN WorldView flood extent 1 Desember 2025 Tahap 3;
- hotspot false negative P175, terutama Nanggalo dan Kuranji.

Analisis integrasi yang direkomendasikan:

1. berapa persen Sentinel-1 event-change mask berada di dalam observed BIG/BRIN extent;
2. berapa persen event-change mask berada di P175 domain versus M175 domain;
3. apakah perubahan ICESat-2 sepanjang RGT 0453 beririsan dengan river corridor, observed extent, atau model hazard domain;
4. apakah lokasi FN P175 mempunyai signal perubahan Sentinel-1 atau ICESat-2 yang konsisten dengan kejadian banjir.

---

## 5. Batas Klaim

Tahap 4 tidak menghasilkan:

- wall-to-wall DeltaDEM;
- full post-event GFI recomputation;
- proof bahwa seluruh perubahan geomorfologi disebabkan hanya oleh Siklon Senyar.

Tahap 4 dapat mendukung klaim yang lebih hati-hati:

> The 2025 flood event was associated with spatially detectable surface-change signals from Sentinel-1 and along-track elevation differences from ICESat-2 in parts of the DAS Batang Kuranji. These observations provide independent geomorphic-change evidence that complements, but does not replace, a full post-event DEM analysis.

---

## 6. Status Data

### Tersedia

- ICESat-2 ATL08 PRE/POST subset via OpenAltimetry;
- Sentinel-1 GRD triplet with matching ASCENDING / orbit 142 / VV+VH geometry;
- BIG/BRIN observed flood extent 1 Dec 2025;
- DEMNAS/GFI/P175 baseline products.

### Tidak tersedia

- NISAR BETA science product over Kuranji for tested window;
- Maxar Open Data Senyar tile intersecting DAS Kuranji;
- public wall-to-wall post-event DEM/DSM/DTM.

---

## 7. Langkah Teknis Berikutnya

1. Parse dan QC OpenAltimetry ATL08 PRE/POST RGT 0453 per beam.
2. Project point coordinates to EPSG:32747.
3. Match PRE/POST points by along-track/proximity criteria dan hitung Delta elevation dengan quality flags yang tersedia.
4. Inspect exact Sentinel-1 scene IDs and download URLs for the selected triplet.
5. Preprocess Sentinel-1 consistently (orbit correction, thermal/noise removal where relevant, calibration, speckle treatment, terrain correction, dB conversion).
6. Compute PRE/EVENT/POST change layers.
7. Overlay Stage-4 evidence with observed flood extent, P175, admin, and FN hotspots.
8. Freeze Stage 4 and synthesize final research conclusions.
