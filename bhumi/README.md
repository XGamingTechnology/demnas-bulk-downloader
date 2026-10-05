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


## Bidang Tanah / Persil WMTS

ArcGIS Online item publik berikut mengidentifikasi service WMTS untuk layer
**Bidang Tanah - Bhumi AtrBpn**:

- Item ID: `11987ae333e5411ea95d5537a2b85296`
- Service: `https://bhumi.atrbpn.go.id/mprx/service`
- Layer: `bhumi_persil`
- TileMatrixSet: `localgrid_high`
- Style: `default`
- Format: `image/png`

Metadata item dapat diperiksa dengan:

```bash
python3 bhumi/resolve_arcgis_item.py --save-dir output/arcgis_bhumi_item
```

Pada pengujian dari VPS, baik `GetCapabilities` maupun `GetTile` ke service
`/mprx/service` mengembalikan **HTTP 403 dari nginx**. Artinya service diketahui
dan dapat direferensikan oleh client GIS, tetapi akses anonim server-to-server
dari host tersebut tidak diizinkan.

Downloader **tidak mencoba memalsukan origin, cookie, token, atau mekanisme lain
untuk melewati kontrol akses**. Untuk penggunaan visual, gunakan service tersebut
melalui client yang memang diberi akses, misalnya ArcGIS Pro / ArcGIS Online /
QGIS, atau gunakan akses resmi ATR/BPN.

Probe:

```bash
python3 bhumi/download_public_layer.py \
  --name "Bidang Tanah" \
  --probe
```

Jika endpoint diblokir, output akan menampilkan
`STATUS: SERVER_SIDE_BLOCKED` beserta konfigurasi client WMTS.


## Checkpoint Persil raster berhasil

Pengujian VPS pada 6 Oktober 2026 berhasil menghasilkan mosaic GeoTIFF
**Bidang Tanah / Persil** melalui WMS `GetMap` dari
`https://bhumi.atrbpn.go.id/mprx/service`.

Hasil terverifikasi:

- grid: `4 x 3`
- pixel per tile: `1600 x 1200`
- raster akhir: `6400 x 3600`
- CRS: `EPSG:3857` (WGS 84 / Pseudo-Mercator)
- output uji: `output/bhumi_persil_sumsel.tif`
- ukuran file uji: sekitar `2.5 MB`
- compression: `DEFLATE`
- valid pixel statistics pada pengujian: sekitar `41.59%`

BBOX pengujian:

```text
104.08144856688278,-3.508670771548452,104.43584512679433,-3.3288696787825245
```

Status akses Persil yang sudah diuji:

- WMS `GetMap`: **HTTP 200 / image/png**
- WMS `GetCapabilities`: **HTTP 403**
- WMS `GetFeatureInfo`: **HTTP 403** untuk request JSON yang diuji
- WMTS `GetCapabilities`: **HTTP 403**
- WMTS `GetTile`: **HTTP 403**

GeoTIFF ini adalah raster render dan bukan sumber vector/NIB.

Untuk diagnosis tambahan `GetFeatureInfo` secara aman, gunakan
`bhumi/test_persil_getfeatureinfo.sh`. Script hanya mencoba variasi WMS standar
dan pemeriksaan HTTP biasa. Script tidak mencoba bypass autentikasi, cookie/token,
path/encoding obfuscation, atau manipulasi access-control.


### Kesimpulan filtering operasi Persil

Dengan client header yang sama seperti downloader yang berhasil
(`User-Agent` + `Referer: https://bhumi.atrbpn.go.id/peta`), pengujian
menunjukkan:

- `HEAD /mprx/service`: HTTP 200
- `OPTIONS /mprx/service`: HTTP 200
- WMS 1.3.0 `GetMap`: HTTP 200
- WMS 1.1.1 `GetMap`: HTTP 200
- WMS 1.3.0 `GetFeatureInfo`: HTTP 403 untuk JSON, GeoJSON, text/plain,
  text/html, dan GML
- WMS 1.1.1 `GetFeatureInfo`: HTTP 403 untuk JSON, text/plain, dan text/html

Ini merupakan bukti kuat bahwa endpoint publik tersebut menerapkan filtering
berdasarkan operasi: render peta (`GetMap`) diizinkan, sedangkan query feature
(`GetFeatureInfo`) ditolak untuk akses anonim yang diuji.

Jangan mencoba melewati filtering tersebut dengan cookie/token yang bukan milik
sendiri, path/encoding obfuscation, origin spoofing, atau teknik bypass lainnya.
