# Keputusan Drainage Network untuk GFI DAS Kuranji

## Status

Keputusan metodologis Tahap 2 setelah preflight `channel_ASk` vs jaringan lokal `FAt 6 km²`.

## Hasil Preflight

Reference RBI:

- panjang = 79.813 km.

### GFA default `channel_ASk`

- panjang = 203.28 km;
- rasio terhadap RBI ≈ 2.55×;
- headwater = 121;
- outlet = 1;
- connected components = 1;
- precision @100 m = 0.117;
- recall @100 m = 0.563;
- F1 @100 m = 0.194;
- F2 @100 m = 0.320.

### Local adaptation `channel_FAt`, threshold 6 km²

- panjang = 81.00 km;
- rasio terhadap RBI ≈ 1.015×;
- headwater = 12;
- outlet = 1;
- connected components = 1;
- precision @100 m = 0.281;
- recall @100 m = 0.551;
- F1 @100 m = 0.372;
- F2 @100 m = 0.462.

### Hubungan ASk dan jaringan 6 km²

- cell Jaccard = 0.3906;
- ASk cells dalam 100 m dari 6 km² = 42.93%;
- 6 km² cells dalam 100 m dari ASk = 98.59%.

Interpretasi: jaringan 6 km² hampir seluruhnya terkandung dalam koridor jaringan ASk, tetapi ASk menghasilkan banyak cabang tambahan yang tidak dipertahankan jaringan lokal dan memiliki agreement jauh lebih rendah terhadap RBI.

## Keputusan

Untuk perhitungan `H`, `Ariver`, `hr`, dan GFI DAS Kuranji, drainage network utama menggunakan:

**minimum contributing area = 6 km² (`channel_FAt` local adaptation).**

Keputusan ini bukan parameter universal GFI. Nilai 6 km² merupakan parameter lokal DAS Kuranji yang dikalibrasi pada Tahap 1 terhadap RBI dan diverifikasi kembali pada Tahap 2.

`channel_ASk` tetap disimpan sebagai sensitivity/reference product karena merupakan default plugin GFA pada modul.

## Justifikasi

1. Modul memperbolehkan penyesuaian perangkat lunak/prosedur selama prinsip dasar metode dipertahankan.
2. GFI membutuhkan elemen drainage yang terhubung secara hidrologis; jaringan 6 km² tetap merupakan D8-derived drainage network.
3. Panjang jaringan 6 km² sangat dekat dengan RBI: 81.00 vs 79.813 km.
4. Jaringan 6 km² membentuk satu connected component dengan satu outlet.
5. Precision, F1, dan F2 terhadap RBI jauh lebih baik daripada ASk.
6. Recall tetap hampir sama: 0.551 vs 0.563, sehingga pruning tidak menghilangkan sebagian besar coverage RBI.
7. 98.59% jaringan 6 km² berada dalam 100 m dari ASk; local adaptation terutama menghapus over-dense branches, bukan mengganti drainage backbone.

## Implementasi Tahap 2B

GFI akan dihitung mengikuti logika aktif plugin GFA dengan adaptasi jaringan lokal:

1. Untuk setiap sel analisis, trace downstream mengikuti D8 sampai bertemu channel 6 km² yang terhubung.
2. `Ariver` = flow accumulation pada channel tersebut.
3. `H` = elevasi sel − elevasi channel terhubung.
4. Jika `H = 0`, gunakan `H = 0.00001` mengikuti plugin untuk mencegah pembagian nol.
5. `hr = [((Ariver + 1) × cell_area) / 1,000,000]^n`.
6. Gunakan `n = 0.354429752`, sesuai runtime default plugin GFA yang dipakai sebagai acuan modul.
7. `GFI_raw = ln(hr/H)`.
8. Normalisasi `GFI_raw` ke rentang -1 sampai +1 seperti source code plugin.
9. Threshold manual `-0.53`, jika digunakan, diterapkan pada **GFI normalized**, bukan raw GFI.
10. Threshold final flood-prone tetap akan dikalibrasi dengan standard/historical flood map jika data independen tersedia.

## Catatan spasial

Routing tetap menggunakan DEM buffer dan D8 dari Tahap 1 untuk menjaga konektivitas di sekitar boundary. Statistik/output GFI utama dimask ke DAS Kuranji referensi. Channel threshold 6 km² dapat dibentuk pada full routing grid untuk memungkinkan sel dekat boundary menemukan drainage downstream secara konsisten; evaluasi/reporting tetap dilakukan di dalam DAS referensi.
