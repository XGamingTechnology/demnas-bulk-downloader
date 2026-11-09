# CHECKPOINT BKPM — 2026-11-09 (Asia/Jakarta)

**Proyek:** BKPM Regional Investment × eksperimen geospasial di repo demnas-bulk-downloader.  
**Branch remote:** feature/bkpm-demnas-geoportal  
**Worktree VPS:** /home/ubuntu/geo-experiments/bkpm-demnas  
**Commit terakhir sebelum penulisan dokumen:** 47711494f446342a345de6d3163803a43774e9e6 (WebGIS package tests)  
**Sifat dokumen:** snapshot historis berdasarkan hasil terminal VPS yang diberikan dalam percakapan, bukan observasi live terbaru.

## Checklist checkpoint

| Tahap | Bukti dan hasil | Status |
|---|---|---|
| Setup Python dan Chromium | Chromium smoke test mencetak RESULT: Chromium OK setelah pemasangan libasound2t64 pada Ubuntu 24.04 | Selesai pada VPS |
| Extract detail publik | 5 URL detail BKPM mengeluarkan 5 titik; nama proyek benar via dom_breadcrumb | Selesai pada sampel |
| Unit test sebelum paket WebGIS | 35/35 lulus pada audit kualitas | Selesai |
| Identifikasi endpoint publik | Browser Network menunjukkan endpoint peluang_investasi_wilayah, card, sektor, komoditas.geojson | Selesai untuk endpoint teramati |
| Pagination proyek wilayah | 21 halaman; meta totalRecords=185; data 185 ID unik | Selesai pada snapshot |
| Data titik peluang | 180 fitur; 5 tidak memiliki lon/lat yang layak digunakan; 0 duplikasi ID di GeoJSON | Selesai dengan pengecualian |
| Data komoditas | 142 fitur Point; declared CRS urn:ogc:def:crs:OGC:1.3:CRS84; SHA-256 5dabe3a070032a05997589814719e372819b413ecb8620df2d107bcf364fae96 | Selesai pada snapshot |
| Audit spasial lokal | 185 ID sumber unik; 180 kecocokan titik; 5 gagal koordinat; 2 kelompok koordinat bersama; tidak ada ID/geometri mismatch | Selesai untuk pemeriksaan terprogram |
| Kelengkapan atribut | nama, nilai_investasi, nilai_irr, nilai_npv tersedia 185; status_proyek tersedia 111/185 | Audit awal selesai |
| Unit test sesudah WebGIS | 37/37 lulus | Selesai pada VPS |
| Paket WebGIS statis | python -m bkpm.webgis_package menghasilkan 180 project_points, 5 missing_coordinate_records, 142 commodity_points | Dibuat pada VPS |
| Smoke test browser WebGIS | Belum ada output screenshot / interaksi filter/popup / konsol browser | **Belum diverifikasi** |
| GitHub Pages | Belum deploy; dataset tetap di data/ dan tidak ikut Git | **Belum dilakukan** |
| Validasi lokasi fisik | Belum validasi lapangan / peta referensi presisi tapak proyek | **Belum dilakukan** |

## Bukti angka dari log

- spatial_api_collect --max-pages 21 --delay 2: pages_accepted=21; unique_region_records=185; point_features_exported=180; pagination_status=all_reported_pages_reached.
- audit ulang lokal: ID unik=180 di GeoJSON, duplikasi ID=0, coordinate quality={'ok':180,'missing_or_invalid_coordinate':5}.
- komoditas.geojson: 142 fitur Point; OGC:CRS84 (urutan lon/lat).
- Paket: data/bkpm/webgis_preview (index.html + data GeoJSON/metadata lokal).
- Jumlah titik yang lolos pemeriksaan rentang bukan jaminan bahwa koordinat adalah tapak proyek.
- API mengembalikan 185 record pada saat audit; jika digunakan di waktu lain, harus dibandingkan metadata totalRecords baru.

### Anomali yang **tidak boleh diam-diam diperbaiki**

1. Proyek tanpa longitude usable: ID **138, 145, 233, 105, 106**. Untuk dua record terakhir ada latitude tidak wajar menurut audit sebelumnya. Tetap sebagai record nonspasial sampai sumber diperbaiki/terverifikasi.
2. Kelompok koordinat bersama: **359,365,369** dan **362,366**. Jangan menghitung tiap koordinat sebagai situs unik tanpa pengecekan.
3. status_proyek hanya terisi 111/185 (~60%). Jangan mengasumsikan null = belum aktif/ditolak.
4. Batas provinsi yang teramati di GeoJSON awal berjumlah 34, tidak otomatis mencerminkan 38 provinsi saat ini; untuk spatial join diperlukan batas administrasi termutakhir dan audit kode.
5. Alur project_discovery melalui DOM pernah menghasilkan 0 URL; **bukan** bukti tidak adanya proyek. Endpoint API wilayah yang teramati menjadi sumber pengumpulan utama.

## File dan asal usul output (lokal VPS)

| Berkas relatif root | Artinya |
|---|---|
| data/bkpm/spatial_api/region_records.json | 185 record JSON asli API yang diperoleh |
| data/bkpm/spatial_api/bkpm_opportunities_api_points.geojson | 180 proyek dengan koordinat valid secara rentang |
| data/bkpm/spatial_api/bkpm_komoditas_original.geojson | 142 fitur komoditas publik |
| data/bkpm/spatial_api/audit.json | halaman, checksums, status pagination, penolakan |
| data/bkpm/spatial_api/quality/quality_summary.json | rekonsiliasi ID/geometri |
| data/bkpm/spatial_api/quality/projects_without_coordinates.csv | lima record bermasalah |
| data/bkpm/spatial_api/quality/shared_coordinates.csv | grup titik yang bertumpuk |
| data/bkpm/spatial_api/quality/attribute_presence.csv | kelengkapan atribut |
| data/bkpm/webgis_preview/index.html | pratinjau statis hasil packaging |
| data/bkpm/webgis_preview/data/ | dua GeoJSON dan ringkasan audit untuk viewer |
| data/bkpm/spatial_api_backup_3pages/ | salinan eksperimen tiga halaman sebelum run penuh (sesuai log VPS) |

**Data tidak di-commit.** Folder data/ diabaikan Git; tidak dapat dipulihkan hanya dari source code GitHub.

## Eksperimen berikutnya

1. **Prioritas 1 — Smoke test WebGIS di browser**: jalankan runbook preview lokal port 8876; periksa kesesuaian statistik, popup, filter, perilaku marker bertumpuk, dan error console.
2. **Prioritas 2 — QA substantif**: cocokkan beberapa nama, lokasi, nilai dan status ke halaman detail BKPM; catat hasil dan ketidakpastian posisi.
3. **Prioritas 3 — Peta administratif**: tetapkan referensi batas 38 provinsi dengan kode resmi dan audit geometri sebelum choropleth/join.
4. **Prioritas 4 — Privasi, lisensi/atribusi dan deployment**: cek izin redistribusi BKPM dan atribusi peta dasar sebelum GitHub Pages.
5. **Prioritas 5 — Produksi**: tambahkan snapshot timestamp/checksum, pengujian regresi browser, dan prosedur refresh yang tidak merusak snapshot terdahulu.

## Cara melanjutkan dengan aman

Dari worktree BKPM:

    cd ~/geo-experiments/bkpm-demnas
    git pull --ff-only
    source .venv/bin/activate
    python -m unittest discover -s bkpm/tests -v
    python -m bkpm.webgis_package

Jangan menjalankan ulang collector hanya untuk melihat peta; gunakan data yang sudah ada. Bacalah [RUNBOOK.md](RUNBOOK.md), [DATA_DICTIONARY.md](DATA_DICTIONARY.md), dan [peta repository](../docs/REPOSITORY_GUIDE.md).

## Larangan inferensi

- 180 titik terstruktur bukan 180 lokasi tapak terverifikasi.
- 185 record peluang bukan realisasi penanaman modal.
- 142 komoditas bertipe Point bukan luas poligon komoditas.
- Status pagination lengkap bukan bukti semua proyek yang pernah terbit di BKPM.
- Unit test lulus bukan bukti UI browser tampil tanpa masalah.

**Checkpoint ini tidak mengubah data produksi DEMNAS, BHUMI, Minerba atau Kuranji.**