# BKPM — kamus data, sumber, dan kualitas (checkpoint 2026-11-09)

Dokumen ini dibuat dari struktur parser yang ada dan log audit VPS. **Nama kolom yang belum terlihat dalam kode/log tidak diasumsikan tersedia.** Detail semua nama kolom sebenarnya dapat diperiksa pada record_records.json atau attribute_presence.csv di VPS.

## Sumber dan dataset

| Dataset | Endpoint/sumber | Unit spasial | Catatan |
|---|---|---|---|
| Peluang investasi proyek | https://regionalinvestment.bkpm.go.id/be/peluang/peluang_investasi_wilayah | 1 record per id_peluang; Point jika koordinat sah | API pagination: page/pageSize/totalPage/totalRecords, 21 halaman dan 185 record pada checkpoint |
| Komoditas | https://regionalinvestment.bkpm.go.id/data/komoditas.geojson | 142 GeoJSON Feature bertipe Point pada checkpoint | CRS dideklarasikan OGC:CRS84; jangan menganggap sebagai poligon |
| Batas wilayah BKPM awal | /data/wilayah_barat.geojson, /data/wilayah_tengah.geojson, /data/wilayah_timur.geojson pada host BKPM | 34 polygon/MultiPolygon provinsi historis | Tidak langsung layak untuk batas 38 provinsi terbaru |
| Data realisasi LKPM/Satu Data | https://data.bkpm.go.id/dataset | Tabular, perlu join admin | Berbeda dari peluang investasi proyek dan tidak otomatis mengandung koordinat |

## Field peluang yang terkonfirmasi

| Kolom/atribut | Sumber | Makna/ketentuan |
|---|---|---|
| id_peluang | API JSON | ID proyek; untuk deduplikasi, 185 ID unik teramati |
| nama | API JSON | Nama proyek sebagaimana diterbitkan |
| lon | API JSON | Longitude mentah; tidak boleh diganti dengan centroid administratif jika hilang |
| lat | API JSON | Latitude mentah; pasangan longitude yang wajib valid |
| nilai_investasi | API JSON | Nilai peluang investasi mentah; **jangan otomatis disamakan dengan realisasi** atau dijumlahkan lintas satuan sebelum normalisasi terverifikasi |
| nilai_irr | API JSON | Nilai IRR menurut sumber, satuan/format perlu audit per record |
| nilai_npv | API JSON | Nilai NPV menurut sumber, satuan/format perlu audit |
| status_proyek | API JSON | Status dari penerbit; 111 dari 185 terisi pada checkpoint; NULL tetap tidak diketahui |
| nama_provinsi, nama_sektor | Referensi kode viewer; cek skema snapshot | Label administratif/sektor yang dipakai dropdown/popup **perlu smoke test**; bila sumber memakai nama field berbeda UI dapat kosong |
| source_project_id | Ditambahkan collector | Salinan id_peluang untuk audit output |
| source_url | Ditambahkan collector | Endpoint sumber record |
| dataset_role | Ditambahkan collector | investment_opportunity_not_realization |
| coordinate_qc | Ditambahkan collector | range_ok_site_unverified; hanya pemeriksaan rentang |
| location_accuracy | Ditambahkan collector | publisher_point_not_site_validated; bukan survei tapak |

GeoJSON proyek menggunakan geometry.type=Point dan geometry.coordinates=[longitude, latitude]. Batas pemeriksaan collector: bujur 94..142, lintang -12..7; ini **filter plausibilitas**, bukan validasi kabupaten/tapak. OGC:CRS84 komoditas juga menggunakan axis order bujur lalu lintang.

## Kualitas, missing, dan koordinat sama

- 185 record sumber diperoleh dari totalRecords=185 pada tanggal checkpoint.
- 180 record lolos fungsi make_point. **Lima record** (ID 138, 145, 233, 105, 106) tidak lolos karena longitude tidak layak/missing; atribut tetap ada di region_records.json dan daftar nonspasial.
- Dua kelompok koordinat sama pada presisi pembulatan 7 digit: ID 359/365/369 dan 362/366. **Bukan** bukti duplikasi proyek; periksa konteks proyek.
- Validasi GeoJSON vs raw record: tidak ada duplikasi ID, mismatch koordinat, maupun ID tidak terduga dalam audit yang dilaporkan.
- Ketersediaan nilai tidak membuktikan kesesuaian satuan/nilai. Tentukan normalisasi secara eksplisit bila membuat grafik agregasi.
- Unit test 37 lulus pada checkpoint; validasi UI peta belum dilakukan.

## Berkas QA utama

- data/bkpm/spatial_api/audit.json — ringkasan respons, metadata pagination/checksum.
- data/bkpm/spatial_api/quality/quality_summary.json — audit kesesuaian ID/geometri.
- data/bkpm/spatial_api/quality/projects_without_coordinates.csv — record tanpa titik.
- data/bkpm/spatial_api/quality/shared_coordinates.csv — kelompok koordinat bersama.
- data/bkpm/spatial_api/quality/attribute_presence.csv — persentase non-null/terisi.
- data/bkpm/webgis_preview/data/snapshot.json — metadata paket viewer.

## Cara mengecek **field sebenarnya** pada snapshot

Dari root worktree dengan file snapshot lokal:

    python - <<'PY'
    import json
    from pathlib import Path
    p = Path("data/bkpm/spatial_api/region_records.json")
    records = json.loads(p.read_text(encoding="utf-8"))["records"]
    print("Jumlah record:", len(records))
    print("Kolom teramati:", sorted(set().union(*(r.keys() for r in records if isinstance(r, dict)))))
    PY

Pemeriksaan di atas hanya membaca dataset lokal. Jangan menuliskan nilai sensitif ke log publik.

## Aturan pemanfaatan

1. Jangan campur indikator **peluang** dengan **realisasi** LKPM.
2. Jangan merekayasa titik proyek dari kabupaten/provinsi ketika lon/lat tidak sah.
3. Untuk join administratif, gunakan batas resmi terkini dan validasi sistem kode serta ketepatan posisi.
4. Untuk WebGIS publik, cek izin lisensi/redistribusi, sumber, periode snapshot dan atribusi.
5. Audit nilai status, Rp, IRR, NPV serta format sebelum analisis ekonomi dan visualisasi komparatif.

[Lihat runbook](RUNBOOK.md) · [checkpoint](CHECKPOINT_2026-11-09.md).