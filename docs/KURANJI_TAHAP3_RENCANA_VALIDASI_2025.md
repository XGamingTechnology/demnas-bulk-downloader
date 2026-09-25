# TAHAP 3 — VALIDASI EVENT BANJIR NOVEMBER 2025 DAS BATANG KURANJI

## 1. Tujuan

Tahap 3 memvalidasi kandidat baseline bahaya banjir Tahap 2 terhadap **flood extent observasi independen** dari kejadian banjir besar 21–27 November 2025.

Tahap ini tidak mengubah baseline hidrologi Tahap 1 dan tidak melakukan tuning tersembunyi terhadap P175. Event 2025 diperlakukan sebagai **validation event**.

## 2. Input yang Diperlukan

### Wajib

1. Raster/vector flood extent kejadian November 2025 yang independen dari model GFI.
2. Batas DAS Kuranji.
3. Raster skenario Tahap 2:
   - M175
   - M250
   - P175
   - P250
4. Administrasi whole-DAS dan focus Pauh–Kuranji.

### Sumber flood extent yang disarankan

Prioritas sumber:

1. Produk resmi/otoritatif yang menyediakan flood extent spasial siap pakai;
2. derivasi Sentinel-1 SAR menggunakan citra sebelum dan saat kejadian;
3. digitasi berdasarkan citra/produk resmi jika polygon siap pakai tidak tersedia.

Jika menggunakan derivasi Sentinel-1, seluruh parameter, tanggal citra, orbit, preprocessing, threshold, dan masking harus disimpan agar reproduktif.

## 3. Prinsip Validasi

### 3.1 Jangan menggunakan event 2025 untuk calibration sekaligus validation

Threshold/model tidak boleh dituning menggunakan flood extent 2025 kemudian diuji terhadap flood extent yang sama.

### 3.2 Validasi extent dan validasi kelas harus dibedakan

Flood extent biner hanya dapat memvalidasi **lokasi area terprediksi banjir**.

Karena:

- P175 dan P250 menggunakan domain flood-prone yang sama (`WD > 0`);
- M175 dan M250 menggunakan domain manual yang sama;
- perbedaan spread 1.75 versus 2.50 terutama mengubah nilai indeks/kelas di dalam domain, bukan extent domain.

Maka flood extent biner dapat membedakan pendekatan `P` versus `M`, tetapi **tidak cukup untuk menentukan spread 1.75 atau 2.50 mana yang lebih benar**.

Untuk memvalidasi spread/kelas rendah–sedang–tinggi diperlukan data tambahan seperti kedalaman genangan observasi, tinggi muka air, survey lapangan, atau proxy severity yang dapat dipertanggungjawabkan.

## 4. Metrik Utama

Untuk setiap skenario, hitung pada domain DAS:

- True Positive (TP)
- False Positive (FP)
- False Negative (FN)
- True Negative (TN)
- Precision = TP / (TP + FP)
- Recall = TP / (TP + FN)
- F1 = 2 * Precision * Recall / (Precision + Recall)
- Intersection over Union (IoU) = TP / (TP + FP + FN)
- Specificity = TN / (TN + FP)
- Predicted flood area
- Observed flood area
- Intersection area
- False-positive area
- False-negative area

Metrik juga dihitung per kecamatan dan, jika relevan, per kelurahan/desa.

## 5. Interpretasi

Tidak ada satu metrik tunggal yang cukup.

- Precision tinggi: sebagian besar area prediksi memang berada di flood extent observasi.
- Recall tinggi: sebagian besar flood extent observasi berhasil ditangkap model.
- F1: keseimbangan precision dan recall.
- IoU: overlap spasial yang lebih ketat.

Kegagalan lokal perlu dipetakan sebagai FP/FN untuk memahami apakah error terkait floodplain datar, urban drainage, tributari kecil, batas pesisir, atau keterbatasan sumber observasi.

## 6. Validasi Kontekstual Administratif

Data jumlah penduduk terdampak, rumah rusak, lokasi kejadian, atau laporan BPBD dapat digunakan sebagai **contextual corroboration**, bukan sebagai pengganti flood extent spasial.

Jumlah warga terdampak tidak boleh dibandingkan langsung sebagai ukuran akurasi hazard karena dipengaruhi exposure, population density, vulnerability, waktu evakuasi, dan definisi pelaporan.

## 7. Output Tahap 3

Folder yang direncanakan:

```text
data/work/kuranji/15_stage3_validation/
├── input/
│   └── OBSERVED_FLOOD_2025.*
├── raster/
│   ├── OBSERVED_FLOOD_2025_ALIGNED.tif
│   ├── P175_TP_FP_FN_TN.tif
│   ├── M175_TP_FP_FN_TN.tif
│   ├── P250_TP_FP_FN_TN.tif
│   └── M250_TP_FP_FN_TN.tif
├── table/
│   ├── validation_metrics_das.csv
│   ├── validation_metrics_kecamatan.csv
│   └── validation_metrics_kelurahan.csv
├── qc/
│   └── stage3_validation_qc.json
└── README_STAGE3_VALIDATION.md
```

## 8. Peta Laporan

1. Flood extent observasi November 2025;
2. overlay observed versus P175;
3. peta TP/FP/FN/TN P175;
4. overlay observed versus M175;
5. perbandingan metrik P-domain versus M-domain;
6. distribusi FP/FN per kecamatan;
7. detail focus Pauh–Kuranji;
8. jika depth observations tersedia, peta validasi kelas/depth.

## 9. Keputusan Setelah Validasi

Setelah metrik eksternal tersedia:

- tentukan apakah physical domain (`WD > 0`) atau manual domain lebih konsisten dengan flood extent observasi;
- jangan memilih spread 1.75/2.50 hanya dari extent biner;
- jika tersedia depth/severity observations, lakukan validasi kelas secara terpisah;
- baru setelah itu status P175 dapat dipertahankan, direvisi, atau diganti sebagai kandidat baseline yang lebih kuat.
