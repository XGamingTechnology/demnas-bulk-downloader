# DEMNAS Bulk Downloader

Downloader Python untuk mengambil **DEMNAS resmi Badan Informasi Geospasial (BIG)** per provinsi melalui ArcGIS ImageServer, lalu menyusun tile menjadi satu GeoTIFF yang di-mask menggunakan batas provinsi resmi BIG.

Default: **Jawa Timur**.

## Sumber resmi

- DEMNAS ImageServer:
  `https://geoservices.big.go.id/raster/rest/services/DEMNAS/DEM_Indonesia/ImageServer`
- Batas Administrasi Provinsi BIG:
  `https://geoservices.big.go.id/gis/rest/services/STIG/Batas_Provinsi/MapServer/0`

Script ini tidak melakukan browser scraping dan tidak membutuhkan password Image Portal.

## Fitur

- Mengambil batas provinsi langsung dari BIG.
- Native DEMNAS resolution dari ImageServer.
- Memecah provinsi menjadi tile karena batas ukuran export server.
- Hanya mengunduh tile yang berpotongan dengan polygon provinsi.
- Resume otomatis: tile valid yang sudah selesai tidak di-download ulang.
- Retry otomatis jika request sementara gagal.
- Output float32 GeoTIFF, EPSG:4326.
- Mask otomatis di luar batas provinsi.
- DEFLATE compression + BigTIFF.
- Overview untuk tampilan lebih ringan di QGIS/ArcGIS.
- Menyimpan batas provinsi sebagai GeoJSON.

## 1. Install Python

Disarankan Python 3.11 atau 3.12.

Cek:

```bash
python3 --version
```

## 2. Buat virtual environment

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Windows PowerShell

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Download Jawa Timur

```bash
python download_demnas.py --province "Jawa Timur"
```

Script akan menampilkan estimasi ukuran dan meminta konfirmasi.

Tanpa konfirmasi:

```bash
python download_demnas.py --province "Jawa Timur" --yes
```

## 4. Hasil

```text
data/
├── output/
│   ├── DEMNAS_JAWA_TIMUR.tif
│   └── BATAS_JAWA_TIMUR_BIG.geojson
└── tiles/
```

Secara default tile sementara dihapus **setelah hasil final berhasil dibuat**.

Kalau ingin menyimpan semua tile:

```bash
python download_demnas.py --province "Jawa Timur" --keep-tiles
```

## Resume setelah koneksi putus

Jalankan perintah yang sama lagi:

```bash
python download_demnas.py --province "Jawa Timur"
```

Tile yang sudah valid akan di-skip.

## Provinsi lain

```bash
python download_demnas.py --province "Bali"
python download_demnas.py --province "Jawa Tengah"
python download_demnas.py --province "Nusa Tenggara Barat"
```

Nama provinsi harus cocok dengan atribut `WADMPR` pada service batas provinsi BIG.

## Catatan ukuran

DEMNAS native resolution sangat detail. Satu provinsi besar seperti Jawa Timur dapat menghasilkan beberapa GB data, tergantung extent, kompresi, jumlah pulau, dan nilai NoData.

Pastikan ruang disk cukup. Untuk Jawa Timur, aman menyediakan **belasan GB ruang kosong** selama proses karena tile sementara dan output final dapat hidup bersamaan sebelum cleanup.

## Jika hanya ingin test kecil

Untuk memastikan environment Python/rasterio berhasil, jalankan:

```bash
python check_environment.py
```

Ini tidak mengunduh DEMNAS.

## Lisensi dan penggunaan data

Repo ini hanya downloader/client. Data DEMNAS dan batas administrasi tetap merupakan data milik/layanan Badan Informasi Geospasial (BIG). Ikuti ketentuan penggunaan dan atribusi BIG untuk pemanfaatan datanya.
