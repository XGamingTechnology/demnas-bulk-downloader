# Downloader WIUP Minerba ESDM

Modul terpisah untuk mengambil polygon dan atribut **layer WIUP publik** dari Geoportal ESDM. Script DEMNAS pada root tetap dapat dipakai seperti sebelumnya. Python 3.10+.

## Instalasi

Jalankan dari root repositori:

```bash
python3 -m venv minerba/.venv
source minerba/.venv/bin/activate
python -m pip install -r minerba/requirements.txt
```

Windows: aktivasi dengan `minerba\.venv\Scripts\Activate.ps1`.

## Unduh

Semua fitur WIUP publik Indonesia:

```bash
python minerba/download_wiup.py --all --output minerba/output/indonesia
```

Sumatera Barat, seluruh komoditas:

```bash
python minerba/download_wiup.py --province "SUMATERA BARAT" --output minerba/output/sumbar
```

PT Lumpo (nama usaha sumber tanpa awalan PT):

```bash
python minerba/download_wiup.py --company LUMPO --wiup 3113013032014015 --output minerba/output/lumpo
```

Filter `--province`, `--company`, `--wiup`, `--commodity` memakai kesamaan persis, diubah ke huruf besar, dan dapat digabung. Jangan gabung filter dengan `--all`. Nama tidak diketahui: unduh provinsi dahulu, periksa CSV.

Hitung fitur dahulu tanpa membuat file:

```bash
python minerba/download_wiup.py --all --count-only
```

Lanjutkan koneksi terputus menggunakan filter dan folder yang sama:

```bash
python minerba/download_wiup.py --all --output minerba/output/indonesia --resume
```

Snapshot baru: gunakan folder baru. `--resume` melanjutkan snapshot ID lama; atribut yang sudah dicache tidak diambil ulang. Jika daftar ID layanan berubah, proses berhenti dan meminta snapshot baru. Jangan mengubah isi cache secara manual. `--batch-size 100` dan `--delay 0.5` adalah default; gunakan delay lebih besar bila server sibuk. Retry terbatas untuk gangguan sementara; penolakan akses dihentikan tanpa mencoba melewati autentikasi. URL layer dapat diganti melalui `--service` bila endpoint resmi berubah.

## Hasil dan pemeriksaan

- `wiup_shp.zip`: SHP, SHX, DBF, PRJ, CPG dan pemetaan nama field.
- `wiup.geojson`: polygon dan atribut nama asli, WGS84 / EPSG:4326.
- `wiup.csv`: atribut lengkap, UTF-8 dengan BOM.
- `wiup_raw.json`: fitur ArcGIS sumber dengan geometri WGS84 hasil query.
- `field_map.json`: nama asli untuk field DBF `F000`, `F001`, dst serta daftar teks terpotong.
- `manifest.json`: sumber, filter, daftar ID, waktu UTC dan status.
- `cache/`: batch untuk resume; jangan diunggah ke GitHub.

Daftar ID diambil sebagai snapshot. Setiap batch diperiksa terhadap ID yang diminta; respons terpotong dipecah, ID hilang/duplikat/tambahan menyebabkan kegagalan. Set ID diperiksa ulang sebelum ekspor. **Hasil sah sebagai unduhan lengkap hanya bila manifest berstatus `complete` dan proses keluar dengan kode 0.** Server tidak menyediakan transaksi snapshot: atribut dapat berubah selama unduhan walaupun set ID tetap sama. Resume yang selesai adalah pengecekan snapshot lokal, bukan pembaruan data.

Geometri sumber dipertahankan; polygon tidak valid atau kosong menghentikan ekspor, dan raw tetap disimpan untuk pemeriksaan. GeoJSON menentukan shell/hole dari hubungan ring, termasuk multipart. SHP mengikuti ring sumber. Semua kolom DBF berupa teks agar kode izin tidak berubah; batas 254 byte dan nama field pendek adalah keterbatasan SHP. Null menjadi teks kosong di DBF; nilai utuh dan null tetap di GeoJSON/raw/CSV (CSV null berupa sel kosong). Kolom tanggal sumber berupa epoch milidetik; tidak diganti diam-diam dengan tanggal lokal.

## Cakupan dan sumber

Sumber aplikasi: <https://geoportal.esdm.go.id/minerba/>. Endpoint default adalah proxy publik layer 0 `Pusat/WIUP_Publish/MapServer`. Uji akses 3 Oktober 2026 melaporkan **8.600 fitur** dan batas **100 fitur per respons**; jumlah dapat berubah. Tidak memerlukan HAR, cookie, token atau password pada saat diuji.

`--all` berarti seluruh fitur layer WIUP tersebut yang bisa diakses publik, bukan semua layer ESDM, semua riwayat izin, atau dokumen SK. Kehadiran polygon tidak membuktikan RKAB disetujui, izin bebas sengketa, atau pencabutan/pemulihan sudah final. Verifikasi legalitas melalui dokumen keputusan dan instansi berwenang. Ikuti ketentuan penggunaan/atribusi ESDM; repositori ini hanya client pengunduh dan tidak memberi lisensi baru atas data.

## Tes

```bash
python -m unittest discover -s minerba/tests -v
```

Tes mencakup batas transfer, ID hilang/duplikat, resume/cache rusak, perubahan ID, penghentian saat akses ditolak, polygon berlubang/multipart, dan batas byte UTF-8 DBF.
