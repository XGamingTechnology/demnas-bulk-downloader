# Downloader Minerba ESDM

Mengunduh geometri dan atribut katalog publik Geoportal Minerba menjadi SHP ZIP, GeoJSON dan CSV. Mendukung polygon, titik dan garis. Modul DEMNAS pada root tetap dapat digunakan. Python 3.10+.

## Ambil branch dan instalasi

Untuk folder baru:

```bash
git clone --branch feature/minerba-wiup-downloader --single-branch https://github.com/XGamingTechnology/demnas-bulk-downloader.git minerba-downloader
cd minerba-downloader
python3 -m venv minerba/.venv
source minerba/.venv/bin/activate
python -m pip install -r minerba/requirements.txt
```

Jika branch ini sudah terpasang, gunakan `git pull --ff-only` sebelum menjalankan. Windows: aktivasi dengan `minerba\.venv\Scripts\Activate.ps1`.

## Seluruh WIUP/izin yang tersedia publik

```bash
python minerba/download_minerba.py --dataset wiup --all --output minerba/output/izin-indonesia
```

Layer WIUP dapat memuat beberapa jenis izin. Untuk memilih atribut `jenis_izin` persis IUP saja:

```bash
python minerba/download_minerba.py --dataset wiup --permit-type IUP --output minerba/output/iup-indonesia
```

Filter dapat digabung:

```bash
python minerba/download_minerba.py --dataset wiup --province "SUMATERA BARAT" --output minerba/output/sumbar
python minerba/download_minerba.py --dataset wiup --company LUMPO --wiup 3113013032014015 --output minerba/output/lumpo
```

Nama perusahaan sumber adalah `LUMPO`, tanpa awalan PT. Filter menggunakan kesamaan persis tanpa membedakan kapitalisasi. `--all` berarti seluruh fitur dan tidak digabung dengan filter.

## Semua dataset katalog dalam satu perintah

```bash
python minerba/download_minerba.py --dataset all --all --output minerba/output/indonesia
```

`--dataset all` memilih 11 layer dalam katalog; `--all` memilih seluruh fitur pada masing-masing layer. Ini bukan semua layanan/arsip ESDM.

| Pilihan dataset | Bentuk | Filter atribut |
|---|---|---|
| `wiup` | Polygon | province, company, wiup, commodity, permit-type |
| `wp2025` | Polygon | province, commodity |
| `batubara` | Titik | Seluruh fitur |
| `mineral-logam` | Titik | commodity |
| `mineral-nonlogam` | Titik | commodity |
| `batas-laut` | Garis, pilihan grup 6 layer | Seluruh fitur |

Enam pilihan individual batas laut: `laut-landas-kontinen`, `laut-mou-perikanan`, `laut-teritorial`, `laut-zee`, `laut-garis-pangkal`, `laut-zona-tambahan`.

Unduh pilihan tertentu, atau lihat daftar lengkap:

```bash
python minerba/download_minerba.py --dataset wiup --dataset batubara --all --output minerba/output/izin-dan-batubara
python minerba/download_minerba.py --dataset batas-laut --all --output minerba/output/laut
python minerba/download_minerba.py --list-datasets
```

Filter provinsi tidak tersedia pada layer potensi titik/batas laut karena schema tersebut tidak memiliki kolom provinsi yang terverifikasi. Script menolak kombinasi filter yang tidak didukung sebelum mulai. Penyaringan geografis dapat dilakukan di QGIS sesudah unduhan. Arti kode kolom dan satuan angka sumber daya/cadangan harus dicek terhadap metadata sumber sebelum digunakan dalam analisis.

## Hitung dan lanjutkan unduhan

Cek jumlah fitur tanpa membuat file:

```bash
python minerba/download_minerba.py --dataset all --all --count-only
```

Jika koneksi putus, gunakan pilihan dataset, filter dan folder yang sama:

```bash
python minerba/download_minerba.py --dataset all --all --output minerba/output/indonesia --resume
```

Resume melanjutkan snapshot ID lokal. Cache batch diperiksa berdasarkan ID dan cache rusak diambil ulang. Atribut cache yang valid tidak diperbarui. Jika daftar ID server berubah, proses dataset dihentikan; gunakan folder baru untuk snapshot terbaru. Jangan menjalankan dua proses terhadap folder output yang sama.

Default `--batch-size 100`, dibatasi lagi oleh maksimum layanan, dan `--delay 0.5` detik antar-request. Tambahkan delay jika server sibuk. Retry terbatas untuk gangguan sementara; penolakan akses dihentikan tanpa melewati autentikasi. Dataset lain tetap diproses jika satu gagal, dengan kode keluar 1 dan status keseluruhan `incomplete`.

## Hasil dan kelengkapan

Setiap dataset disimpan dalam subfolder sendiri, misalnya `indonesia/wiup/` dan `indonesia/batubara/`:

- `<dataset>_shp.zip`: SHP, SHX, DBF, PRJ, CPG dan pemetaan field.
- `<dataset>.geojson`: geometri dan atribut asli, WGS84 / EPSG:4326.
- `<dataset>.csv`: atribut, UTF-8 dengan BOM.
- `<dataset>_raw.json`: fitur ArcGIS sumber dari query WGS84.
- `field_map.json`: pemetaan field DBF pendek `F000`, `F001`, dst ke nama asli dan daftar teks terpotong.
- `manifest.json`: sumber, filter, ID snapshot, waktu UTC dan status dataset.
- `geometry_quality.json`: fitur dengan topologi polygon bermasalah atau geometri kosong, juga disertakan dalam ZIP SHP.
- `cache/`: batch resume. Jangan unggah output/cache ke GitHub.

`index.json` di folder utama mencatat status dan jumlah setiap dataset. **Semua dataset pilihan selesai hanya jika index berstatus `complete`, manifest masing-masing dataset `complete`, dan proses keluar dengan kode 0.** Hasil sebagian tidak diberi status lengkap.

Daftar ID diambil sebelum unduhan. Setiap batch diperiksa terhadap ID yang diminta; respons terpotong dipecah, ID hilang/duplikat/tambahan menyebabkan kegagalan. Set ID dicek ulang sebelum ekspor. Server tidak menyediakan transaksi snapshot: atribut dapat berubah selama pengambilan meskipun ID tetap sama.

Polygon dengan topologi tidak valid tetap disimpan dengan ring sumber di SHP/raw, tanpa perbaikan otomatis. GeoJSON memakai aturan ring SHP sebagai fallback jika klasifikasi polygon ketat gagal. Geometri kosong menjadi null shape/null GeoJSON, dengan atribut tetap disimpan. Masalah dicatat dalam `geometry_quality.json` dan jumlahnya di manifest/index. Status `complete` berarti seluruh fitur snapshot terambil, bukan jaminan semua geometri valid untuk analisis. Ring yang tidak tertutup, koordinat tidak valid atau format geometri tidak didukung tetap menyebabkan kegagalan dataset, tanpa membuang fitur diam-diam.

SHP mengikuti ring/garis/titik sumber. DBF memakai teks untuk mempertahankan kode izin; batas 254 byte dan nama field pendek merupakan keterbatasan SHP. Null menjadi string kosong dan spasi akhir dapat dihilangkan di DBF; nilai lengkap tetap di raw/GeoJSON. CSV null berupa sel kosong. Tanggal sumber tetap epoch milidetik.

## Kompatibilitas perintah lama

Perintah sebelumnya tetap didukung, dengan nama file output `wiup.*` langsung dalam folder pilihan:

```bash
python minerba/download_wiup.py --all --output minerba/output/wiup-lama
python minerba/download_wiup.py --all --output minerba/output/wiup-lama --resume
```

Jangan memakai folder yang sama untuk launcher lama dan launcher katalog: struktur output keduanya berbeda. Launcher lama juga mendukung `--service` untuk URL layer ArcGIS publik yang berubah.

## Sumber dan cakupan

Sumber: <https://geoportal.esdm.go.id/minerba/>. Katalog mengikuti layer yang tercantum di webmap aplikasi, dengan URL yang disimpan dalam `download_minerba.py`. Pada 3 Oktober 2026 query publik melaporkan: WIUP 8.600; WP 2025 2.958; potensi batubara 1.174; mineral logam 3.214; mineral bukan logam/batuan 6.738. Jumlah dan akses dapat berubah. Layanan diuji tanpa HAR, cookie, token atau password.

Katalog ini tidak mencakup semua riwayat izin, dokumen SK atau data internal ESDM. Kehadiran polygon tidak membuktikan RKAB disetujui atau keputusan pencabutan/pemulihan final. Titik potensi bukan batas cadangan perusahaan. Ikuti ketentuan penggunaan/atribusi ESDM; repositori ini hanya client pengunduh dan tidak memberi lisensi baru atas data.

## Tes

```bash
python -m unittest discover -s minerba/tests -v
```

Tes memeriksa respons terpotong, ID hilang/duplikat, resume/cache rusak, perubahan ID, akses ditolak, polygon berlubang/multipart, preservasi polygon invalid dan null shape, ekspor titik/garis/kosong, byte UTF-8, validasi filter dan pelaporan kegagalan sebagian.
