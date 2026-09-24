#!/usr/bin/env python3
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.merge import merge
from rasterio.warp import calculate_default_transform, reproject, Resampling
from shapely.geometry import shape, mapping
from shapely.ops import unary_union, transform as shp_transform
from pyproj import Transformer

SRC_DIR = Path("data/input/kuranji/dem_source")
AOI_FILE = Path("data/input/kuranji/DAS_KURANJI_WGS84.geojson")
OUT = Path("data/work/kuranji/01_prepared")
OUT.mkdir(parents=True, exist_ok=True)

NODATA = -9999.0
DST_CRS = "EPSG:32747"
VALID_MIN = -100.0
VALID_MAX = 5000.0

MOSAIC_WGS = OUT / "DEMNAS_KURANJI_SOURCE_MOSAIC_WGS84.tif"
DEM_UTM = OUT / "DEMNAS_KURANJI_BUFFER_UTM47S.tif"
DEM_DAS_UTM = OUT / "DEMNAS_DAS_KURANJI_UTM47S.tif"


def load_aoi():
    with AOI_FILE.open(encoding="utf-8") as f:
        data = json.load(f)
    return unary_union([
        shape(feat["geometry"])
        for feat in data.get("features", [])
        if feat.get("geometry")
    ])


def clean_array(arr, src_nodata=None):
    a = arr.astype("float32", copy=True)
    invalid = (~np.isfinite(a)) | (a < VALID_MIN) | (a > VALID_MAX)
    if src_nodata is not None:
        invalid |= np.isclose(a, src_nodata)
    a[invalid] = NODATA
    return a


def inspect(path):
    with rasterio.open(path) as ds:
        a = ds.read(1).astype("float64", copy=False)
        valid = np.isfinite(a)
        if ds.nodata is not None:
            valid &= ~np.isclose(a, ds.nodata)
        valid &= (a >= VALID_MIN) & (a <= VALID_MAX)
        x = a[valid]
        print("\nFILE       :", path)
        print("CRS        :", ds.crs)
        print("Size       :", ds.width, "x", ds.height)
        print("Resolution :", ds.res)
        print("Bounds     :", ds.bounds)
        print("NoData     :", ds.nodata)
        print("Valid px   :", f"{x.size:,}")
        if x.size:
            print("Min        :", float(x.min()))
            print("Mean       :", float(x.mean()))
            print("Median     :", float(np.median(x)))
            print("Max        :", float(x.max()))
            print("P1/P99     :", float(np.percentile(x, 1)), "/", float(np.percentile(x, 99)))


def main():
    files = sorted(list(SRC_DIR.glob("*.tif")) + list(SRC_DIR.glob("*.tiff")))
    if not files:
        raise RuntimeError(
            f"Tidak ada TIFF pada {SRC_DIR}. Taruh file DEMNAS/SIBATNAS di folder tersebut."
        )

    print("DEM source files:")
    for p in files:
        print(" -", p)

    sources = []
    for p in files:
        ds = rasterio.open(p)
        if ds.crs is None:
            ds.close()
            raise RuntimeError(f"CRS tidak tersedia: {p}")
        sources.append(ds)

    try:
        # Rasterio merge requires a common CRS. SIBATNAS DEMNAS is expected in geographic CRS.
        crs0 = sources[0].crs
        for ds in sources[1:]:
            if ds.crs != crs0:
                raise RuntimeError("Source TIFF memiliki CRS berbeda; reprojection source diperlukan dulu.")

        mosaic, transform = merge(sources, nodata=NODATA)
        mosaic = clean_array(mosaic, None)

        profile = sources[0].profile.copy()
        profile.update(
            driver="GTiff",
            height=mosaic.shape[1],
            width=mosaic.shape[2],
            transform=transform,
            count=1,
            dtype="float32",
            nodata=NODATA,
            compress="DEFLATE",
            predictor=3,
            tiled=True,
            BIGTIFF="IF_SAFER",
        )

        with rasterio.open(MOSAIC_WGS, "w", **profile) as dst:
            dst.write(mosaic[0], 1)
    finally:
        for ds in sources:
            ds.close()

    aoi = load_aoi()

    # Buffer 3 km in UTM 47S, then transform back to source CRS for clipping.
    to_utm = Transformer.from_crs("EPSG:4326", DST_CRS, always_xy=True).transform
    to_wgs = Transformer.from_crs(DST_CRS, "EPSG:4326", always_xy=True).transform
    aoi_utm = shp_transform(to_utm, aoi)
    buffer_utm = aoi_utm.buffer(3000)
    buffer_wgs = shp_transform(to_wgs, buffer_utm)

    with rasterio.open(MOSAIC_WGS) as src:
        # Clip to 3 km buffered DAS before reprojection.
        clipped, ctr = mask(src, [mapping(buffer_wgs)], crop=True, nodata=NODATA)
        clipped = clean_array(clipped, src.nodata)

        tmp = OUT / "DEMNAS_KURANJI_BUFFER3KM_SOURCE_CLEAN.tif"
        prof = src.profile.copy()
        prof.update(
            height=clipped.shape[1],
            width=clipped.shape[2],
            transform=ctr,
            dtype="float32",
            nodata=NODATA,
            compress="DEFLATE",
            predictor=3,
            tiled=True,
        )
        with rasterio.open(tmp, "w", **prof) as dst:
            dst.write(clipped)

    # Reproject buffered clean DEM to UTM 47S.
    with rasterio.open(tmp) as src:
        tr, width, height = calculate_default_transform(
            src.crs, DST_CRS, src.width, src.height, *src.bounds
        )
        prof = src.profile.copy()
        prof.update(
            crs=DST_CRS,
            transform=tr,
            width=width,
            height=height,
            dtype="float32",
            nodata=NODATA,
            compress="DEFLATE",
            predictor=3,
            tiled=True,
            BIGTIFF="IF_SAFER",
        )
        with rasterio.open(DEM_UTM, "w", **prof) as dst:
            reproject(
                source=rasterio.band(src, 1),
                destination=rasterio.band(dst, 1),
                src_transform=src.transform,
                src_crs=src.crs,
                src_nodata=NODATA,
                dst_transform=tr,
                dst_crs=DST_CRS,
                dst_nodata=NODATA,
                resampling=Resampling.bilinear,
                num_threads=2,
            )

    # Final exact DAS clip in UTM.
    with rasterio.open(DEM_UTM) as src:
        das_clip, das_tr = mask(src, [mapping(aoi_utm)], crop=True, nodata=NODATA)
        prof = src.profile.copy()
        prof.update(
            height=das_clip.shape[1],
            width=das_clip.shape[2],
            transform=das_tr,
            nodata=NODATA,
            compress="DEFLATE",
        )
        with rasterio.open(DEM_DAS_UTM, "w", **prof) as dst:
            dst.write(das_clip)

    print("\n=== QC ===")
    inspect(MOSAIC_WGS)
    inspect(tmp)
    inspect(DEM_UTM)
    inspect(DEM_DAS_UTM)

    print("\nDONE")
    print("Mosaic source :", MOSAIC_WGS)
    print("Buffer UTM    :", DEM_UTM)
    print("DAS UTM       :", DEM_DAS_UTM)


if __name__ == "__main__":
    main()
