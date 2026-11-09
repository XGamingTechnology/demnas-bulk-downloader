# Integrasi BKPM Geoportal × DEMNAS (eksperimen)

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
