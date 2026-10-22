# Project Track Record & Continuation Guide

> **Repository:** `XGamingTechnology/demnas-bulk-downloader`  
> **Active development branch:** `feature/bhumi-wms-downloader`  
> **Last consolidated:** 2026-10-22  
> **Purpose:** one place to understand what this repository contains, what has
> already been verified, what is still pending, and exactly how to continue.

---

## 1. Start Here When Continuing Work

On the VPS:

```bash
cd /opt/demnas-bulk-downloader
git checkout feature/bhumi-wms-downloader
git pull origin feature/bhumi-wms-downloader

source .venv/bin/activate
```

If the virtual environment does not exist:

```bash
cd /opt/demnas-bulk-downloader
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Environment check:

```bash
python -c "import requests, rasterio, shapely, pyproj; print('ENV_OK', rasterio.__version__)"
```

Important: run project commands while `.venv` is active.

---

# 2. What This Repository Currently Does

This repository began as a DEMNAS bulk downloader and now contains several
independent public geospatial data adapters.

| Module | Purpose | Current state |
|---|---|---|
| `download_demnas.py` | BIG DEMNAS province downloader | Existing/stable |
| `minerba/` | Public ESDM Minerba/WIUP downloader | Separate workflow |
| `bhumi/` | BHUMI ATR/BPN public catalog/service downloader | Active development |
| `bathymetry/` | BIG BATNAS and detailed bathymetry downloader | Active development |

Do not mix Minerba-specific work with BHUMI-specific work. The current branch is
focused on BHUMI + bathymetry integration.

---

# 3. BHUMI ATR/BPN — Current Status

## 3.1 Public catalog

Catalog endpoint:

```text
https://bhumi.atrbpn.go.id/panel/items/layers
```

The latest verified dry-run found:

```text
36 published catalog layers
```

Main tools:

```text
bhumi/catalog_layers.py
bhumi/plan_catalog_downloads.py
bhumi/download_public_layer.py
bhumi/download_catalog_bulk.py
```

Inspect catalog:

```bash
python bhumi/plan_catalog_downloads.py \
  --json output/bhumi_catalog_plan.json \
  --csv output/bhumi_catalog_plan.csv
```

---

## 3.2 Verified BHUMI category inventory

The catalog has included these strategy groups:

- `bhumi-persil-wms`
- `xyz`
- `bhumi-wrapper`
- `arcgis`
- `ogc`
- `wms`
- `3d-tiles`
- `terrain`

The dry-run successfully classified all 36 catalog entries.

---

# 4. CHECKPOINT — Bidang Tanah / Persil

## Status: VERIFIED RASTER DOWNLOAD

Catalog layer:

```text
Name          : Bidang Tanah
Catalog layer : umum:Persil
Public render : https://bhumi.atrbpn.go.id/mprx/service
WMS layer     : bhumi_persil
```

### What works

- WMS 1.3.0 `GetMap`: HTTP 200
- WMS 1.1.1 `GetMap`: HTTP 200
- `GetLegendGraphic`: HTTP 200
- PNG render: verified
- tiled WMS download: verified
- tiled GeoTIFF mosaic: verified
- CRS output: EPSG:3857

Verified test AOI:

```text
104.08144856688278,-3.508670771548452,
104.43584512679433,-3.3288696787825245
```

Verified test command:

```bash
python bhumi/download_public_layer.py \
  --name "Bidang Tanah" \
  --download \
  --bbox 104.08144856688278,-3.508670771548452,104.43584512679433,-3.3288696787825245 \
  --cols 4 \
  --rows 3 \
  --width 1600 \
  --height 1200 \
  --delay 0.5 \
  --output output/bhumi_persil_sumsel.tif
```

Verified output:

```text
output/bhumi_persil_sumsel.tif
Size: 6400 x 3600
CRS: EPSG:3857
Compression: DEFLATE
Approx test file size: 2.5 MB
```

### What does NOT work anonymously

- WMS `GetFeatureInfo`: HTTP 403
- WMS `DescribeLayer`: HTTP 403
- WFS `GetCapabilities`: HTTP 403
- WFS `DescribeFeatureType`: HTTP 403
- WMTS `GetCapabilities`: HTTP 403
- WMTS `GetTile`: HTTP 403

Conclusion:

> `/mprx/service` is currently usable as a public **render path**, but not as a
> public feature/vector-query path.

Do not spend more time repeating the same anonymous GetFeatureInfo/WFS probes
unless the public service behavior changes.

The repository intentionally does not bypass access controls, reuse third-party
tokens/cookies, or decrypt protected responses.

Relevant diagnostic scripts:

```text
bhumi/test_persil_getfeatureinfo.sh
bhumi/test_persil_ogc_operations.sh
bhumi/query_persil.py
```

---

# 5. Other Verified BHUMI Downloads

## 5.1 Index Peta Dasar

Category:

```text
xyz
```

Template:

```text
/petadasartmi/{x}/{y}/{z}
```

A prior test successfully downloaded XYZ tiles.

Example:

```bash
python bhumi/download_public_layer.py \
  --name "Index Peta Dasar" \
  --download \
  --bbox 104.08144856688278,-3.508670771548452,104.43584512679433,-3.3288696787825245 \
  --zoom 12 \
  --output output/index_peta_dasar
```

Status: **VERIFIED DOWNLOADABLE**

---

## 5.2 Peta Tematik Pertanahan dan Ruang — PTPR

Catalog service:

```text
https://geoportaltematik.atrbpn.go.id/geoserver/geoportal
```

Catalog typename:

```text
geoportal:PTPRPublish
```

Actual advertised WFS FeatureType discovered:

```text
geoportal:PTPRPublished
```

A prior WFS test successfully produced GeoJSON and approximately 3,264 features.

Example:

```bash
python bhumi/download_public_layer.py \
  --name "Peta Tematik Pertanahan dan Ruang (PTPR)" \
  --download \
  --bbox 104.08144856688278,-3.508670771548452,104.43584512679433,-3.3288696787825245 \
  --output output/ptpr.geojson
```

Status: **VERIFIED VECTOR DOWNLOADABLE**

---

## 5.3 RTRW Provinsi / GISTARU WMS

The public GISTARU wrapper is usable for rendered WMS requests.

Important implementation detail discovered during testing:

- GISTARU wrapper expects uppercase `BBOX`
- use `SRS=EPSG:4326` for the tested WMS route
- WFS-like vector attempts returned empty feature sets in previous tests

Status:

```text
WMS render      : usable
public vector   : not verified / previously empty
```

---

## 5.4 RTRWN ArcGIS

Catalog service:

```text
https://gistaru.atrbpn.go.id/arcgis/rest/services/000_RTRWN/_RTRWN_PP_2017/MapServer
```

Previous tests returned service-not-started / HTTP 500 behavior.

Status: **UPSTREAM UNAVAILABLE during previous test**

Do not assume the code is broken if this source fails again; first inspect the
ArcGIS service status.

---

## 5.5 Kawasan IKN

Catalog:

```text
https://bhumi.atrbpn.go.id/geoserver/ows
geonode:ksn_ikn_ar
```

Category: OGC.

Status: adapter exists; real AOI download should be tested only where the AOI
intersects IKN.

---

# 6. BHUMI Bulk Catalog Runner

Main runner:

```text
bhumi/download_catalog_bulk.py
```

Features:

- reads all 36 published catalog layers;
- auto-selects adapter by category;
- stores a JSON manifest;
- resumes completed downloads;
- records failed/skipped layers;
- skips catalog layers outside the requested AOI when published extents are
  available;
- does not use protected BHUMI wrapper feature endpoints.

### Dry-run

```bash
python bhumi/download_catalog_bulk.py \
  --bbox 104.08144856688278,-3.508670771548452,104.43584512679433,-3.3288696787825245 \
  --zoom 12 \
  --output-dir output/bhumi_bulk \
  --dry-run
```

The 36-layer classification dry-run has already succeeded.

### Important pending re-test

AOI extent filtering was added **after** the first successful 36-layer dry-run.
Before doing a large real run, repeat the dry-run using the latest branch and
confirm `skipped-outside-aoi` classifications.

Recommended:

```bash
rm -f output/bhumi_bulk/manifest.json

python bhumi/download_catalog_bulk.py \
  --bbox 104.08144856688278,-3.508670771548452,104.43584512679433,-3.3288696787825245 \
  --zoom 12 \
  --output-dir output/bhumi_bulk \
  --dry-run

jq -r '.layers[] | [.name,.category,.status] | @tsv' \
  output/bhumi_bulk/manifest.json
```

### Real run after dry-run validation

```bash
python bhumi/download_catalog_bulk.py \
  --bbox 104.08144856688278,-3.508670771548452,104.43584512679433,-3.3288696787825245 \
  --zoom 12 \
  --output-dir output/bhumi_bulk \
  --delay 0.5
```

### Manifest

```text
output/bhumi_bulk/manifest.json
```

This manifest is the authoritative runtime record for batch progress.

---

# 7. BHUMI Wrapper Layers

Examples include:

- Toponim
- Lahan Baku Sawah 2024
- Pengumuman Yuridis
- Lahan Sawah Dilindungi
- Zona Nilai Tanah
- Peta Nilai Bidang Tanah
- Penggunaan Tanah
- Kawasan Hutan
- PIPPIB
- Area Penggunaan Lain
- Tanah Ulayat

These catalog records use paths such as:

```text
/bhumigs/umum
```

Current policy:

> Mark them as `bhumi-wrapper` and skip bulk vector extraction unless a public,
> documented or otherwise openly accessible data route is identified.

---

# 8. 3D Tiles and Terrain

BHUMI catalog contains multiple 3D Tiles datasets, including examples for:

- Gandaria City
- Mataram
- PUSDATIN ATR/BPN
- Badung/Bali
- Honolulu apartment
- Blok M
- Bundaran HI
- LOD1 Mataram/Bali

Current adapter:

```text
3d-tiles -> download tileset.json metadata
```

Recursive downloading of all referenced `.b3dm`, `.glb`, nested tilesets,
etc. is **not yet implemented**.

Terrain catalog entry:

```text
DEM1
https://demotiles.maplibre.org/terrain-tiles/tiles.json
```

Current adapter saves TileJSON metadata only.

---

# 9. BIG Bathymetry / BATNAS

Main files:

```text
bathymetry/probe_big.py
bathymetry/download_bathymetry.py
bathymetry/probe_detail_sources.py
bathymetry/analyze_depth_vectors.py
bathymetry/README.md
```

---

# 10. CHECKPOINT — BATNAS ImageServer

Official BIG service:

```text
https://geoservices.big.go.id/raster/rest/services/BATNAS/Grid_Batimetri_Indonesia/ImageServer
```

Verified metadata:

```text
pixel type : F32
bands      : 1
pixelSizeX : ~0.0013888889 degrees
pixelSizeY : ~0.0013888889 degrees
extent     : approx 79E–161E, 26S–26N
```

Verified capabilities include Image, Metadata and Mensuration.

### Verified functionality

- ImageServer metadata: HTTP 200
- `exportImage`: HTTP 200
- direct TIFF download: verified
- `getSamples`: HTTP 200
- GeoTIFF numeric raster: verified
- bathymetry-only masking: implemented
- positive-depth conversion: implemented

---

# 11. BATNAS Test — Sumsel AOI

Test:

```bash
python bathymetry/download_bathymetry.py \
  --bbox 104.08144856688278,-3.508670771548452,104.43584512679433,-3.3288696787825245 \
  --output output/bathymetry/batnas_sumsel.tif \
  --metadata \
  --atlas-vector
```

Verified output:

```text
256 x 130
EPSG:4326
float32
min  ~= -3.32 m
max  ~= +119.10 m
mean ~= +42.91 m
centre sample ~= +59 m
```

This AOI is mostly land, so positive elevations dominate.

---

# 12. CHECKPOINT — Selat Bangka Bathymetry

Preset BBOX:

```text
105.10,-2.50,105.80,-1.60
```

Command:

```bash
python bathymetry/probe_detail_sources.py \
  --preset bangka-strait \
  --download-vectors \
  --positive-depth
```

## 12.1 BATNAS raster result

Verified:

```text
size                : 504 x 648
CRS                 : EPSG:4326
dtype               : float32
minimum elevation   : ~-75.81 m
maximum topography  : ~+426.99 m
water pixels        : 159,819 / 326,592
max positive depth  : ~75.81 m
mean positive depth : ~14.83 m
```

Outputs:

```text
output/bathymetry_detail/bangka-strait/batnas.tif
output/bathymetry_detail/bangka-strait/batnas_depth_positive.tif
```

---

# 13. Selat Bangka — Detailed Vector Bathymetry

Official BIG service tested:

```text
PKLP/DataBatimetri_BIG_2017
```

Verified feature counts within the Bangka Strait preset:

| Dataset | Features |
|---|---:|
| LPI 1:50K sounding points | 717 |
| LPI 1:50K depth contours | 136 |
| LPI 1:50K depth areas | 0 |
| LLN 1:500K sounding points | 577 |
| LLN 1:500K depth contours | 47 |
| LLN 1:500K depth areas | 24 |
| LPI 1:25K | 0 |
| LLN 1:50K | 0 |
| LLN 1:250K | 0 |
| LPI 1:250K | 0 |
| HIPSOGRAFI_WLP_25K | 0 |

For this AOI, the best verified vector product is:

```text
LPI 1:50,000
- sounding points
- depth contours
```

Remember:

> 1:50K is a map scale, **not 50 metre raster resolution**.

---

# 14. Bathymetry Attribute Mapping

Verified from downloaded BIG LPI50K features:

### Sounding point

```text
NIKDLM = depth value in metres
```

Example observed:

```text
NIKDLM = 2
```

Interpretation: sounding depth approximately 2 m.

Useful accompanying fields:

```text
DTMVER   vertical datum code
EXPSOU   sounding exposition code
QUASOU   sounding quality code
INFORM   information code
ISBDTA   source indication
IRKDTA   recording indication
SKLMAK   maximum scale
SKLMIN   minimum scale
```

### Depth contour

```text
NKKDLM = contour depth value in metres
```

Example observed:

```text
NKKDLM = 15
```

Interpretation: 15 m depth contour.

Other useful fields:

```text
IDXKNT
JNSKNT
DTMVER
SKLMAK
SKLMIN
```

---

# 15. Analyze Bathymetry Vectors

Analyzer:

```text
bathymetry/analyze_depth_vectors.py
```

Run for Selat Bangka:

```bash
python bathymetry/analyze_depth_vectors.py \
  --points output/bathymetry_detail/bangka-strait/databatimetri_big_2017_26_LPI50K_titik.geojson \
  --contours output/bathymetry_detail/bangka-strait/databatimetri_big_2017_27_LPI50K_kontur.geojson \
  --output-dir output/bathymetry_detail/bangka-strait/analysis
```

Outputs:

```text
analysis/
├── soundings.csv
├── depth_contours.csv
└── depth_summary.json
```

## Current status

Analyzer has been committed but **has not yet been executed/verified on the VPS**.

That is a good immediate continuation step.

---

# 16. NEXT TEST — Tanjung Kelayang / Belitung

Preset already exists in:

```text
bathymetry/probe_detail_sources.py
```

Run:

```bash
python bathymetry/probe_detail_sources.py \
  --preset tanjung-kelayang \
  --download-vectors \
  --positive-depth
```

Goal:

Determine whether Belitung has coverage from higher-detail sources such as:

- LPI 1:25K sounding points
- LPI 1:25K contours
- HIPSOGRAFI_WLP_25K
- SIBATNAS regional Tanjung Kelayang products

This test is **PENDING**.

---

# 17. Recommended Priority Order From Here

## Priority A — Finish current bathymetry validation

1. Run `analyze_depth_vectors.py` for Selat Bangka.
2. Record depth min/max/mean/median from the 717 LPI50K sounding points.
3. Run Tanjung Kelayang preset.
4. Determine best available scale/product for Belitung.
5. Compare BATNAS raster values against nearby LPI sounding points.

## Priority B — Resume BHUMI bulk download

1. Re-run the 36-layer dry-run using the latest AOI-filter code.
2. Inspect `skipped-outside-aoi`.
3. Run the actual batch.
4. Review `manifest.json`.
5. Fix only source-specific failures; do not repeat already-successful adapters.

## Priority C — Improve downloaders

Potential additions:

- download 3D Tiles recursively;
- terrain tile AOI downloader;
- GeoPackage output for vector bathymetry;
- interpolation of sounding points to a local depth surface;
- automatic source ranking:
  `LPI25K > LPI50K > LPI250K > LLN250K > LLN500K > BATNAS`
  **only where each source actually has coverage**;
- produce bathymetry package per AOI:
  raster + soundings + contours + metadata + manifest.

---

# 18. Important Known Limitations

### BHUMI Persil

Raster render is available, but anonymous vector/NIB query is blocked by the
current public service policy.

### ArcGIS services

Some catalog ArcGIS entries may be temporarily stopped upstream. Record these as
source failures rather than rewriting working client code unnecessarily.

### WMS

WMS output is rendered raster. It is not equivalent to raw vector features.

### BATNAS

BATNAS contains both negative bathymetric elevations and positive land
topography. Use `--bathymetry-only` or `--depth-positive` when appropriate.

### Vector bathymetry scale

LPI/LLN map scale is not the same as grid/pixel resolution.

---

# 19. Useful Status Commands

BHUMI batch manifest:

```bash
jq -r '.layers[] | [.name,.category,.status] | @tsv' \
  output/bhumi_bulk/manifest.json
```

List generated bathymetry files:

```bash
find output/bathymetry* -maxdepth 4 -type f -printf '%p\t%k KB\n' | sort
```

Inspect GeoTIFF:

```bash
gdalinfo output/bathymetry_detail/bangka-strait/batnas_depth_positive.tif | head -60
```

Inspect depth point:

```bash
jq '.features[0].properties' \
  output/bathymetry_detail/bangka-strait/databatimetri_big_2017_26_LPI50K_titik.geojson
```

Git status:

```bash
git status
git log --oneline -12
```

---

# 20. Key Checkpoint Commits

These are useful landmarks, not a replacement for the full Git history.

| Commit | Checkpoint |
|---|---|
| `fc77aa9` | Persil WMS GetMap working |
| `d9d4694` | tiled Persil GeoTIFF mosaic |
| `ff31fc7` | GeoTIFF block-size fix |
| `62a3a9e` | Persil GetFeatureInfo diagnostics |
| `fd5c4df` | verified Persil OGC operation matrix |
| `b63f2b1` | resumable 36-layer BHUMI bulk runner |
| `3f01cd8` | AOI extent filtering in bulk runner |
| `403747b` | official BIG bathymetry service probe |
| `d54ac8a` | BATNAS GeoTIFF downloader |
| `9d80059` | bathymetry-only / positive-depth raster |
| `c5e138d` | Bangka/Belitung detailed source probe |
| `ed67632` | Selat Bangka bathymetry checkpoint |
| `c15e714` | vector depth CSV/statistics analyzer |

---

# 21. Data Safety / Repository Hygiene

Do not commit:

- HAR files;
- cookies;
- Authorization headers;
- JWT/session tokens;
- raw browser session dumps;
- credentials.

The downloader should use only public data routes or credentials the operator is
explicitly authorized to use.

---

# 22. Definition of “Done”

A source/adapter should only be marked **VERIFIED** after all of the following
are true:

1. endpoint responds successfully from the VPS;
2. output file is actually created;
3. output format is validated;
4. CRS/geometry or raster metadata is checked;
5. meaningful data is present, not an error page disguised as HTTP 200;
6. command used for the test is recorded;
7. result is added to this track record or module README.

This rule prevents repeating old investigations and makes continuation from a
new chat/session straightforward.
