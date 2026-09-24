#!/usr/bin/env python3
"""Inspect the stable ~32 km2 secondary drainage partition inside reference DAS Kuranji.

The grouped-exit diagnostic showed a persistent secondary zone of ~31.7-32.0 km2
across 25, 50, 100 and 250 m grouping radii. This script focuses on the 100 m
clustering result (fine enough to avoid the over-merging seen at 250 m) and inspects
rank-2 zone in detail.

It reports:
- exact area and dominant raw outlet
- outlet distance to RBI
- elevation statistics
- FillDepressions depth statistics within the zone
- 6 km2 modeled-stream agreement with RBI within the zone
- a raster mask and polygon GeoJSON for QGIS inspection

Outputs
-------
data/work/kuranji/03_watershed/
  SECONDARY_PARTITION_100M_RANK2.tif
  SECONDARY_PARTITION_100M_RANK2.geojson
  secondary_partition_diagnostic.json
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize, shapes
from scipy.ndimage import distance_transform_edt
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent
PREP = ROOT / "data/work/kuranji/01_prepared"
HYD = ROOT / "data/work/kuranji/02_hydrology"
OUT = ROOT / "data/work/kuranji/03_watershed"

ZONE_REPORT = OUT / "drainage_exit_zones.json"
EXIT_POINTS = OUT / "DAS_D8_EXIT_POINTS.geojson"
PARTITIONS = OUT / "DAS_D8_PARTITIONS.tif"
DEM = PREP / "DEMNAS_KURANJI_BUFFER3KM_UTM47S.tif"
FILLED = HYD / "01_DEM_FILLED.tif"
ACC = HYD / "03_FLOW_ACCUM_CELLS.tif"
RBI = PREP / "SUNGAI_RBI_DAS_KURANJI_UTM47S.geojson"

MASK_OUT = OUT / "SECONDARY_PARTITION_100M_RANK2.tif"
POLY_OUT = OUT / "SECONDARY_PARTITION_100M_RANK2.geojson"
JSON_OUT = OUT / "secondary_partition_diagnostic.json"

GROUPING_KEY = "100m"
ZONE_RANK = 2
STREAM_THRESHOLD_KM2 = 6.0
STREAM_TOLS_M = [25.0, 50.0, 100.0]


def load_json(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_geoms(path: Path):
    data = load_json(path)
    geoms = [shape(ft["geometry"]) for ft in data.get("features", []) if ft.get("geometry")]
    if not geoms:
        raise RuntimeError(f"No geometries in {path}")
    return geoms


def write_mask(path: Path, arr: np.ndarray, ref):
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


def stats(vals: np.ndarray):
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return None
    return {
        "min": float(np.min(vals)),
        "mean": float(np.mean(vals)),
        "median": float(np.median(vals)),
        "p95": float(np.percentile(vals, 95)),
        "p99": float(np.percentile(vals, 99)),
        "max": float(np.max(vals)),
    }


def main():
    for p in [ZONE_REPORT, EXIT_POINTS, PARTITIONS, DEM, FILLED, ACC, RBI]:
        if not p.exists():
            raise FileNotFoundError(p)

    zone_report = load_json(ZONE_REPORT)
    top = zone_report["grouped_results"][GROUPING_KEY]["top_zones"]
    target = next((z for z in top if int(z["rank"]) == ZONE_RANK), None)
    if target is None:
        raise RuntimeError(f"Zone rank {ZONE_RANK} not found in {GROUPING_KEY}")
    outlet_ids = set(int(x) for x in target["outlet_ids"])

    exits_fc = load_json(EXIT_POINTS)
    exits = []
    for ft in exits_fc.get("features", []):
        p = ft.get("properties", {})
        if int(p.get("outlet_id", -1)) in outlet_ids:
            exits.append(p)
    if not exits:
        raise RuntimeError("No raw exit points found for target zone")
    dominant_exit = max(exits, key=lambda p: float(p.get("accum_area_global_km2", 0.0)))

    rbi_geoms = load_geoms(RBI)

    with rasterio.open(PARTITIONS) as pds, rasterio.open(DEM) as dds, rasterio.open(FILLED) as fds, rasterio.open(ACC) as ads:
        for ds in [dds, fds, ads]:
            if ds.width != pds.width or ds.height != pds.height or ds.crs != pds.crs or not ds.transform.almost_equals(pds.transform):
                raise RuntimeError("Raster grids differ")

        labels = pds.read(1).astype("int64", copy=False)
        mask = np.isin(labels, np.array(sorted(outlet_ids), dtype="int64"))
        write_mask(MASK_OUT, mask, pds)

        cell_area = abs(pds.res[0] * pds.res[1])
        rx, ry = abs(pds.res[0]), abs(pds.res[1])
        zone_cells = int(np.count_nonzero(mask))
        zone_area = float(zone_cells * cell_area / 1_000_000.0)

        dem = dds.read(1).astype("float64", copy=False)
        filled = fds.read(1).astype("float64", copy=False)
        accum = ads.read(1).astype("float64", copy=False)

        valid = mask & np.isfinite(dem) & np.isfinite(filled) & np.isfinite(accum)
        if dds.nodata is not None:
            valid &= ~np.isclose(dem, dds.nodata)
        if fds.nodata is not None:
            valid &= ~np.isclose(filled, fds.nodata)
        if ads.nodata is not None:
            valid &= ~np.isclose(accum, ads.nodata)

        fill_delta = filled - dem
        fill_vals = fill_delta[valid]
        fill_classes = {}
        for th in [0.1, 1.0, 5.0, 10.0]:
            n = int(np.count_nonzero(valid & (fill_delta > th)))
            fill_classes[f">{th:g}m"] = {
                "cells": n,
                "area_km2": float(n * cell_area / 1_000_000.0),
                "percent_zone": float(n / zone_cells * 100.0) if zone_cells else 0.0,
            }

        rbi_mask = rasterize(
            [(g, 1) for g in rbi_geoms],
            out_shape=(pds.height, pds.width),
            transform=pds.transform,
            fill=0,
            all_touched=True,
            dtype="uint8",
        ).astype(bool)
        sampling = (ry, rx)
        dist_to_rbi = distance_transform_edt(~rbi_mask, sampling=sampling)

        min_cells = int(math.ceil(STREAM_THRESHOLD_KM2 * 1_000_000.0 / cell_area))
        stream = valid & (accum >= min_cells)
        stream_cells = int(np.count_nonzero(stream))
        stream_agreement = {}
        for tol in STREAM_TOLS_M:
            near = int(np.count_nonzero(stream & (dist_to_rbi <= tol)))
            stream_agreement[f"{int(tol)}m"] = {
                "stream_cells_near_rbi": near,
                "fraction_model_stream_near_rbi": float(near / stream_cells) if stream_cells else 0.0,
            }

        # Polygonize mask for QGIS. Merge all component polygons into one MultiPolygon/Polygon geometry.
        polys = []
        for geom, value in shapes(mask.astype("uint8"), mask=mask, transform=pds.transform):
            if int(value) == 1:
                polys.append(shape(geom))
        merged = unary_union(polys) if polys else None

        poly_fc = {
            "type": "FeatureCollection",
            "name": "secondary_partition_100m_rank2",
            "crs": {"type": "name", "properties": {"name": str(pds.crs)}},
            "features": [],
        }
        if merged is not None and not merged.is_empty:
            poly_fc["features"].append({
                "type": "Feature",
                "geometry": mapping(merged),
                "properties": {
                    "grouping": GROUPING_KEY,
                    "rank": ZONE_RANK,
                    "area_km2": zone_area,
                    "raw_exit_count": len(exits),
                    "dominant_exit_accum_km2": float(dominant_exit.get("accum_area_global_km2", 0.0)),
                    "dominant_exit_rbi_dist_m": float(dominant_exit.get("distance_to_rbi_m", float("nan"))),
                },
            })

        result = {
            "selection": {
                "grouping_radius": GROUPING_KEY,
                "zone_rank": ZONE_RANK,
                "reported_group_area_km2": float(target["reference_das_area_km2"]),
                "mask_area_km2": zone_area,
                "raw_exit_count": len(exits),
                "outlet_ids": sorted(outlet_ids),
            },
            "dominant_raw_exit": dominant_exit,
            "elevation_m": stats(dem[valid]),
            "fill_depth_m": stats(fill_vals),
            "fill_depth_classes": fill_classes,
            "stream_threshold_km2": STREAM_THRESHOLD_KM2,
            "stream_cells_in_zone": stream_cells,
            "stream_to_rbi_agreement": stream_agreement,
            "interpretation_note": (
                "If the ~32 km2 zone has low fill-depth modification but a coherent stream network that exits far from RBI, "
                "the mismatch is more likely a DEM/reference-boundary drainage-divide disagreement than a FillDepressions artefact. "
                "If deep fill is concentrated along its drainage path or divide, conditioning should be re-tested before hydrologic enforcement."
            ),
        }

    with POLY_OUT.open("w", encoding="utf-8") as f:
        json.dump(poly_fc, f, indent=2)
    with JSON_OUT.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print("=== KURANJI SECONDARY PARTITION DIAGNOSTIC ===")
    print(f"Grouping / rank : {GROUPING_KEY} / {ZONE_RANK}")
    print(f"Zone area       : {zone_area:.3f} km2")
    print(f"Raw exits       : {len(exits)}")
    print(f"Dominant outlet : X={float(dominant_exit['x']):.3f}, Y={float(dominant_exit['y']):.3f}")
    print(f"Outlet accum    : {float(dominant_exit['accum_area_global_km2']):.3f} km2")
    print(f"Outlet RBI dist : {float(dominant_exit['distance_to_rbi_m']):.1f} m")
    print("Elevation       :", result["elevation_m"])
    print("Fill depth      :", result["fill_depth_m"])
    print("Fill classes:")
    for k, v in fill_classes.items():
        print(f"  {k:>5}: {v['area_km2']:.4f} km2 ({v['percent_zone']:.3f}%)")
    print("Stream -> RBI:")
    for k, v in stream_agreement.items():
        print(f"  {k}: {v['fraction_model_stream_near_rbi']:.4f}")
    print("Raster  :", MASK_OUT)
    print("Polygon :", POLY_OUT)
    print("JSON    :", JSON_OUT)


if __name__ == "__main__":
    main()
