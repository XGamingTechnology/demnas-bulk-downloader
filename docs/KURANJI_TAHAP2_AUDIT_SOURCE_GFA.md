# Audit Source Code GFA untuk Tahap 2 DAS Kuranji

## Tujuan

Dokumen ini merekam hasil audit terhadap source code `GeomorphicFloodArea / GeomorphicFloodIndex` versi 2.0 yang menjadi dasar plugin GFA pada MODUL TEKNIS KRB BANJIR-2. Audit dilakukan sebelum implementasi Python agar workflow penelitian tidak hanya meniru tampilan GUI lama QGIS 2.14, tetapi mereplikasi logika inti metode.

Repository sumber:

`HydroLAB-UNIBAS/GFA-Geomorphic-Flood-Area`

File utama:

`GeomorphicFloodIndex/doGeomorphicFloodIndex.py`

---

## 1. Input inti plugin

Plugin membaca:

- conditioned/fill DEM;
- DEM untuk valid mask;
- flow direction;
- flow accumulation;
- optional standard flood map untuk calibration.

Semua grid harus memiliki dimensi, cell size, dan projection yang sama. Hal ini sesuai dengan prinsip snap/grid consistency pada modul.

---

## 2. Flow-direction coding

Plugin menyediakan tiga coding:

- ESRI;
- HyGrid2k2;
- TauDEM.

Coding ESRI pada source:

- E = 1
- SE = 2
- S = 4
- SW = 8
- W = 16
- NW = 32
- N = 64
- NE = 128

WhiteboxTools baseline Tahap 1 menggunakan coding native Whitebox:

- NE = 1
- E = 2
- SE = 4
- S = 8
- SW = 16
- W = 32
- NW = 64
- N = 128

Dengan demikian pointer Whitebox **tidak boleh diberikan langsung ke GFA dengan pilihan ESRI**. Jika kompatibilitas file GFA diperlukan, pointer harus dikonversi:

`1→128, 2→1, 4→2, 8→4, 16→8, 32→16, 64→32, 128→64`.

Implementasi Python native dapat tetap menggunakan coding Whitebox asalkan downstream tracing menggunakan mapping Whitebox secara eksplisit.

---

## 3. Drainage network identification

Plugin menyediakan dua metode:

### 3.1 `channel_ASk`

Ini adalah default yang ditunjukkan modul.

Source code menghitung slope menggunakan `gdaldem slope`, mengubah slope degree ke radian, lalu membentuk seed channel menggunakan slope-area criterion:

`tmp = FlowAccumulation × cellsize² × (slope_rad + 0.0001)^1.7`

Seed channel jika:

`tmp > 100000`

Seed kemudian diteruskan downstream mengikuti D8.

### 3.2 `channel_FAt`

Metode ini langsung mengubah flow accumulation menjadi stream dengan aturan:

`FlowAccumulation >= threshold_cell`.

Pada metode inilah parameter `Drainage network identification threshold` berfungsi secara langsung sebagai threshold jumlah cell.

---

## 4. Makna parameter GUI `10000`

UI plugin memberi label `Drainage network identification threshold` dan default 10000.

Namun source code menunjukkan perilaku berbeda tergantung metode:

- pada `channel_FAt`, nilai tersebut benar-benar dipakai sebagai minimum flow-accumulation cells;
- pada `channel_ASk`, seed channel ditentukan oleh slope-area criterion tetap `>100000`. Nilai GUI 10000 dipakai pada kondisi downstream propagation `DEM < th_channel`.

Karena elevasi DAS Kuranji maksimum sekitar 1900 m, default 10000 pada `channel_ASk` secara praktis tidak menjadi stream-area threshold; ia hanya tidak membatasi propagasi downstream pada wilayah studi ini.

Kesimpulan: **nilai 10000 pada screenshot modul tidak boleh disamakan dengan threshold stream 6 km² Tahap 1.**

---

## 5. H dan Ariver

Untuk setiap sel terrain, plugin menelusuri downstream mengikuti D8 sampai mencapai elemen channel yang terhubung.

Kemudian:

- `Ariver` = flow accumulation pada channel yang terhubung;
- `H` = elevasi sel terrain − elevasi channel yang terhubung.

Jika `H = 0`, plugin menggantinya dengan `0.00001` untuk menghindari pembagian dengan nol.

Dengan demikian H bukan Euclidean nearest-stream elevation difference, tetapi **hydrologically connected relative elevation**.

---

## 6. Hydraulic scaling `hr`

Source code menggunakan:

`hr = [ ((Ariver + 1) × cellsize²) / 1,000,000 ] ^ n`

Artinya contributing area dikonversi menjadi km² sebelum dipangkatkan.

Runtime plugin menetapkan default exponent:

`n = 0.354429752`

Walaupun source code memiliki komentar lama terkait coefficient `a = 0.1035`, coefficient tersebut tidak digunakan dalam baris aktif. Implementasi aktif ekuivalen dengan:

`hr = A_km2 ^ n`

untuk `n = 0.354429752` pada default modul/plugin.

Penelitian Kuranji akan mereplikasi implementasi aktif ini untuk hasil utama yang mengikuti modul. Alternatif coefficient dari literatur hanya boleh dipakai sebagai sensitivity analysis terpisah jika diperlukan.

---

## 7. GFI mentah dan normalisasi

GFI mentah dihitung sebagai:

`GFI_raw = ln(hr / H)`

Kemudian plugin melakukan min-max normalization ke rentang -1 sampai +1:

`GFI_norm = 2 × [ (GFI_raw - min) / (max - min) - 0.5 ]`

Plugin mengekspor:

- file output utama = `GFI_raw` (`ln_hronH`);
- file tambahan `norm.tif` = `GFI_norm`.

Ini penting karena classifier threshold tidak diterapkan pada GFI mentah.

---

## 8. Threshold flood-prone

Manual GUI default adalah:

`-0.53`

Tetapi source code menerapkannya pada:

`GFI_norm > threshold`

bukan pada `GFI_raw`.

Dengan demikian penggunaan `-0.53` terhadap raster raw `ln(hr/H)` adalah implementasi yang salah.

---

## 9. Calibration threshold

Jika calibration mode aktif, standard flood map diubah menjadi binary flooded/non-flooded.

Plugin membentuk calibration area berbasis drainage connectivity, lalu menghitung ROC menggunakan `GFI_norm`.

Threshold optimum dipilih dengan meminimalkan:

`F = FPR + (1 - TPR)`

atau ekuivalen memaksimalkan separation berdasarkan true-positive dan false-positive rates.

Plugin juga mencatat:

- selected threshold;
- false-positive rate;
- true-positive rate;
- objective function;
- AUC;
- percentage calibration area.

Penelitian Kuranji harus menyimpan metric yang sama ditambah confusion metrics modern untuk transparansi.

---

## 10. Flood-prone cleanup

Setelah threshold diterapkan, plugin melakukan connected-component labelling dengan 8-neighbour connectivity.

Komponen dengan ukuran kurang dari 8 pixel dihapus.

Dengan resolusi Kuranji sekitar 8.33 m, 8 pixel setara sekitar 555 m², sehingga cleanup tersebut hanya menghilangkan patch sangat kecil/isolate.

---

## 11. Catatan bug/legacy implementation

Source lama memiliki beberapa ciri legacy yang tidak perlu direplikasi secara literal apabila tidak mengubah prinsip metode:

1. GUI dibuat untuk PyQt4 / QGIS 2.x.
2. Variabel `file_demvoid` pada fungsi `accept()` mengambil `cmbDemCon` alih-alih `cmbDemVoid`, sehingga input DEM kedua secara praktis tidak dipakai sebagaimana UI mengindikasikan.
3. Coefficient `a=0.1035` terdapat sebagai komentar tetapi tidak digunakan dalam formula aktif `hr`.
4. Label GUI threshold tidak sepenuhnya menggambarkan perilaku `channel_ASk`.

Implementasi penelitian akan mereplikasi **algoritma aktif dan prinsip metode**, tetapi memperbaiki handling file/grid dan mendokumentasikan perbedaan tersebut.

---

## 12. Implikasi terhadap Tahap 1

Threshold 6 km² Tahap 1 dan default `channel_ASk` tidak mengukur hal yang sama.

Karena modul meminta default `channel_ASk`, sebelum GFI final dihitung dilakukan preflight comparison:

1. bangun jaringan internal GFA `channel_ASk` dari BREACH100 flow accumulation + slope;
2. bandingkan dengan RBI;
3. bandingkan dengan final stream network 6 km²;
4. ukur network length, connected components, headwater/outlet, precision, recall, F1/F2;
5. putuskan apakah hasil utama memakai `channel_ASk` default atau local-adaptation `channel_FAt` 6 km².

Primary preference tetap `channel_ASk` karena merupakan default modul, kecuali validasi spasial menunjukkan alasan kuat untuk local adaptation.

---

## 13. Checkpoint berikutnya

Jalankan script preflight Stage 2 yang akan:

- memvalidasi alignment DEM, D8, dan accumulation;
- menghasilkan pointer ESRI-compatible;
- menghitung slope Horn/GDAL-compatible;
- membentuk GFA `channel_ASk`;
- membandingkan `channel_ASk` vs stream final 6 km² vs RBI;
- menghasilkan JSON/CSV/raster untuk keputusan metodologis sebelum H/hr/GFI dihitung.
