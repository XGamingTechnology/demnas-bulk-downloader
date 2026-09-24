# Kuranji prepared DEM artifacts

Prepared research DEM outputs for DAS Kuranji are stored here through Git LFS.

Expected package:

- `KURANJI_DEM_PREPARED.zip`

Package contents:

- `DEMNAS_KURANJI_BUFFER3KM_UTM47S.tif`
- `DEMNAS_DAS_KURANJI_UTM47S.tif`
- `DAS_KURANJI_WGS84.geojson`
- `KURANJI_DEM_PREPARED_README.txt`

Source DEMNAS tiles used:

- `DEMNAS_0715-32_v1.0.tif`
- `DEMNAS_0815-11_v1.0.tif`

Working CRS: EPSG:32747 (WGS 84 / UTM zone 47S).
NoData value: -9999.
Hydrology should use the 3 km buffered DEM rather than the exact-DAS clip.
