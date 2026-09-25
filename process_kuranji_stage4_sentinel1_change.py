#!/usr/bin/env python3
"""Build aligned Sentinel-1 RTC change rasters for Kuranji Stage 4.

Inputs
------
Three HyP3 RTC ZIP products already downloaded to:
  data/work/kuranji/18_stage4_sentinel1_rtc/products/

Expected dates/roles:
  PRE   2025-11-10
  EVENT 2025-11-22
  POST  2025-12-04

Method
------
1. Inspect each HyP3 ZIP and extract GeoTIFFs only.
2. Discover VV, VH and incidence-angle rasters robustly from filenames.
3. Reproject/resample all polarizations to one 20 m EPSG:32747 grid snapped
   to the actual DAS Batang Kuranji bounds.
4. Mask pixels outside the DAS.
5. Preserve gamma0 power rasters and derive dB = 10*log10(power).
6. Produce optional 3x3 NaN-aware median-filtered dB derivatives for visual /
   distributional inspection; RAW aligned dB remains the primary evidence.
7. Compute dB differences (equivalent to log-ratios):
      EVENT - PRE
      POST  - PRE
      POST  - EVENT
   separately for VV and VH.
8. Compute VH/VV dB ratio for each date and its temporal differences.
9. Write descriptive statistics and grid/QC metadata.

Important
---------
This script DOES NOT classify flood/non-flood and DOES NOT tune thresholds.
Change rasters are evidence layers that will later be evaluated against the
independent BIG/BRIN observed extent and the frozen P175 baseline candidate.

Dependencies already present in the project venv:
  numpy, rasterio, shapely, pyproj, scipy
"""

from __future__ import annotations

import csv
import json
import math
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from scipy.ndimage import generic_filter
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform, unary_union

ROOT = Path(__file__).resolve().parent
PRODUCTS = ROOT / "data/work/kuranji/18_stage4_sentinel1_rtc/products"
OUT = ROOT / "data/work/kuranji/19_stage4_sentinel1_change"
EXTRACTED = OUT / "extracted"
ALIGNED = OUT / "aligned"
CHANGE = OUT / "change"
QC = OUT / "qc"
for d in [OUT, EXTRACTED, ALIGNED, CHANGE, QC]:
    d.mkdir(parents=True, exist_ok=True)

DAS_UTM = ROOT / "data/work/kuranji/01_prepared/DAS_KURANJI_UTM47S.geojson"
TARGET_CRS = CRS.from_epsg(32747)
TARGET_RES = 20.0
NODATA = -9999.0

ROLE_DATES = {
    "PRE": "20251110",
    "EVENT": "20251122",
    "POST": "20251204",
}


def load_das_utm():
    if not DAS_UTM.exists():
        raise FileNotFoundError(DAS_UTM)
    fc = json.loads(DAS_UTM.read_text(encoding="utf-8"))
    geoms = [shape(f["geometry"]) for f in fc.get("features", []) if f.get("geometry")]
    if not geoms:
        raise RuntimeError("No DAS geometry found")
    return unary_union(geoms)


def snap_floor(x, res):
    return math.floor(x / res) * res


def snap_ceil(x, res):
    return math.ceil(x / res) * res


def build_target_grid(das):
    minx, miny, maxx, maxy = das.bounds
    left = snap_floor(minx, TARGET_RES)
    right = snap_ceil(maxx, TARGET_RES)
    bottom = snap_floor(miny, TARGET_RES)
    top = snap_ceil(maxy, TARGET_RES)
    width = int(round((right - left) / TARGET_RES))
    height = int(round((top - bottom) / TARGET_RES))
    transform = from_origin(left, top, TARGET_RES, TARGET_RES)
    return {
        "left": left,
        "right": right,
        "bottom": bottom,
        "top": top,
        "width": width,
        "height": height,
        "transform": transform,
    }


def find_role_zip(role: str):
    date = ROLE_DATES[role]
    matches = sorted(PRODUCTS.glob(f"*{date}*.zip"))
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one ZIP for {role}/{date}, found {len(matches)}: {matches}")
    return matches[0]


def safe_member_name(name: str):
    p = Path(name)
    if p.is_absolute() or ".." in p.parts:
        raise RuntimeError(f"Unsafe ZIP member path: {name}")
    return p


def extract_tifs(zip_path: Path, role: str):
    role_dir = EXTRACTED / role
    role_dir.mkdir(parents=True, exist_ok=True)
    extracted = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir() or not info.filename.lower().endswith((".tif", ".tiff")):
                continue
            member = safe_member_name(info.filename)
            # Flatten to basename; HyP3 product filenames are unique within one product.
            dst = role_dir / member.name
            with zf.open(info) as src, dst.open("wb") as out:
                shutil.copyfileobj(src, out)
            extracted.append(dst)
    if not extracted:
        raise RuntimeError(f"No GeoTIFF found in {zip_path}")
    return extracted


def classify_tif(path: Path):
    n = path.name.lower()
    # HyP3 naming has variants; keep matching deliberately conservative.
    if re.search(r"(^|[_-])vv([_.-]|$)", n):
        return "VV"
    if re.search(r"(^|[_-])vh([_.-]|$)", n):
        return "VH"
    if "inc" in n and ("map" in n or "angle" in n):
        return "INC"
    if "ls_map" in n or "layover" in n or "shadow" in n:
        return "LS"
    return "OTHER"


def discover_layers(paths):
    layers: dict[str, list[Path]] = {"VV": [], "VH": [], "INC": [], "LS": [], "OTHER": []}
    for p in paths:
        layers[classify_tif(p)].append(p)
    for pol in ["VV", "VH"]:
        if len(layers[pol]) != 1:
            raise RuntimeError(f"Expected one {pol} raster, found: {layers[pol]}")
    return layers


def raster_metadata(path: Path):
    with rasterio.open(path) as ds:
        b = ds.bounds
        return {
            "file": str(path),
            "driver": ds.driver,
            "crs": str(ds.crs),
            "width": ds.width,
            "height": ds.height,
            "res_x": ds.res[0],
            "res_y": ds.res[1],
            "count": ds.count,
            "dtype": str(ds.dtypes[0]),
            "nodata": ds.nodata,
            "bounds": [b.left, b.bottom, b.right, b.top],
        }


def das_shapes_in_target(das):
    return [mapping(das)]


def target_inside_mask(das, grid):
    # True inside DAS.
    return geometry_mask(
        das_shapes_in_target(das),
        out_shape=(grid["height"], grid["width"]),
        transform=grid["transform"],
        invert=True,
        all_touched=False,
    )


def align_raster(src_path: Path, grid, inside_mask, resampling=Resampling.bilinear):
    dst = np.full((grid["height"], grid["width"]), np.nan, dtype="float32")
    with rasterio.open(src_path) as src:
        src_arr = src.read(1, masked=True).astype("float32")
        src_data = src_arr.filled(np.nan)
        reproject(
            source=src_data,
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=np.nan,
            dst_transform=grid["transform"],
            dst_crs=TARGET_CRS,
            dst_nodata=np.nan,
            resampling=resampling,
            num_threads=2,
        )
    dst[~inside_mask] = np.nan
    return dst


def write_float(path: Path, arr: np.ndarray, grid, description=""):
    data = np.where(np.isfinite(arr), arr, NODATA).astype("float32")
    profile = {
        "driver": "GTiff",
        "height": grid["height"],
        "width": grid["width"],
        "count": 1,
        "dtype": "float32",
        "crs": TARGET_CRS,
        "transform": grid["transform"],
        "nodata": NODATA,
        "compress": "deflate",
        "predictor": 3,
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)
        if description:
            dst.set_band_description(1, description)
        dst.update_tags(
            AREA="DAS Batang Kuranji",
            STAGE="4",
            TARGET_RESOLUTION_M=str(TARGET_RES),
        )


def power_to_db(power):
    out = np.full(power.shape, np.nan, dtype="float32")
    valid = np.isfinite(power) & (power > 0)
    out[valid] = 10.0 * np.log10(power[valid])
    return out


def nanmedian_window(values):
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return np.nan
    return float(np.median(finite))


def median3(arr):
    # Generic filter is deliberate so NaN pixels outside the DAS do not bleed
    # artificial NODATA values into edge pixels.
    return generic_filter(arr, nanmedian_window, size=3, mode="constant", cval=np.nan).astype("float32")


def stats(arr):
    x = arr[np.isfinite(arr)]
    if x.size == 0:
        return {"n": 0}
    q = np.percentile(x, [1, 5, 25, 50, 75, 95, 99])
    return {
        "n": int(x.size),
        "min": float(np.min(x)),
        "p01": float(q[0]),
        "p05": float(q[1]),
        "p25": float(q[2]),
        "median": float(q[3]),
        "mean": float(np.mean(x)),
        "p75": float(q[4]),
        "p95": float(q[5]),
        "p99": float(q[6]),
        "max": float(np.max(x)),
        "std": float(np.std(x)),
    }


def pair_valid(a, b):
    return np.isfinite(a) & np.isfinite(b)


def diff(a, b):
    """Return a-b where both are valid."""
    out = np.full(a.shape, np.nan, dtype="float32")
    m = pair_valid(a, b)
    out[m] = a[m] - b[m]
    return out


def write_stats_csv(path: Path, records):
    fields = ["layer", "n", "min", "p01", "p05", "p25", "median", "mean", "p75", "p95", "p99", "max", "std"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for name, st in records:
            row = {"layer": name}
            row.update(st)
            w.writerow(row)


def main():
    print("=== KURANJI STAGE 4 SENTINEL-1 RTC CHANGE PROCESSING ===")
    das = load_das_utm()
    grid = build_target_grid(das)
    inside = target_inside_mask(das, grid)

    print(f"Target CRS : EPSG:32747")
    print(f"Target res : {TARGET_RES:.1f} m")
    print(f"Grid       : {grid['width']} x {grid['height']}")
    print(f"DAS pixels : {int(inside.sum())}")

    inventory = {}
    arrays: dict[str, dict[str, np.ndarray]] = {}
    stats_records = []

    for role in ["PRE", "EVENT", "POST"]:
        z = find_role_zip(role)
        print(f"\n[{role}] ZIP: {z.name} ({z.stat().st_size / (1024**3):.3f} GiB)")
        paths = extract_tifs(z, role)
        layers = discover_layers(paths)
        inventory[role] = {
            "zip": str(z),
            "zip_size_bytes": z.stat().st_size,
            "tifs": {k: [str(p) for p in v] for k, v in layers.items()},
            "metadata": {str(p): raster_metadata(p) for p in paths},
        }
        print("  TIFF classes:", {k: len(v) for k, v in layers.items()})

        arrays[role] = {}
        for pol in ["VV", "VH"]:
            arr_power = align_raster(layers[pol][0], grid, inside, Resampling.bilinear)
            # Power <= 0 is not physically meaningful for log transform.
            arr_power[~np.isfinite(arr_power) | (arr_power <= 0)] = np.nan
            arr_db = power_to_db(arr_power)
            arr_db_med3 = median3(arr_db)
            arr_db_med3[~inside] = np.nan

            arrays[role][f"{pol}_POWER"] = arr_power
            arrays[role][f"{pol}_DB"] = arr_db
            arrays[role][f"{pol}_DB_MED3"] = arr_db_med3

            write_float(ALIGNED / f"{role}_{pol}_gamma0_power_20m_DAS.tif", arr_power, grid, f"{role} {pol} gamma0 power")
            write_float(ALIGNED / f"{role}_{pol}_gamma0_dB_20m_DAS.tif", arr_db, grid, f"{role} {pol} gamma0 dB")
            write_float(ALIGNED / f"{role}_{pol}_gamma0_dB_med3_20m_DAS.tif", arr_db_med3, grid, f"{role} {pol} gamma0 dB 3x3 median")
            stats_records.append((f"{role}_{pol}_DB", stats(arr_db)))
            stats_records.append((f"{role}_{pol}_DB_MED3", stats(arr_db_med3)))

        # Optional incidence map, for comparability QC only.
        if len(layers["INC"]) == 1:
            inc = align_raster(layers["INC"][0], grid, inside, Resampling.bilinear)
            arrays[role]["INC"] = inc
            write_float(ALIGNED / f"{role}_incidence_angle_20m_DAS.tif", inc, grid, f"{role} incidence angle")
            stats_records.append((f"{role}_INC", stats(inc)))

        # VH/VV ratio in dB = VH_dB - VV_dB.
        ratio = diff(arrays[role]["VH_DB"], arrays[role]["VV_DB"])
        ratio_med3 = diff(arrays[role]["VH_DB_MED3"], arrays[role]["VV_DB_MED3"])
        arrays[role]["VH_VV_DB"] = ratio
        arrays[role]["VH_VV_DB_MED3"] = ratio_med3
        write_float(ALIGNED / f"{role}_VHminusVV_dB_20m_DAS.tif", ratio, grid, f"{role} VH minus VV dB")
        write_float(ALIGNED / f"{role}_VHminusVV_dB_med3_20m_DAS.tif", ratio_med3, grid, f"{role} VH minus VV dB 3x3 median")
        stats_records.append((f"{role}_VHminusVV_DB", stats(ratio)))
        stats_records.append((f"{role}_VHminusVV_DB_MED3", stats(ratio_med3)))

    print("\nComputing temporal dB differences...")
    comparisons = [
        ("EVENT_MINUS_PRE", "EVENT", "PRE"),
        ("POST_MINUS_PRE", "POST", "PRE"),
        ("POST_MINUS_EVENT", "POST", "EVENT"),
    ]
    for label, later, earlier in comparisons:
        for pol in ["VV", "VH"]:
            raw = diff(arrays[later][f"{pol}_DB"], arrays[earlier][f"{pol}_DB"])
            med3 = diff(arrays[later][f"{pol}_DB_MED3"], arrays[earlier][f"{pol}_DB_MED3"])
            write_float(CHANGE / f"{label}_{pol}_dB_20m_DAS.tif", raw, grid, f"{label} {pol} dB difference")
            write_float(CHANGE / f"{label}_{pol}_dB_med3_20m_DAS.tif", med3, grid, f"{label} {pol} dB difference 3x3 median")
            stats_records.append((f"{label}_{pol}_DB", stats(raw)))
            stats_records.append((f"{label}_{pol}_DB_MED3", stats(med3)))

        ratio_raw = diff(arrays[later]["VH_VV_DB"], arrays[earlier]["VH_VV_DB"])
        ratio_med = diff(arrays[later]["VH_VV_DB_MED3"], arrays[earlier]["VH_VV_DB_MED3"])
        write_float(CHANGE / f"{label}_VHminusVV_dB_20m_DAS.tif", ratio_raw, grid, f"{label} VH minus VV dB difference")
        write_float(CHANGE / f"{label}_VHminusVV_dB_med3_20m_DAS.tif", ratio_med, grid, f"{label} VH minus VV dB difference 3x3 median")
        stats_records.append((f"{label}_VHminusVV_DB", stats(ratio_raw)))
        stats_records.append((f"{label}_VHminusVV_DB_MED3", stats(ratio_med)))

    # Incidence-map comparability checks where all are available.
    incidence_qc = {}
    if all("INC" in arrays[r] for r in ["PRE", "EVENT", "POST"]):
        for label, later, earlier in comparisons:
            d = diff(arrays[later]["INC"], arrays[earlier]["INC"])
            incidence_qc[label] = stats(d)
            write_float(QC / f"{label}_incidence_angle_diff_20m_DAS.tif", d, grid, f"{label} incidence angle difference")

    transform = grid["transform"]
    grid_json = {
        "crs": "EPSG:32747",
        "resolution_m": TARGET_RES,
        "width": grid["width"],
        "height": grid["height"],
        "bounds": [grid["left"], grid["bottom"], grid["right"], grid["top"]],
        "transform": [transform.a, transform.b, transform.c, transform.d, transform.e, transform.f],
        "das_pixels": int(inside.sum()),
        "approx_das_grid_area_km2": float(inside.sum() * TARGET_RES * TARGET_RES / 1e6),
    }

    (QC / "source_inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    (QC / "grid_qc.json").write_text(json.dumps(grid_json, ensure_ascii=False, indent=2), encoding="utf-8")
    (QC / "incidence_comparability.json").write_text(json.dumps(incidence_qc, ensure_ascii=False, indent=2), encoding="utf-8")
    write_stats_csv(QC / "descriptive_statistics.csv", stats_records)

    readme = """# Kuranji Stage 4 — Sentinel-1 RTC change rasters\n\n"
    readme += "Three matched Sentinel-1A ascending orbit-142 VV+VH RTC scenes were aligned to a common 20 m EPSG:32747 grid and clipped to the DAS Batang Kuranji.\n\n"
    readme += "Primary evidence layers are raw aligned gamma0 dB rasters and temporal dB differences. A 3x3 NaN-aware median derivative is included only as a sensitivity/visual layer.\n\n"
    readme += "No flood/change threshold has been selected here. Classification, if undertaken, must be independently evaluated against the BIG/BRIN observed flood extent and must not tune on the same reference without clearly separating calibration from validation.\n"
    (OUT / "README.md").write_text(readme, encoding="utf-8")

    print("\n=== DONE ===")
    print("Aligned rasters :", ALIGNED)
    print("Change rasters  :", CHANGE)
    print("QC/statistics   :", QC)
    print("Statistics CSV  :", QC / "descriptive_statistics.csv")
    print("NEXT: inspect change distributions and overlay them with the frozen BIG/BRIN observed extent and P175 baseline candidate; do not threshold before that QC.")


if __name__ == "__main__":
    main()
