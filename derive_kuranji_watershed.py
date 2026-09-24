#!/usr/bin/env python3
"""Derive Kuranji watershed from the calibrated D8 network.

Baseline stream threshold: 6.0 km2.
Rationale: among focused candidates (4, 5, 6, 20 km2), 6 km2 gave the best
recall-weighted F2 while preserving a modeled network length close to RBI.

Workflow
--------
1. Build the 6 km2 stream mask inside the reference DAS.
2. Identify outlet candidates near the reference DAS boundary and near RBI streams.
3. Rank candidates by D8 flow accumulation (no hard-coded outlet coordinate).
4. Snap the selected candidate to the local maximum flow accumulation.
5. Create a pour-point raster.
6. Delineate a watershed with WhiteboxTools Watershed.
7. Compare modeled watershed against reference DAS using area, IoU, and Dice.

Outputs
-------
data/work/kuranji/03_watershed/
  STREAM_FINAL_6KM2.tif
  OUTLET_CANDIDATES.geojson
  POUR_POINT_FINAL.tif
  WATERSHED_MODEL.tif
  watershed_validation.json
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from scipy.ndimage import distance_transform_edt, maximum_filter
from shapely.geometry import shape
from whitebox import WhiteboxTools

ROOT = Path(__file__).resolve().parent
PREP = ROOT / "data/work/kuranji/01_prepared"
HYD = ROOT / "data/work/kuranji/02_hydrology"
OUT = ROOT / "data/work/kuranji/03_watershed"
OUT.mkdir(parents=True, exist_ok=True)

DAS = PREP / "DAS_KURANJI_UTM47S.geojson"
RBI = PREP / "SUNGAI_RBI_DAS_KURANJI_UTM47S.geojson"
POINTER = HYD / "02_D8_POINTER.tif"
ACC = HYD / "03_FLOW_ACCUM_CELLS.tif"

STREAM = OUT / "STREAM_FINAL_6KM2.tif"
CANDIDATES = OUT / "OUTLET_CANDIDATES.geojson"
POUR = OUT / "POUR_POINT_FINAL.tif"
WATERSHED = OUT / "WATERSHED_MODEL.tif"
QC = OUT / "watershed_validation.json"

THRESHOLD_KM2 = 6.0
BOUNDARY_TOL_M = 250.0
RBI_TOL_M = 150.0
LOCAL_SNAP_RADIUS_M = 150.0
TOP_N = 20


def load_geoms(path: Path):
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    gs = [shape(ft["geometry"]) for ft in data.get("features", []) if ft.get("geometry")]
    if not gs:
        raise RuntimeError(f"No geometries: {path}")
    return gs


def write_byte(path: Path, arr, ref, nodata=0):
    profile = ref.profile.copy()
    profile.update(
        driver="GTiff",
        dtype="uint8",
        count=1,
        nodata=nodata,
        compress="DEFLATE",
        tiled=True,
        blockxsize=512,
        blockysize=512,
    )
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr.astype("uint8"), 1)


def main():
    for p in [DAS, RBI, POINTER, ACC]:
        if not p.exists():
            raise FileNotFoundError(p)

    das_geoms = load_geoms(DAS)
    rbi_geoms = load_geoms(RBI)

    with rasterio.open(POINTER) as pds, rasterio.open(ACC) as ads:
        if pds.width != ads.width or pds.height != ads.height or pds.crs != ads.crs or not pds.transform.almost_equals(ads.transform):
            raise RuntimeError("Pointer and accumulation grids differ")

        rx, ry = abs(ads.res[0]), abs(ads.res[1])
        cell_area = rx * ry
        sampling = (ry, rx)
        min_cells = int(math.ceil(THRESHOLD_KM2 * 1_000_000.0 / cell_area))

        das_mask = rasterize(
            [(g, 1) for g in das_geoms],
            out_shape=(ads.height, ads.width),
            transform=ads.transform,
            fill=0,
            all_touched=False,
            dtype="uint8",
        ).astype(bool)

        rbi_mask = rasterize(
            [(g, 1) for g in rbi_geoms],
            out_shape=(ads.height, ads.width),
            transform=ads.transform,
            fill=0,
            all_touched=True,
            dtype="uint8",
        ).astype(bool)

        accum = ads.read(1).astype("float64", copy=False)
        valid = np.isfinite(accum)
        if ads.nodata is not None:
            valid &= ~np.isclose(accum, ads.nodata)

        stream = valid & das_mask & (accum >= min_cells)
        write_byte(STREAM, stream, ads)

        # Approximate inside edge of the reference DAS using distance to outside.
        dist_to_outside = distance_transform_edt(das_mask, sampling=sampling)
        near_boundary = das_mask & (dist_to_outside <= BOUNDARY_TOL_M)

        # Require candidates to remain reasonably close to official RBI lines.
        dist_to_rbi = distance_transform_edt(~rbi_mask, sampling=sampling)
        near_rbi = dist_to_rbi <= RBI_TOL_M

        candidate_mask = stream & near_boundary & near_rbi
        rr, cc = np.where(candidate_mask)
        if rr.size == 0:
            raise RuntimeError("No outlet candidates found near DAS boundary and RBI")

        values = accum[rr, cc]
        order = np.argsort(values)[::-1]
        records = []
        for rank, idx in enumerate(order[:TOP_N], start=1):
            r, c = int(rr[idx]), int(cc[idx])
            x, y = rasterio.transform.xy(ads.transform, r, c, offset="center")
            records.append({
                "rank": rank,
                "row": r,
                "col": c,
                "x": float(x),
                "y": float(y),
                "accum_cells": float(accum[r, c]),
                "catchment_area_km2": float(accum[r, c] * cell_area / 1_000_000.0),
                "distance_to_rbi_m": float(dist_to_rbi[r, c]),
                "distance_inside_boundary_m": float(dist_to_outside[r, c]),
            })

        # Start from highest accumulation candidate, then snap to local max.
        best = records[0]
        r0, c0 = best["row"], best["col"]
        radius_rows = max(1, int(math.ceil(LOCAL_SNAP_RADIUS_M / ry)))
        radius_cols = max(1, int(math.ceil(LOCAL_SNAP_RADIUS_M / rx)))
        r1, r2 = max(0, r0 - radius_rows), min(ads.height, r0 + radius_rows + 1)
        c1, c2 = max(0, c0 - radius_cols), min(ads.width, c0 + radius_cols + 1)

        local_acc = accum[r1:r2, c1:c2]
        local_valid = valid[r1:r2, c1:c2] & das_mask[r1:r2, c1:c2]
        local = np.where(local_valid, local_acc, -np.inf)
        lr, lc = np.unravel_index(np.argmax(local), local.shape)
        final_r, final_c = r1 + int(lr), c1 + int(lc)
        fx, fy = rasterio.transform.xy(ads.transform, final_r, final_c, offset="center")

        final = {
            "row": final_r,
            "col": final_c,
            "x": float(fx),
            "y": float(fy),
            "accum_cells": float(accum[final_r, final_c]),
            "catchment_area_km2": float(accum[final_r, final_c] * cell_area / 1_000_000.0),
            "distance_to_rbi_m": float(dist_to_rbi[final_r, final_c]),
            "distance_inside_boundary_m": float(dist_to_outside[final_r, final_c]),
        }

        fc = {
            "type": "FeatureCollection",
            "name": "outlet_candidates",
            "crs": {"type": "name", "properties": {"name": str(ads.crs)}},
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [r["x"], r["y"]]},
                    "properties": r,
                }
                for r in records
            ] + [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [final["x"], final["y"]]},
                    "properties": {"rank": 0, "selected_final": True, **final},
                }
            ],
        }
        with CANDIDATES.open("w", encoding="utf-8") as f:
            json.dump(fc, f, indent=2)

        pour = np.zeros((ads.height, ads.width), dtype="uint8")
        pour[final_r, final_c] = 1
        write_byte(POUR, pour, ads)

    wbt = WhiteboxTools()
    wbt.set_verbose_mode(True)
    wbt.set_compress_rasters(False)
    rc = wbt.watershed(
        d8_pntr=str(POINTER),
        pour_pts=str(POUR),
        output=str(WATERSHED),
        esri_pntr=False,
    )
    if rc not in (0, None) or not WATERSHED.exists():
        raise RuntimeError(f"Whitebox Watershed failed, rc={rc}")

    with rasterio.open(WATERSHED) as wds, rasterio.open(ACC) as ads:
        wat = wds.read(1)
        model = np.isfinite(wat)
        if wds.nodata is not None:
            model &= ~np.isclose(wat, wds.nodata)
        model &= wat > 0

        das_mask = rasterize(
            [(g, 1) for g in das_geoms],
            out_shape=(ads.height, ads.width),
            transform=ads.transform,
            fill=0,
            all_touched=False,
            dtype="uint8",
        ).astype(bool)

        inter = int(np.count_nonzero(model & das_mask))
        union = int(np.count_nonzero(model | das_mask))
        model_n = int(np.count_nonzero(model))
        ref_n = int(np.count_nonzero(das_mask))
        iou = float(inter / union) if union else 0.0
        dice = float(2 * inter / (model_n + ref_n)) if (model_n + ref_n) else 0.0

        result = {
            "stream_threshold_km2": THRESHOLD_KM2,
            "stream_threshold_cells": min_cells,
            "outlet_selection": {
                "boundary_tolerance_m": BOUNDARY_TOL_M,
                "rbi_tolerance_m": RBI_TOL_M,
                "snap_radius_m": LOCAL_SNAP_RADIUS_M,
                "top_candidate_before_snap": records[0],
                "selected_final": final,
            },
            "watershed_validation": {
                "cell_area_m2": cell_area,
                "reference_area_km2": float(ref_n * cell_area / 1_000_000.0),
                "model_area_km2": float(model_n * cell_area / 1_000_000.0),
                "intersection_area_km2": float(inter * cell_area / 1_000_000.0),
                "union_area_km2": float(union * cell_area / 1_000_000.0),
                "iou": iou,
                "dice": dice,
            },
        }

    with QC.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print("=== KURANJI WATERSHED DERIVATION ===")
    print(f"Threshold       : {THRESHOLD_KM2:.2f} km2 ({min_cells:,} cells)")
    print(f"Outlet          : X={final['x']:.3f}, Y={final['y']:.3f}")
    print(f"Accum area      : {final['catchment_area_km2']:.3f} km2")
    print(f"Distance to RBI : {final['distance_to_rbi_m']:.2f} m")
    print(f"Reference area  : {result['watershed_validation']['reference_area_km2']:.3f} km2")
    print(f"Model area      : {result['watershed_validation']['model_area_km2']:.3f} km2")
    print(f"IoU             : {iou:.4f}")
    print(f"Dice            : {dice:.4f}")
    print("JSON            :", QC)
    print("Candidates      :", CANDIDATES)


if __name__ == "__main__":
    main()
