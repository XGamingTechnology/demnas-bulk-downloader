#!/usr/bin/env python3
"""Baseline hydrology workflow for DAS Kuranji DEMNAS.

Inputs
------
data/work/kuranji/01_prepared/DEMNAS_KURANJI_BUFFER3KM_UTM47S.tif

Outputs
-------
data/work/kuranji/02_hydrology/
  00_DEM_WBT_INPUT.tif
  01_DEM_FILLED.tif
  02_D8_POINTER.tif
  03_FLOW_ACCUM_CELLS.tif
  04_FLOW_ACCUM_CA_M2.tif
  hydrology_qc.json

Method
------
1. Validate projected DEM (EPSG:32747).
2. Rewrite the source DEM to a WhiteboxTools-compatible GeoTIFF. This removes
   floating-point TIFF PREDICTOR=3, which WhiteboxTools 2.4.0 cannot read.
3. Fill depressions and resolve flats using WhiteboxTools FillDepressions.
4. Generate Whitebox-style D8 flow pointer.
5. Generate D8 flow accumulation as upstream cell count and catchment area.
6. Write QC statistics and area-to-cell thresholds for later stream calibration.

Important: stream thresholds are NOT selected here. They must be calibrated against
RBI river data before a final stream network is adopted.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import rasterio
from whitebox import WhiteboxTools

ROOT = Path(__file__).resolve().parent
PREP = ROOT / "data/work/kuranji/01_prepared"
OUT = ROOT / "data/work/kuranji/02_hydrology"
OUT.mkdir(parents=True, exist_ok=True)

DEM = PREP / "DEMNAS_KURANJI_BUFFER3KM_UTM47S.tif"
WBT_INPUT = OUT / "00_DEM_WBT_INPUT.tif"
FILLED = OUT / "01_DEM_FILLED.tif"
POINTER = OUT / "02_D8_POINTER.tif"
ACC_CELLS = OUT / "03_FLOW_ACCUM_CELLS.tif"
ACC_CA = OUT / "04_FLOW_ACCUM_CA_M2.tif"
QC_JSON = OUT / "hydrology_qc.json"

EXPECTED_EPSG = 32747
POINTER_VALUES = {0, 1, 2, 4, 8, 16, 32, 64, 128}


def valid_mask(ds, arr):
    m = np.isfinite(arr)
    if ds.nodata is not None and np.isfinite(ds.nodata):
        m &= ~np.isclose(arr, ds.nodata)
    return m


def raster_stats(path: Path):
    with rasterio.open(path) as ds:
        a = ds.read(1).astype("float64", copy=False)
        valid = valid_mask(ds, a)
        x = a[valid]
        if x.size == 0:
            raise RuntimeError(f"Raster tidak memiliki pixel valid: {path}")
        return {
            "path": str(path.relative_to(ROOT)),
            "crs": str(ds.crs),
            "width": ds.width,
            "height": ds.height,
            "resolution": [float(ds.res[0]), float(ds.res[1])],
            "nodata": None if ds.nodata is None else float(ds.nodata),
            "image_structure": ds.tags(ns="IMAGE_STRUCTURE"),
            "valid_pixels": int(x.size),
            "min": float(np.min(x)),
            "mean": float(np.mean(x)),
            "median": float(np.median(x)),
            "max": float(np.max(x)),
            "p99": float(np.percentile(x, 99)),
        }


def check_dem():
    if not DEM.exists():
        raise FileNotFoundError(f"DEM tidak ditemukan: {DEM}")

    with rasterio.open(DEM) as ds:
        if ds.crs is None or ds.crs.to_epsg() != EXPECTED_EPSG:
            raise RuntimeError(f"CRS DEM harus EPSG:{EXPECTED_EPSG}; ditemukan {ds.crs}")
        rx, ry = map(abs, ds.res)
        if not np.isclose(rx, ry, rtol=1e-6, atol=1e-9):
            raise RuntimeError(f"Pixel DEM tidak square: {ds.res}")
        a = ds.read(1).astype("float64", copy=False)
        valid = valid_mask(ds, a)
        x = a[valid]
        if x.size == 0:
            raise RuntimeError("DEM tidak memiliki pixel valid")
        if np.any(np.abs(x) > 1e6):
            raise RuntimeError("DEM masih mengandung nilai sentinel/extreme")
        return rx, ry, int(x.size), ds.tags(ns="IMAGE_STRUCTURE")


def create_wbt_compatible_input():
    """Rewrite DEM as a simple uncompressed GeoTIFF readable by WhiteboxTools.

    Rasterio/GDAL can read the prepared source with DEFLATE + PREDICTOR=3, but
    WhiteboxTools 2.4.0 panics on floating-point predictor 3. We therefore make
    a deterministic, lossless copy with identical grid/values/NoData and no
    TIFF predictor/compression before invoking WhiteboxTools.
    """
    print("\n[0/4] Membuat GeoTIFF kompatibel WhiteboxTools")
    with rasterio.open(DEM) as src:
        profile = src.profile.copy()

        # Remove creation options inherited from the compressed source.
        for key in (
            "compress",
            "predictor",
            "tiled",
            "blockxsize",
            "blockysize",
            "interleave",
        ):
            profile.pop(key, None)

        profile.update(
            driver="GTiff",
            dtype=src.dtypes[0],
            count=1,
            crs=src.crs,
            transform=src.transform,
            width=src.width,
            height=src.height,
            nodata=src.nodata,
            BIGTIFF="IF_SAFER",
        )

        with rasterio.open(WBT_INPUT, "w", **profile) as dst:
            for _, window in src.block_windows(1):
                dst.write(src.read(1, window=window), 1, window=window)

    with rasterio.open(WBT_INPUT) as ds:
        tags = ds.tags(ns="IMAGE_STRUCTURE")
        predictor = str(tags.get("PREDICTOR", "")).strip()
        if predictor == "3":
            raise RuntimeError(
                "GeoTIFF compatibility rewrite masih menghasilkan PREDICTOR=3"
            )
        if ds.crs is None or ds.crs.to_epsg() != EXPECTED_EPSG:
            raise RuntimeError(f"CRS WBT input berubah: {ds.crs}")

    print("WBT input    :", WBT_INPUT)
    print("TIFF tags    :", tags if tags else "{}")


def require_success(name: str, rc, output: Path):
    if rc not in (0, None):
        raise RuntimeError(f"WhiteboxTools gagal pada {name}; return code={rc}")
    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError(f"Output {name} tidak terbentuk: {output}")


def fill_difference_stats():
    with rasterio.open(DEM) as a_ds, rasterio.open(FILLED) as b_ds:
        a = a_ds.read(1).astype("float64", copy=False)
        b = b_ds.read(1).astype("float64", copy=False)
        valid = valid_mask(a_ds, a) & valid_mask(b_ds, b)
        d = b[valid] - a[valid]
        return {
            "compared_pixels": int(d.size),
            "changed_pixels_gt_1e-6m": int(np.count_nonzero(np.abs(d) > 1e-6)),
            "raised_pixels_gt_1e-6m": int(np.count_nonzero(d > 1e-6)),
            "lowered_pixels_lt_minus_1e-6m": int(np.count_nonzero(d < -1e-6)),
            "mean_delta_m": float(np.mean(d)),
            "max_raise_m": float(np.max(d)),
            "min_delta_m": float(np.min(d)),
        }


def pointer_qc():
    with rasterio.open(POINTER) as ds:
        a = ds.read(1).astype("float64", copy=False)
        valid = valid_mask(ds, a)
        vals, counts = np.unique(a[valid].astype("int64"), return_counts=True)
        unknown = sorted(set(map(int, vals)) - POINTER_VALUES)
        return {
            "values": {str(int(v)): int(c) for v, c in zip(vals, counts)},
            "unexpected_values": unknown,
        }


def main():
    rx, ry, n_valid, src_tags = check_dem()
    cell_area = rx * ry

    print("=== KURANJI HYDROLOGY BASELINE ===")
    print("Input       :", DEM)
    print("CRS         : EPSG:32747")
    print("Resolution  :", rx, "m")
    print("Cell area   :", cell_area, "m2")
    print("Valid cells :", f"{n_valid:,}")
    print("Source TIFF :", src_tags if src_tags else "{}")

    create_wbt_compatible_input()

    wbt = WhiteboxTools()
    wbt.set_verbose_mode(True)
    # Keep Whitebox outputs uncompressed for maximum cross-tool compatibility.
    wbt.set_compress_rasters(False)

    print("\n[1/4] Fill depressions + resolve flats")
    rc = wbt.fill_depressions(
        dem=str(WBT_INPUT),
        output=str(FILLED),
        fix_flats=True,
    )
    require_success("FillDepressions", rc, FILLED)

    print("\n[2/4] D8 pointer")
    rc = wbt.d8_pointer(
        dem=str(FILLED),
        output=str(POINTER),
        esri_pntr=False,
    )
    require_success("D8Pointer", rc, POINTER)

    print("\n[3/4] D8 flow accumulation - cells")
    rc = wbt.d8_flow_accumulation(
        i=str(POINTER),
        output=str(ACC_CELLS),
        out_type="cells",
        log=False,
        clip=False,
        pntr=True,
        esri_pntr=False,
    )
    require_success("D8FlowAccumulation cells", rc, ACC_CELLS)

    print("\n[4/4] D8 flow accumulation - catchment area")
    rc = wbt.d8_flow_accumulation(
        i=str(POINTER),
        output=str(ACC_CA),
        out_type="catchment area",
        log=False,
        clip=False,
        pntr=True,
        esri_pntr=False,
    )
    require_success("D8FlowAccumulation catchment area", rc, ACC_CA)

    thresholds = {}
    for km2 in (0.25, 0.50, 1.00):
        cells = math.ceil(km2 * 1_000_000.0 / cell_area)
        thresholds[f"{km2:.2f}_km2"] = {
            "area_m2": km2 * 1_000_000.0,
            "minimum_cells": cells,
        }

    qc = {
        "method": {
            "compatibility_rewrite": (
                "Source DEM rewritten losslessly to uncompressed GeoTIFF because "
                "WhiteboxTools 2.4.0 cannot read floating-point TIFF PREDICTOR=3"
            ),
            "conditioning": "WhiteboxTools FillDepressions, fix_flats=True",
            "flow_direction": "D8Pointer, Whitebox pointer convention",
            "flow_accumulation": "D8FlowAccumulation",
            "accumulation_units": ["cells", "catchment area"],
        },
        "cell_area_m2": cell_area,
        "candidate_stream_thresholds_for_calibration_only": thresholds,
        "input": raster_stats(DEM),
        "wbt_input": raster_stats(WBT_INPUT),
        "filled": raster_stats(FILLED),
        "fill_change": fill_difference_stats(),
        "pointer": raster_stats(POINTER),
        "pointer_qc": pointer_qc(),
        "flow_accum_cells": raster_stats(ACC_CELLS),
        "flow_accum_catchment_area": raster_stats(ACC_CA),
    }

    with QC_JSON.open("w", encoding="utf-8") as f:
        json.dump(qc, f, indent=2)

    print("\n=== DONE ===")
    print("WBT input      :", WBT_INPUT)
    print("Filled DEM     :", FILLED)
    print("D8 pointer     :", POINTER)
    print("Flow accum     :", ACC_CELLS)
    print("Catchment area :", ACC_CA)
    print("QC JSON        :", QC_JSON)
    print("\nCandidate stream thresholds (not final):")
    for k, v in thresholds.items():
        print(f"  {k}: >= {v['minimum_cells']:,} cells")


if __name__ == "__main__":
    main()
