# Sinkronisasi Tahap 2 dengan MODUL TEKNIS KRB BANJIR-2

## Status

Dokumen ini menjadi checkpoint metodologis Tahap 2. Acuan utama adalah `MODUL TEKNIS KRB BANJIR-2.pdf`, sedangkan `RBI 2023-2_2.pdf` digunakan sebagai referensi pendukung. Deskripsi penelitian tetap menjadi kerangka tujuan: analisis indeks bahaya banjir DAS Batang Kuranji, fokus Pauh dan Kuranji hingga kelurahan, serta perbandingan kondisi sebelum dan setelah kejadian 2025 apabila data temporal yang memadai tersedia.

---

## 1. Hierarki Acuan

1. **Acuan operasional utama:** MODUL TEKNIS KRB BANJIR-2.
2. **Acuan pendukung:** RBI 2023-2.
3. **Literatur ilmiah:** Samela et al. 2017/2018, Manfreda & Samela 2019, serta referensi lain untuk justifikasi dan pembahasan.
4. **Adaptasi komputasi:** Python, Rasterio, NumPy, SciPy, WhiteboxTools, dan QGIS diperbolehkan selama prinsip dasar prosedur modul dipertahankan dan setiap penyimpangan dari langkah literal modul didokumentasikan.

---

## 2. Koreksi terhadap Roadmap Lama

Roadmap lama yang memasukkan `slope + distance to stream -> fuzzy overlay -> flood hazard index` **tidak sesuai dengan modul yang sekarang sudah tersedia**.

Alur modul yang benar adalah:

```text
DEM + DAS + RBI + Batas Administrasi
              ↓
Hydrological preparation
              ↓
Flow Direction + Flow Accumulation
              ↓
Geomorphic Flood Index (GFI)
              ↓
Flood-prone / Area Potensi Banjir
              ↓
H dan hr
              ↓
Ketinggian Genangan: WD = hr - H
              ↓
Fuzzy Membership (Large)
 midpoint = 1.125 m
 spread = 1.75
              ↓
Indeks Bahaya Banjir 0–1
              ↓
Rendah / Sedang / Tinggi
              ↓
Tabulate area per kelurahan/kecamatan
```

Slope dan Euclidean distance to stream tidak menjadi komponen pembentuk indeks bahaya pada modul ini.

---

## 3. Data Minimum Menurut Modul

Modul mensyaratkan:

- batas administrasi, sumber BIG/Bappeda;
- DEM Nasional (DEMNAS), sumber BIG;
- batas DAS, sumber KLHK;
- jaringan sungai RBI, sumber BIG.

Data penelitian DAS Kuranji telah memenuhi kebutuhan dasar tersebut.

Data tambahan yang sangat penting untuk kalibrasi adalah peta area banjir historis atau peta genangan hasil simulasi yang telah divalidasi.

---

## 4. Sinkronisasi dengan Tahap 1

### 4.1 Yang sudah sesuai prinsip modul

Tahap 1 telah menghasilkan:

- DEM terproyeksi UTM EPSG:32747;
- hydrologically conditioned DEM;
- D8 flow direction;
- flow accumulation;
- jaringan sungai model;
- delineasi watershed;
- validasi terhadap DAS dan RBI.

Modul secara eksplisit menganjurkan penyeragaman sistem koordinat ke UTM/World Mercator agar perhitungan matematis menggunakan meter. Tahap 1 telah menggunakan EPSG:32747.

### 4.2 Adaptasi penting: Breach100 vs Fill

Modul literal menggunakan `Fill` untuk memperbaiki DEM sebelum flow direction dan accumulation.

Tahap 1 menguji Fill dan menemukan watershed hanya sekitar 177.161 km². Uji sensitivitas kemudian menunjukkan `BreachDepressionsLeastCost` 100 cells menghasilkan watershed 212.125 km², IoU 0.9161, Dice 0.9562, serta menghubungkan 98.47% secondary partition.

Karena itu penelitian menggunakan BREACH100 sebagai **adaptasi hydrological conditioning berbasis validasi lokal**.

Keputusan ini harus dilaporkan sebagai adaptasi dari prosedur modul, bukan replikasi literal ArcGIS Fill.

Baseline Fill tetap disimpan sebagai sensitivity/reference product.

---

## 5. Formula GFI yang Dikunci

Konsep modul mengikuti:

`GFI = ln(hr / H)`

Dengan:

- `H` = perbedaan elevasi antara piksel/floodplain dan elemen jaringan sungai yang terhubung secara hidrologis (konsep HAND/relative elevation);
- `hr` = estimasi kedalaman sungai pada elemen jaringan sungai terhubung;
- `Ar` = upslope contributing area pada elemen sungai;
- `hr` diturunkan dari hydraulic scaling relation yang menggunakan contributing area;
- plugin GFA pada modul menunjukkan default hydraulic scaling relation exponent sekitar `0.3544`.

Implementasi Python Tahap 2 harus diverifikasi terhadap perilaku plugin GFA sebelum hasil dianggap final.

---

## 6. Parameter GFA Modul

Gambar methodology options pada modul menunjukkan default:

- flow direction coding: `ESRI`;
- drainage network identification method: `channel_ASk`;
- drainage network identification threshold: `10000`;
- hydraulic scaling relation exponent: sekitar `0.3544`.

Catatan penting: `10000` pada GFA adalah threshold internal plugin yang perlu dipastikan unit dan perilakunya dari source code. Tahap 1 menghasilkan threshold stream lokal 6 km² untuk jaringan final/validasi RBI. Kedua threshold tidak boleh dianggap otomatis identik sebelum fungsi internal GFA direplikasi dan diuji.

---

## 7. Kalibrasi Threshold GFI

Modul menunjukkan dua kemungkinan:

1. `Manually set threshold`, dengan antarmuka menampilkan classifier threshold sekitar `-0.53` sebagai nilai default/manual;
2. `Calibrate Threshold`, dengan memasukkan `Standard flood hazard map`.

Prosedur studi kasus modul memilih **Calibrate Threshold**.

Dengan demikian `-0.53` tidak diperlakukan sebagai threshold universal yang wajib digunakan.

### Rencana Kuranji

Urutan preferensi:

1. Gunakan flood extent historis independen sebelum 2025 untuk kalibrasi GFI.
2. Gunakan flood extent 2025 sebagai data validasi independen.
3. Jika tidak tersedia data historis independen, gunakan threshold manual/default sebagai baseline dan gunakan 2025 hanya untuk validasi.
4. Hindari menggunakan flood extent 2025 untuk kalibrasi sekaligus validasi pada dataset yang sama karena menghasilkan evaluasi sirkular.

---

## 8. Area Potensi Banjir

Output GFA mencakup:

- GFI raster;
- GFI-derived flood-prone areas map;
- intermediate `H`;
- intermediate `hr`.

Area potensi banjir diperoleh dari flood-prone output setelah klasifikasi threshold GFI.

Area di luar potensi banjir tidak digunakan untuk menghitung hazard inundation final.

---

## 9. Ketinggian Genangan

Modul menetapkan:

`WD = hr - H`

Dengan:

- `WD` = water depth / ketinggian genangan;
- `hr` dan `H` merupakan output/intermediate GFI.

Raster WD harus mengikuti extent, snap/grid, dan mask area potensi banjir.

Output yang direncanakan:

`KETINGGIAN_GENANGAN_WD.tif`

---

## 10. Indeks Bahaya Banjir

Ukuran hazard menurut modul adalah **ketinggian genangan**.

Kelas kedalaman berdasarkan Perka BNPB No. 2/2012:

- rendah: WD ≤ 0.75 m;
- sedang: 0.75 m < WD ≤ 1.5 m;
- tinggi: WD > 1.5 m.

Untuk menghasilkan indeks kontinu 0–1, modul menggunakan Fuzzy Membership:

- membership type: `Large`;
- midpoint: `1.125`;
- spread: `1.75`.

Semakin besar WD, nilai membership semakin mendekati 1.

Output:

`INDEKS_BAHAYA_BANJIR.tif`

---

## 11. Klasifikasi Indeks Bahaya

Kelas indeks hazard:

- Rendah: `H ≤ 0.333`;
- Sedang: `0.333 < H ≤ 0.666`;
- Tinggi: `H > 0.666`.

Kode raster final:

- 1 = rendah;
- 2 = sedang;
- 3 = tinggi.

Output:

`KELAS_BAHAYA_BANJIR.tif`

---

## 12. Statistik Administratif

Modul menghitung luas per kelas dengan pendekatan Tabulate Area:

- unit dasar: m²;
- dikonversi ke hektar dengan membagi 10,000;
- statistik minimal: luas rendah, sedang, tinggi, total.

Penelitian Kuranji akan menghitung:

- seluruh DAS;
- Kecamatan Pauh;
- Kecamatan Kuranji;
- setiap kelurahan yang beririsan dengan wilayah analisis.

### Catatan interpretasi modul

Teks modul menyebut kesimpulan administratif menggunakan `skenario terburuk atau kelas maksimum`, tetapi formula Excel contoh pada tingkat desa/kelurahan memilih kelas dengan **luas terbesar** di antara rendah/sedang/tinggi. Setelah itu kelas kecamatan direkap dengan fungsi `Max` pada kode kelas.

Karena ada potensi ambiguitas tersebut, penelitian akan selalu melaporkan **luas setiap kelas** sebagai hasil utama. Satu kolom kelas administratif dapat disediakan mengikuti aturan modul, tetapi metode agregasinya harus dinyatakan eksplisit dan tidak menggantikan statistik luas per kelas.

---

## 13. Hubungan dengan Tujuan Sebelum–Sesudah Siklon Senyar

Modul KRB menjelaskan pembuatan hazard untuk **satu kondisi topografi**. Modul tidak menyediakan metode khusus untuk analisis perubahan temporal T0–T1.

Karena Deskripsi Riset meminta perbandingan sebelum dan setelah kejadian, prosedur yang benar adalah menjalankan pipeline yang sama pada dua kondisi DEM yang comparable:

```text
T0 DEM pra-event
    ↓
GFI T0 → WD T0 → Indeks Bahaya T0 → Kelas T0

T1 DEM pasca-event
    ↓
GFI T1 → WD T1 → Indeks Bahaya T1 → Kelas T1

                    ↓
       Perbandingan / perubahan
```

Untuk comparability:

- CRS sama;
- grid/snap sama;
- vertical datum kompatibel;
- co-registration dilakukan;
- parameter GFI/hydraulic relation sama;
- classifier/calibration threshold sama, kecuali ada alasan ilmiah kuat dan hasil dilaporkan terpisah;
- perubahan di bawah uncertainty DEM tidak dinyatakan sebagai perubahan fisik.

Jika DEM T1 yang layak tidak tersedia, output penelitian dibatasi menjadi baseline hazard + validasi terhadap observed flood 2025, bukan perubahan topografi kausal.

---

## 14. Roadmap Tahap 2 yang Dikunci

### Checkpoint 2A — Replikasi GFA

1. Audit source code plugin GFA.
2. Pastikan unit threshold internal `10000`.
3. Replikasi channel identification dan hydraulic scaling relation.
4. Uji hasil intermediate terhadap expected behaviour plugin.

### Checkpoint 2B — GFI Baseline

5. Gunakan baseline hydrology final Tahap 1.
6. Hitung `H`.
7. Hitung `hr`.
8. Hitung `GFI = ln(hr/H)`.
9. QC GFI dan intermediate rasters.

### Checkpoint 2C — Flood-prone Calibration

10. Siapkan standard/historical flood map yang independen jika tersedia.
11. Kalibrasi classifier threshold GFI.
12. Jika tidak tersedia, gunakan manual/default threshold sebagai baseline dan dokumentasikan.
13. Bentuk `Area_Potensi_Banjir`.

### Checkpoint 2D — Water Depth dan Hazard

14. Hitung `WD = hr - H` hanya dalam area potensi banjir.
15. Terapkan Fuzzy Large, midpoint 1.125, spread 1.75.
16. Hasilkan indeks hazard 0–1.
17. Klasifikasikan: ≤0.333, 0.333–0.666, >0.666.

### Checkpoint 2E — Administrasi dan Laporan

18. Tabulasi luas kelas DAS.
19. Tabulasi Pauh dan Kuranji.
20. Tabulasi per kelurahan.
21. Buat tabel, grafik, dan peta.
22. Dokumentasikan QC, parameter, adaptation, dan uncertainty.

---

## 15. Peta Tahap 2

Minimum:

1. GFI kontinu.
2. Area potensi banjir / flood-prone mask.
3. H / relative elevation.
4. hr.
5. Ketinggian genangan WD.
6. Indeks bahaya banjir 0–1.
7. Kelas bahaya rendah–sedang–tinggi seluruh DAS.
8. Kelas bahaya Pauh dan Kuranji.
9. Kelas bahaya per kelurahan.

Intermediate maps dapat ditempatkan di lampiran jika laporan utama terlalu padat.

---

## 16. Tabel Tahap 2

Minimum:

1. Parameter GFI dan sumbernya.
2. Parameter GFA/module vs implementasi Python.
3. Statistik H, hr, GFI, dan WD.
4. Hasil threshold calibration GFI.
5. Luas flood-prone area.
6. Luas kelas hazard seluruh DAS.
7. Luas kelas hazard per kecamatan.
8. Luas kelas hazard per kelurahan.
9. QC dan uncertainty summary.

---

## 17. Keputusan yang Dikunci Saat Ini

- Tahap 1 tidak diulang.
- BREACH100 tetap baseline penelitian, dengan Fill dipertahankan sebagai sensitivity product.
- GFI bukan kelas bahaya final; GFI digunakan untuk menentukan area potensi genangan.
- Hazard final berasal dari WD yang ditransformasikan dengan Fuzzy Large.
- Slope + distance-to-stream fuzzy overlay dihapus dari roadmap karena tidak terdapat dalam modul ini.
- Threshold GFI tidak otomatis -0.53; kalibrasi independen lebih diutamakan.
- Flood extent 2025 sebaiknya tidak digunakan sekaligus sebagai calibration dan validation dataset.
- Statistik luas per kelas selalu dilaporkan meskipun satu kelas administratif juga disimpulkan.
