#!/usr/bin/env python3
"""Calibrate DEM-derived stream thresholds against RBI river lines for DAS Kuranji.

This script does NOT assume a final stream initiation threshold. It evaluates a
set of contributing-area thresholds against the prepared RBI river network and
also audits FillDepressions depth inside the reference DAS.

Inputs
------
data/work/kuranji/01_prepared/DAS_KURANJI_UTM47S.geojson
data/work/kuranji/01_prepared/SUNGAI_RBI_DAS_KURANJI_UTM47S.geojson
data/work/kuranji/01_prepared/DEMNAS_KURANJI_BUFFER3KM_UTM47S.tif
data/work/kuranji/02_hydrology/01_DEM_FILLED.tif
data/work/kuranji/02_hydrology/03_FLOW_ACCUM_CELLS.tif

Outputs
-------
data/work/kuranji/05_validation/
  FILL_DEPTH_DAS_KURANJI.tif
  RBI_STREAM_REFERENCE_RASTER.tif
  STREAM_THRESHOLD_<area>KM2.tif
  stream_threshold_calibration.json

Calibration metrics
-------------------
For each threshold and tolerance (25, 50, 100 m):
- model_near_rbi_fraction: fraction of modeled stream cells within tolerance of RBI
- rbi_near_model_fraction: fraction of RBI raster cells within tolerance of model
- harmonic_f1: harmonic mean of the two fractions

The metrics are diagnostic. A final threshold should be selected after checking
both quantitative agreement and map topology, especially the main Kuranji channel.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from scipy.ndimage import distance_transform_edt
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent
PREP = ROOT / "data/work/kuranji/01_prepared"
HYD = ROOT / "data/work/kuranji/02_hydrology"
OUT = ROOT / "data/work/kuranji/05_validation"
OUT.mkdir(parents=True, exist_ok=True)

DAS = PREP / "DAS_KURANJI_UTM47S.geojson"
RBI = PREP / "SUNGAI_RBI_DAS_KURANJI_UTM47S.geojson"
DEM = PREP / "DEMNAS_KURANJI_BUFFER3KM_UTM47S.tif"
FILLED = HYD / "01_DEM_FILLED.tif"
ACC = HYD / "03_FLOW_ACCUM_CELLS.tif"

FILL_DEPTH = OUT / "FILL_DEPTH_DAS_KURANJI.tif"
RBI_RASTER = OUT / "RBI_STREAM_REFERENCE_RASTER.tif"
CALIBRATION_JSON = OUT / "stream_threshold_calibration.json"

AREA_THRESHOLDS_KM2 = [0.10, 0.25, 0.50, 0.75, 1.00, 1.50, 2.00]
TOLERANCES_M = [25.0, 50.0, 100.0]


def load_geometries(path: Path):
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    geoms = [shape(feat["geometry"]) for feat in data.get("features", []) if feat.get("geometry")]
    if not geoms:
        raise RuntimeError(f"Tidak ada geometry pada {path}")
    return geoms


def assert_same_grid(*datasets):
    ref = datasets[0]
    for ds in datasets[1:]:
        if ds.width != ref.width or ds.height != ref.height:
            raise RuntimeError("Raster dimensions berbeda")
        if ds.crs != ref.crs:
            raise RuntimeError(f"CRS raster berbeda: {ref.crs} vs {ds.crs}")
        if not ds.transform.almost_equals(ref.transform):
            raise RuntimeError("Raster transform/grid berbeda")


def write_byte_raster(path: Path, arr: np.ndarray, ref):
    profile = ref.profile.copy()
    profile.update(
        driver="GTiff",
        dtype="uint8",
        count=1,
        nodata=0,
        compress="DEFLATE",
        tiled=True,
        blockxsize=512,
        blockysize=512,
    )
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr.astype("uint8"), 1)


def write_float_raster(path: Path, arr: np.ndarray, ref):
    profile = ref.profile.copy()
    profile.update(
        driver="GTiff",
        dtype="float32",
        count=1,
        nodata=-9999.0,
        compress="DEFLATE",
        predictor=3,
        tiled=True,
        blockxsize=512,
        blockysize=512,
    )
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr.astype("float32"), 1)


def fraction_near(source_mask, distance_to_target_m, tolerance_m):
    n = int(np.count_nonzero(source_mask))
    if n == 0:
        return 0.0
    return float(np.count_nonzero(source_mask & (distance_to_target_m <= tolerance_m)) / n)


def harmonic(a, b):
    return 0.0 if (a + b) == 0 else float(2.0 * a * b / (a + b))


def main():
    for p in [DAS, RBI, DEM, FILLED, ACC]:
        if not p.exists():
            raise FileNotFoundError(p)

    das_geoms = load_geometries(DAS)
    rbi_geoms = load_geometries(RBI)

    with rasterio.open(DEM) as dem_ds, rasterio.open(FILLED) as fill_ds, rasterio.open(ACC) as acc_ds:
        assert_same_grid(dem_ds, fill_ds, acc_ds)

        rx, ry = abs(dem_ds.res[0]), abs(dem_ds.res[1])
        cell_area = rx * ry
        sampling = (ry, rx)  # row, col spacing for scipy EDT

        das_mask = rasterize(
            [(g, 1) for g in das_geoms],
            out_shape=(dem_ds.height, dem_ds.width),
            transform=dem_ds.transform,
            fill=0,
            all_touched=False,
            dtype="uint8",
        ).astype(bool)

        rbi_mask = rasterize(
            [(g, 1) for g in rbi_geoms],
            out_shape=(dem_ds.height, dem_ds.width),
            transform=dem_ds.transform,
            fill=0,
            all_touched=True,
            dtype="uint8",
        ).astype(bool)
        rbi_mask &= das_mask

        dem = dem_ds.read(1).astype("float64", copy=False)
        filled = fill_ds.read(1).astype("float64", copy=False)
        accum = acc_ds.read(1).astype("float64", copy=False)

        valid = das_mask & np.isfinite(dem) & np.isfinite(filled) & np.isfinite(accum)
        if dem_ds.nodata is not None:
            valid &= ~np.isclose(dem, dem_ds.nodata)
        if fill_ds.nodata is not None:
            valid &= ~np.isclose(filled, fill_ds.nodata)
        if acc_ds.nodata is not None:
            valid &= ~np.isclose(accum, acc_ds.nodata)

        fill_depth = np.full(dem.shape, -9999.0, dtype="float32")
        fill_delta = filled - dem
        fill_depth[valid] = fill_delta[valid].astype("float32")
        write_float_raster(FILL_DEPTH, fill_depth, dem_ds)
        write_byte_raster(RBI_RASTER, rbi_mask.astype("uint8"), dem_ds)

        fill_vals = fill_delta[valid]
        fill_summary = {
            "valid_das_cells": int(fill_vals.size),
            "das_area_km2_from_raster_mask": float(fill_vals.size * cell_area / 1_000_000.0),
            "mean_fill_m": float(np.mean(fill_vals)),
            "max_fill_m": float(np.max(fill_vals)),
            "percentiles_m": {
                "p50": float(np.percentile(fill_vals, 50)),
                "p90": float(np.percentile(fill_vals, 90)),
                "p95": float(np.percentile(fill_vals, 95)),
                "p99": float(np.percentile(fill_vals, 99)),
                "p99_9": float(np.percentile(fill_vals, 99.9)),
            },
            "depth_classes": {},
        }

        for threshold in [0.001, 0.1, 1, 5, 10, 25, 50, 100]:
            n = int(np.count_nonzero(valid & (fill_delta > threshold)))
            fill_summary["depth_classes"][f">{threshold:g}m"] = {
                "cells": n,
                "area_km2": float(n * cell_area / 1_000_000.0),
                "percent_of_valid_das_cells": float(n / fill_vals.size * 100.0),
            }

        # distance to RBI once, in metres
        dist_to_rbi = distance_transform_edt(~rbi_mask, sampling=sampling)

        candidates = []
        for area_km2 in AREA_THRESHOLDS_KM2:
            minimum_cells = int(math.ceil(area_km2 * 1_000_000.0 / cell_area))
            model_mask = valid & (accum >= minimum_cells)
            model_path = OUT / f"STREAM_THRESHOLD_{area_km2:.2f}KM2.tif"
            write_byte_raster(model_path, model_mask.astype("uint8"), dem_ds)

            # distance to candidate stream, in metres
            dist_to_model = distance_transform_edt(~model_mask, sampling=sampling)

            model_cells = int(np.count_nonzero(model_mask))
            rbi_cells = int(np.count_nonzero(rbi_mask))
            metrics = {}
            for tol in TOLERANCES_M:
                model_near = fraction_near(model_mask, dist_to_rbi, tol)
                rbi_near = fraction_near(rbi_mask, dist_to_model, tol)
                metrics[f"{int(tol)}m"] = {
                    "model_near_rbi_fraction": model_near,
                    "rbi_near_model_fraction": rbi_near,
                    "harmonic_f1": harmonic(model_near, rbi_near),
                }

            candidates.append({
                "threshold_area_km2": area_km2,
                "minimum_cells": minimum_cells,
                "model_stream_cells": model_cells,
                "model_stream_cell_area_km2": float(model_cells * cell_area / 1_000_000.0),
                "rbi_reference_cells": rbi_cells,
                "metrics": metrics,
                "raster": str(model_path.relative_to(ROOT)),
            })

        # Best-by-metric is reported only as an objective diagnostic, not automatically final.
        best = {}
        for tol in TOLERANCES_M:
            key = f"{int(tol)}m"
            ranked = sorted(candidates, key=lambda c: c["metrics"][key]["harmonic_f1"], reverse=True)
            best[key] = {
                "threshold_area_km2": ranked[0]["threshold_area_km2"],
                "minimum_cells": ranked[0]["minimum_cells"],
                "harmonic_f1": ranked[0]["metrics"][key]["harmonic_f1"],
            }

        result = {
            "grid": {
                "crs": str(dem_ds.crs),
                "resolution_m": [rx, ry],
                "cell_area_m2": cell_area,
            },
            "reference": {
                "das": str(DAS.relative_to(ROOT)),
                "rbi_streams": str(RBI.relative_to(ROOT)),
                "rbi_raster_cells_inside_das": int(np.count_nonzero(rbi_mask)),
            },
            "fill_depth_audit": fill_summary,
            "tolerances_m": TOLERANCES_M,
            "candidates": candidates,
            "best_harmonic_f1_by_tolerance": best,
            "selection_note": (
                "Best harmonic F1 is diagnostic only. Inspect topology/main channel and fill-depth hotspots "
                "before adopting a final stream threshold."
            ),
        }

    with CALIBRATION_JSON.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print("=== STREAM THRESHOLD CALIBRATION ===")
    print("Cell area:", f"{cell_area:.6f} m2")
    print("RBI reference raster cells:", result["reference"]["rbi_raster_cells_inside_das"])
    print("\nFill-depth audit inside DAS:")
    print("  mean:", f"{fill_summary['mean_fill_m']:.6f} m")
    print("  max :", f"{fill_summary['max_fill_m']:.3f} m")
    for label, row in fill_summary["depth_classes"].items():
        print(f"  {label:>7}: {row['cells']:,} cells | {row['area_km2']:.4f} km2 | {row['percent_of_valid_das_cells']:.4f}%")

    print("\nThreshold comparison:")
    for c in candidates:
        m25 = c["metrics"]["25m"]["harmonic_f1"]
        m50 = c["metrics"]["50m"]["harmonic_f1"]
        m100 = c["metrics"]["100m"]["harmonic_f1"]
        print(
            f"  {c['threshold_area_km2']:>4.2f} km2 | {c['minimum_cells']:>6,} cells | "
            f"F1 25m={m25:.4f} 50m={m50:.4f} 100m={m100:.4f}"
        )

    print("\nBest diagnostic by tolerance:")
    for k, v in best.items():
        print(f"  {k}: {v['threshold_area_km2']:.2f} km2 ({v['minimum_cells']:,} cells), F1={v['harmonic_f1']:.4f}")

    print("\nJSON:", CALIBRATION_JSON)
    print("Fill depth raster:", FILL_DEPTH)
    print("RBI reference raster:", RBI_RASTER)


if __name__ == "__main__":
    main()
