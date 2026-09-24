# QC Parameter Fuzzy Tahap 2 DAS Kuranji

## Latar Belakang

Setelah perbandingan full GFI pipeline antara `channel_ASk` dan local `channel_FAt 6 km2`, kedua metode menghasilkan proporsi WD negatif yang hampir sama pada manual GFI threshold -0.53:

- GFA channel_ASk: WD negatif 78.9%, WD positif 21.1%;
- Local FAt 6 km2: WD negatif 78.0%, WD positif 22.0%.

Dengan demikian WD negatif bukan terutama akibat pemilihan drainage network lokal. Jaringan 6 km2 tetap dipertahankan karena agreement terhadap RBI lebih baik dan perilaku GFI/WD tetap konsisten dengan ASk.

---

## 1. Ketentuan tertulis modul

MODUL TEKNIS KRB BANJIR-2 menetapkan:

- water depth: `WD = hr - H`;
- fuzzy membership type: `Large`;
- midpoint: `1.125` m;
- spread: `1.75`;
- hazard class:
  - rendah: indeks <= 0.333;
  - sedang: 0.333 < indeks <= 0.666;
  - tinggi: indeks > 0.666.

---

## 2. Inkonsistensi pada Gambar 2-25

Tabel numerik pada Gambar 2-25 menunjukkan pasangan kedalaman-indeks berikut, antara lain:

- 0.125 m -> 0.004
- 0.250 m -> 0.023
- 0.500 m -> 0.116
- 0.750 m -> 0.266
- 1.000 m -> 0.427
- 1.125 m -> 0.500
- 1.250 m -> 0.565
- 1.500 m -> 0.672
- 1.750 m -> 0.751
- 2.000 m -> 0.808
- 2.500 m -> 0.880
- 3.000 m -> 0.921

Untuk standard ArcGIS Fuzzy Large:

`mu(x) = 1 / [1 + (x / midpoint)^(-spread)]`

Dengan midpoint 1.125:

- spread 1.75 tidak mereproduksi tabel tersebut;
- spread 2.5 mereproduksi tabel tersebut hampir tepat sampai tiga desimal.

Contoh:

| WD (m) | Gambar modul | FuzzyLarge spread 1.75 | FuzzyLarge spread 2.5 |
|---:|---:|---:|---:|
| 0.125 | 0.004 | 0.021 | 0.004 |
| 0.250 | 0.023 | 0.067 | 0.023 |
| 0.500 | 0.116 | 0.195 | 0.116 |
| 0.750 | 0.266 | 0.330 | 0.266 |
| 1.000 | 0.427 | 0.449 | 0.427 |
| 1.125 | 0.500 | 0.500 | 0.500 |
| 1.500 | 0.672 | 0.623 | 0.672 |
| 2.000 | 0.808 | 0.732 | 0.808 |
| 3.000 | 0.921 | 0.848 | 0.921 |

Dengan demikian terdapat inkonsistensi internal antara parameter teks (`spread=1.75`) dan angka pada Gambar 2-25 (`spread≈2.5`).

---

## 3. ArcGIS Fuzzy Large dan WD negatif

Dokumentasi ArcGIS menyatakan input Fuzzy Large harus berupa nilai positif. Pada Kuranji, manual GFI threshold -0.53 menghasilkan banyak `WD = hr-H < 0`.

Karena modul tidak menjelaskan secara eksplisit cara menangani WD negatif, penelitian tidak akan menghapus masalah tersebut secara diam-diam.

Untuk sensitivity analysis digunakan dua perlakuan transparan:

### A. Module-default mask

- flood-prone mask: `GFI_norm > -0.53`;
- raw WD tetap disimpan;
- untuk input fuzzy, nilai WD negatif di-floor ke 0 sebagai physical no-inundation floor;
- hasil ini disebut **module-default provisional scenario**, bukan calibrated final hazard.

### B. Physical-positive mask

- flood-prone mask: `GFI_raw > 0`, ekuivalen dengan `hr > H` dan `WD > 0`;
- pada local 6 km2 equivalen dengan `GFI_norm > -0.337819` untuk dataset baseline ini;
- skenario ini disebut **physical-consistency sensitivity**, bukan empirical calibration.

---

## 4. Dua spread yang diuji

Kedua flood-prone strategies diuji dengan:

1. `spread = 1.75` untuk mengikuti teks modul;
2. `spread = 2.5` untuk mereplikasi angka Gambar 2-25.

Dengan demikian terdapat empat skenario diagnostic:

| Scenario | Flood-prone definition | Fuzzy spread |
|---|---|---:|
| M175 | GFI norm > -0.53 | 1.75 |
| M250 | GFI norm > -0.53 | 2.5 |
| P175 | GFI raw > 0 | 1.75 |
| P250 | GFI raw > 0 | 2.5 |

Tidak satu pun otomatis dinyatakan sebagai final calibrated hazard sebelum hasil sensitivity dibandingkan dan/atau standard flood map tersedia.

---

## 5. Keputusan sementara

- Drainage network final Tahap 2 tetap local FAt 6 km2.
- `channel_ASk` tidak dilanjutkan sebagai primary network.
- Manual threshold -0.53 hanya baseline modul dan belum dikalibrasi lokal.
- Written spread 1.75 diperlakukan sebagai parameter tekstual utama modul.
- Spread 2.5 wajib diuji sebagai sensitivity karena mereproduksi Gambar 2-25.
- Semua raw WD negatif tetap disimpan sebagai QC evidence.
- Proses final hazard tidak boleh menghilangkan uncertainty ini dari laporan.
