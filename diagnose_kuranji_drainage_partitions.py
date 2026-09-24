#!/usr/bin/env python3
"""Diagnose how the reference DAS Kuranji is partitioned by the DEM-derived D8 flow field.

The outlet audit showed that the maximum contributing area at any candidate outlet
inside the reference DAS is ~177 km2, while the official reference polygon is ~224.7
km2. This script identifies every D8 terminal/outflow point of the reference DAS,
uses them as pour points, delineates all DEM-derived drainage partitions, and reports
how much of the reference DAS drains to each outlet.

This is diagnostic only. It does not force the DEM to match the reference polygon.

Outputs
-------
data/work/kuranji/03_watershed/
  DAS_D8_EXIT_POINTS.geojson
  DAS_D8_EXIT_POUR_POINTS.tif
  DAS_D8_PARTITIONS.tif
  drainage_partition_diagnostic.json
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from scipy.ndimage import distance_transform_edt
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

EXIT_POINTS = OUT / "DAS_D8_EXIT_POINTS.geojson"
POUR_RASTER = OUT / "DAS_D8_EXIT_POUR_POINTS.tif"
PARTITIONS = OUT / "DAS_D8_PARTITIONS.tif"
REPORT = OUT / "drainage_partition_diagnostic.json"

# Whitebox D8 pointer convention.
D8 = {
    1: (-1, 1),
    2: (0, 1),
    4: (1, 1),
    8: (1, 0),
    16: (1, -1),
    32: (0, -1),
    64: (-1, -1),
    128: (-1, 0),
}


def load_geoms(path: Path):
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    gs = [shape(ft["geometry"]) for ft in data.get("features", []) if ft.get("geometry")]
    if not gs:
        raise RuntimeError(f"No geometries: {path}")
    return gs


def write_int_raster(path: Path, arr: np.ndarray, ref):
    profile = ref.profile.copy()
    for key in ("compress", "predictor", "tiled", "blockxsize", "blockysize", "interleave"):
        profile.pop(key, None)
    profile.update(
        driver="GTiff",
        dtype="int32",
        count=1,
        nodata=0,
        crs=ref.crs,
        transform=ref.transform,
        width=ref.width,
        height=ref.height,
        BIGTIFF="IF_SAFER",
    )
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr.astype("int32"), 1)


def main():
    for p in [DAS, RBI, POINTER, ACC]:
        if not p.exists():
            raise FileNotFoundError(p)

    das_geoms = load_geoms(DAS)
    rbi_geoms = load_geoms(RBI)

    with rasterio.open(POINTER) as pds, rasterio.open(ACC) as ads:
        if pds.width != ads.width or pds.height != ads.height or pds.crs != ads.crs or not pds.transform.almost_equals(ads.transform):
            raise RuntimeError("Pointer and accumulation grids differ")

        pointer = pds.read(1)
        accum = ads.read(1).astype("float64", copy=False)
        rows, cols = pointer.shape
        rx, ry = abs(ads.res[0]), abs(ads.res[1])
        cell_area = rx * ry
        sampling = (ry, rx)

        das_mask = rasterize(
            [(g, 1) for g in das_geoms],
            out_shape=(rows, cols),
            transform=ads.transform,
            fill=0,
            all_touched=False,
            dtype="uint8",
        ).astype(bool)

        rbi_mask = rasterize(
            [(g, 1) for g in rbi_geoms],
            out_shape=(rows, cols),
            transform=ads.transform,
            fill=0,
            all_touched=True,
            dtype="uint8",
        ).astype(bool)
        dist_to_rbi = distance_transform_edt(~rbi_mask, sampling=sampling)
        dist_to_outside = distance_transform_edt(das_mask, sampling=sampling)

        valid = das_mask & np.isfinite(accum)
        if ads.nodata is not None:
            valid &= ~np.isclose(accum, ads.nodata)

        terminals = []
        rr, cc = np.where(valid)
        for r, c in zip(rr.tolist(), cc.tolist()):
            code = int(pointer[r, c])
            if code == 0:
                terminals.append((r, c, "pointer_zero"))
                continue
            step = D8.get(code)
            if step is None:
                terminals.append((r, c, "unexpected_pointer"))
                continue
            dr, dc = step
            nr, nc = r + dr, c + dc
            if nr < 0 or nr >= rows or nc < 0 or nc >= cols or not das_mask[nr, nc]:
                terminals.append((r, c, "boundary_exit"))

        if not terminals:
            raise RuntimeError("No D8 exits/terminals found inside reference DAS")

        # Rank by accumulation so IDs are deterministic and largest outlet is ID 1.
        terminals.sort(key=lambda t: float(accum[t[0], t[1]]), reverse=True)

        pour = np.zeros((rows, cols), dtype="int32")
        features = []
        lookup = {}
        for outlet_id, (r, c, kind) in enumerate(terminals, start=1):
            pour[r, c] = outlet_id
            x, y = rasterio.transform.xy(ads.transform, r, c, offset="center")
            rec = {
                "outlet_id": outlet_id,
                "kind": kind,
                "row": r,
                "col": c,
                "x": float(x),
                "y": float(y),
                "accum_cells_global": float(accum[r, c]),
                "accum_area_global_km2": float(accum[r, c] * cell_area / 1_000_000.0),
                "distance_to_rbi_m": float(dist_to_rbi[r, c]),
                "distance_inside_reference_boundary_m": float(dist_to_outside[r, c]),
            }
            lookup[outlet_id] = rec
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(x), float(y)]},
                "properties": rec,
            })

        write_int_raster(POUR_RASTER, pour, ads)

        fc = {
            "type": "FeatureCollection",
            "name": "das_d8_exit_points",
            "crs": {"type": "name", "properties": {"name": str(ads.crs)}},
            "features": features,
        }
        with EXIT_POINTS.open("w", encoding="utf-8") as f:
            json.dump(fc, f, indent=2)

    wbt = WhiteboxTools()
    wbt.set_verbose_mode(True)
    wbt.set_compress_rasters(False)
    rc = wbt.watershed(
        d8_pntr=str(POINTER),
        pour_pts=str(POUR_RASTER),
        output=str(PARTITIONS),
        esri_pntr=False,
    )
    if rc not in (0, None) or not PARTITIONS.exists():
        raise RuntimeError(f"Whitebox Watershed failed, rc={rc}")

    with rasterio.open(PARTITIONS) as wds, rasterio.open(ACC) as ads:
        labels = wds.read(1)
        das_mask = rasterize(
            [(g, 1) for g in das_geoms],
            out_shape=(ads.height, ads.width),
            transform=ads.transform,
            fill=0,
            all_touched=False,
            dtype="uint8",
        ).astype(bool)

        valid_labels = labels[das_mask]
        if wds.nodata is not None:
            valid_labels = valid_labels[~np.isclose(valid_labels, wds.nodata)]
        valid_labels = valid_labels[np.isfinite(valid_labels)]
        ids, counts = np.unique(valid_labels.astype("int64"), return_counts=True)

        partitions = []
        assigned_cells = 0
        for oid, n in zip(ids.tolist(), counts.tolist()):
            if oid <= 0:
                continue
            assigned_cells += int(n)
            rec = dict(lookup.get(int(oid), {"outlet_id": int(oid)}))
            rec.update({
                "reference_das_cells_draining_to_outlet": int(n),
                "reference_das_area_km2_draining_to_outlet": float(n * cell_area / 1_000_000.0),
            })
            partitions.append(rec)

        partitions.sort(key=lambda r: r["reference_das_area_km2_draining_to_outlet"], reverse=True)

        ref_cells = int(np.count_nonzero(das_mask))
        ref_area = float(ref_cells * cell_area / 1_000_000.0)
        unassigned = ref_cells - assigned_cells

        report = {
            "grid": {
                "crs": str(ads.crs),
                "resolution_m": [rx, ry],
                "cell_area_m2": cell_area,
            },
            "reference_das": {
                "cells": ref_cells,
                "area_km2": ref_area,
            },
            "d8_terminals": {
                "count": len(terminals),
                "boundary_exit_count": sum(1 for _, _, k in terminals if k == "boundary_exit"),
                "pointer_zero_count": sum(1 for _, _, k in terminals if k == "pointer_zero"),
                "unexpected_pointer_count": sum(1 for _, _, k in terminals if k == "unexpected_pointer"),
            },
            "assigned_reference_cells": assigned_cells,
            "assigned_reference_area_km2": float(assigned_cells * cell_area / 1_000_000.0),
            "unassigned_reference_cells": unassigned,
            "unassigned_reference_area_km2": float(unassigned * cell_area / 1_000_000.0),
            "partitions": partitions,
            "interpretation_note": (
                "Large secondary partitions indicate that the reference DAS polygon crosses DEM-derived drainage divides or that the DEM conditioning/routing differs from the official delineation. "
                "Do not force a single outlet until these partitions are inspected."
            ),
        }

    with REPORT.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("=== KURANJI D8 DRAINAGE PARTITIONS ===")
    print(f"Reference DAS area : {ref_area:.3f} km2")
    print(f"D8 terminals       : {len(terminals)}")
    print(f"  boundary exits   : {report['d8_terminals']['boundary_exit_count']}")
    print(f"  pointer zero     : {report['d8_terminals']['pointer_zero_count']}")
    print(f"Assigned area      : {report['assigned_reference_area_km2']:.3f} km2")
    print(f"Unassigned area    : {report['unassigned_reference_area_km2']:.3f} km2")
    print("\nLargest partitions:")
    for row in partitions[:15]:
        print(
            f"  ID={row['outlet_id']:>3} {row.get('kind','?'):<13} | "
            f"area={row['reference_das_area_km2_draining_to_outlet']:>8.3f} km2 | "
            f"global-acc={row.get('accum_area_global_km2', float('nan')):>8.3f} km2 | "
            f"dRBI={row.get('distance_to_rbi_m', float('nan')):>7.1f} m"
        )
    print("\nReport     :", REPORT)
    print("Exit points:", EXIT_POINTS)
    print("Partitions :", PARTITIONS)


if __name__ == "__main__":
    main()
