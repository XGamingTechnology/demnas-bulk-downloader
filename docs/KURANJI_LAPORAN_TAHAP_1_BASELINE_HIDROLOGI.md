# LAPORAN TAHAP 1
# Penyusunan Baseline Hidrologi DAS Batang Kuranji untuk Analisis Geomorphic Flood Index dan Evaluasi Banjir Siklon Senyar 2025

## Status Dokumen

Dokumen ini merupakan laporan lengkap Tahap 1 penelitian dan menjadi checkpoint resmi sebelum pekerjaan dilanjutkan ke Tahap 2, yaitu perhitungan Geomorphic Flood Index (GFI).

Keputusan utama Tahap 1:

- metode hydrological conditioning final: `BreachDepressionsLeastCost`;
- maximum search distance: 100 cells, sekitar 833 m;
- opsi: `min_dist=True` dan `fill=True`;
- flow routing: D8;
- threshold jaringan sungai final: **6 km²** minimum contributing area;
- luas watershed model: sekitar 212.125 km²;
- luas DAS referensi berbasis raster: sekitar 224.694 km²;
- IoU: 0.9161;
- Dice similarity: 0.9562.

Tahap 1 dianggap selesai untuk kepentingan penelitian, dengan residual mismatch tetap dicatat sebagai uncertainty dan tidak dipaksa menjadi kecocokan 100%.

---

# 1. Latar Belakang

Banjir merupakan hasil interaksi antara karakteristik hujan, topografi, morfometri DAS, jaringan drainase, kondisi tutupan lahan, kapasitas alur, serta perubahan geomorfologi. Dalam analisis bahaya banjir berbasis topografi, kualitas representasi medan dan jaringan aliran merupakan fondasi penting karena kesalahan pada arah aliran atau akumulasi aliran dapat diteruskan ke seluruh produk turunan, termasuk Geomorphic Flood Index (GFI).

Penelitian ini berfokus pada DAS Batang Kuranji, Kota Padang, Sumatera Barat, dengan perhatian khusus terhadap Kecamatan Pauh dan Kuranji. Kajian selanjutnya diarahkan untuk menganalisis bahaya banjir terkait kejadian banjir besar pada periode Siklon Senyar 21–27 November 2025.

Sebelum GFI dihitung, perlu dibangun baseline hidrologi yang konsisten. Baseline tersebut harus mampu merepresentasikan arah aliran, akumulasi aliran, jaringan sungai, dan watershed dengan tingkat kesesuaian yang dapat diterima terhadap data referensi resmi.

Pada tahap awal ditemukan bahwa routing berbasis `FillDepressions` menghasilkan watershed sekitar 177 km², jauh lebih kecil dari DAS referensi sekitar 224.7 km². Investigasi lanjutan menunjukkan keberadaan secondary drainage partition sekitar 32 km². Oleh karena itu dilakukan serangkaian audit outlet, partition analysis, hydrological conditioning sensitivity test, serta recalibration jaringan sungai.

Hasil pengujian menunjukkan bahwa least-cost breaching memberikan representasi watershed yang jauh lebih baik dibanding full depression filling. Temuan ini menjadi dasar pemilihan baseline hidrologi final pada Tahap 1.

---

# 2. Tujuan Tahap 1

Tahap 1 bertujuan untuk:

1. menyiapkan DEMNAS DAS Batang Kuranji dalam sistem koordinat dan format yang sesuai untuk analisis hidrologi;
2. membangun DEM hidrologis yang memiliki flow routing kontinu;
3. menentukan metode hydrological conditioning yang paling sesuai untuk wilayah studi;
4. menghasilkan D8 flow direction dan flow accumulation;
5. mengekstraksi jaringan sungai berbasis minimum contributing area;
6. mengkalibrasi jaringan sungai model terhadap jaringan sungai RBI;
7. mendelineasi watershed model dan membandingkannya dengan DAS referensi;
8. mengukur uncertainty dan residual mismatch;
9. menetapkan baseline hidrologi final yang akan digunakan pada perhitungan GFI.

---

# 3. Pertanyaan Teknis Tahap 1

Tahap ini diarahkan untuk menjawab pertanyaan teknis berikut:

1. Apakah DEMNAS yang tersedia dapat digunakan untuk membangun routing hidrologi DAS Kuranji secara konsisten?
2. Apakah full depression filling atau least-cost depression breaching menghasilkan representasi watershed yang lebih dekat terhadap DAS referensi?
3. Berapa minimum contributing area yang memberikan keseimbangan terbaik antara panjang jaringan, topology, dan agreement terhadap RBI?
4. Seberapa besar residual perbedaan antara watershed model dan DAS referensi setelah conditioning final diterapkan?
5. Apakah residual tersebut cukup kecil dan terkontrol sehingga baseline dapat diteruskan ke tahap GFI?

---

# 4. Wilayah Studi

Wilayah studi utama adalah DAS Batang Kuranji, Kota Padang, Provinsi Sumatera Barat.

Karakteristik referensi DAS:

| Parameter | Nilai |
|---|---|
| Nama DAS | KURANJI |
| Kode DAS | DAS110385 |
| Wilayah kerja | BPDAS AGAM KUANTAN |
| Luas referensi vektor | ±224.696 km² |
| Luas referensi berbasis raster analisis | ±224.694 km² |
| CRS kerja | EPSG:32747, WGS 84 / UTM Zone 47S |
| Fokus administrasi lanjutan | Kecamatan Pauh dan Kuranji |

Pemodelan hidrologi dilakukan pada seluruh DAS dan DEM buffer sekitar 3 km. Analisis tidak dipotong lebih awal hanya pada Pauh dan Kuranji karena routing membutuhkan konteks topografi dan aliran di luar batas administrasi.

---

# 5. Bahan dan Sumber Data

## 5.1 DEMNAS

Sumber utama elevasi adalah DEM Nasional Indonesia (DEMNAS) yang disediakan oleh Badan Informasi Geospasial (BIG).

Menurut dokumentasi BIG, DEMNAS dibangun dari kombinasi IFSAR, TerraSAR-X, ALOS PALSAR, serta masspoint hasil stereo-plotting. Resolusi spasial produk DEMNAS adalah sekitar 0.27 arc-second dan datum vertikal yang digunakan adalah EGM2008.

Tile yang digunakan dalam penelitian ini:

1. `DEMNAS_0715-32_v1.0.tif`
2. `DEMNAS_0815-11_v1.0.tif`

Metadata tile yang diperoleh menunjukkan sumber IFSAR dan tahun data 2012.

Setelah reprojection dan mosaicking, karakteristik DEM kerja adalah:

| Parameter | DEM Buffer 3 km | DEM DAS |
|---|---:|---:|
| CRS | EPSG:32747 | EPSG:32747 |
| Resolusi | ±8.3295 m | ±8.3295 m |
| NoData | -9999 | -9999 |
| Valid cells | 6,739,609 | 3,238,533 |
| Elevasi minimum | -7.522 m | -7.420 m |
| Elevasi rata-rata | 591.132 m | 519.657 m |
| Median | 476.139 m | 413.417 m |
| Elevasi maksimum | 1902.682 m | 1864.797 m |

Sumber resmi:

- Badan Informasi Geospasial, DEMNAS: https://www.big.go.id/en/content/produk/demnas
- Portal DEMNAS BIG: http://tides.big.go.id/DEMNAS/

## 5.2 Batas DAS Kuranji

Batas DAS referensi digunakan sebagai kontrol geometrik untuk validasi watershed hasil DEM.

Atribut utama:

- `nama_das = KURANJI`
- `kd_das = DAS110385`
- `wil_kerja = BPDAS AGAM KUANTAN`

Data dipersiapkan dalam WGS84 dan EPSG:32747.

File kerja utama:

- `data/input/kuranji/DAS_KURANJI_WGS84.geojson`
- `data/input/kuranji/DAS_KURANJI_UTM47S.gpkg`
- `data/work/kuranji/01_prepared/DAS_KURANJI_UTM47S.geojson`

## 5.3 Jaringan Sungai RBI

Jaringan sungai referensi berasal dari data Rupabumi Indonesia (RBI) BIG, layer `Sungai (Garis)`.

Secara konseptual layer ini merepresentasikan alur atau wadah air alami dan/atau buatan berupa jaringan pengaliran dari hulu hingga muara.

Setelah pemotongan dan transformasi ke CRS kerja:

- jumlah fitur: 70;
- panjang total jaringan: sekitar 79.813 km;
- geometry: polyline;
- CRS kerja: EPSG:32747.

File kerja:

`data/work/kuranji/01_prepared/SUNGAI_RBI_DAS_KURANJI_UTM47S.geojson`

Sumber resmi layanan geospasial BIG:

https://geoservices.big.go.id/rbi/rest/services/BASEMAP/Rupabumi_Indonesia/MapServer

## 5.4 Batas Administrasi

Data administrasi yang tersedia mencakup 18 kelurahan pada Kecamatan Pauh dan Kuranji.

Pada Tahap 1 data ini belum digunakan untuk membatasi routing. Layer administrasi disiapkan untuk Tahap 2 dan Tahap 3, khususnya analisis statistik GFI dan dampak banjir per kelurahan.

---

# 6. Metode Pengambilan dan Persiapan Data

## 6.1 Pengambilan DEMNAS

DEMNAS diambil berdasarkan cakupan spasial DAS Kuranji ditambah buffer sekitar 3 km. Buffer digunakan untuk menghindari artefak routing akibat pemotongan DEM tepat pada batas DAS referensi.

Dua tile DEMNAS dipilih karena secara bersama-sama mencakup seluruh area studi dan buffer.

## 6.2 Pengambilan RBI

Jaringan sungai RBI diperoleh dari layanan geospasial BIG. Data sungai dipilih berdasarkan intersection terhadap DAS Kuranji, kemudian disimpan sebagai GeoJSON dan direproject ke EPSG:32747.

## 6.3 Pemilihan CRS

Semua analisis jarak, luas, dan flow routing dilakukan pada:

`EPSG:32747 — WGS 84 / UTM Zone 47S`

CRS proyeksi digunakan agar:

- jarak dapat dihitung dalam meter;
- luas dihitung dalam m²/km²;
- pixel DEM memiliki ukuran linear yang sesuai untuk analisis hidrologi;
- toleransi spatial agreement RBI vs model dapat dihitung secara langsung.

---

# 7. Perangkat Keras dan Perangkat Lunak

Analisis dijalankan pada VPS berbasis Ubuntu.

Lingkungan yang tercatat pada saat analisis:

| Komponen | Versi / Keterangan |
|---|---|
| Operating System | Ubuntu 24.04.4 LTS |
| Python | 3.12.3 |
| Whitebox Python package | 2.3.6 |
| WhiteboxTools binary | 2.4.0 |
| rasterio | 1.5.1 |
| numpy | 2.5.2 |
| shapely | 2.1.2 |
| pyproj | 3.8.0 |
| scipy | 1.18.1 |
| Git | version-controlled workflow |
| Repository | `XGamingTechnology/demnas-bulk-downloader` |

QGIS direncanakan untuk visual validation dan layout kartografi final. Versi QGIS harus dicatat pada saat tahap layout dilakukan dan tidak diasumsikan dalam dokumen ini.

Library utama digunakan untuk:

- Rasterio: pembacaan, penulisan, transformasi, raster mask;
- NumPy: operasi raster dan statistik numerik;
- SciPy: distance transform, connected-component analysis;
- Shapely: operasi geometri;
- PyProj: transformasi CRS;
- WhiteboxTools: DEM conditioning, D8 pointer, flow accumulation, watershed delineation.

---

# 8. Workflow Analisis

Workflow Tahap 1 adalah:

```text
Batas DAS + RBI
       ↓
DEMNAS tiles
       ↓
Mosaic + reprojection EPSG:32747
       ↓
DEM buffer 3 km
       ↓
GeoTIFF compatibility rewrite
       ↓
Hydrological conditioning test
       ├── FillDepressions
       └── BreachDepressionsLeastCost
       ↓
D8 Flow Direction
       ↓
D8 Flow Accumulation
       ↓
Stream threshold calibration
       ↓
Watershed delineation
       ↓
Validation against RBI + DAS reference
       ↓
Final baseline hydrology
```

---

# 9. Persiapan DEM untuk WhiteboxTools

DEM hasil persiapan awal menggunakan GeoTIFF DEFLATE dengan floating-point TIFF `PREDICTOR=3`.

WhiteboxTools 2.4.0 pada lingkungan analisis tidak dapat membaca file tersebut secara stabil. Oleh karena itu DEM direwrite secara lossless menjadi GeoTIFF uncompressed:

`data/work/kuranji/02_hydrology/00_DEM_WBT_INPUT.tif`

Rewrite mempertahankan:

- ukuran raster;
- resolusi;
- CRS;
- transform;
- nilai elevasi;
- NoData.

Tahap ini hanya merupakan compatibility conversion dan tidak mengubah topografi.

---

# 10. Uji Hydrological Conditioning Awal: FillDepressions

Metode pertama menggunakan WhiteboxTools `FillDepressions` dengan `fix_flats=True`.

Tahapan:

1. fill depression;
2. resolve flats;
3. D8 pointer;
4. D8 flow accumulation.

Output awal:

- `01_DEM_FILLED.tif`
- `02_D8_POINTER.tif`
- `03_FLOW_ACCUM_CELLS.tif`
- `04_FLOW_ACCUM_CA_M2.tif`

## 10.1 Statistik perubahan elevasi

Di dalam DAS referensi:

| Indikator | Nilai |
|---|---:|
| Mean fill depth | 0.061 m |
| P95 | 0.315 m |
| P99 | 1.300 m |
| Maximum fill | 22.241 m |
| Area fill >5 m | 0.259 km² |
| Area fill >10 m | 0.071 km² |

Walaupun sebagian besar perubahan kecil, watershed yang dihasilkan hanya sekitar 177.161 km².

Dibanding DAS referensi sekitar 224.694 km², terdapat deficit sekitar 47.5 km².

---

# 11. Audit Outlet dan Drainage Partition

Audit dilakukan untuk memastikan deficit watershed bukan hanya akibat kesalahan snapping outlet.

Pencarian kandidat outlet diperluas sampai sekitar 1 km dari boundary dan RBI. Maximum contributing area tetap sekitar 177.161 km².

Kesimpulan:

**deficit watershed tidak disebabkan semata-mata oleh posisi outlet.**

Analisis D8 drainage partition kemudian menunjukkan secondary zone stabil sekitar 31.7–32.0 km².

Pada grouping radius 100 m:

| Zona | Luas | Persentase DAS |
|---|---:|---:|
| Main zone | 177.768 km² | 79.12% |
| Secondary zone | 31.969 km² | 14.23% |

Dominant raw outlet secondary partition memiliki contributing area sekitar 32.705 km² dan berada sekitar 1.420 km dari jaringan RBI.

---

# 12. Audit Secondary Partition

Secondary partition dianalisis secara khusus.

Karakteristik:

| Parameter | Nilai |
|---|---:|
| Mask area | 32.848 km² |
| Elevasi minimum | 61.807 m |
| Elevasi mean | 993.385 m |
| Median | 1049.789 m |
| Maksimum | 1890.212 m |
| Mean fill depth | 0.043 m |
| Fill >0.1 m | 1.545% |
| Fill >1 m | 0.828% |
| Fill >5 m | 0.278% |
| Fill >10 m | 0.101% |

Pada routing FillDepressions, jaringan stream threshold 6 km² dalam zone tersebut tidak berada dalam 100 m dari RBI.

Temuan tersebut memicu uji alternatif hydrological conditioning.

---

# 13. Hydrological Conditioning Sensitivity Test

Alternatif yang diuji adalah WhiteboxTools `BreachDepressionsLeastCost`.

Metode least-cost breaching mencari jalur minimum-cost yang menghubungkan pit dengan sel lebih rendah. Dibanding full depression filling, metode ini dirancang sebagai pendekatan yang sering menghasilkan perubahan topografi lebih rendah karena lebih memilih membuka jalur drainase daripada menaikkan seluruh depression hingga spill elevation.

Referensi metodologis utama:

Lindsay, J.B. & Dhun, K. (2015). Modelling surface drainage patterns in altered landscapes using LiDAR. International Journal of Geographical Information Science, 29. DOI: 10.1080/13658816.2014.975715.

Dua skenario diuji:

| Scenario | Maximum search distance | Approx. distance |
|---|---:|---:|
| breach100 | 100 cells | ±833 m |
| breach250 | 250 cells | ±2082 m |

Keduanya menggunakan:

- `min_dist=True`
- `fill=True`

## 13.1 Hasil sensitivitas

| Parameter | breach100 | breach250 |
|---|---:|---:|
| Watershed area | 212.125 km² | 212.125 km² |
| IoU | 0.9161 | 0.9161 |
| Dice | 0.9562 | 0.9562 |
| Stream F1 @100m, threshold 6 km² | 0.372 | 0.353 |
| Secondary max CA | 32.167 km² | 32.167 km² |
| Mean absolute DEM change | 0.0151 m | 0.0148 m |

Breach100 dan breach250 menghasilkan watershed yang identik secara cell-by-cell, XOR = 0 km².

Karena breach100 menggunakan search distance lebih konservatif namun menghasilkan agreement jaringan sungai lebih baik terhadap RBI, breach100 dipilih sebagai conditioning final.

---

# 14. Residual Analysis setelah Breaching

Setelah breach100:

| Parameter | Nilai |
|---|---:|
| Reference DAS | 224.694 km² |
| Model watershed | 212.125 km² |
| Intersection | 208.849 km² |
| Reference-only | 15.844 km² |
| Model-only | 3.276 km² |
| IoU | 0.9161 |
| Dice | 0.9562 |

Secondary partition lama sekitar 32.848 km² ternyata menjadi:

| Status | Luas | Persentase |
|---|---:|---:|
| Captured by main watershed | 32.347 km² | 98.47% |
| Remaining outside | 0.501 km² | 1.53% |

Dengan demikian secondary partition besar pada full filling terutama berkaitan dengan metode hydrological conditioning, bukan bukti langsung perubahan geomorfologi akibat kejadian 2025.

Dua residual reference-only terbesar:

1. 7.670 km²;
2. 6.213 km².

Residual tersebut dipertahankan sebagai uncertainty model dan tidak dipaksa masuk ke watershed melalui manipulasi data referensi.

---

# 15. Final Stream Threshold Calibration pada BREACH100

Setelah conditioning final dipilih, threshold stream dikalibrasi ulang karena threshold lama 6 km² berasal dari routing FillDepressions.

Kandidat:

2, 3, 4, 5, 6, 7.5, 10, 12.5, 15, dan 20 km².

Reference RBI vector length = 79.813 km.

## 15.1 Hasil calibration

| Threshold | Length | Ratio RBI | Heads | Outlets | Components | Precision 100m | Recall 100m | F1 | F2 | Length Diff |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2.0 km² | 128.91 km | 1.62 | 30 | 4 | 4 | 0.202 | 0.586 | 0.300 | 0.425 | 49.09 km |
| 3.0 km² | 110.54 km | 1.38 | 21 | 2 | 2 | 0.226 | 0.577 | 0.325 | 0.441 | 30.73 km |
| 4.0 km² | 94.42 km | 1.18 | 15 | 1 | 1 | 0.260 | 0.570 | 0.357 | 0.460 | 14.61 km |
| 5.0 km² | 86.73 km | 1.09 | 12 | 1 | 1 | 0.265 | 0.553 | 0.358 | 0.454 | 6.92 km |
| **6.0 km²** | **81.00 km** | **1.01** | **12** | **1** | **1** | **0.281** | **0.551** | **0.372** | **0.462** | **1.19 km** |
| 7.5 km² | 74.75 km | 0.94 | 8 | 1 | 1 | 0.299 | 0.548 | 0.387 | 0.470 | 5.06 km |
| 10.0 km² | 71.45 km | 0.90 | 7 | 1 | 1 | 0.313 | 0.548 | 0.399 | 0.477 | 8.36 km |
| 12.5 km² | 63.45 km | 0.80 | 6 | 1 | 1 | 0.327 | 0.514 | 0.400 | 0.461 | 16.36 km |
| 15.0 km² | 59.36 km | 0.74 | 5 | 1 | 1 | 0.339 | 0.502 | 0.405 | 0.458 | 20.45 km |
| 20.0 km² | 48.96 km | 0.61 | 5 | 1 | 1 | 0.393 | 0.487 | 0.435 | 0.465 | 30.85 km |

## 15.2 Pemilihan threshold final

F1 tertinggi secara matematis terjadi pada 20 km², tetapi threshold tersebut hanya mempertahankan jaringan sekitar 48.96 km, atau 61% dari panjang RBI. Dengan demikian F1 meningkat karena network menjadi sangat terpruning, bukan karena representasi seluruh sistem sungai menjadi lebih baik.

F2 tertinggi terjadi pada 10 km², tetapi panjang jaringan model turun menjadi 71.45 km, sekitar 10.5% lebih pendek dari RBI.

Threshold 6 km² dipilih sebagai threshold final karena:

1. panjang jaringan 81.00 km hanya berbeda sekitar 1.19 km atau ±1.49% dari RBI 79.813 km;
2. network telah menjadi satu connected component;
3. hanya memiliki satu outlet/truncated outlet;
4. recall 100 m tetap tinggi, 0.551;
5. F2 0.462 tetap kompetitif;
6. tidak menghilangkan tributary secara agresif seperti threshold lebih besar;
7. threshold yang sama juga muncul sebagai kandidat kuat pada calibration awal sehingga keputusan relatif stabil terhadap perubahan conditioning.

Dengan demikian threshold **6 km² ditetapkan sebagai final threshold Tahap 1**.

---

# 16. Baseline Hidrologi Final Tahap 1

Konfigurasi final:

```text
DEMNAS buffer 3 km
       ↓
BreachDepressionsLeastCost
  dist = 100 cells
  min_dist = True
  fill = True
       ↓
D8 Pointer
       ↓
D8 Flow Accumulation
       ↓
Stream threshold = 6 km²
       ↓
Main watershed
       ↓
Validation against RBI + DAS reference
```

Parameter utama:

| Parameter | Final value |
|---|---|
| CRS | EPSG:32747 |
| DEM resolution | ±8.3295 m |
| Cell area | 69.381334 m² |
| Conditioning | BreachDepressionsLeastCost |
| Breach search distance | 100 cells |
| Flow routing | D8 |
| Stream threshold | 6 km² |
| Threshold cells | sekitar 86,479 cells |
| Stream length | 81.00 km |
| RBI length | 79.813 km |
| Connected components | 1 |
| Outlet | 1 |
| Watershed area | 212.125 km² |
| IoU | 0.9161 |
| Dice | 0.9562 |

---

# 17. Interpretasi Hasil Tahap 1

Hasil menunjukkan bahwa pemilihan metode conditioning memiliki pengaruh besar terhadap representasi drainage basin.

Full depression filling menghasilkan separation besar dalam internal drainage yang menyebabkan watershed utama hanya sekitar 177 km². Least-cost breaching menghubungkan kembali hampir seluruh secondary partition dan meningkatkan watershed menjadi sekitar 212 km².

Peningkatan IoU dari sekitar 0.782 menjadi 0.916 dan Dice dari sekitar 0.878 menjadi 0.956 menunjukkan perbaikan yang substansial.

Namun model tidak dipaksa untuk menutup seluruh 224.694 km² DAS referensi. Hal ini penting karena batas DAS resmi dan watershed berbasis DEM tidak harus identik secara pixel-by-pixel akibat:

- perbedaan resolusi;
- perbedaan sumber dan tahun data;
- vertical/horizontal uncertainty;
- generalized cartographic boundary;
- perbedaan metode delineasi;
- perubahan permukaan yang tidak terekam seragam oleh seluruh dataset.

Residual mismatch diperlakukan sebagai bagian dari uncertainty penelitian.

---

# 18. Batasan Ilmiah

## 18.1 DEMNAS bukan DEM pascakejadian

DEMNAS yang digunakan berasal dari data sebelum kejadian November 2025. Oleh karena itu perbedaan DEM-derived drainage terhadap RBI tidak boleh secara langsung dinyatakan sebagai akibat Siklon Senyar.

## 18.2 Tidak ada DEM T1 pada Tahap 1

Analisis perubahan topografi secara langsung memerlukan:

- DEM T0 sebelum kejadian;
- DEM T1 setelah kejadian;
- vertical datum kompatibel;
- horizontal co-registration;
- uncertainty threshold.

Tanpa DEM T1, Tahap 2 harus diposisikan sebagai GFI baseline dan Tahap 3 sebagai evaluasi terhadap observed flood/event data.

## 18.3 RBI adalah reference layer

RBI digunakan sebagai spatial reference dan validation dataset. RBI bukan dianggap sebagai ground truth sempurna pada resolusi DEM.

## 18.4 Threshold stream bersifat scale-dependent

Threshold 6 km² berlaku untuk DEM, resolusi, conditioning, dan wilayah studi ini. Nilai tersebut tidak dapat secara otomatis diterapkan ke DAS lain tanpa calibration baru.

---

# 19. Quality Assurance / Quality Control

QC yang telah dilakukan:

1. pemeriksaan CRS;
2. pemeriksaan NoData dan nilai sentinel;
3. validasi lossless compatibility rewrite;
4. audit FillDepressions;
5. audit D8 pointer values;
6. audit flow accumulation;
7. outlet sensitivity test;
8. drainage partition analysis;
9. secondary partition inspection;
10. conditioning sensitivity test;
11. residual watershed analysis;
12. stream threshold recalibration;
13. comparison terhadap RBI dan DAS referensi.

Semua langkah utama dibuat dalam script Python dan disimpan dalam Git repository agar reproducible.

---

# 20. Script Utama Tahap 1

Script penting yang membentuk audit trail penelitian:

- `run_kuranji_hydrology.py`
- `calibrate_kuranji_streams.py`
- `refine_kuranji_stream_calibration.py`
- `compare_kuranji_stream_candidates.py`
- `derive_kuranji_watershed.py`
- `audit_kuranji_outlet.py`
- `diagnose_kuranji_drainage_partitions.py`
- `group_kuranji_drainage_exits.py`
- `inspect_kuranji_secondary_partition.py`
- `test_kuranji_breach_sensitivity.py`
- `analyze_kuranji_breach_residuals.py`
- `calibrate_kuranji_stream_breach100.py`

Dokumentasi:

- `docs/KURANJI_METODE_TEKNIS_HIDROLOGI_BASELINE.md`
- `docs/KURANJI_ROADMAP_DELIVERABLE_LAPORAN.md`
- `docs/KURANJI_LAPORAN_TAHAP_1_BASELINE_HIDROLOGI.md`

---

# 21. Tabel yang Digunakan dalam Laporan Tahap 1

Tabel final yang perlu dipertahankan dalam naskah penelitian:

1. Karakteristik wilayah studi.
2. Sumber dan karakteristik data.
3. Statistik DEM.
4. Perangkat lunak dan versi.
5. Statistik FillDepressions.
6. Perbandingan conditioning Fill vs breach100 vs breach250.
7. Residual watershed.
8. Stream threshold calibration.
9. Konfigurasi baseline final.

CSV calibration tersedia pada:

`data/work/kuranji/05_validation/breach100_stream_calibration/breach100_stream_threshold_calibration.csv`

---

# 22. Peta yang Harus Dibuat untuk Tahap 1

Untuk versi laporan final, Tahap 1 harus dilengkapi minimal dengan enam peta.

## Peta 1 — Lokasi Studi

Isi:

- Indonesia/Sumatera Barat inset;
- Kota Padang;
- DAS Batang Kuranji;
- Pauh;
- Kuranji;
- jaringan sungai;
- batas administrasi.

## Peta 2 — DEM DAS Batang Kuranji

Isi:

- elevation ramp;
- hillshade;
- DAS reference;
- RBI;
- elevasi minimum–maksimum;
- scale bar, north arrow, legend.

## Peta 3 — Flow Accumulation BREACH100

Isi:

- flow accumulation log-scaled;
- DAS boundary;
- outlet;
- jaringan RBI sebagai pembanding.

## Peta 4 — Stream Calibration / Final Network

Isi:

- final 6 km² stream network;
- RBI;
- outlet;
- DAS reference.

Peta ini harus menunjukkan secara visual bagian model yang mengikuti dan berbeda dari RBI.

## Peta 5 — Watershed Model vs Reference DAS

Kelas visual minimum:

- intersection;
- reference-only;
- model-only;
- outlet.

## Peta 6 — Residual Mismatch

Menampilkan dua reference-only component terbesar dan residual kecil lainnya sebagai bahan interpretasi uncertainty.

Semua layout peta harus menggunakan:

- judul;
- legend;
- north arrow;
- scale bar;
- CRS;
- sumber data;
- tahun data;
- nomor gambar;
- caption metodologis.

---

# 23. Produk Digital Tahap 1

Produk yang dipertahankan sebagai evidence dan input Tahap 2:

- DEM original prepared;
- BREACH100 conditioned DEM;
- BREACH100 D8 pointer;
- BREACH100 flow accumulation;
- candidate stream calibration rasters;
- final stream threshold 6 km² raster;
- BREACH100 watershed;
- residual rasters;
- reference DAS;
- RBI stream reference;
- JSON QC;
- CSV calibration;
- technical documentation.

Pada tahap packaging final disarankan dibuat folder:

`data/work/kuranji/06_final_baseline/`

untuk menyimpan salinan produk yang benar-benar digunakan pada analisis GFI.

---

# 24. Kesimpulan Tahap 1

Tahap 1 berhasil membangun baseline hidrologi DAS Batang Kuranji yang telah melalui serangkaian pengujian kualitas dan sensitivitas.

Metode awal `FillDepressions` menghasilkan watershed sekitar 177 km² dan secondary partition besar sekitar 32 km². Penggantian conditioning menjadi `BreachDepressionsLeastCost` dengan search distance 100 cells berhasil menghubungkan 98.47% secondary partition tersebut ke watershed utama dan meningkatkan watershed model menjadi sekitar 212.125 km².

Agreement terhadap DAS referensi meningkat menjadi IoU 0.9161 dan Dice 0.9562.

Recalibration stream network pada routing BREACH100 menunjukkan bahwa threshold 6 km² memberikan keseimbangan paling kuat antara panjang jaringan, topology, preservation of tributaries, dan agreement terhadap RBI. Panjang jaringan model sebesar 81.00 km hanya berbeda sekitar 1.19 km dari RBI 79.813 km.

Dengan demikian konfigurasi berikut ditetapkan sebagai baseline final Tahap 1:

**DEMNAS → BreachDepressionsLeastCost (100 cells) → D8 → Flow Accumulation → Stream Threshold 6 km² → Watershed Baseline.**

Tahap penelitian berikutnya adalah perhitungan GFI berdasarkan formula dan klasifikasi yang secara eksplisit tercantum dalam `MODUL TEKNIS KRB BANJIR-2`.

---

# 25. Referensi Teknis Awal

Badan Informasi Geospasial. DEMNAS. https://www.big.go.id/en/content/produk/demnas

Badan Informasi Geospasial. Rupabumi Indonesia / Geoservices BIG. https://geoservices.big.go.id/rbi/rest/services/BASEMAP/Rupabumi_Indonesia/MapServer

Lindsay, J.B., & Dhun, K. (2015). Modelling surface drainage patterns in altered landscapes using LiDAR. International Journal of Geographical Information Science. DOI: 10.1080/13658816.2014.975715.

Whitebox Geospatial Inc. Whitebox hydrological analysis documentation, including `BreachDepressionsLeastCost`, D8 flow direction, and flow accumulation tools. https://www.whiteboxgeo.com/

Catatan: daftar pustaka penelitian akhir harus dilengkapi kembali pada saat Tahap 2 dan Tahap 3, terutama untuk teori GFI, flood-hazard validation, Siklon Senyar 2025, dan sumber data kejadian banjir.
