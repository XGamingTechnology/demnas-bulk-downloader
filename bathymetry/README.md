# Bathymetry Downloader



## Checkpoint: Selat Bangka

AOI:

```text
105.10,-2.50,105.80,-1.60
```

### BATNAS raster

Public BIG BATNAS ImageServer successfully exported a numeric GeoTIFF subset:

- raster size: `504 x 648`
- CRS: `EPSG:4326`
- dtype: `float32`
- minimum elevation: approximately `-75.81 m`
- maximum elevation/topography: approximately `+426.99 m`
- bathymetry-only water pixels: `159,819 / 326,592`
- positive-depth maximum: approximately `75.81 m`
- mean positive water depth: approximately `14.83 m`

Output:

```text
output/bathymetry_detail/bangka-strait/batnas.tif
output/bathymetry_detail/bangka-strait/batnas_depth_positive.tif
```

### Detailed BIG vector bathymetry

`PKLP/DataBatimetri_BIG_2017` returned:

| Dataset | Features in AOI |
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

For this AOI, the preferred detailed vector source is therefore **LPI 1:50K**
(soundings + contours), with **LLN 1:500K** as a coarser fallback.

Note: `1:50K` is a cartographic map scale, not a statement that raster
resolution is 50 metres.

