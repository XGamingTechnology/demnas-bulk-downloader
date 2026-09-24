# QC Threshold GFI dan Ketinggian Genangan DAS Kuranji

## Status

Checkpoint QC setelah perhitungan GFI baseline dan audit threshold manual GFA `-0.53`.

## Hasil utama

Threshold manual/default plugin:

`GFI_normalized > -0.53`

menghasilkan:

- flood-prone area sementara = 60.138 km²;
- 2 connected components, dengan component utama 60.137 km²;
- WD negatif = 675,819 cells (77.969% dari flood-prone mask);
- WD positif = 190,955 cells (22.031%);
- WD range = -32.697 sampai 6.677 m;
- WD median = -3.253 m;
- WD mean = -4.286 m;
- positive WD p95 = 4.293 m;
- positive WD p99 = 5.603 m.

## Interpretasi

Menurut MODUL TEKNIS KRB BANJIR-2, ketinggian genangan dihitung sebagai:

`WD = hr - H`

dan hazard final didasarkan pada ketinggian genangan.

Nilai WD negatif tidak memiliki interpretasi fisik sebagai kedalaman genangan. Oleh karena itu hasil threshold manual `-0.53` tidak dapat langsung dinyatakan sebagai final area potensi banjir DAS Kuranji tanpa calibration atau penyesuaian metodologis yang transparan.

## Hubungan matematis GFI dan WD

Karena:

`GFI_raw = ln(hr/H)`

maka:

- `GFI_raw > 0` ekuivalen dengan `hr > H`;
- `hr > H` ekuivalen dengan `WD = hr - H > 0`.

Dengan range GFI raw Kuranji:

- minimum = -6.638383;
- maksimum = 13.411668;

normalisasi plugin:

`GFI_norm = 2 * ((GFI_raw - min)/(max-min) - 0.5)`

mengubah `GFI_raw = 0` menjadi kira-kira:

`GFI_norm = -0.337819`.

Artinya setiap threshold normalized di bawah sekitar `-0.3378` secara matematis akan mengizinkan sebagian sel dengan `WD <= 0` masuk ke flood-prone mask.

Nilai ini **bukan threshold final yang dikalibrasi**, tetapi merupakan physical-consistency reference untuk memahami hubungan GFI dan WD.

## Calibration data audit

Scanner lokal menemukan lima file bernama `calibration`, tetapi semuanya terkait **stream-threshold calibration Tahap 1**, bukan peta banjir atau genangan historis.

Dengan demikian pada VPS saat ini belum terdeteksi standard/historical flood map yang layak untuk calibration threshold GFI.

## Keputusan QC

1. Threshold `-0.53` tetap disimpan sebagai manual/default sensitivity case.
2. Threshold `-0.53` **tidak dikunci sebagai final Kuranji flood-prone threshold**.
3. Tidak dilakukan fuzzy hazard final sebelum threshold flood-prone diputuskan.
4. Tahap berikutnya adalah sensitivity analysis threshold normalized untuk mengukur:
   - luas flood-prone;
   - proporsi WD positif/negatif;
   - connected components;
   - distribusi WD positif;
   - threshold reference pada GFI_raw = 0 / WD = 0.
5. Jika historical flood extent independen diperoleh, threshold final harus dikalibrasi menggunakan data tersebut sebagaimana prinsip plugin GFA/modul.
6. Jika data calibration independen tidak tersedia, penelitian harus menyatakan dengan eksplisit bahwa threshold dipilih menggunakan physical-consistency + sensitivity analysis, bukan calibration terhadap observed flood.
