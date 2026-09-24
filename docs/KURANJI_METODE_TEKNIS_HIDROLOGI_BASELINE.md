# Metode Teknis Analisis Hidrologi Baseline DAS Batang Kuranji

## 1. Tujuan Dokumen

Dokumen ini merekam metode teknis, keputusan pemodelan, hasil validasi, dan batasan ilmiah untuk penyusunan baseline hidrologi DAS Batang Kuranji sebagai dasar analisis Geomorphic Flood Index (GFI) dan kajian perubahan bahaya banjir terkait kejadian banjir besar Siklon Senyar 21–27 November 2025.

Dokumen ini bukan hasil akhir analisis GFI. Tahap ini bertujuan memastikan bahwa DEM, arah aliran, akumulasi aliran, jaringan sungai model, dan delineasi watershed cukup konsisten secara hidrologis sebelum digunakan dalam perhitungan indeks bahaya.

---

## 2. Prinsip Ilmiah Utama

Perbedaan antara jaringan sungai RBI, batas DAS referensi, dan jaringan aliran hasil DEM tidak boleh langsung diinterpretasikan sebagai perubahan akibat bencana.

Penyebab perbedaan dapat berasal dari:

1. perbedaan tahun dan sumber data;
2. resolusi spasial;
3. metode delineasi;
4. kesalahan vertikal atau horizontal DEM;
5. metode hydrological conditioning;
6. perubahan geomorfologi yang benar-benar terjadi.

Karena DEMNAS yang digunakan berasal dari data lama dan bukan DEM pascakejadian November 2025, DEMNAS tidak dapat digunakan sendirian untuk menyatakan perubahan topografi sebelum–sesudah bencana.

Untuk analisis perubahan topografi secara langsung diperlukan setidaknya:

- T0 = DEM sebelum kejadian;
- T1 = DEM setelah kejadian;
- sistem referensi horizontal dan vertikal yang kompatibel;
- co-registration dan kontrol kesalahan elevasi.

Dengan kondisi data saat ini, DEMNAS diperlakukan sebagai **baseline topografi dan hidrologi**, sementara RBI diperlakukan sebagai **layer referensi/validasi**, bukan sebagai representasi waktu pascabencana.

---

## 3. Wilayah Studi

Wilayah utama adalah DAS Batang Kuranji, Kota Padang, Sumatera Barat.

Parameter DAS referensi:

- Nama DAS: KURANJI
- Kode DAS: DAS110385
- Wilayah kerja: BPDAS AGAM KUANTAN
- Luas referensi: sekitar 224.696 km²
- CRS kerja: EPSG:32747 (WGS 84 / UTM zone 47S)

Analisis administrasi lanjutan difokuskan pada Kecamatan Pauh dan Kuranji hingga tingkat kelurahan, tetapi pemodelan hidrologi dilakukan pada seluruh DAS dan area buffer agar tidak menimbulkan artefak batas.

---

## 4. Data Utama

### 4.1 DEMNAS

Dua tile DEMNAS digunakan untuk menutup DAS Kuranji dan buffer sekitar 3 km:

- DEMNAS_0715-32_v1.0.tif
- DEMNAS_0815-11_v1.0.tif

Karakteristik DEM hasil persiapan:

- CRS: EPSG:32747
- resolusi piksel: sekitar 8.3295 m
- ukuran sel: sekitar 69.3813 m²
- NoData: -9999

DEM buffer digunakan untuk hydrological conditioning dan routing agar aliran tidak terpotong pada batas DAS referensi.

### 4.2 Jaringan Sungai RBI

Layer referensi:

- Sungai (Garis)
- skala sekitar 1:50.000
- jumlah fitur setelah persiapan: 70
- panjang total jaringan di DAS: sekitar 79.813 km

RBI digunakan sebagai referensi geometrik untuk kalibrasi jaringan sungai model.

### 4.3 Batas DAS Referensi

Batas DAS Kuranji digunakan untuk:

- evaluasi luas watershed model;
- pengukuran IoU dan Dice;
- audit area reference-only dan model-only;
- kontrol interpretasi terhadap hasil routing DEM.

---

## 5. Persiapan DEM

DEM dikonversi ke CRS kerja EPSG:32747 dan disiapkan dalam dua bentuk:

1. DEM buffer 3 km untuk conditioning dan routing;
2. DEM clipped DAS untuk statistik dan pemeriksaan internal.

DEM sumber menggunakan GeoTIFF DEFLATE dengan floating-point `PREDICTOR=3`. WhiteboxTools 2.4.0 tidak dapat membaca format ini secara langsung.

Oleh karena itu dilakukan rewrite lossless ke GeoTIFF uncompressed:

`data/work/kuranji/02_hydrology/00_DEM_WBT_INPUT.tif`

Rewrite ini mempertahankan:

- nilai elevasi;
- grid;
- CRS;
- resolusi;
- NoData;

sehingga hanya berfungsi sebagai langkah kompatibilitas perangkat lunak dan bukan transformasi topografi.

---

## 6. Hydrological Conditioning Awal

Baseline pertama menggunakan:

- WhiteboxTools `FillDepressions`
- `fix_flats=True`
- `D8Pointer`
- `D8FlowAccumulation`

Output utama:

- `01_DEM_FILLED.tif`
- `02_D8_POINTER.tif`
- `03_FLOW_ACCUM_CELLS.tif`
- `04_FLOW_ACCUM_CA_M2.tif`

### 6.1 Audit FillDepressions

Di dalam DAS referensi:

- mean fill depth: sekitar 0.061 m
- p95: sekitar 0.315 m
- p99: sekitar 1.300 m
- maksimum: sekitar 22.241 m
- area dengan fill >5 m: sekitar 0.259 km²
- area dengan fill >10 m: sekitar 0.071 km²

Perubahan besar yang sebelumnya terlihat pada seluruh buffer tidak terjadi di dalam DAS dalam skala yang sama.

Namun hasil delineasi menunjukkan bahwa conditioning dengan full filling belum menghasilkan watershed yang cukup dekat dengan DAS referensi.

---

## 7. Kalibrasi Jaringan Sungai Model

Flow accumulation dikonversi menjadi jaringan sungai berdasarkan minimum contributing area.

Kandidat threshold yang diuji berkembang dari 0.1 hingga 20 km².

Evaluasi mencakup:

- panjang jaringan model;
- jumlah komponen;
- headwater;
- outlet;
- proximity model-to-RBI;
- proximity RBI-to-model;
- F1;
- F2 untuk memberikan bobot lebih tinggi pada recall.

Perbandingan kandidat utama:

| Threshold | Panjang model | Rasio terhadap RBI | Komponen | F1 100 m | F2 100 m |
|---|---:|---:|---:|---:|---:|
| 4 km² | 100.72 km | 1.26× | 3 | 0.320 | 0.417 |
| 5 km² | 89.60 km | 1.12× | 2 | 0.332 | 0.419 |
| 6 km² | 82.74 km | 1.04× | 2 | 0.341 | 0.422 |
| 20 km² | 53.32 km | 0.67× | 2 | 0.352 | 0.375 |

Threshold 6 km² dipilih sebagai **working threshold** karena:

- panjang jaringan paling dekat dengan RBI;
- F2 tertinggi;
- recall RBI tetap lebih baik dibanding threshold 20 km²;
- topology jaringan tetap sederhana dan konsisten.

Catatan penting: threshold 6 km² awalnya dipilih pada routing berbasis `FillDepressions`. Setelah conditioning final dipilih, threshold harus diuji ulang agar tidak membawa parameter kalibrasi secara otomatis dari conditioning lama.

---

## 8. Delineasi Watershed dengan Full Filling

Dengan baseline `FillDepressions`, outlet dengan flow accumulation maksimum di sekitar batas DAS menghasilkan:

- contributing area: sekitar 177.161 km²
- luas watershed model: sekitar 177.161 km²
- luas DAS referensi: sekitar 224.694 km²
- IoU: 0.7819
- Dice: 0.8776

Audit toleransi outlet hingga 1 km dari boundary dan 1 km dari RBI tidak menghasilkan catchment lebih besar. Dengan demikian masalah bukan sekadar snapping outlet.

Analisis partition menunjukkan adanya satu secondary drainage partition stabil sekitar 31.7–32.0 km².

Pada grouping 100 m:

- zona utama: sekitar 177.768 km²
- zona sekunder: sekitar 31.969 km²

Partition sekunder tersebut memiliki:

- dominant outlet accumulation sekitar 32.705 km²;
- jarak outlet dominan ke RBI sekitar 1.420 km;
- jaringan stream threshold 6 km² yang tidak berada dalam 100 m dari RBI.

Audit fill depth di partition sekunder menunjukkan perubahan conditioning relatif kecil secara areal:

- >0.1 m: sekitar 1.545% zona;
- >1 m: sekitar 0.828%;
- >5 m: sekitar 0.278%;
- >10 m: sekitar 0.101%.

Temuan ini menunjukkan bahwa perbedaan jaringan aliran tidak dapat dijelaskan hanya oleh beberapa sel fill yang dalam.

---

## 9. Uji Sensitivitas Conditioning

Karena full filling menghasilkan watershed hanya sekitar 177 km², dilakukan uji dengan WhiteboxTools `BreachDepressionsLeastCost`.

Dua skenario diuji:

1. `breach100`: search distance 100 cells (~833 m)
2. `breach250`: search distance 250 cells (~2.082 km)

Kedua skenario menggunakan:

- `--min_dist`
- `--fill`

sehingga depression yang tidak berhasil dibreach tetap ditangani agar flow routing kontinu.

### 9.1 Hasil Breach Sensitivity

Kedua skenario menghasilkan watershed yang identik cell-by-cell:

- watershed area: 212.125 km²
- IoU: 0.9161
- Dice: 0.9562
- XOR area antara breach100 dan breach250: 0 km²

Hasil stream 6 km² terhadap RBI pada toleransi 100 m:

| Scenario | Precision | Recall | F1 |
|---|---:|---:|---:|
| breach100 | 0.281 | 0.551 | 0.372 |
| breach250 | 0.272 | 0.503 | 0.353 |

Dengan demikian `breach100` menghasilkan agreement jaringan sungai yang lebih baik terhadap RBI dengan search distance yang lebih konservatif.

---

## 10. Residual Watershed setelah Least-Cost Breaching

Untuk kedua skenario:

- model area: 212.125 km²
- intersection dengan referensi: 208.849 km²
- reference-only: 15.844 km²
- model-only: 3.276 km²

Partition sekunder lama sekitar 32.848 km² ternyata **98.47% sudah masuk ke watershed utama** setelah least-cost breaching:

- captured: 32.347 km²
- remaining outside: 0.501 km²

Artinya, masalah partition ~32 km² pada baseline full filling terutama merupakan konsekuensi metode conditioning/routing, bukan bukti langsung adanya basin geomorfologi terpisah akibat kejadian bencana.

Residual reference-only terbesar setelah breaching terdiri terutama dari dua komponen:

1. sekitar 7.670 km²;
2. sekitar 6.213 km².

Sisa komponen lainnya jauh lebih kecil.

Residual ini perlu diperlakukan sebagai mismatch lokal antara DEM-derived watershed dan batas DAS referensi, bukan dipaksa hilang semata-mata untuk mencapai kecocokan 100%.

---

## 11. Keputusan Metodologis Baseline

Berdasarkan seluruh pengujian, conditioning yang direkomendasikan untuk baseline selanjutnya adalah:

### **BreachDepressionsLeastCost dengan search distance 100 cells (`breach100`)**

Alasan:

1. menghasilkan watershed yang jauh lebih dekat dengan DAS referensi dibanding `FillDepressions`;
2. IoU meningkat dari 0.7819 menjadi 0.9161;
3. Dice meningkat dari 0.8776 menjadi 0.9562;
4. 98.47% secondary partition lama berhasil tersambung ke watershed utama;
5. jaringan stream 6 km² memiliki F1 100 m lebih baik daripada breach250;
6. search distance lebih konservatif daripada breach250;
7. breach100 dan breach250 menghasilkan watershed final yang identik, sehingga tidak ada keuntungan geometrik watershed dari memperbesar search distance sampai 250 cells.

`breach100` diperlakukan sebagai **baseline conditioning yang dipilih secara provisional/final-working**, dengan satu langkah validasi parameter stream yang masih harus dilakukan.

---

## 12. Langkah yang Masih Harus Dilakukan sebelum GFI

### 12.1 Recalibration/verification threshold stream pada breach100

Threshold 6 km² harus diuji ulang pada flow accumulation hasil breach100.

Tujuannya bukan mencari threshold yang membuat model identik dengan RBI, tetapi memastikan bahwa threshold final masih seimbang dari sisi:

- panjang jaringan;
- topology;
- precision;
- recall;
- F1/F2;
- kestabilan outlet utama.

### 12.2 QGIS visual validation

Layer yang perlu diperiksa bersama:

- DAS referensi;
- watershed breach100;
- reference-only residual;
- model-only residual;
- RBI river;
- stream model threshold final;
- outlet utama;
- residual components;
- fill/breach modification hotspots.

### 12.3 GFI

Perhitungan GFI **tidak boleh menggunakan formula yang diasumsikan**.

Formula, parameter, normalisasi, dan klasifikasi harus mengikuti dokumen sumber `MODUL TEKNIS KRB BANJIR-2` yang menjadi acuan penelitian.

---

## 13. Kerangka Analisis Penelitian Selanjutnya

Dengan keterbatasan temporal DEM saat ini, kerangka analisis yang dapat dipertanggungjawabkan adalah:

```text
DEMNAS baseline
    ↓
Hydrological conditioning (BreachDepressionsLeastCost, 100 cells)
    ↓
D8 flow direction
    ↓
Flow accumulation
    ↓
Final stream-threshold calibration
    ↓
GFI baseline
    ↓
Data kejadian banjir Siklon Senyar November 2025
    ↓
Validasi extent / hazard response
    ↓
Overlay Kecamatan Pauh dan Kuranji hingga kelurahan
    ↓
Analisis perubahan atau perbedaan bahaya yang didukung oleh data temporal
```

Jika tersedia DEM pascakejadian yang kompatibel, analisis dapat dikembangkan menjadi:

```text
DEM T0 sebelum kejadian → GFI T0
DEM T1 setelah kejadian → GFI T1
                   ↓
           ΔGFI = GFI T1 − GFI T0
                   ↓
      Analisis perubahan bahaya banjir
```

Tanpa DEM T1, istilah “perubahan topografi/GFI sebelum–sesudah bencana” tidak boleh digunakan sebagai kesimpulan langsung dari perbedaan DEMNAS dan RBI.

---

## 14. Kesimpulan Tahap Baseline

Tahap validasi hidrologi telah menunjukkan bahwa metode conditioning sangat memengaruhi delineasi DAS Kuranji.

Full depression filling menghasilkan watershed sekitar 177 km² dan meninggalkan secondary partition sekitar 32 km². Least-cost breaching menghubungkan kembali 98.47% partition tersebut dan menghasilkan watershed 212.125 km² dengan IoU 0.9161 dan Dice 0.9562 terhadap DAS referensi.

Dengan mempertimbangkan kecocokan watershed, agreement jaringan sungai, tingkat intervensi DEM, dan prinsip kehati-hatian metodologis, `BreachDepressionsLeastCost` dengan search distance 100 cells dipilih sebagai baseline conditioning untuk tahap berikutnya.

Tahap berikutnya adalah menguji ulang threshold jaringan sungai pada routing breach100, melakukan validasi visual QGIS, kemudian menghitung GFI sesuai formula resmi dalam modul teknis yang digunakan sebagai acuan penelitian.
