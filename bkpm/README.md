# BKPM — panduan modul dan checkpoint eksperimen

**Status pada 9 November 2026:** 185 record peluang investasi diambil melalui 21 halaman endpoint publik, 180 titik proyek, lima record tanpa koordinat usable, serta 142 titik komoditas. Audit lokal tidak menemukan mismatch ID/geometri; 37 unit test lulus; paket WebGIS statis berhasil dibuat tetapi **belum diverifikasi secara visual di browser**. Ini adalah bukti historis dari VPS, bukan jaminan total data real-time.

## Baca yang mana?

| Dokumen | Untuk apa |
|---|---|
| [RUNBOOK.md](RUNBOOK.md) | **Mulai dari sini:** perintah VPS, install, API, QA, WebGIS preview, troubleshooting |
| [CHECKPOINT_2026-11-09.md](CHECKPOINT_2026-11-09.md) | Rekaman hasil pengujian, daftar output, keterbatasan, keputusan dan prioritas lanjutan |
| [DATA_DICTIONARY.md](DATA_DICTIONARY.md) | Makna atribut, sumber data, koordinat, kualitas, nilai yang kosong, larangan interpretasi |
| [INVESTMENT_README.md](INVESTMENT_README.md) | Tahap riset sebelumnya: inventaris metadata HTML BKPM/Satu Data, bukan pengunduhan massal CSV |
| [Panduan seluruh repository](../docs/REPOSITORY_GUIDE.md) | Posisi BKPM dibanding DEMNAS, BHUMI, Minerba dan penelitian DAS Kuranji |

## Jalur kerja utama yang **sudah teruji**

Dari worktree BKPM yang ada, jalankan:

~~~bash
cd ~/geo-experiments/bkpm-demnas
git pull --ff-only
source .venv/bin/activate
python -m unittest discover -s bkpm/tests -v

# Bila snapshot data/bkpm/spatial_api sudah ada, TIDAK perlu unduh ulang API:
python -m bkpm.spatial_quality
python -m bkpm.webgis_package
~~~

Untuk **snapshot baru** (mengambil data publik dari internet dengan jeda dan mengganti output default; cadangkan folder lebih dulu):

~~~bash
python -m bkpm.spatial_api_collect --max-pages 21 --delay 2
python -m bkpm.spatial_quality
python -m bkpm.webgis_package
~~~

Untuk preview, jalankan server HTTP localhost pada port **8876**, bukan port default proxy BHUMI 8765. Cara port-forward SSH lengkap ada di [RUNBOOK.md](RUNBOOK.md). Jangan publish output data ke GitHub Pages sebelum memastikan syarat penggunaan/redistribusi.

### Folder utama hasil

- data/bkpm/spatial_api/: JSON asli proyek, GeoJSON proyek/komoditas, audit pagination.
- data/bkpm/spatial_api/quality/: QA koordinat, ID dan kelengkapan atribut.
- data/bkpm/webgis_preview/: index.html, data GeoJSON dan laporan ringkas untuk viewer.
- Semua data/ diabaikan Git: git pull mengambil **kode**, bukan data.

### Batas ilmiah dan operasional

- Peluang proyek **bukan** realisasi investasi LKPM.
- Fitur titik yang lolos cek angka/rentang bukan berarti sudah tervalidasi sebagai tapak fisik.
- Lima proyek tanpa longitude tidak dibuatkan koordinat dugaan.
- Komoditas merupakan 142 geometri Point dengan CRS sumber OGC:CRS84; bukan bidang/poligon.
- Batas provinsi dari tiga GeoJSON wilayah lama mencakup 34 entitas; bukan pengganti otomatis batas administrasi terkini.
- Tidak ada bypass form disclaimer Satu Data, scraping privat, atau brute-force ID proyek.
- Jangan mereset/menghapus worktree/hasil DEMNAS/BHUMI utama ketika mengerjakan eksperimen BKPM.

---

## Arsip petunjuk tahap awal: audit GeoJSON wilayah dan DEMNAS

Bagian di bawah dipertahankan sebagai dokumentasi pekerjaan pendahulu. Untuk pipeline proyek investasi terbaru, utamakan [RUNBOOK.md](RUNBOOK.md).

Modul ini **tidak mengubah** downloader DEMNAS yang sudah ada. Versi awal hanya memeriksa tiga sumber GeoJSON **yang teramati di Network browser**, bukan melakukan pemindaian endpoint dan bukan menjanjikan endpoint investasi aktif.

## Endpoint publik yang diamati

- https://regionalinvestment.bkpm.go.id/data/wilayah_barat.geojson
- https://regionalinvestment.bkpm.go.id/data/wilayah_tengah.geojson
- https://regionalinvestment.bkpm.go.id/data/wilayah_timur.geojson

Temuan awal dari browser: Tengah 12 fitur MultiPolygon dan Timur 4 fitur MultiPolygon, dengan atribut NAME_0, NAME_1, KODE, Wilayah. Angka Barat belum diverifikasi. Ketiganya adalah data batas, **bukan** data nilai investasi.

## Persiapan

Dari root repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Audit GeoJSON

```bash
python -m bkpm.audit
```

Output default: `data/bkpm/`

- `wilayah_{barat,tengah,timur}.geojson`: berkas cache sumber (diunduh saat belum ada; tidak berubah otomatis)
- `bkpm_wilayah_merged.geojson`: gabungan batas provinsi, dengan `BKPM_SOURCE`
- `provinces.csv`: inventaris provinsi dan kode dari sumber
- `audit.json`: inventaris geometri, anomali, checksum SHA256, dan jumlah fitur

Gunakan `--refresh` untuk unduh ulang, `--offline` untuk hanya memakai cache yang sudah ada, atau `--output /lokasi/lain` untuk mengganti direktori output.

**Penting:** hasil validasi format tidak menjamin batas provinsi sesuai administrasi terbaru, dan tidak menggantikan rujukan resmi BIG/Kemendagri. Kode `KODE` harus diaudit sebelum dipakai join statistik.

## Eksperimen DEMNAS lokal

Bila sudah memiliki berkas GeoTIFF DEMNAS:

```bash
python -m bkpm.audit --offline --dem data/output/DEMNAS_JAWA_TIMUR.tif
```

Output tambahan `terrain_sample_approx.csv` berisi nilai minimum, rata-rata, dan maksimum elevasi **perkiraan** dari sampel raster yang diturunkan resolusinya. Area di luar cakupan DEM akan dilabeli `outside_dem`. Ini bukan zonal statistics resolusi asli, **tidak** menghasilkan skor kelayakan investasi, dan tidak mengestimasi risiko longsor/banjir. Jangan menafsirkan hasil numeriknya sebagai nilai presisi untuk keseluruhan provinsi.

Pastikan sistem koordinat dan datum vertikal DEM sesuai kebutuhan analisis. Untuk hasil kuantitatif perlu pengolahan pada resolusi yang tepat, verifikasi NoData, cakupan, datum, dan pemeriksaan silang dengan data sektoral.

## Integrasi selanjutnya

1. Cocokkan daftar seluruh provinsi dan evaluasi versi batas administrasi.
2. Catat URL JSON/GeoJSON **yang benar-benar teramati** saat pengguna menekan layer/filter BKPM pada browser.
3. Inventaris field, tipe geometri, lisensi dan izin penggunaan dataset investasi.
4. Untuk proyek yang memiliki geometri sah, lakukan spatial join dengan batas dan DEMNAS; jangan mengarang lokasi proyek dari nama daerah.
5. Jika perlu, hasilkan paket peta visual dan GeoPackage secara terpisah.

Tidak ada token MapTiler atau kredensial yang disimpan dalam repository.

## Pengujian offline

```bash
python -m unittest discover -s bkpm/tests -v
```
