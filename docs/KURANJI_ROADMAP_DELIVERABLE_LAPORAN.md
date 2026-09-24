# Roadmap Deliverable Laporan Analisis DAS Batang Kuranji

Dokumen ini merangkum tiga blok analisis utama yang harus diselesaikan dan bentuk output yang wajib disiapkan untuk laporan akhir. Setiap blok tidak hanya menghasilkan raster atau script, tetapi juga harus memiliki narasi metode, tabel hasil, peta, interpretasi, dan file data pendukung.

---

## BLOK 1 — Baseline Hidrologi Final

### Tujuan
Membentuk baseline hidrologi DAS Batang Kuranji yang stabil, teruji, dan dapat dipakai sebagai fondasi perhitungan GFI.

### Tahapan
1. Gunakan DEMNAS buffer 3 km sebagai DEM kerja.
2. Gunakan `BreachDepressionsLeastCost` dengan search distance 100 cells sebagai conditioning baseline.
3. Hitung D8 flow direction.
4. Hitung flow accumulation.
5. Recalibrate threshold jaringan sungai pada hasil `breach100`.
6. Pilih threshold final berdasarkan panjang jaringan, topology, precision, recall, F1, F2, dan konsistensi outlet.
7. Bentuk watershed final.
8. Lakukan validasi terhadap DAS referensi dan RBI.
9. Simpan hanya produk final ke folder baseline final.

### Tabel yang wajib masuk laporan

#### Tabel 1. Karakteristik data dasar
Kolom minimum:
- dataset;
- sumber;
- tahun data;
- resolusi/skala;
- CRS;
- fungsi dalam analisis.

Dataset minimum:
- DEMNAS;
- batas DAS Kuranji;
- jaringan sungai RBI;
- batas administrasi Pauh dan Kuranji.

#### Tabel 2. Statistik DEM baseline
Kolom minimum:
- minimum elevasi;
- maksimum elevasi;
- mean;
- median;
- resolusi;
- luas area valid;
- jumlah pixel valid.

#### Tabel 3. Perbandingan metode conditioning
Baris minimum:
- FillDepressions;
- Breach100;
- Breach250.

Kolom minimum:
- watershed area;
- intersection area;
- reference-only;
- model-only;
- IoU;
- Dice;
- mean absolute DEM change;
- catatan.

#### Tabel 4. Kalibrasi threshold jaringan sungai final
Baris berupa kandidat threshold, misalnya 3, 4, 5, 6, 7.5, 10 km².

Kolom minimum:
- threshold km²;
- threshold cells;
- panjang jaringan;
- rasio panjang terhadap RBI;
- jumlah komponen;
- jumlah headwater;
- jumlah outlet;
- precision 25/50/100 m;
- recall 25/50/100 m;
- F1;
- F2;
- status kandidat/final.

#### Tabel 5. Validasi watershed final
Kolom minimum:
- luas DAS referensi;
- luas watershed model;
- intersection;
- union;
- reference-only;
- model-only;
- IoU;
- Dice;
- perbedaan luas (%).

### Peta yang wajib disiapkan

#### Peta 1. Lokasi penelitian
Harus menampilkan:
- Sumatera Barat;
- Kota Padang;
- DAS Batang Kuranji;
- Kecamatan Pauh dan Kuranji;
- jaringan sungai utama;
- inset map.

#### Peta 2. DEM baseline
Harus menampilkan:
- hillshade atau elevation colour ramp;
- batas DAS;
- sungai RBI;
- skala elevasi;
- north arrow;
- scale bar;
- CRS.

#### Peta 3. Flow direction / drainage structure
Tidak harus menampilkan semua pointer sel secara visual. Dapat disederhanakan menggunakan drainage structure atau arah aliran utama.

#### Peta 4. Flow accumulation
Harus menunjukkan pola akumulasi dari headwater ke outlet.

#### Peta 5. Jaringan sungai model vs RBI
Harus menampilkan:
- stream model final;
- RBI;
- DAS referensi;
- outlet utama.

#### Peta 6. Watershed model vs DAS referensi
Harus menampilkan secara jelas:
- overlap;
- reference-only area;
- model-only area;
- outlet.

### Narasi hasil yang harus dijelaskan
- alasan memilih breach100;
- kenapa FillDepressions tidak dipakai sebagai baseline final;
- bagaimana threshold jaringan sungai dipilih;
- apakah residual mismatch masih signifikan;
- batasan data dan alasan tidak memaksa model identik 100% dengan DAS resmi.

### Output digital
- DEM conditioned final;
- D8 pointer final;
- flow accumulation final;
- stream network final;
- watershed final;
- outlet final;
- QC JSON/CSV;
- layout peta siap laporan.

---

## BLOK 2 — Geomorphic Flood Index (GFI)

### Tujuan
Menghasilkan indeks bahaya banjir geomorfologi berdasarkan terrain dan jaringan drainase dari baseline hidrologi yang telah divalidasi.

### Prinsip
Formula GFI, parameter, normalisasi, threshold, dan klasifikasi harus mengikuti `MODUL TEKNIS KRB BANJIR-2`. Tidak boleh mengasumsikan formula dari referensi lain tanpa persetujuan eksplisit.

### Tahapan
1. Pastikan baseline hydrology sudah final.
2. Implementasikan formula GFI sesuai modul teknis.
3. Hitung seluruh variabel intermediate yang diperlukan.
4. Hitung raster GFI kontinu.
5. Klasifikasikan GFI sesuai kelas yang ditetapkan modul.
6. Lakukan QC terhadap distribusi nilai.
7. Hitung luas masing-masing kelas GFI.
8. Overlay dengan Pauh, Kuranji, dan kelurahan.

### Tabel yang wajib masuk laporan

#### Tabel 6. Parameter dan formula GFI
Kolom minimum:
- parameter;
- definisi;
- satuan;
- sumber data;
- metode perhitungan;
- referensi/modul.

#### Tabel 7. Statistik raster GFI
Kolom minimum:
- minimum;
- maksimum;
- mean;
- median;
- p25;
- p50;
- p75;
- p90/p95;
- jumlah pixel valid.

#### Tabel 8. Klasifikasi GFI
Kolom minimum:
- kelas;
- rentang nilai;
- luas km²;
- luas ha;
- persentase DAS.

#### Tabel 9. GFI per kecamatan
Minimal:
- Pauh;
- Kuranji.

Kolom minimum:
- luas administrasi dalam DAS;
- luas tiap kelas GFI;
- persen tiap kelas;
- kelas dominan.

#### Tabel 10. GFI per kelurahan
Kolom minimum:
- kecamatan;
- kelurahan;
- luas kelurahan dalam DAS;
- luas kelas rendah;
- sedang;
- tinggi;
- sangat tinggi jika modul menggunakan kelas tersebut;
- persen area tinggi/sangat tinggi.

### Peta yang wajib disiapkan

#### Peta 7. Raster GFI kontinu
Untuk menunjukkan variasi spasial indeks tanpa klasifikasi.

#### Peta 8. Kelas bahaya GFI DAS Kuranji
Harus mengikuti klasifikasi warna dan interval dari modul.

#### Peta 9. GFI Kecamatan Pauh dan Kuranji
Fokus pada dua kecamatan utama.

#### Peta 10. GFI per kelurahan
Menampilkan batas kelurahan dengan kelas GFI sebagai layer utama.

### Grafik yang disarankan
- bar chart luas kelas GFI;
- stacked bar GFI per kecamatan;
- stacked bar atau ranking kelurahan berdasarkan persentase kelas tinggi.

### Narasi hasil yang harus dijelaskan
- pola spasial GFI;
- lokasi konsentrasi bahaya;
- hubungan dengan topografi dan jaringan drainase;
- kecamatan/kelurahan dengan proporsi area bahaya paling besar;
- keterbatasan bahwa GFI baseline berasal dari kondisi DEM yang tersedia.

### Output digital
- raster GFI kontinu;
- raster GFI kelas;
- statistik GFI CSV;
- statistik kecamatan/kelurahan CSV;
- layout peta siap laporan.

---

## BLOK 3 — Analisis Kejadian Siklon Senyar 21–27 November 2025 dan Dampak Administratif

### Tujuan
Menguji bagaimana baseline bahaya geomorfologi berhubungan dengan kejadian banjir aktual November 2025 dan, apabila tersedia data temporal yang memadai, mengukur perubahan sebelum dan sesudah kejadian.

### Dua skenario metodologis

#### Skenario A — Tidak tersedia DEM pascakejadian
Analisis yang sah:

`GFI baseline → overlay observed flood/event extent → validasi → statistik dampak administrasi`

Dalam skenario ini tidak boleh menyebut perbedaan DEMNAS dan RBI sebagai perubahan topografi akibat Siklon Senyar.

#### Skenario B — Tersedia DEM T1 pascakejadian yang kompatibel
Analisis dapat dikembangkan menjadi:

`DEM T0 → GFI T0`

`DEM T1 → GFI T1`

`ΔDEM = T1 − T0`

`ΔGFI = GFI T1 − GFI T0`

Kemudian perubahan dapat dianalisis sebagai perubahan geomorfologi/hazard dengan tetap memperhitungkan uncertainty dan co-registration.

### Data event yang perlu disiapkan jika tersedia
- flood extent November 2025;
- citra Sentinel-1/Sentinel-2 atau produk flood mapping;
- curah hujan event;
- debit observasi;
- titik/lokasi dampak lapangan;
- dokumentasi BPBD/BMKG/instansi terkait;
- DEM pascakejadian jika tersedia.

### Tabel yang wajib masuk laporan

#### Tabel 11. Data kejadian Siklon Senyar
Kolom minimum:
- dataset;
- periode;
- resolusi;
- sumber;
- fungsi analisis;
- kualitas/keterbatasan.

#### Tabel 12. Overlay GFI vs flood extent
Kolom minimum:
- kelas GFI;
- luas kelas;
- luas tergenang;
- persentase kelas yang tergenang;
- kontribusi terhadap total genangan.

#### Tabel 13. Confusion/validation matrix jika flood extent memadai
Dapat membandingkan:
- predicted susceptible;
- observed flooded;
- observed non-flooded.

Metric yang dapat dilaporkan jika metodologinya valid:
- precision;
- recall;
- F1;
- overall agreement;
- hit rate.

#### Tabel 14. Dampak per kecamatan
Kolom minimum:
- kecamatan;
- luas dalam DAS;
- luas flood extent;
- % area terdampak;
- luas GFI tinggi yang tergenang.

#### Tabel 15. Dampak per kelurahan
Kolom minimum:
- kecamatan;
- kelurahan;
- luas wilayah;
- luas flood extent;
- persentase flood extent;
- kelas GFI dominan;
- luas overlap GFI tinggi + flooded.

#### Tabel 16. Perubahan T0–T1 jika DEM T1 tersedia
Kolom minimum:
- unit wilayah;
- ΔDEM mean;
- ΔDEM max/min;
- GFI T0;
- GFI T1;
- ΔGFI;
- luas perubahan kelas hazard;
- catatan uncertainty.

### Peta yang wajib disiapkan

#### Peta 11. Flood extent November 2025
Harus menampilkan extent aktual yang digunakan.

#### Peta 12. Overlay GFI baseline vs flood extent
Peta inti untuk menunjukkan apakah lokasi bahaya geomorfologi berhubungan dengan kejadian aktual.

#### Peta 13. Flood extent per kelurahan
Fokus pada Pauh dan Kuranji.

#### Peta 14. Hotspot GFI tinggi + observed flood
Peta prioritas untuk interpretasi risiko.

#### Peta 15. ΔDEM jika T1 tersedia
Menampilkan erosi, deposisi, atau perubahan elevasi dengan threshold uncertainty yang jelas.

#### Peta 16. ΔGFI jika T1 tersedia
Menampilkan area naik/turun kelas bahaya setelah kejadian.

### Grafik yang disarankan
- flood area per kelas GFI;
- flood area per kelurahan;
- ranking kelurahan terdampak;
- distribusi ΔDEM jika tersedia;
- perubahan luas kelas GFI T0 vs T1 jika tersedia.

### Narasi hasil yang harus dijelaskan
- hubungan GFI baseline dengan observed flood;
- area di mana GFI dan flood extent konsisten;
- false positive/false negative jika ada;
- kelurahan dengan dampak terbesar;
- apakah data mendukung klaim perubahan sebelum–sesudah;
- batasan sensor, resolusi, waktu akuisisi, dan kualitas data.

### Output digital
- flood extent final;
- overlay GFI-event;
- statistik per kelas dan administrasi;
- confusion/validation outputs jika layak;
- ΔDEM/ΔGFI jika T1 tersedia;
- layout peta siap laporan.

---

# Struktur Laporan Akhir yang Disarankan

## Bab Metodologi
1. Wilayah studi
2. Data dan sumber data
3. Persiapan DEM
4. Hydrological conditioning
5. Flow direction dan flow accumulation
6. Kalibrasi jaringan sungai
7. Validasi watershed
8. Metode GFI
9. Metode analisis kejadian 2025
10. Metode overlay administratif
11. Quality control dan keterbatasan

## Bab Hasil
1. Karakteristik topografi DAS
2. Hasil baseline hidrologi
3. Hasil kalibrasi stream network
4. Validasi watershed
5. Distribusi GFI
6. GFI Pauh dan Kuranji
7. GFI per kelurahan
8. Kejadian banjir November 2025
9. Overlay GFI vs observed flood
10. Perubahan T0–T1 jika data tersedia
11. Hotspot dan wilayah prioritas

## Bab Pembahasan
1. Arti geomorfologis pola GFI
2. Kesesuaian model dengan kejadian aktual
3. Perbedaan DEM-derived drainage dan referensi RBI/DAS
4. Dampak Siklon Senyar
5. Implikasi bagi Pauh dan Kuranji
6. Ketidakpastian dan keterbatasan data

---

# Checklist Final Deliverable

Setiap blok analisis baru dianggap selesai jika memiliki:

- [ ] metode terdokumentasi;
- [ ] script reproducible;
- [ ] input tercatat;
- [ ] output raster/vector final;
- [ ] QC;
- [ ] tabel statistik;
- [ ] peta layout final;
- [ ] interpretasi hasil;
- [ ] batasan/uncertainty;
- [ ] file siap dimasukkan ke laporan.

Dengan sistem ini, pekerjaan teknis dan penulisan laporan berjalan paralel. Kita tidak menunggu seluruh analisis selesai baru mulai menyusun tabel dan peta.
