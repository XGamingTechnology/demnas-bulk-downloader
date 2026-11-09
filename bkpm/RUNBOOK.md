# BKPM — Runbook pengumpulan, audit, dan pratinjau WebGIS

Dokumen ini untuk **branch eksperimen** feature/bkpm-demnas-geoportal. Semua perintah dijalankan dari root checkout pada VPS, bukan checkout DEMNAS produksi. Source data publik: https://regionalinvestment.bkpm.go.id/ dan https://data.bkpm.go.id/ . Simpan snapshot dan audit di data/bkpm/ (diabaikan Git).

## A. Mulai/lanjut pada worktree VPS yang sudah ada

    cd ~/geo-experiments/bkpm-demnas
    git status --short
    git branch --show-current
    git pull --ff-only
    source .venv/bin/activate
    python -m unittest discover -s bkpm/tests -v

Pada VPS checkpoint 9 Nov 2026 tes terakhir **37/37 lulus**. Jangan menganggap jumlah tes selalu 37 setelah perubahan kode. Tidak perlu membuat worktree baru, menghapus data, menjalankan sudo atau mereset branch.

Bagi instalasi baru saja: buat Python venv, install requirements.txt ditambah **beautifulsoup4**; untuk pengambilan detail dengan Chromium install playwright dan Chromium beserta system library Playwright sesuai OS. Modul api/QA/WebGIS tidak perlu Chromium. Versi Ubuntu VPS yang berhasil memakai libasound2t64. Jangan pasang seluruh paket browser bila hanya ingin menjalankan API/QA/WebGIS.

## B. Alur utama yang sudah terbukti: API → QC → WebGIS

**1. Pengumpulan peluang + komoditas.** Unduh ulang hanya bila ingin snapshot terbaru dan telah memeriksa aturan penggunaan layanan.

    python -m bkpm.spatial_api_collect --max-pages 21 --delay 2

Endpoint yang teramati: https://regionalinvestment.bkpm.go.id/be/peluang/peluang_investasi_wilayah (pagination ?page=N yang dicek pada respons), dan https://regionalinvestment.bkpm.go.id/data/komoditas.geojson . Program tidak memakai ID yang ditebak. Hard cap max-pages 30; jangan meningkatkan batas tanpa kebutuhan. Hindari job paralel atau loop polling.

Output default di data/bkpm/spatial_api/:

- region_records.json: atribut asli 185 record dalam snapshot 9 Nov, metadata per halaman;
- bkpm_opportunities_api_points.geojson: hanya fitur proyek yang koordinatnya lulus cek rentang;
- bkpm_komoditas_original.geojson: GeoJSON komoditas apa adanya;
- audit.json: meta halaman, total sumber, checksum respons, jumlah fitur/penolakan.

**Hati-hati:** eksekusi collector menimpa file di output yang sama. Sebelum pengunduhan ulang, salin folder atau pakai --output berbeda. Jika server gagal di tengah pengambilan, audit bisa berstatus incomplete; jangan publikasikan sebagai snapshot lengkap.

**2. Audit offline.** Tidak mengirim request Internet.

    python -m bkpm.spatial_quality
    cat data/bkpm/spatial_api/quality/quality_summary.json

Output quality/: projects_without_coordinates.csv, shared_coordinates.csv, attribute_presence.csv, quality_summary.json. Cek rekonsiliasi ID, geometri, dan kelengkapan; hindari geocoding lokasi hilang tanpa bukti.

**3. Buat paket WebGIS statis offline dari snapshot lokal.**

    python -m bkpm.webgis_package

Output default data/bkpm/webgis_preview/: index.html dan data/ (GeoJSON proyek, komoditas, metadata snapshot, data nonspasial tanpa koordinat, koordinat bersama, ringkasan atribut). Packager menolak sumber yang tidak lengkap atau tidak konsisten. UI Leaflet menggunakan CDN dan OSM tiles saat dibuka browser, sehingga tampilan penuh butuh Internet.

**4. Preview lokal tanpa membuka port publik.** Pakai port **8876** untuk menghindari default proxy BHUMI localhost:8765.

    cd data/bkpm/webgis_preview
    python -m http.server 8876 --bind 127.0.0.1

Pada **terminal komputer lokal yang berbeda** (bukan dalam VPS), buat tunnel SSH (ganti alamat dengan host VPS Anda):

    ssh -N -L 8876:127.0.0.1:8876 ubuntu@HOST_VPS

Buka http://localhost:8876/ di komputer lokal. Jika port sudah terpakai pilih port lain dengan menggantinya pada kedua perintah. Jangan menjadikan server sederhana ini sebagai server publik permanen.

**5. Smoke test browser MANUAL** (belum terverifikasi pada checkpoint): dashboard menampilkan 185 record, 180 proyek, 142 komoditas, 5 hilang koordinat; peta OpenStreetMap tampil, tombol layer berfungsi, filter/pencarian bekerja, popup berisi nama dan ID yang sesuai API, proyek berbagi titik tidak hilang, dan tidak ada error di browser Console. Foto/screenshot hasil tes bila diperlukan untuk dokumentasi lanjutan. Angka hanya cocok untuk snapshot 9 Nov; jika dataset baru berubah ikuti audit terbaru.

## C. Modul tambahan, tidak harus dipakai pada alur utama

| Modul / perintah | Kegunaan | Status dan kapan dipakai |
|---|---|---|
| python -m bkpm.audit | Ambil/audit wilayah_{barat,tengah,timur}.geojson, gabung batas provinsi | 34 provinsi historis; **bukan** batas 38 provinsi terbaru; lihat catatan di README |
| python -m bkpm.public_api_probe | Inventaris struktur JSON endpoint cards, wilayah, sektor, komoditas | Diagnostik struktur, tidak menghasilkan GeoJSON proyek |
| python -m bkpm.project_discovery | Penemuan link DOM menggunakan Chromium | Eksperimen: pada VPS tidak menghasilkan URL baru; API wilayah lebih berhasil |
| python -m bkpm.spatial_opportunities --render-browser | 5 URL detail proyek yang memang diamati | Berhasil 5/5, dengan parser nama berbasis breadcrumb; **sampel**, bukan populasi penuh |
| python -m bkpm.investment_inventory | Audit halaman katalog BKPM dan Satu Data | Inventaris metadata, bukan download massal isi CSV |
| bkpm/resource_extract.py, bkpm/download_manifest.py | Inspeksi tautan file / metadata unduh publik | Form disclaimer tetap harus dihormati; jangan berasumsi file CSV berhasil didownload |
| bkpm/browser_render.py, bkpm/project_title.py | Helper internal render HTML dan pembacaan judul | Dipakai alur detail; tidak perlu dijalankan sendiri |

Perintah audit wilayah dan inventaris metadata lebih detail dijelaskan di [panduan awal](INVESTMENT_README.md) dan [panduan batas provinsi](README.md) sebelum versi terbaru. Dokumentasi baru tidak menghapus hasil tahapan sebelumnya.

## D. Status kualitas / ketelitian interpretasi

- **185** record adalah total yang **dilaporkan API pada 9 Nov 2026**, bukan total semua proyek BKPM sepanjang waktu.
- **180** proyek memiliki titik lolos validasi sintaks dan bounding box Indonesia; bukan jaminan tapak/site surveyed.
- **5** proyek tidak memiliki lon yang dapat dipakai: tidak ditampilkan sebagai titik buatan.
- **2 kelompok** koordinat bersama perlu dikaji manual sebelum analisis kepadatan lokasi.
- **142** fitur komoditas bertipe Point, CRS sumber OGC:CRS84 (lon/lat, WGS84).
- **status_proyek** terisi 111/185 menurut audit; nilai kosong tidak boleh dianggap status proyek tertentu.
- Angka rupiah peluang investasi tidak boleh digabung dengan realisasi LKPM PMA/PMDN.
- Browser viewer & publikasi GitHub Pages **belum lolos verifikasi saat checkpoint**.

## E. GitHub Pages dan redistribusi

Branch saat ini hanya menyimpan **kode dan dokumentasi**, karena data/ berada dalam .gitignore. Jangan menyalin data/bkpm/webgis_preview ke repo publik sebelum memeriksa hak penggunaan/redistribusi dataset BKPM, atribusi sumber dan informasi yang bisa ditampilkan. Untuk deployment setelah izin jelas, gunakan branch/folder publikasi khusus dan lakukan QA browser terlebih dahulu.

## F. Troubleshooting

- ImportError bs4: python -m pip install beautifulsoup4
- BrowserType.launch libasound.so.2 hilang (Ubuntu 24.04): instal paket libasound2t64 sesuai repo OS dan ulang smoke test Chromium; hanya relevan untuk modul Playwright.
- HTTP 401/403/429: hentikan request, jangan bypass.
- 0 URL pada project_discovery: bukan bukti 0 proyek; gunakan spatial_api_collect yang membaca endpoint JSON teramati.
- Paket WebGIS gagal: cek status pagination harus all_reported_pages_reached dan jumlah record = metadata sumber; lihat audit.json.
- Browser putih / gagal fetch: jalankan melalui python -m http.server, bukan file://; periksa jaringan untuk Leaflet/OSM dan browser Console.
- README perubahan tidak terlihat di VPS: dari worktree BKPM gunakan git pull --ff-only, lalu git status --short.

Lanjutkan pekerjaan dari [checkpoint bertanggal](CHECKPOINT_2026-11-09.md).