# Kuranji Tahap 4 — Freeze Sentinel-1 RTC Change Evidence

## Status

Komponen Sentinel-1 Tahap 4 **dibekukan sebagai bukti perubahan kondisi permukaan berbasis radar (multitemporal RTC backscatter evidence)**. Hasil ini **bukan DEM pascakejadian**, **bukan ΔDEM**, dan **tidak membuktikan perubahan elevasi/topografi permanen**.

## Scene yang digunakan

Semua scene berasal dari Sentinel-1A, ascending, relative orbit 142, VV+VH, dengan cakupan DAS praktis 100% pada preflight.

- PRE: 2025-11-10 11:41:17 UTC
- EVENT: 2025-11-22 11:41:17 UTC
- POST: 2025-12-04 11:41:15 UTC

Produk diproses melalui ASF HyP3 RTC dengan:

- radiometry: gamma0
- resolution: 20 m
- scale: power
- DEM matching: true
- DEM: Copernicus
- incidence map: included
- speckle filter pada HyP3: false

Power kemudian dikonversi ke dB dengan `10*log10(power)`. Semua scene disejajarkan pada grid EPSG:32747 resolusi 20 m dan dipotong terhadap DAS Batang Kuranji.

## QC grid dan domain

Grid Stage 4:

- CRS: EPSG:32747
- resolusi: 20 m
- ukuran grid: 1258 × 812
- geometric DAS: 561,743 pixel = 224.6972 km²
- common-valid PRE/EVENT/POST VV+VH: 559,176 pixel = 223.6704 km²
- excluded S1 NoData: 2,567 pixel = 1.0268 km²
- common-valid coverage ≈ 99.54% geometric DAS

Retensi referensi pada common-valid domain:

- BIG/BRIN observed extent 2025-12-01: 4.1768 km² retained 100.00%
- P175 domain: 13.2780 km² retained 99.97%

Dengan demikian NoData SAR tidak mengganggu perbandingan observed/P175 secara material.

## QC incidence angle

Perbedaan incidence angle antar-scene sangat kecil.

Median difference:

- EVENT − PRE: +0.000125°
- POST − PRE: −0.000033°
- POST − EVENT: −0.000155°

Skala perubahan incidence ini jauh lebih kecil daripada variasi backscatter yang dianalisis, sehingga perubahan temporal backscatter tidak dijelaskan oleh perubahan sudut pengamatan yang berarti.

## Zona referensi

Analisis overlay menggunakan:

- BIG/BRIN observed flood extent dated 2025-12-01
- frozen P175 baseline hazard candidate
- Stage-3 TP = observed ∩ P175
- Stage-3 FN = observed dan di luar P175
- NON_OBSERVED_REFERENCE = area common-valid di luar observed BIG/BRIN

Catatan penting: NON_OBSERVED_REFERENCE **bukan** confirmed dry / true negative event-peak karena observed BIG/BRIN bertanggal 2025-12-01 dan dapat tidak merepresentasikan puncak banjir 2025-11-21 s.d. 2025-11-27.

## Hasil utama raw dB

### EVENT − PRE

Observed BIG/BRIN dibanding non-observed reference:

| Variable | Observed median | Non-observed median | Observed − Non-observed |
|---|---:|---:|---:|
| VV | +0.253 dB | +0.558 dB | −0.305 dB |
| VH | +0.122 dB | +0.609 dB | −0.487 dB |
| VH−VV | −0.136 dB | +0.045 dB | −0.181 dB |

Area observed menunjukkan kenaikan backscatter yang lebih lemah daripada non-observed reference pada tanggal EVENT.

### POST − PRE

| Variable | Observed median | Non-observed median | Observed − Non-observed |
|---|---:|---:|---:|
| VV | −0.354 dB | +0.049 dB | −0.404 dB |
| VH | −0.578 dB | +0.132 dB | −0.710 dB |
| VH−VV | −0.282 dB | +0.078 dB | −0.360 dB |

Kontras observed vs non-observed pada POST lebih kuat daripada EVENT untuk ketiga variabel, terutama VH. Area non-observed kembali mendekati baseline PRE secara median, sedangkan observed tetap lebih rendah daripada PRE.

### POST − EVENT

| Variable | Observed median | Non-observed median | Observed − Non-observed |
|---|---:|---:|---:|
| VV | −0.601 dB | −0.496 dB | −0.106 dB |
| VH | −0.677 dB | −0.467 dB | −0.211 dB |
| VH−VV | −0.134 dB | +0.022 dB | −0.155 dB |

## TP vs FN Stage 3

Perbedaan median TP dan FN relatif kecil dibanding lebar distribusi piksel.

EVENT − PRE:

- VV: TP +0.285 dB; FN +0.239 dB; FN−TP −0.046 dB
- VH: TP +0.179 dB; FN +0.094 dB; FN−TP −0.085 dB
- VH−VV: TP −0.123 dB; FN −0.146 dB; FN−TP −0.024 dB

POST − PRE:

- VV: TP −0.377 dB; FN −0.334 dB
- VH: TP −0.673 dB; FN −0.526 dB
- VH−VV: TP −0.301 dB; FN −0.265 dB

Karena TP dan FN memiliki respons radar yang cukup serupa, hasil ini tidak mendukung interpretasi sederhana bahwa FN P175 terjadi karena FN mempunyai signature radar yang sama sekali berbeda dari TP.

## Sensitivitas speckle: RAW vs median 3×3

Median 3×3 mempertahankan **arah kontras observed − non-observed yang sama pada seluruh kombinasi waktu dan variabel**.

EVENT − PRE:

- VV: RAW −0.305 dB; MED3 −0.285 dB
- VH: RAW −0.487 dB; MED3 −0.466 dB
- VH−VV: RAW −0.181 dB; MED3 −0.156 dB

POST − PRE:

- VV: RAW −0.404 dB; MED3 −0.385 dB
- VH: RAW −0.710 dB; MED3 −0.623 dB
- VH−VV: RAW −0.360 dB; MED3 −0.295 dB

POST − EVENT:

- VV: RAW −0.106 dB; MED3 −0.126 dB
- VH: RAW −0.211 dB; MED3 −0.167 dB
- VH−VV: RAW −0.155 dB; MED3 −0.197 dB

Karena arah kontras tetap konsisten setelah median filtering, pola tersebut lebih sesuai dengan sinyal spasial yang koheren daripada artefak speckle piksel tunggal. Besaran kontras tetap harus diperlakukan sebagai statistik deskriptif, bukan threshold klasifikasi.

## Interpretasi yang dibekukan

1. Sentinel-1 menunjukkan **event-associated multitemporal surface-state contrast** pada area yang kemudian dipetakan BIG/BRIN sebagai terdampak.
2. Kontras paling kuat pada analisis POST − PRE terjadi pada VH.
3. Area observed pada 2025-12-04 tetap berbeda dari baseline 2025-11-10, sementara median non-observed reference mendekati baseline.
4. Pola bertahan setelah median 3×3, sehingga tidak hanya bergantung pada speckle piksel tunggal.
5. Hasil ini dapat konsisten dengan kombinasi kelembapan/genangan residual, deposisi sedimen, perubahan roughness, vegetasi terdampak, atau perubahan kondisi permukaan lainnya.
6. Hasil ini **tidak boleh ditulis sebagai bukti Δelevasi, perubahan DEM, atau perubahan topografi permanen**.
7. Tidak ada threshold Sentinel-1 banjir/perubahan yang dipilih pada tahap ini.
8. Binary BIG/BRIN 2025-12-01 tetap merupakan observed/reference extent candidate dan bukan perfect event-peak ground truth.

## Status penelitian setelah freeze Sentinel-1

Komponen Sentinel-1 Tahap 4 selesai sebagai salah satu kaki **multimodal geomorphic/surface-change evidence**. Tahap berikutnya adalah pemeriksaan ICESat-2 ATL08 repeat-track RGT0453 (2025-10-14 vs 2026-01-13) untuk mencari bukti perubahan elevasi sepanjang lintasan, dengan kontrol ketat terhadap beam identity, positional matching, quality fields, ground-vs-canopy elevation, track offset, dan uncertainty.
