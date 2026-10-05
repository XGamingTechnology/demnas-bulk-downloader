# BHUMI WMS Downloader

Modul ini menambahkan dukungan untuk membaca dan mengunduh layer dari endpoint
OGC WMS BHUMI/proxy lokal tanpa mengganggu downloader DEMNAS atau Minerba.

Default endpoint:

```
http://127.0.0.1:8765/bhumi/wms
```

## 1. Cek GetCapabilities dan daftar layer

```bash
python bhumi/download_wms.py --capabilities --list-layers
```

Jika proxy berjalan di host/port berbeda:

```bash
python bhumi/download_wms.py \
  --url "http://127.0.0.1:8765/bhumi/wms" \
  --capabilities \
  --list-layers
```

File capabilities akan disimpan sebagai:

```
bhumi_wms_capabilities.xml
```

## 2. Download satu area

Setelah mendapatkan nama layer:

```bash
python bhumi/download_wms.py \
  --layer "NAMA_LAYER" \
  --bbox 106.5,-6.5,107.0,-6.0 \
  --crs EPSG:4326 \
  --output output/bhumi_area.tif
```

## 3. Bulk/tiled download

Untuk area lebih besar, pecah request menjadi beberapa bagian agar server tidak
menerima satu permintaan raster sangat besar:

```bash
python bhumi/download_wms.py \
  --layer "NAMA_LAYER" \
  --bbox 95,-11,141,6 \
  --crs EPSG:4326 \
  --cols 20 \
  --rows 10 \
  --width 2048 \
  --height 2048 \
  --delay 1 \
  --output output/bhumi_mosaic.tif
```

Script akan:

1. membagi BBOX menjadi grid;
2. melakukan `GetMap` untuk tiap tile;
3. mengubah response image menjadi GeoTIFF bergeoreferensi;
4. menggabungkan tile menjadi satu mosaic GeoTIFF;
5. retry otomatis jika request sementara gagal.

## Catatan WMS

WMS pada dasarnya adalah layanan render peta. Hasil yang diunduh merepresentasikan
layer yang dirender oleh server, bukan otomatis feature/vector mentah.

Jika dari audit network/HAR ditemukan WFS, ArcGIS REST, vector tile, atau endpoint
feature lain, sebaiknya dibuat adapter tambahan karena format tersebut dapat
memberikan data geometri/atribut yang lebih kaya dibanding WMS.

Default script memakai WMS 1.1.1 agar urutan sumbu EPSG:4326 tetap
`longitude,latitude`. Gunakan `--version 1.3.0` hanya jika endpoint memang
membutuhkannya dan axis order-nya sudah diverifikasi.

Gunakan hanya layer dan data yang memang diizinkan untuk diakses/diunduh oleh
layanan terkait.


## Audit HAR BHUMI

BHUMI versi baru tidak selalu mengekspos satu URL WMS yang bisa diasumsikan
stabil. Untuk menemukan endpoint yang benar dari browser, gunakan HAR analyzer:

```bash
python3 bhumi/analyze_har.py /path/to/bhumi.har --details
```

Capture HAR yang berguna harus dilakukan dengan Network filter **All**:

1. buka DevTools → Network;
2. aktifkan **Persist Logs** bila tersedia;
3. reload halaman `https://bhumi.atrbpn.go.id/peta`;
4. aktifkan layer yang ingin diambil (mis. Bidang Tanah);
5. klik satu objek sampai panel informasinya muncul;
6. Save All As HAR.

Analyzer mencari WMS/WFS/GeoServer/ArcGIS/vector-tile serta endpoint BHUMI seperti
`expapi`, `getPersil`, `rating_layer`, `persil`, dan `bidang`.

**Jangan commit HAR mentah.** HAR sering memuat cookie, session token, header
authorization, dan data privat. File HAR harus tetap lokal dan masuk
`.gitignore`.
