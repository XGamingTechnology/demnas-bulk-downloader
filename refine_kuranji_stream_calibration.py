#!/usr/bin/env python3
"""Refine Kuranji stream-threshold calibration beyond the initial 0.1-2.0 km2 sweep.

Why this script exists
----------------------
The first calibration sweep showed harmonic F1 increasing monotonically up to the
largest tested threshold (2.0 km2). Therefore 2.0 km2 cannot yet be treated as an
optimum. This script extends the search range and adds simple topology diagnostics.

It also reports connected fill-depth hotspots (>5 m and >10 m) inside the DAS so
large conditioning adjustments can be inspected spatially before adopting the
hydrology baseline.

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
  stream_threshold_refined.json
  FILL_HOTSPOTS_GT5M.geojson
  FILL_HOTSPOTS_GT10M.geojson
  STREAM_REFINED_<area>KM2.tif
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from scipy.ndimage import (
    center_of_mass,
    distance_transform_edt,
    label,
    sum as ndi_sum,
    maximum as ndi_maximum,
)
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

RESULT_JSON = OUT / "stream_threshold_refined.json"
HOTSPOTS_5 = OUT / "FILL_HOTSPOTS_GT5M.geojson"
HOTSPOTS_10 = OUT / "FILL_HOTSPOTS_GT10M.geojson"

# Extended search. Dense enough around the initial boundary while still testing
# materially larger drainage areas.
AREA_THRESHOLDS_KM2 = [
    2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 7.5, 10.0, 12.5, 15.0, 20.0,
]
TOLERANCES_M = [25.0, 50.0, 100.0]

# 8-neighbour connectivity for raster stream/fill components.
STRUCTURE_8 = np.ones((3, 3), dtype=np.uint8)


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


def fraction_near(source_mask, distance_to_target_m, tolerance_m):
    n = int(np.count_nonzero(source_mask))
    if n == 0:
        return 0.0
    return float(np.count_nonzero(source_mask & (distance_to_target_m <= tolerance_m)) / n)


def harmonic(a, b):
    return 0.0 if (a + b) == 0 else float(2.0 * a * b / (a + b))


def topology_summary(mask: np.ndarray):
    labelled, ncomp = label(mask, structure=STRUCTURE_8)
    n = int(np.count_nonzero(mask))
    if n == 0:
        return {
            "connected_components_8n": 0,
            "largest_component_cells": 0,
            "largest_component_fraction": 0.0,
        }

    counts = np.bincount(labelled.ravel())
    if counts.size <= 1:
        largest = n
    else:
        largest = int(counts[1:].max())
    return {
        "connected_components_8n": int(ncomp),
        "largest_component_cells": largest,
        "largest_component_fraction": float(largest / n),
    }


def fill_hotspots_geojson(mask, fill_delta, transform, cell_area, crs_text, min_cells=3):
    labelled, ncomp = label(mask, structure=STRUCTURE_8)
    if ncomp == 0:
        return {
            "type": "FeatureCollection",
            "name": "fill_hotspots",
            "crs": {"type": "name", "properties": {"name": crs_text}},
            "features": [],
        }

    ids = np.arange(1, ncomp + 1)
    counts = ndi_sum(np.ones(mask.shape, dtype=np.uint8), labelled, ids)
    max_depths = ndi_maximum(fill_delta, labelled, ids)
    centres = center_of_mass(np.ones(mask.shape, dtype=np.uint8), labelled, ids)

    features = []
    for comp_id, count, max_depth, centre in zip(ids, counts, max_depths, centres):
        count = int(count)
        if count < min_cells or centre is None or np.any(np.isnan(centre)):
            continue
        row, col = centre
        x, y = rasterio.transform.xy(transform, row, col, offset="center")
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(x), float(y)]},
            "properties": {
                "component_id": int(comp_id),
                "cells": count,
                "area_m2": float(count * cell_area),
                "area_ha": float(count * cell_area / 10000.0),
                "max_fill_m": float(max_depth),
            },
        })

    features.sort(key=lambda f: (f["properties"]["max_fill_m"], f["properties"]["cells"]), reverse=True)
    return {
        "type": "FeatureCollection",
        "name": "fill_hotspots",
        "crs": {"type": "name", "properties": {"name": crs_text}},
        "features": features,
    }


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
        sampling = (ry, rx)

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

        fill_delta = filled - dem
        for depth, path in [(5.0, HOTSPOTS_5), (10.0, HOTSPOTS_10)]:
            fc = fill_hotspots_geojson(
                valid & (fill_delta > depth),
                fill_delta,
                dem_ds.transform,
                cell_area,
                str(dem_ds.crs),
                min_cells=3,
            )
            with path.open("w", encoding="utf-8") as f:
                json.dump(fc, f, indent=2)

        dist_to_rbi = distance_transform_edt(~rbi_mask, sampling=sampling)

        candidates = []
        for area_km2 in AREA_THRESHOLDS_KM2:
            minimum_cells = int(math.ceil(area_km2 * 1_000_000.0 / cell_area))
            model_mask = valid & (accum >= minimum_cells)
            model_path = OUT / f"STREAM_REFINED_{area_km2:.2f}KM2.tif"
            write_byte_raster(model_path, model_mask, dem_ds)

            dist_to_model = distance_transform_edt(~model_mask, sampling=sampling)
            metrics = {}
            for tol in TOLERANCES_M:
                model_near = fraction_near(model_mask, dist_to_rbi, tol)
                rbi_near = fraction_near(rbi_mask, dist_to_model, tol)
                metrics[f"{int(tol)}m"] = {
                    "model_near_rbi_fraction": model_near,
                    "rbi_near_model_fraction": rbi_near,
                    "harmonic_f1": harmonic(model_near, rbi_near),
                }

            topo = topology_summary(model_mask)
            candidates.append({
                "threshold_area_km2": area_km2,
                "minimum_cells": minimum_cells,
                "model_stream_cells": int(np.count_nonzero(model_mask)),
                "model_stream_cell_area_km2": float(np.count_nonzero(model_mask) * cell_area / 1_000_000.0),
                "topology": topo,
                "metrics": metrics,
                "raster": str(model_path.relative_to(ROOT)),
            })

        best = {}
        for tol in TOLERANCES_M:
            key = f"{int(tol)}m"
            ranked = sorted(candidates, key=lambda c: c["metrics"][key]["harmonic_f1"], reverse=True)
            best[key] = {
                "threshold_area_km2": ranked[0]["threshold_area_km2"],
                "minimum_cells": ranked[0]["minimum_cells"],
                "harmonic_f1": ranked[0]["metrics"][key]["harmonic_f1"],
                "model_near_rbi_fraction": ranked[0]["metrics"][key]["model_near_rbi_fraction"],
                "rbi_near_model_fraction": ranked[0]["metrics"][key]["rbi_near_model_fraction"],
                "largest_component_fraction": ranked[0]["topology"]["largest_component_fraction"],
            }

        result = {
            "grid": {
                "crs": str(dem_ds.crs),
                "resolution_m": [rx, ry],
                "cell_area_m2": cell_area,
            },
            "reference": {
                "rbi_raster_cells_inside_das": int(np.count_nonzero(rbi_mask)),
            },
            "thresholds_tested_km2": AREA_THRESHOLDS_KM2,
            "tolerances_m": TOLERANCES_M,
            "candidates": candidates,
            "best_harmonic_f1_by_tolerance": best,
            "fill_hotspot_files": {
                ">5m": str(HOTSPOTS_5.relative_to(ROOT)),
                ">10m": str(HOTSPOTS_10.relative_to(ROOT)),
            },
            "selection_note": (
                "Do not adopt a threshold merely because it is the largest tested value. "
                "Prefer an interior optimum with acceptable RBI agreement and coherent network topology; "
                "inspect the main Kuranji channel in QGIS before final adoption."
            ),
        }

    with RESULT_JSON.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print("=== REFINED STREAM CALIBRATION ===")
    print(f"Cell area: {cell_area:.6f} m2")
    print(f"RBI cells: {int(np.count_nonzero(rbi_mask)):,}")
    print("\nThreshold comparison:")
    for c in candidates:
        m25 = c["metrics"]["25m"]["harmonic_f1"]
        m50 = c["metrics"]["50m"]["harmonic_f1"]
        m100 = c["metrics"]["100m"]["harmonic_f1"]
        topo = c["topology"]
        print(
            f" {c['threshold_area_km2']:>5.1f} km2 | {c['minimum_cells']:>7,} cells | "
            f"F1: {m25:.4f}/{m50:.4f}/{m100:.4f} | "
            f"components={topo['connected_components_8n']:,} | "
            f"largest={topo['largest_component_fraction']:.3f}"
        )

    print("\nBest diagnostic by tolerance:")
    for key, row in best.items():
        print(
            f" {key}: {row['threshold_area_km2']:.2f} km2 | "
            f"F1={row['harmonic_f1']:.4f} | "
            f"model->RBI={row['model_near_rbi_fraction']:.4f} | "
            f"RBI->model={row['rbi_near_model_fraction']:.4f} | "
            f"largest-component={row['largest_component_fraction']:.3f}"
        )

    print("\nHotspots >5m :", HOTSPOTS_5)
    print("Hotspots >10m:", HOTSPOTS_10)
    print("JSON          :", RESULT_JSON)


if __name__ == "__main__":
    main()
