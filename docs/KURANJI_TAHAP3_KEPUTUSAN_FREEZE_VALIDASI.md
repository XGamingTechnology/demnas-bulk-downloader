# KEPUTUSAN FREEZE TAHAP 3 — VALIDASI EKSTERNAL DAS BATANG KURANJI

## 1. Status

Tahap 3 dinyatakan **frozen sebagai external validation stage** terhadap observed flood extent BIG/BRIN hasil interpretasi WorldView tanggal 1 Desember 2025.

Freeze ini tidak mengubah status P175 menjadi final calibrated flood hazard map. Status yang dipertahankan adalah:

> **P175 = primary baseline hazard candidate, externally evaluated against the 1 Dec 2025 BIG/BRIN observed flood extent.**

## 2. Validasi Strict Pixel Overlap

Observed extent di dalam DAS: **4.1760 km²**.

### Manual domain (M175/M250)

- predicted area: 60.138 km²
- TP: 3.956 km²
- FP: 56.182 km²
- FN: 0.220 km²
- precision: 0.0658
- recall: 0.9474
- F1: 0.1230
- IoU: 0.0655

### Physical domain (P175/P250)

- predicted area: 13.249 km²
- TP: 1.632 km²
- FP: 11.616 km²
- FN: 2.544 km²
- precision: 0.1232
- recall: 0.3909
- F1: 0.1874
- IoU: 0.1034

Interpretasi: M-domain memiliki recall lebih tinggi tetapi sangat overpredictive. P-domain mempunyai precision, F1, dan IoU yang lebih tinggi dan secara global memberikan trade-off spasial yang lebih seimbang terhadap observed post-event extent.

## 3. Positional-Tolerance QC

QC dilakukan secara simetris. Recall tolerance dihitung dengan mengecek observed cell yang mempunyai predicted cell dalam radius tertentu; precision tolerance dihitung dengan mengecek predicted cell yang mempunyai observed cell dalam radius yang sama.

| Tolerance | Approx. distance | P175 Recall | P175 Precision | P175 F1 | M175 Recall | M175 Precision | M175 F1 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 px | 0.0 m | 0.3909 | 0.1232 | 0.1874 | 0.9474 | 0.0658 | 0.1230 |
| 1 px | 8.3 m | 0.4983 | 0.1393 | 0.2177 | 0.9520 | 0.0738 | 0.1369 |
| 2 px | 16.7 m | 0.5760 | 0.1536 | 0.2425 | 0.9552 | 0.0812 | 0.1497 |
| 3 px | 25.0 m | 0.6309 | 0.1659 | 0.2627 | 0.9580 | 0.0882 | 0.1615 |
| 5 px | 41.6 m | 0.7075 | 0.1874 | 0.2964 | 0.9625 | 0.1015 | 0.1836 |

P175 mempertahankan F1 yang lebih tinggi daripada M175 pada seluruh tolerance yang diuji. Dengan tolerance 1–2 pixel, F1 P175 meningkat dari 0.1874 menjadi 0.2177–0.2425, menunjukkan bahwa sebagian mismatch memang sensitif terhadap positional offset kecil. Namun peningkatan berlanjut hingga 5 pixel sehingga mismatch P175 tidak dapat dijelaskan hanya oleh offset satu-dua pixel; masih terdapat perbedaan struktural antara modeled physical domain dan observed post-event extent.

Tolerance 3–5 pixel digunakan sebagai sensitivity diagnostic, bukan justifikasi untuk menganggap semua near-miss sebagai match.

## 4. Keputusan Model

1. **P-domain (WD > 0 / GFI_raw > 0) dipertahankan sebagai domain baseline primer.**
2. M-domain manual -0.53 tetap disimpan sebagai sensitivity scenario karena kemampuan capture yang sangat tinggi, tetapi tidak dipilih sebagai baseline utama akibat overprediction yang besar.
3. P175 tetap dipertahankan atas P250 karena spread 1.75 merupakan nilai tertulis pada modul. Binary extent tidak dapat membedakan P175 dan P250 karena keduanya mempunyai domain yang identik.
4. Tidak dilakukan retuning threshold GFI menggunakan event 2025 agar validation tidak berubah menjadi calibration menggunakan data yang sama.

## 5. Keterbatasan yang Harus Dipertahankan dalam Laporan

- observed reference merupakan hasil interpretasi WorldView tanggal **1 Desember 2025**, sesudah periode utama banjir 21–27 November 2025;
- FP adalah model-only relative to observed 1 Dec, bukan bukti bahwa area tersebut tidak pernah tergenang saat puncak kejadian;
- binary flood extent tidak dapat memvalidasi modeled water depth atau kelas Low/Medium/High;
- positional-tolerance metrics adalah sensitivity diagnostic dan strict r=0 tetap menjadi validasi utama;
- Stage 3 bukan empirical calibration terhadap independent calibration dataset.

## 6. Status Akhir

Tahap 3 selesai untuk tujuan **external spatial validation of the Stage-2 baseline candidate**.

Status akhir yang aman untuk penelitian:

> P175 menunjukkan kecocokan spasial yang lebih seimbang dibanding manual-domain scenario terhadap BIG/BRIN post-event flood extent tanggal 1 Desember 2025, dengan F1 dan IoU strict yang lebih tinggi serta keunggulan F1 yang tetap bertahan pada positional tolerance 1–5 pixel. M-domain mempunyai recall jauh lebih tinggi tetapi disertai overprediction yang besar. P175 karena itu dipertahankan sebagai primary baseline hazard candidate, dengan keterbatasan bahwa observed reference bukan peak-event extent dan kelas kedalaman belum tervalidasi.
