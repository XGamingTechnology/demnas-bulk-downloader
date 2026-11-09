# Peta repository dan panduan memilih modul

**Repository:** [XGamingTechnology/demnas-bulk-downloader](https://github.com/XGamingTechnology/demnas-bulk-downloader)  
**Cakupan:** inspeksi branch eksperimen BKPM, 9 November 2026.  
**Penting:** keberadaan kode bukan bukti bahwa semua dataset atau workflow berhasil dijalankan.

Repository ini berisi beberapa **workflow geospasial berbeda**, bukan satu pipeline otomatis. Pilih satu modul sesuai kebutuhan.

## Indeks modul

| Area | Dokumentasi / kode utama | Tujuan | Catatan status |
|---|---|---|---|
| DEMNAS BIG | [README utama](../README.md), download_demnas.py | Unduh dan mosaik DEMNAS per provinsi | Instruksi/resume ada di README utama; tidak diaudit ulang di checkpoint BKPM |
| BHUMI | [bhumi/README.md](../bhumi/README.md), bhumi/download_wms.py | Akses dan unduh peta WMS melalui proxy | WMS adalah render peta, bukan data vektor mentah; proxy default localhost:8765 |
| Minerba ESDM | [minerba/README.md](../minerba/README.md), minerba/download_minerba.py | Inventaris WIUP/WP/potensi/laut, filter, resume | Manifest dan syarat kelengkapan terpisah; tidak diuji ulang di checkpoint BKPM |
| DAS Kuranji | [roadmap](KURANJI_ROADMAP_DELIVERABLE_LAPORAN.md), [baseline](KURANJI_LAPORAN_TAHAP_1_BASELINE_HIDROLOGI.md) | Penelitian hidrologi, GFI, validasi, citra dan peta | Banyak script kandidat/tahap; baca keputusan freeze sebelum menganggap output final |
| BKPM | [panduan](../bkpm/README.md), [runbook](../bkpm/RUNBOOK.md), [checkpoint](../bkpm/CHECKPOINT_2026-11-09.md) | Peluang investasi, titik proyek/komoditas, QA, WebGIS | Snapshot VPS 9 Nov: 185 record, 180 titik, 142 komoditas, 37 tes lulus, paket WebGIS dibuat; browser belum diperiksa |

## Struktur kerja

- **Root repo**: DEMNAS downloader, check_environment.py, download_hydro.py, serta skrip-skrip analisis Kuranji.
- **bhumi/**: downloader WMS; petunjuk proxy dan GetCapabilities dalam README-nya.
- **minerba/**: pengunduh katalog data Minerba; gunakan requirements dan test-nya sendiri.
- **bkpm/**: collector, audit spasial, dan viewer WebGIS; mulai dari README BKPM.
- **docs/**: laporan tahapan, keputusan dan metodologi DAS Kuranji.
- **artifacts/kuranji/**: artefak penelitian yang memang telah tercatat dalam Git.
- **data/**: output kerja lokal, diabaikan oleh .gitignore global; tidak ikut terkirim melalui git pull/push.

Jangan menyamakan: DEMNAS (raster elevasi), WMS BHUMI (peta render), Minerba (izin/potensi), BKPM peluang (titik proyek), dan realisasi investasi LKPM (statistik). Perlu validasi CRS, kualitas lokasi, periode, skala, metadata dan lisensi sebelum overlay antar-data.

## Workflow aman

1. Pilih **satu modul** dan baca petunjuk modul tersebut.
2. Gunakan branch/worktree terpisah. BKPM diuji pada VPS di /home/ubuntu/geo-experiments/bkpm-demnas, remote branch feature/bkpm-demnas-geoportal. Jangan reset worktree DEMNAS/BHUMI yang ada.
3. Jalankan pengujian sebelum beralih ke produksi. BKPM: python -m unittest discover -s bkpm/tests -v. Minerba: python -m unittest discover -s minerba/tests -v.
4. Simpan bukti audit dan waktu pemeriksaan. Jumlah data publik bisa berubah.
5. Cek git status --short sebelum melakukan commit. Jangan menghapus data hanya demi kebersihan status.
6. Kode berhasil di-commit **tidak** berarti paket hasil terpublikasi. Snapshot data tetap berada pada VPS kecuali dipindahkan secara eksplisit.
7. Gunakan endpoint publik yang telah teramati; hormati aturan akses dan rate limit. Jangan menyimpan token, cookie, HAR sensitif atau kredensial ke repository.

## Navigasi cepat

- [BKPM — operasi lengkap](../bkpm/RUNBOOK.md)
- [BKPM — checkpoint eksperimen](../bkpm/CHECKPOINT_2026-11-09.md)
- [BKPM — kamus data dan QA](../bkpm/DATA_DICTIONARY.md)
- [BHUMI](../bhumi/README.md)
- [Minerba](../minerba/README.md)
- [Kuranji — roadmap](KURANJI_ROADMAP_DELIVERABLE_LAPORAN.md)

**Catatan:** checkpoint bertanggal adalah *rekaman hasil saat itu*, bukan jaminan data resmi tidak berubah.