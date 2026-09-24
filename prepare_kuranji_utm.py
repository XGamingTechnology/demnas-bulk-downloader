#!/usr/bin/env python3
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.warp import calculate_default_transform, reproject, Resampling
from shapely.geometry import shape, mapping
from shapely.ops import unary_union, transform as shp_transform
from pyproj import Transformer

RAW = Path("data/output/kuranji")
INPUT = Path("data/input/kuranji")
OUT = Path("data/work/kuranji/01_prepared")
OUT.mkdir(parents=True, exist_ok=True)

DEM_RAW = RAW / "DEMNAS_KURANJI_BUFFER3KM_WGS84.tif"
DAS_RAW = INPUT / "DAS_KURANJI_WGS84.geojson"
RIVER_RAW = RAW / "SUNGAI_RBI_DAS_KURANJI.geojson"

DEM_CLEAN = OUT / "DEMNAS_KURANJI_BUFFER3KM_CLEAN_WGS84.tif"
DEM_UTM = OUT / "DEMNAS_KURANJI_BUFFER3KM_UTM47S.tif"
DEM_DAS_UTM = OUT / "DEMNAS_DAS_KURANJI_UTM47S.tif"
DAS_UTM_FILE = OUT / "DAS_KURANJI_UTM47S.geojson"
RIVER_UTM_FILE = OUT / "SUNGAI_RBI_DAS_KURANJI_UTM47S.geojson"

DST_CRS = "EPSG:32747"
NODATA = -9999.0

# Keep plausible DEMNAS elevations and discard ArcGIS float sentinel values (~1e38).
VALID_MIN = -100.0
VALID_MAX = 5000.0


def load_union(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    geoms = [
        shape(feat["geometry"])
        for feat in data["features"]
        if feat.get("geometry")
    ]
    return unary_union(geoms)


def save_geojson(features, path, epsg):
    fc = {
        "type": "FeatureCollection",
        "name": path.stem,
        "crs": {
            "type": "name",
            "properties": {"name": f"EPSG:{epsg}"},
        },
        "features": features,
    }
    path.write_text(
        json.dumps(fc, ensure_ascii=False),
        encoding="utf-8",
    )


def clean_dem(src_path, dst_path):
    with rasterio.open(src_path) as src:
        data = src.read(1).astype("float32", copy=False)

        invalid = (
            (~np.isfinite(data))
            | (data < VALID_MIN)
            | (data > VALID_MAX)
        )

        if src.nodata is not None:
            invalid |= np.isclose(data, src.nodata)

        clean = data.copy()
        clean[invalid] = NODATA

        profile = src.profile.copy()
        profile.update(
            dtype="float32",
            nodata=NODATA,
            compress="DEFLATE",
            predictor=3,
            tiled=True,
            BIGTIFF="IF_SAFER",
        )

        with rasterio.open(dst_path, "w", **profile) as dst:
            dst.write(clean, 1)

        valid = clean[clean != NODATA]

        print("Raw DEM pixels    :", f"{data.size:,}")
        print("Invalid -> NoData :", f"{int(invalid.sum()):,}")
        print("Valid pixels      :", f"{valid.size:,}")
        if valid.size:
            print(
                "Clean min/max     :",
                float(valid.min()),
                "/",
                float(valid.max()),
            )


def stats(path):
    with rasterio.open(path) as ds:
        data = ds.read(1).astype("float64", copy=False)

        valid = np.isfinite(data)
        if ds.nodata is not None:
            valid &= ~np.isclose(data, ds.nodata)
        valid &= (data >= VALID_MIN) & (data <= VALID_MAX)

        x = data[valid]

        print()
        print("FILE       :", path)
        print("CRS        :", ds.crs)
        print("Size       :", ds.width, "x", ds.height)
        print("Resolution :", ds.res)
        print("Bounds     :", ds.bounds)
        print("NoData     :", ds.nodata)
        print("Valid px   :", f"{x.size:,}")

        if x.size:
            print("Min elev   :", float(x.min()))
            print("Mean elev  :", float(x.mean()))
            print("Median     :", float(np.median(x)))
            print("Max elev   :", float(x.max()))
            print(
                "P1 / P99   :",
                float(np.percentile(x, 1)),
                "/",
                float(np.percentile(x, 99)),
            )


print("=" * 70)
print("1. LOAD DAS")
print("=" * 70)

das_wgs = load_union(DAS_RAW)

to_utm = Transformer.from_crs(
    "EPSG:4326",
    DST_CRS,
    always_xy=True,
).transform

das_utm = shp_transform(to_utm, das_wgs)

print("DAS valid :", das_utm.is_valid)
print("DAS area  :", f"{das_utm.area / 1_000_000:.6f} km2")
print("Bounds    :", das_utm.bounds)

save_geojson(
    [{
        "type": "Feature",
        "properties": {
            "nama": "DAS Kuranji",
            "luas_km2": das_utm.area / 1_000_000,
        },
        "geometry": mapping(das_utm),
    }],
    DAS_UTM_FILE,
    32747,
)

print()
print("=" * 70)
print("2. CLEAN RAW DEM")
print("=" * 70)

clean_dem(DEM_RAW, DEM_CLEAN)

print()
print("=" * 70)
print("3. REPROJECT CLEAN DEM -> UTM 47S")
print("=" * 70)

with rasterio.open(DEM_CLEAN) as src:
    transform, width, height = calculate_default_transform(
        src.crs,
        DST_CRS,
        src.width,
        src.height,
        *src.bounds,
    )

    profile = src.profile.copy()
    profile.update(
        crs=DST_CRS,
        transform=transform,
        width=width,
        height=height,
        dtype="float32",
        nodata=NODATA,
        compress="DEFLATE",
        predictor=3,
        tiled=True,
        BIGTIFF="IF_SAFER",
    )

    with rasterio.open(DEM_UTM, "w", **profile) as dst:
        reproject(
            source=rasterio.band(src, 1),
            destination=rasterio.band(dst, 1),
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=NODATA,
            dst_transform=transform,
            dst_crs=DST_CRS,
            dst_nodata=NODATA,
            resampling=Resampling.bilinear,
            num_threads=2,
        )

print()
print("=" * 70)
print("4. CLIP DEM KE DAS")
print("=" * 70)

with rasterio.open(DEM_UTM) as src:
    clipped, clipped_transform = mask(
        src,
        [mapping(das_utm)],
        crop=True,
        nodata=NODATA,
    )

    profile = src.profile.copy()
    profile.update(
        height=clipped.shape[1],
        width=clipped.shape[2],
        transform=clipped_transform,
        nodata=NODATA,
        compress="DEFLATE",
    )

    with rasterio.open(DEM_DAS_UTM, "w", **profile) as dst:
        dst.write(clipped)

print()
print("=" * 70)
print("5. REPROJECT SUNGAI")
print("=" * 70)

with open(RIVER_RAW, encoding="utf-8") as f:
    river_data = json.load(f)

river_features = []
total_length = 0.0

for feat in river_data["features"]:
    if not feat.get("geometry"):
        continue

    try:
        geom = shape(feat["geometry"])
        geom_utm = shp_transform(to_utm, geom)
    except Exception:
        continue

    if geom_utm.is_empty:
        continue

    total_length += geom_utm.length

    river_features.append({
        "type": "Feature",
        "properties": feat.get("properties", {}),
        "geometry": mapping(geom_utm),
    })

save_geojson(
    river_features,
    RIVER_UTM_FILE,
    32747,
)

print("River features :", len(river_features))
print("River length   :", f"{total_length / 1000:.3f} km")

print()
print("=" * 70)
print("6. QC")
print("=" * 70)

stats(DEM_RAW)
stats(DEM_CLEAN)
stats(DEM_UTM)
stats(DEM_DAS_UTM)

print()
print("=" * 70)
print("SELESAI")
print("=" * 70)
print("DEM CLEAN      :", DEM_CLEAN)
print("DEM buffer UTM :", DEM_UTM)
print("DEM DAS UTM    :", DEM_DAS_UTM)
print("DAS UTM        :", DAS_UTM_FILE)
print("Sungai UTM     :", RIVER_UTM_FILE)
