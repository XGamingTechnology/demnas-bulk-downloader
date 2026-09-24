#!/usr/bin/env python3
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.mask import mask
from rasterio.merge import merge
from rasterio.warp import calculate_default_transform, reproject, Resampling
from shapely.geometry import shape, mapping, box
from shapely.ops import unary_union, transform as shp_transform
from pyproj import Transformer

SRC_DIR = Path("data/input/kuranji/dem_source")
AOI_FILE = Path("data/input/kuranji/DAS_KURANJI_WGS84.geojson")
OUT = Path("data/work/kuranji/01_prepared")
OUT.mkdir(parents=True, exist_ok=True)

NODATA = -9999.0
SRC_CRS = "EPSG:4326"
DST_CRS = "EPSG:32747"
VALID_MIN = -100.0
VALID_MAX = 5000.0

MOSAIC_WGS = OUT / "DEMNAS_KURANJI_SOURCE_MOSAIC_WGS84.tif"
BUFFER_WGS = OUT / "DEMNAS_KURANJI_BUFFER3KM_SOURCE_CLEAN.tif"
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
    if src_nodata is not None and np.isfinite(src_nodata):
        invalid |= np.isclose(a, src_nodata)
    a[invalid] = NODATA
    return a


def inspect(path):
    with rasterio.open(path) as ds:
        a = ds.read(1).astype("float64", copy=False)
        valid = np.isfinite(a)
        if ds.nodata is not None and np.isfinite(ds.nodata):
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


def normalized_dataset(path):
    """Open a DEMNAS tile and assign EPSG:4326 in-memory when the TIFF lacks CRS metadata."""
    src = rasterio.open(path)
    if src.crs is not None:
        return src, None

    b = src.bounds
    looks_geographic = (
        -180 <= b.left <= 180 and -180 <= b.right <= 180
        and -90 <= b.bottom <= 90 and -90 <= b.top <= 90
    )
    if not looks_geographic:
        src.close()
        raise RuntimeError(f"CRS tidak tersedia dan bounds tidak tampak geografis: {path}")

    data = src.read(1)
    profile = src.profile.copy()
    profile.update(crs=SRC_CRS)
    mem = MemoryFile()
    mem_ds = mem.open(**profile)
    mem_ds.write(data, 1)
    src.close()
    print(f"  CRS kosong -> diasumsikan {SRC_CRS}: {path.name}")
    return mem_ds, mem


def main():
    files = sorted(list(SRC_DIR.glob("*.tif")) + list(SRC_DIR.glob("*.tiff")))
    if not files:
        raise RuntimeError(f"Tidak ada TIFF pada {SRC_DIR}")

    aoi = load_aoi()
    to_utm = Transformer.from_crs(SRC_CRS, DST_CRS, always_xy=True).transform
    to_wgs = Transformer.from_crs(DST_CRS, SRC_CRS, always_xy=True).transform
    aoi_utm = shp_transform(to_utm, aoi)
    buffer_utm = aoi_utm.buffer(3000)
    buffer_wgs = shp_transform(to_wgs, buffer_utm)

    print("DEM source files:")
    for p in files:
        print(" -", p)

    sources = []
    memories = []
    footprints = []

    for p in files:
        ds, mem = normalized_dataset(p)
        footprint = box(*ds.bounds)

        # Ignore tiles that do not overlap the 3 km buffered research AOI.
        if not footprint.intersects(buffer_wgs):
            print(f"  SKIP tidak overlap AOI+buffer: {p.name}")
            ds.close()
            if mem is not None:
                mem.close()
            continue

        if ds.crs.to_string() != SRC_CRS:
            ds.close()
            if mem is not None:
                mem.close()
            raise RuntimeError(f"CRS source bukan {SRC_CRS}: {p} -> {ds.crs}")

        sources.append(ds)
        footprints.append(footprint)
        if mem is not None:
            memories.append(mem)

    if not sources:
        raise RuntimeError("Tidak ada source DEM yang overlap AOI Kuranji + buffer 3 km")

    coverage = unary_union(footprints)
    covered = aoi.intersection(coverage)
    pct = (covered.area / aoi.area * 100.0) if aoi.area else 0.0
    print(f"Coverage DAS oleh source saat ini: {pct:.2f}%")

    if pct < 99.0:
        print("PERINGATAN: coverage DAS belum lengkap. Output parsial tidak boleh dipakai untuk hidrologi final.")

    try:
        mosaic, transform = merge(sources, nodata=NODATA)
        mosaic = clean_array(mosaic, None)

        profile = sources[0].profile.copy()
        profile.update(
            driver="GTiff",
            crs=SRC_CRS,
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
        for mem in memories:
            mem.close()

    with rasterio.open(MOSAIC_WGS) as src:
        clipped, ctr = mask(src, [mapping(buffer_wgs)], crop=True, nodata=NODATA)
        clipped = clean_array(clipped, src.nodata)

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
        with rasterio.open(BUFFER_WGS, "w", **prof) as dst:
            dst.write(clipped)

    with rasterio.open(BUFFER_WGS) as src:
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
    inspect(BUFFER_WGS)
    inspect(DEM_UTM)
    inspect(DEM_DAS_UTM)

    print("\nDONE")
    print(f"Coverage DAS : {pct:.2f}%")
    print("Mosaic source:", MOSAIC_WGS)
    print("Buffer UTM   :", DEM_UTM)
    print("DAS UTM      :", DEM_DAS_UTM)

    if pct < 99.0:
        raise SystemExit(
            "STOP: coverage DAS belum lengkap. Tambahkan tile DEMNAS yang hilang sebelum analisis hidrologi final."
        )


if __name__ == "__main__":
    main()
