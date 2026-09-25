# LAPORAN TAHAP 2 — ANALISIS GFI DAN KANDIDAT BASELINE BAHAYA BANJIR DAS BATANG KURANJI

## 1. Status Tahap 2

Tahap 2 analisis DAS Batang Kuranji telah diselesaikan secara komputasional dan administratif.

Produk utama tahap ini adalah **kandidat baseline bahaya banjir P175**, bukan peta bahaya final terkalibrasi. Validasi eksternal terhadap kejadian banjir besar 21–27 November 2025 masih harus dilakukan pada Tahap 3.

Status akhir Tahap 2:

- baseline hidrologi Tahap 1 tetap digunakan dan tidak diulang;
- jaringan drainase utama menggunakan threshold flow accumulation ekuivalen 6 km²;
- GFI dihitung menggunakan pendekatan GFA/Geomorphic Flood Index yang diaudit terhadap source code plugin;
- domain flood-prone primer ditetapkan berdasarkan kondisi fisik `WD > 0`, ekuivalen dengan `GFI_raw > 0`;
- tinggi genangan dihitung sebagai `WD = hr - H`;
- indeks bahaya dihitung dengan Fuzzy Membership tipe Large;
- parameter primer fuzzy menggunakan midpoint 1.125 m dan spread 1.75;
- klasifikasi indeks bahaya: rendah `<=0.333`, sedang `>0.333–0.666`, tinggi `>0.666`;
- statistik administratif dihitung untuk seluruh DAS dan fokus Pauh–Kuranji;
- QC konservasi administratif berstatus **PASS**.

---

## 2. Dasar Metode

Metode Tahap 2 mengikuti struktur prosedural dalam `MODUL TEKNIS KRB BANJIR-2` dengan penyesuaian perangkat lunak dan implementasi yang tetap mempertahankan prinsip dasar prosedur.

Urutan metode yang digunakan:

1. DEM dan batas DAS hasil Tahap 1;
2. flow direction dan flow accumulation;
3. identifikasi jaringan drainase;
4. perhitungan parameter GFI;
5. penentuan area berpotensi banjir;
6. perhitungan `H` dan `hr`;
7. perhitungan tinggi genangan `WD = hr - H`;
8. Fuzzy Membership tipe Large;
9. klasifikasi indeks bahaya rendah, sedang, tinggi;
10. overlay dengan administrasi;
11. tabulasi luas bahaya per wilayah administrasi.

Tahap 2 tidak menggunakan kombinasi slope + distance-to-stream sebagai hazard index karena alur tersebut tidak sesuai dengan prosedur utama modul yang menjadi dasar penelitian ini.

---

## 3. Audit Implementasi GFA

Source code `HydroLAB-UNIBAS/GFA-Geomorphic-Flood-Area` telah diaudit untuk memastikan interpretasi metodologi.

Temuan penting:

### 3.1 Drainage network

Mode `channel_ASk` pada GFA menggunakan relasi slope–area dengan seed:

```text
tmp = flowacc * cellsize² * (G + 0.0001)^1.7
seed = tmp > 100000
```

Angka GUI `10000` pada mode tersebut bukan threshold 10.000 cell flow accumulation seperti yang semula dapat diasumsikan.

### 3.2 Parameter hr

Source aktif menghitung:

```text
hr = A_km² ^ n
```

dengan nilai default runtime:

```text
n = 0.354429752
```

### 3.3 GFI

GFI mentah:

```text
GFI_raw = ln(hr / H)
```

Kemudian dinormalisasi ke rentang `[-1,+1]`.

Threshold manual `-0.53` dalam plugin diterapkan pada GFI ternormalisasi, bukan GFI mentah.

### 3.4 Kalibrasi

Plugin mendukung kalibrasi threshold GFI menggunakan flood map referensi dan ROC. Namun, tidak ditemukan flood map independen pra-2025 yang memadai untuk kalibrasi di dataset lokal.

Karena itu, threshold final tidak boleh disebut sebagai threshold empiris terkalibrasi.

---

## 4. Keputusan Jaringan Drainase

Dua pendekatan diuji:

| Metode | Panjang jaringan | Heads | Outlet | Components | P100 | R100 | F1 | F2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GFA channel_ASk | 203.28 km | 121 | 1 | 1 | 0.117 | 0.563 | 0.194 | 0.320 |
| Local FAt 6 km² | 81.00 km | 12 | 1 | 1 | 0.281 | 0.551 | 0.372 | 0.462 |

Panjang RBI adalah sekitar 79.813 km.

Jaringan `Local FAt 6 km²` dipilih sebagai baseline karena paling mendekati panjang RBI, tetap menghasilkan satu outlet dan satu komponen jaringan, serta mempertahankan struktur tributari yang memadai.

---

## 5. GFI Baseline

Hasil GFI baseline menggunakan jaringan drainase 6 km²:

```text
Analysis cells      : 3,238,533
Channel cells       : 8,274
Resolved routing    : 99.862%
Unresolved          : 4,469 cells
Negative H cells    : 0
Zero H cells        : 8,274
GFI raw range       : -6.638383 .. 13.411668
GFI norm range      : -1.000000 .. 1.000000
```

Threshold manual `GFI_norm > -0.53` menghasilkan area potensial banjir sekitar 60.138 km² atau 26.76% DAS raster.

Namun, audit WD menunjukkan bahwa sebagian besar area tersebut memiliki nilai `WD < 0`, sehingga threshold manual tersebut tidak layak langsung dianggap sebagai baseline fisik final untuk DAS Kuranji.

---

## 6. Audit Threshold dan Water Depth

Dengan threshold manual `-0.53`:

```text
Flood-prone area    : 60.138 km²
WD negative cells   : 675,819 (77.969%)
WD positive cells   : 190,955 (22.031%)
WD raw range        : -32.696686 .. 6.677484 m
```

Secara matematis:

```text
WD > 0
<=> hr > H
<=> ln(hr/H) > 0
<=> GFI_raw > 0
```

Batas `GFI_raw = 0` ekuivalen dengan sekitar `GFI_norm = -0.337819` pada rentang GFI Kuranji.

Batas ini **bukan hasil kalibrasi banjir eksternal**. Ia hanya batas fisik yang konsisten dengan syarat `WD > 0`.

---

## 7. Sensitivitas Threshold GFI

Hasil sensitivitas menunjukkan bahwa area dengan `GFI_raw > 0` sama dengan area `WD > 0`:

```text
Physical positive WD area : 13.249 km²
Share of DAS               : 5.90%
```

Contoh sensitivitas:

| GFI norm threshold | Area (km²) | Positive WD | Negative WD |
|---:|---:|---:|---:|
| -0.5300 | 60.138 | 22.03% | 77.97% |
| -0.4000 | 28.257 | 46.89% | 53.11% |
| -0.3500 | 16.598 | 79.82% | 20.18% |
| -0.3400 | 13.819 | 95.87% | 4.13% |
| -0.3378 | 13.244 | 100.00% | 0.00% |

Karena hubungan ini bersifat matematis, kesesuaian tersebut tidak boleh digunakan sebagai klaim validasi independen.

---

## 8. Ambiguitas Parameter Fuzzy

Modul tertulis menyebutkan:

```text
Fuzzy Membership = Large
midpoint = 1.125 m
spread = 1.75
```

Namun, nilai numerik pada salah satu contoh gambar modul lebih sesuai dengan spread sekitar 2.5.

Karena itu empat skenario diuji:

| Scenario | Domain | Spread | Area (km²) | Low | Medium | High |
|---|---|---:|---:|---:|---:|---:|
| M175 | manual -0.53 | 1.75 | 60.138 | 85.79% | 7.08% | 7.13% |
| M250 | manual -0.53 | 2.50 | 60.138 | 86.67% | 5.03% | 8.30% |
| P175 | physical WD>0 | 1.75 | 13.249 | 35.49% | 32.13% | 32.38% |
| P250 | physical WD>0 | 2.50 | 13.249 | 39.51% | 22.81% | 37.67% |

---

## 9. Kandidat Baseline Primer: P175

Scenario **P175** dipilih sebagai kandidat baseline primer karena:

1. mengikuti struktur modul `GFI -> flood-prone -> WD -> fuzzy`;
2. menggunakan domain dengan `WD > 0`, sehingga tidak mempertahankan nilai tinggi genangan negatif dalam domain hazard;
3. menggunakan spread 1.75 yang tertulis eksplisit dalam modul;
4. midpoint 1.125 m mengikuti modul;
5. tetap mempertahankan seluruh skenario alternatif sebagai analisis sensitivitas.

Status P175 harus disebut:

> **primary baseline hazard candidate**

bukan:

> final calibrated flood hazard map.

---

## 10. Hasil P175 Seluruh DAS

Luas DAS raster:

```text
224.694 km²
```

Area hazard P175:

```text
13.249 km²
5.90% dari DAS raster
```

Distribusi kelas:

| Kelas | Luas (km²) | Persentase area hazard |
|---|---:|---:|
| Rendah | 4.702 | 35.49% |
| Sedang | 4.257 | 32.13% |
| Tinggi | 4.290 | 32.38% |

---

## 11. Audit Administrasi Seluruh DAS

Master administrasi menggunakan `Sumatera_Barat.shp` dengan atribut:

```text
WADMPR = Provinsi
WADMKK = Kabupaten/Kota
WADMKC = Kecamatan
WADMKD = Desa/Kelurahan
```

Audit spasial menghasilkan:

```text
Official DAS area    : 224.696 km²
Admin union coverage : 224.598 km²
Coverage              : 99.9565%
Uncovered             : 0.097688 km²
```

DAS Kuranji beririsan dengan:

- 3 kabupaten/kota;
- 10 kecamatan;
- 41 desa/kelurahan.

### 11.1 Kabupaten/Kota

| Kabupaten/Kota | Luas dalam DAS (km²) | % DAS |
|---|---:|---:|
| Kota Padang | 223.531 | 99.482% |
| Solok | 1.008 | 0.449% |
| Kota Solok | 0.058 | 0.026% |

### 11.2 Kecamatan

| Kecamatan | Kab/Kota | Luas dalam DAS (km²) | % DAS |
|---|---|---:|---:|
| Pauh | Kota Padang | 124.549 | 55.43% |
| Kuranji | Kota Padang | 50.130 | 22.31% |
| Koto Tangah | Kota Padang | 32.069 | 14.27% |
| Nanggalo | Kota Padang | 9.417 | 4.19% |
| Padang Utara | Kota Padang | 7.148 | 3.18% |
| Kubung | Solok | 0.722 | 0.32% |
| X Koto Singkarak | Solok | 0.286 | 0.13% |
| Padang Barat | Kota Padang | 0.109 | 0.05% |
| Lubuk Kilangan | Kota Padang | 0.107 | 0.05% |
| Lubuk Sikarah | Kota Solok | 0.058 | 0.03% |

---

## 12. Focus Area Pauh dan Kuranji

Pauh dan Kuranji tetap dipertahankan sebagai focus area penelitian karena secara bersama mencakup:

```text
174.680 km²
77.74% dari DAS
```

Pauh:

```text
124.549 km²
55.43% DAS
```

Kuranji:

```text
50.130 km²
22.31% DAS
```

Namun, analisis fisik tetap dilakukan pada seluruh DAS agar tidak memotong proses hidrologi dan hazard secara administratif.

---

## 13. Distribusi Hazard P175 per Kecamatan

| Kecamatan | Zone (km²) | Hazard (km²) | High (km²) |
|---|---:|---:|---:|
| Pauh | 124.550 | 1.443 | 0.894 |
| Kuranji | 50.127 | 2.086 | 0.642 |
| Koto Tangah | 32.070 | 3.322 | 0.825 |
| Nanggalo | 9.418 | 3.888 | 0.878 |
| Padang Utara | 7.150 | 2.480 | 1.031 |
| Kubung | 0.722 | 0.000 | 0.000 |
| X Koto Singkarak | 0.285 | 0.000 | 0.000 |
| Padang Barat | 0.110 | 0.000 | 0.000 |
| Lubuk Kilangan | 0.108 | 0.000 | 0.000 |
| Lubuk Sikarah | 0.058 | 0.000 | 0.000 |

Temuan ini menunjukkan bahwa area hazard P175 tidak terkonsentrasi hanya di Pauh dan Kuranji. Area hilir perkotaan pada Nanggalo, Koto Tangah, dan Padang Utara memiliki luasan hazard kandidat yang besar.

Interpretasi tersebut masih bersifat geomorfologis/model-based dan belum boleh disamakan dengan distribusi banjir aktual November 2025 sebelum validasi eksternal dilakukan.

---

## 14. Focus Kelurahan Pauh–Kuranji

Layer fokus memiliki 18 kelurahan.

Tiga kelurahan tercatat di luar DAS:

- Koto Lua;
- Piai Tangah;
- Pisang.

Kelurahan fokus dengan area kelas tinggi P175 terbesar antara lain:

| Kecamatan | Kelurahan | High (km²) | Total Hazard (km²) |
|---|---|---:|---:|
| Pauh | Lambung Bukit | 0.391 | 0.635 |
| Pauh | Limau Manis | 0.390 | 0.657 |
| Kuranji | Gunung Sarik | 0.242 | 0.601 |
| Kuranji | Pasar Ambacang | 0.129 | 0.152 |
| Kuranji | Kuranji | 0.103 | 0.323 |

Istilah **prioritas risiko** tidak digunakan pada tahap ini karena belum ada komponen exposure dan vulnerability. Angka tersebut hanya menunjukkan luasan kelas bahaya tinggi hasil model.

---

## 15. Kelurahan/Desa dengan Area Kelas Tinggi Terbesar di Seluruh DAS

| Rank | Kab/Kota | Kecamatan | Kelurahan/Desa | High (km²) | Hazard (km²) |
|---:|---|---|---|---:|---:|
| 1 | Kota Padang | Koto Tangah | Dadok Tunggul Hitam | 0.596 | 1.919 |
| 2 | Kota Padang | Padang Utara | Ulak Karang Utara | 0.426 | 0.643 |
| 3 | Kota Padang | Pauh | Lambung Bukit | 0.391 | 0.635 |
| 4 | Kota Padang | Pauh | Limau Manis | 0.390 | 0.657 |
| 5 | Kota Padang | Nanggalo | Kurao Pagang | 0.328 | 2.087 |
| 6 | Kota Padang | Padang Utara | Ulak Karang Selatan | 0.261 | 0.759 |
| 7 | Kota Padang | Kuranji | Gunung Sarik | 0.242 | 0.601 |
| 8 | Kota Padang | Nanggalo | Kampung Lapai | 0.219 | 0.678 |
| 9 | Kota Padang | Koto Tangah | Aie Pacah | 0.217 | 1.064 |
| 10 | Kota Padang | Padang Utara | Air Tawar Timur | 0.161 | 0.445 |

---

## 16. QC Konservasi Administratif

QC konservasi membandingkan total DAS terhadap agregasi kabupaten/kota, kecamatan, dan kelurahan.

Hasil:

```text
DAS raster area : 224.694 km²
Tolerance       : 0.100% dari luas DAS penuh
```

| Level | Zone diff (km²) | Hazard diff (km²) | Hazard diff % DAS |
|---|---:|---:|---:|
| Kab/Kota | -0.0961 | -0.0302 | 0.0134% |
| Kecamatan | -0.0961 | -0.0302 | 0.0134% |
| Kelurahan | -0.0961 | -0.0302 | 0.0134% |

Defisit identik pada seluruh level administrasi.

Interpretasi:

- tidak ditemukan kehilangan area akibat agregasi antar level;
- selisih konsisten dengan gap coverage batas administrasi terhadap batas DAS;
- focus Pauh–Kuranji identik pada master, tabel kecamatan, dan tabel 18 kelurahan.

Status:

```text
WHOLE-DAS HAZARD CONSERVATION: PASS
```

---

## 17. Produk Final Tahap 2

Folder utama:

```text
data/work/kuranji/14_stage2_admin_final/
```

Raster:

```text
P175_WD_INPUT.tif
P175_HAZARD_INDEX.tif
P175_HAZARD_CLASS.tif
```

Tabel:

```text
hazard_stats_das.csv
hazard_stats_kabkota.csv
hazard_stats_kecamatan_all.csv
hazard_stats_kelurahan_all_intersecting.csv
hazard_stats_focus_kecamatan.csv
hazard_stats_focus_kelurahan_18.csv
sensitivity_das.csv
sensitivity_kecamatan_all.csv
```

Vector:

```text
ADMIN_ALL_INTERSECTING_UTM47S.geojson
ADMIN_FOCUS_PAUH_KURANJI_18_UTM47S.geojson
```

QC:

```text
stage2_admin_final_qc.json
stage2_admin_conservation_qc.json
```

---

## 18. Daftar Peta untuk Layout QGIS

Peta yang perlu dibuat untuk laporan:

1. Peta lokasi DAS Batang Kuranji dan batas administrasi;
2. Peta jaringan sungai RBI dan jaringan drainase baseline 6 km²;
3. Peta GFI raw;
4. Peta GFI normalized;
5. Peta domain flood-prone P175 (`WD > 0`);
6. Peta water depth P175;
7. Peta indeks bahaya P175 0–1;
8. Peta kelas bahaya P175 rendah/sedang/tinggi;
9. Peta kelas bahaya P175 seluruh DAS dengan batas kecamatan;
10. Peta fokus Pauh–Kuranji dengan batas 18 kelurahan;
11. Peta perbandingan M175–M250–P175–P250;
12. Peta validasi 2025 pada Tahap 3.

Untuk layout kelas bahaya, gunakan legenda:

```text
Rendah
Sedang
Tinggi
```

Peta Tahap 2 harus diberi label yang menjelaskan bahwa P175 adalah **baseline hazard candidate**.

---

## 19. Keterbatasan Tahap 2

1. P175 belum dikalibrasi menggunakan flood extent independen.
2. Threshold `GFI_raw > 0` berasal dari konsistensi fisik `WD > 0`, bukan dari empirical flood calibration.
3. Ambiguitas spread fuzzy antara teks modul dan nilai numerik contoh tetap dicatat dan diuji melalui sensitivitas.
4. Distribusi hazard P175 tidak boleh langsung disebut sebagai pola banjir aktual November 2025.
5. Fokus Pauh–Kuranji adalah fokus administratif/penelitian, bukan batas proses hidrologi.
6. Tidak dapat disimpulkan adanya perubahan topografi sebelum–sesudah bencana hanya dari satu DEMNAS statis.
7. Analisis perubahan topografi aktual membutuhkan DEM pascakejadian yang kompatibel secara temporal, horizontal, vertikal, dan resolusi.

---

## 20. Tahap 3 — Validasi Kejadian November 2025

Tahap berikutnya adalah validasi eksternal menggunakan flood extent/observasi kejadian banjir besar 21–27 November 2025.

Minimal skenario yang dibandingkan:

- P175;
- M175;
- P250;
- M250 sebagai sensitivitas tambahan.

Metrik validasi yang direkomendasikan:

- spatial overlap;
- precision;
- recall;
- F1;
- hit rate;
- false positive area;
- false negative area;
- distribusi error spasial per kecamatan/kelurahan.

Banjir 2025 sebaiknya digunakan sebagai **validation event**, bukan digunakan diam-diam untuk tuning threshold yang kemudian diuji terhadap data yang sama.

---

## 21. Keputusan Freeze Tahap 2

Tahap 2 dinyatakan **frozen untuk baseline komputasional** dengan ketentuan:

- P175 adalah primary baseline hazard candidate;
- jaringan drainase baseline = local FAt 6 km²;
- domain flood-prone primer = WD > 0 / GFI_raw > 0;
- fuzzy primer = Large, midpoint 1.125, spread 1.75;
- seluruh DAS dianalisis secara fisik;
- Pauh + Kuranji tetap sebagai focus area;
- hasil belum disebut final calibrated flood hazard sampai validasi Tahap 3 selesai.
