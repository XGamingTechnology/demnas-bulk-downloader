#!/usr/bin/env python3
"""Audit possible Kuranji outlets before final watershed delineation.

This script diagnoses whether the current 177 km2 watershed result is caused by
an overly strict outlet-search window or by upstream D8 routing/conditioning.
It does NOT select a final outlet and does NOT use reference DAS area as a ranking
criterion.

For combinations of distance-to-reference-DAS-boundary and distance-to-RBI limits,
it reports the cell with maximum D8 flow accumulation. This shows whether a more
downstream, higher-accumulation candidate exists near the official river network.

Outputs
-------
data/work/kuranji/03_watershed/outlet_audit.json
data/work/kuranji/03_watershed/OUTLET_AUDIT_CANDIDATES.geojson
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
OUT = ROOT / "data/work/kuranji/03_watershed"
OUT.mkdir(parents=True, exist_ok=True)

DAS = PREP / "DAS_KURANJI_UTM47S.geojson"
RBI = PREP / "SUNGAI_RBI_DAS_KURANJI_UTM47S.geojson"
ACC = HYD / "03_FLOW_ACCUM_CELLS.tif"

JSON_OUT = OUT / "outlet_audit.json"
GEOJSON_OUT = OUT / "OUTLET_AUDIT_CANDIDATES.geojson"

THRESHOLD_KM2 = 6.0
BOUNDARY_TOLS_M = [50.0, 100.0, 250.0, 500.0, 1000.0]
RBI_TOLS_M = [50.0, 100.0, 150.0, 250.0, 500.0, 1000.0]


def load_geoms(path: Path):
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    out = [shape(ft["geometry"]) for ft in data.get("features", []) if ft.get("geometry")]
    if not out:
        raise RuntimeError(f"No geometries: {path}")
    return out


def main():
    for p in [DAS, RBI, ACC]:
        if not p.exists():
            raise FileNotFoundError(p)

    das_geoms = load_geoms(DAS)
    rbi_geoms = load_geoms(RBI)

    with rasterio.open(ACC) as ads:
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
        dist_to_outside = distance_transform_edt(das_mask, sampling=sampling)
        dist_to_rbi = distance_transform_edt(~rbi_mask, sampling=sampling)

        tests = []
        features = []
        seen = set()

        for b_tol in BOUNDARY_TOLS_M:
            for r_tol in RBI_TOLS_M:
                mask = (
                    stream
                    & (dist_to_outside <= b_tol)
                    & (dist_to_rbi <= r_tol)
                )
                rr, cc = np.where(mask)
                if rr.size == 0:
                    tests.append({
                        "boundary_tolerance_m": b_tol,
                        "rbi_tolerance_m": r_tol,
                        "candidate_cells": 0,
                        "best": None,
                    })
                    continue

                vals = accum[rr, cc]
                idx = int(np.argmax(vals))
                r, c = int(rr[idx]), int(cc[idx])
                x, y = rasterio.transform.xy(ads.transform, r, c, offset="center")
                best = {
                    "row": r,
                    "col": c,
                    "x": float(x),
                    "y": float(y),
                    "accum_cells": float(accum[r, c]),
                    "catchment_area_km2": float(accum[r, c] * cell_area / 1_000_000.0),
                    "distance_to_rbi_m": float(dist_to_rbi[r, c]),
                    "distance_inside_boundary_m": float(dist_to_outside[r, c]),
                }
                tests.append({
                    "boundary_tolerance_m": b_tol,
                    "rbi_tolerance_m": r_tol,
                    "candidate_cells": int(rr.size),
                    "best": best,
                })

                key = (r, c)
                if key not in seen:
                    seen.add(key)
                    features.append({
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [float(x), float(y)],
                        },
                        "properties": {
                            **best,
                            "first_boundary_tolerance_m": b_tol,
                            "first_rbi_tolerance_m": r_tol,
                        },
                    })

        # Also report the maximum-accumulation stream cell anywhere inside DAS.
        rr, cc = np.where(stream)
        vals = accum[rr, cc]
        idx = int(np.argmax(vals))
        r, c = int(rr[idx]), int(cc[idx])
        x, y = rasterio.transform.xy(ads.transform, r, c, offset="center")
        max_inside = {
            "row": r,
            "col": c,
            "x": float(x),
            "y": float(y),
            "accum_cells": float(accum[r, c]),
            "catchment_area_km2": float(accum[r, c] * cell_area / 1_000_000.0),
            "distance_to_rbi_m": float(dist_to_rbi[r, c]),
            "distance_inside_boundary_m": float(dist_to_outside[r, c]),
        }

        result = {
            "threshold_km2": THRESHOLD_KM2,
            "threshold_cells": min_cells,
            "cell_area_m2": cell_area,
            "maximum_accumulation_stream_cell_inside_reference_das": max_inside,
            "tests": tests,
            "interpretation": (
                "If maximum catchment area remains near 177 km2 even with broad boundary/RBI tolerances, "
                "the missing area is caused by D8 routing/conditioning or a mismatch between DEM drainage and the reference DAS, not merely outlet snapping."
            ),
        }

    with JSON_OUT.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    fc = {
        "type": "FeatureCollection",
        "name": "outlet_audit_candidates",
        "crs": {"type": "name", "properties": {"name": str(ads.crs)}},
        "features": features,
    }
    with GEOJSON_OUT.open("w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2)

    print("=== KURANJI OUTLET AUDIT ===")
    print(f"Threshold: {THRESHOLD_KM2:.2f} km2 ({min_cells:,} cells)")
    print("\nMaximum accumulation stream cell anywhere inside reference DAS:")
    print(
        f"  area={max_inside['catchment_area_km2']:.3f} km2 | "
        f"RBI dist={max_inside['distance_to_rbi_m']:.1f} m | "
        f"boundary dist={max_inside['distance_inside_boundary_m']:.1f} m"
    )

    print("\nBest candidate for each search window:")
    for row in tests:
        b, r = row["boundary_tolerance_m"], row["rbi_tolerance_m"]
        best = row["best"]
        if best is None:
            print(f"  boundary<={b:>5.0f}m RBI<={r:>5.0f}m : NONE")
        else:
            print(
                f"  boundary<={b:>5.0f}m RBI<={r:>5.0f}m : "
                f"area={best['catchment_area_km2']:>8.3f} km2 | "
                f"dRBI={best['distance_to_rbi_m']:>6.1f}m | "
                f"dBND={best['distance_inside_boundary_m']:>6.1f}m"
            )

    print("\nJSON   :", JSON_OUT)
    print("Points :", GEOJSON_OUT)


if __name__ == "__main__":
    main()
