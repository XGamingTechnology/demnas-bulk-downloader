# TAHAP 3 — INTERPRETASI VALIDASI BIG/BRIN WORLDVIEW 1 DESEMBER 2025

## 1. Sumber Observasi

Observed flood reference menggunakan BIG/BRIN `2025_BANJIRSUMATERA` MapServer Layer 3 dengan metadata hasil preflight:

- `Tgl_citra = 1/12/2025`
- `Sumber_dat = Hasil interpretasi citra WorldView`
- `Kabupaten = Kota Padang`
- observed flood extent di dalam DAS Kuranji = **4.1760 km²**

Layer 5 tidak digunakan karena atributnya mengidentifikasi `kab_ac_tami_flood`, sehingga provenance-nya tidak sesuai dengan Padang/Kuranji.

Observed reference bertanggal sesudah periode utama banjir 21–27 November 2025. Karena itu, hasil validasi mengukur kesesuaian terhadap **post-event mapped extent 1 Desember 2025**, bukan extent puncak banjir.

---

## 2. Validasi Biner Seluruh DAS

| Scenario | Domain | Predicted (km²) | TP (km²) | FP (km²) | FN (km²) | Precision | Recall | F1 | IoU |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| M175 | manual | 60.138 | 3.956 | 56.182 | 0.220 | 0.0658 | 0.9474 | 0.1230 | 0.0655 |
| M250 | manual | 60.138 | 3.956 | 56.182 | 0.220 | 0.0658 | 0.9474 | 0.1230 | 0.0655 |
| P175 | physical WD>0 | 13.249 | 1.632 | 11.616 | 2.544 | 0.1232 | 0.3909 | 0.1874 | 0.1034 |
| P250 | physical WD>0 | 13.249 | 1.632 | 11.616 | 2.544 | 0.1232 | 0.3909 | 0.1874 | 0.1034 |

### Interpretasi

M-domain mempunyai recall sangat tinggi (94.74%), tetapi prediksi area sangat luas dibandingkan observed extent, sehingga precision hanya 6.58% dan FP mencapai 56.182 km².

P-domain jauh lebih sempit. Recall turun menjadi 39.09%, tetapi precision meningkat menjadi 12.32%, F1 meningkat dari 0.1230 menjadi 0.1874, dan IoU meningkat dari 0.0655 menjadi 0.1034.

Dengan demikian, terhadap observed post-event 1 Desember, **P-domain menunjukkan kecocokan spasial global yang lebih efisien menurut F1 dan IoU**, tetapi masih kehilangan sebagian besar observed extent.

Pernyataan ini tidak berarti P-domain telah terbukti sebagai representasi banjir puncak 21–27 November. Sebagian model-only area yang tercatat sebagai FP relatif terhadap citra 1 Desember dapat merupakan area yang sempat tergenang dan telah surut sebelum tanggal observasi.

---

## 3. Equivalence P175/P250 dan M175/M250

Validasi biner mengonfirmasi:

```text
P175 == P250 : True
M175 == M250 : True
```

Hal ini sesuai desain model karena spread fuzzy 1.75 versus 2.50 mengubah indeks/kelas di dalam flood-prone domain, bukan binary extent domain.

Karena itu, binary flood extent tidak dapat digunakan untuk menentukan spread 1.75 atau 2.50 mana yang lebih benar.

---

## 4. Pola Kecamatan — P175

| Kecamatan | Observed km² | Predicted km² | TP km² | FP km² | FN km² | Precision | Recall | F1 | IoU |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Nanggalo | 2.473 | 3.888 | 0.852 | 3.035 | 1.621 | 0.219 | 0.345 | 0.268 | 0.155 |
| Kuranji | 0.917 | 2.086 | 0.228 | 1.858 | 0.689 | 0.109 | 0.248 | 0.152 | 0.082 |
| Padang Utara | 0.490 | 2.480 | 0.420 | 2.060 | 0.071 | 0.169 | 0.855 | 0.283 | 0.164 |
| Pauh | 0.199 | 1.443 | 0.054 | 1.389 | 0.145 | 0.037 | 0.271 | 0.066 | 0.034 |
| Koto Tangah | 0.087 | 3.322 | 0.068 | 3.254 | 0.018 | 0.021 | 0.791 | 0.040 | 0.020 |

P175 menangkap observed extent dengan recall tinggi di Padang Utara dan Koto Tangah, tetapi overprediction tetap besar di Koto Tangah. FN terbesar berada di Nanggalo dan Kuranji.

---

## 5. Pola Kelurahan Penting — P175

Contoh performa lokal:

- Air Tawar Timur: F1 = 0.704; precision = 0.628; recall = 0.801.
- Kampung Lapai: F1 = 0.429; recall = 0.820.
- Kampung Olo: F1 = 0.369; precision dan recall relatif seimbang.
- Gurun Laweh: precision = 0.880 tetapi recall = 0.169.
- Tabiang Banda Gadang: precision = 0.994 tetapi recall = 0.089.
- Kurao Pagang: recall = 0.734 tetapi precision = 0.107.

FN P175 terbesar:

1. Gurun Laweh = 0.580 km²
2. Tabiang Banda Gadang = 0.478 km²
3. Gunung Sarik = 0.331 km²
4. Kampung Olo = 0.314 km²
5. Kuranji = 0.305 km²

Pola ini menunjukkan bahwa kekurangan P-domain tidak seragam secara spasial.

---

## 6. Pola M175

M175 berhasil menangkap seluruh observed extent di sejumlah wilayah, termasuk Nanggalo dan Padang Utara, tetapi overprediction sangat besar.

Contoh:

- Nanggalo: recall 1.000; precision 0.263.
- Padang Utara: recall 1.000; precision 0.074.
- Kuranji: recall 0.786; precision 0.037.
- Koto Tangah: recall 0.887; precision 0.004.

Secara lokal, M175 dapat menghasilkan F1 tinggi pada beberapa kelurahan dengan observed extent yang kompak, seperti Tabiang Banda Gadang dan Cupak Tangah, tetapi performa tersebut tidak menghilangkan masalah overprediction besar pada domain keseluruhan.

---

## 7. Komposisi Observed Extent terhadap Kelas Model

Komposisi overlap observed extent di dalam kelas P175:

- Low: 0.361 km² (8.64%)
- Medium: 0.383 km² (9.16%)
- High: 0.889 km² (21.28%)

P250:

- Low: 0.409 km² (9.80%)
- Medium: 0.273 km² (6.53%)
- High: 0.950 km² (22.76%)

Nilai ini hanya bersifat deskriptif. Binary observed flood extent tidak memberikan informasi kedalaman genangan sehingga tidak dapat memvalidasi kelas Low/Medium/High secara langsung.

---

## 8. Keputusan Sementara Tahap 3

1. P-domain tetap lebih defensible sebagai kandidat baseline primer karena menghasilkan F1 dan IoU global yang lebih tinggi daripada M-domain terhadap observed post-event 1 Desember.
2. M-domain menunjukkan kemampuan capture yang sangat tinggi tetapi terlalu luas untuk dianggap sebagai flood extent representatif tanpa pembatas tambahan.
3. P-domain belum dapat dianggap final karena FN masih besar, terutama di Nanggalo dan Kuranji.
4. Tidak dilakukan tuning threshold baru menggunakan observed event ini agar validation tidak berubah menjadi calibration tersembunyi.
5. Binary validation belum dapat memilih antara spread 1.75 dan 2.50.

---

## 9. QC Berikutnya

Sebelum membekukan Tahap 3, lakukan **positional-tolerance validation** karena:

- resolusi model sekitar 8.33 m;
- observed polygon berasal dari interpretasi citra WorldView;
- garis sungai, DEM, dan polygon interpretasi dapat mempunyai offset beberapa meter;
- exact pixel overlap dapat menghukum near-miss yang secara spasial masih dekat.

Tolerance yang diuji:

- 0 pixel
- 1 pixel (~8.33 m)
- 2 pixel (~16.66 m)
- 3 pixel (~24.99 m)
- 5 pixel (~41.65 m)

Tolerance analysis hanya mengukur sensitivitas terhadap positional uncertainty; bukan tuning threshold GFI.
