#!/usr/bin/env python3
"""Recalibrate Kuranji stream threshold on the selected BREACH100 hydrologic baseline.

This is the final stream-threshold verification step before freezing the baseline
hydrology for GFI analysis. The previous 6 km2 working threshold was calibrated on
FillDepressions routing, so it must not be carried forward automatically after the
conditioning method changed to BreachDepressionsLeastCost (100 cells).

The script compares candidate minimum contributing areas against RBI using:
- modeled D8 network length and ratio to RBI vector length;
- headwater, outlet, junction and connected-component counts;
- model-to-RBI precision-like proximity;
- RBI-to-model recall-like proximity;
- F1 and recall-weighted F2 at 25, 50 and 100 m;
- length deviation from RBI.

Outputs are intentionally report-ready: JSON + CSV + candidate stream rasters.
No threshold is automatically declared final; the final choice must combine these
metrics with visual map inspection.

Outputs
-------
data/work/kuranji/05_validation/breach100_stream_calibration/
  breach100_stream_threshold_calibration.json
  breach100_stream_threshold_calibration.csv
  STREAM_BREACH100_<threshold>KM2.tif
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from scipy.ndimage import distance_transform_edt, label
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent
PREP = ROOT / "data/work/kuranji/01_prepared"
VAL = ROOT / "data/work/kuranji/05_validation"
SENS = VAL / "conditioning_sensitivity"
OUT = VAL / "breach100_stream_calibration"
OUT.mkdir(parents=True, exist_ok=True)

DAS = PREP / "DAS_KURANJI_UTM47S.geojson"
RBI = PREP / "SUNGAI_RBI_DAS_KURANJI_UTM47S.geojson"
POINTER = SENS / "BREACH100_D8_POINTER.tif"
ACC = SENS / "BREACH100_FLOW_ACCUM_CELLS.tif"

OUT_JSON = OUT / "breach100_stream_threshold_calibration.json"
OUT_CSV = OUT / "breach100_stream_threshold_calibration.csv"

# Focused range around the old 6 km2 working threshold, with lower/higher controls.
CANDIDATES_KM2 = [2.0, 3.0, 4.0, 5.0, 6.0, 7.5, 10.0, 12.5, 15.0, 20.0]
TOLERANCES_M = [25.0, 50.0, 100.0]
STRUCTURE_8 = np.ones((3, 3), dtype=np.uint8)

# Whitebox D8 pointer convention: NE, E, SE, S, SW, W, NW, N.
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


def load_geojson(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_geoms(path: Path):
    data = load_geojson(path)
    geoms = [shape(ft["geometry"]) for ft in data.get("features", []) if ft.get("geometry")]
    if not geoms:
        raise RuntimeError(f"No geometries found: {path}")
    return geoms


def harmonic(a: float, b: float) -> float:
    return 0.0 if a + b == 0 else 2.0 * a * b / (a + b)


def fbeta(precision: float, recall: float, beta: float) -> float:
    b2 = beta * beta
    den = b2 * precision + recall
    return 0.0 if den == 0 else (1.0 + b2) * precision * recall / den


def fraction_near(source: np.ndarray, distances: np.ndarray, tol: float) -> float:
    n = int(np.count_nonzero(source))
    return 0.0 if n == 0 else float(np.count_nonzero(source & (distances <= tol)) / n)


def network_graph_metrics(mask: np.ndarray, pointer: np.ndarray, rx: float, ry: float):
    rows, cols = mask.shape
    inflow = np.zeros(mask.shape, dtype=np.uint8)
    total_length = 0.0
    edge_count = 0
    outlets = 0

    rr, cc = np.where(mask)
    for r, c in zip(rr.tolist(), cc.tolist()):
        code = int(pointer[r, c])
        step = D8.get(code)
        if step is None:
            outlets += 1
            continue
        dr, dc = step
        nr, nc = r + dr, c + dc
        if nr < 0 or nr >= rows or nc < 0 or nc >= cols or not mask[nr, nc]:
            outlets += 1
            continue
        inflow[nr, nc] = min(255, int(inflow[nr, nc]) + 1)
        total_length += math.hypot(dc * rx, dr * ry)
        edge_count += 1

    heads = int(np.count_nonzero(mask & (inflow == 0)))
    junctions = int(np.count_nonzero(mask & (inflow >= 2)))
    labelled, ncomp = label(mask, structure=STRUCTURE_8)
    counts = np.bincount(labelled.ravel())
    largest = int(counts[1:].max()) if counts.size > 1 else 0
    n = int(np.count_nonzero(mask))

    return {
        "stream_cells": n,
        "d8_edges": edge_count,
        "network_length_km": float(total_length / 1000.0),
        "headwater_cells": heads,
        "outlet_or_truncated_cells": int(outlets),
        "junction_cells_inflow_ge_2": junctions,
        "connected_components_8n": int(ncomp),
        "largest_component_cells": largest,
        "largest_component_fraction": float(largest / n) if n else 0.0,
    }


def write_stream_raster(path: Path, mask: np.ndarray, ref):
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
        dst.write(mask.astype("uint8"), 1)


def threshold_slug(area: float) -> str:
    s = f"{area:g}".replace(".", "P")
    return s


def main():
    for p in [DAS, RBI, POINTER, ACC]:
        if not p.exists():
            raise FileNotFoundError(p)

    das_geoms = load_geoms(DAS)
    rbi_geoms = load_geoms(RBI)
    rbi_length_km = float(sum(g.length for g in rbi_geoms) / 1000.0)

    with rasterio.open(POINTER) as pds, rasterio.open(ACC) as ads:
        if (
            pds.width != ads.width
            or pds.height != ads.height
            or pds.crs != ads.crs
            or not pds.transform.almost_equals(ads.transform)
        ):
            raise RuntimeError("BREACH100 pointer and accumulation grids differ")

        rx, ry = abs(ads.res[0]), abs(ads.res[1])
        cell_area = rx * ry
        sampling = (ry, rx)

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
        ).astype(bool) & das_mask

        pointer = pds.read(1)
        accum = ads.read(1).astype("float64", copy=False)
        valid = das_mask & np.isfinite(accum)
        if ads.nodata is not None and np.isfinite(ads.nodata):
            valid &= ~np.isclose(accum, ads.nodata)

        dist_to_rbi = distance_transform_edt(~rbi_mask, sampling=sampling)
        rows = []

        for area in CANDIDATES_KM2:
            min_cells = int(math.ceil(area * 1_000_000.0 / cell_area))
            model = valid & (accum >= min_cells)
            dist_to_model = distance_transform_edt(~model, sampling=sampling)

            agreement = {}
            for tol in TOLERANCES_M:
                precision = fraction_near(model, dist_to_rbi, tol)
                recall = fraction_near(rbi_mask, dist_to_model, tol)
                agreement[f"{int(tol)}m"] = {
                    "model_near_rbi_fraction_precision_like": precision,
                    "rbi_near_model_fraction_recall_like": recall,
                    "f1": harmonic(precision, recall),
                    "f_beta_2_recall_weighted": fbeta(precision, recall, 2.0),
                }

            graph = network_graph_metrics(model, pointer, rx, ry)
            graph["length_ratio_to_rbi"] = (
                float(graph["network_length_km"] / rbi_length_km) if rbi_length_km else None
            )
            graph["absolute_length_difference_km"] = float(
                abs(graph["network_length_km"] - rbi_length_km)
            )
            graph["absolute_length_difference_percent"] = float(
                abs(graph["network_length_km"] - rbi_length_km) / rbi_length_km * 100.0
            ) if rbi_length_km else None

            raster_path = OUT / f"STREAM_BREACH100_{threshold_slug(area)}KM2.tif"
            write_stream_raster(raster_path, model, ads)

            rows.append({
                "threshold_area_km2": area,
                "minimum_cells": min_cells,
                "graph": graph,
                "agreement": agreement,
                "stream_raster": str(raster_path.relative_to(ROOT)),
            })

    result = {
        "method": {
            "conditioning": "BreachDepressionsLeastCost, dist=100 cells, min_dist=True, fill=True",
            "flow_direction": "WhiteboxTools D8Pointer",
            "flow_accumulation": "WhiteboxTools D8FlowAccumulation, cells",
            "candidate_thresholds_km2": CANDIDATES_KM2,
            "tolerances_m": TOLERANCES_M,
            "selection_rule": (
                "Do not select on F1 alone. Consider RBI length similarity, F2 recall preservation, "
                "precision/recall balance, network topology, connected components and map inspection."
            ),
        },
        "grid": {
            "crs": str(ads.crs),
            "resolution_m": [rx, ry],
            "cell_area_m2": cell_area,
        },
        "rbi_reference": {
            "feature_count": len(rbi_geoms),
            "vector_total_length_km": rbi_length_km,
            "raster_cells_inside_das": int(np.count_nonzero(rbi_mask)),
        },
        "candidates": rows,
    }

    with OUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    csv_fields = [
        "threshold_km2",
        "minimum_cells",
        "network_length_km",
        "length_ratio_to_rbi",
        "length_diff_km",
        "length_diff_percent",
        "stream_cells",
        "headwaters",
        "outlets",
        "junctions",
        "components",
        "largest_component_fraction",
        "precision_25m",
        "recall_25m",
        "f1_25m",
        "f2_25m",
        "precision_50m",
        "recall_50m",
        "f1_50m",
        "f2_50m",
        "precision_100m",
        "recall_100m",
        "f1_100m",
        "f2_100m",
        "stream_raster",
    ]

    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=csv_fields)
        w.writeheader()
        for row in rows:
            g = row["graph"]
            rec = {
                "threshold_km2": row["threshold_area_km2"],
                "minimum_cells": row["minimum_cells"],
                "network_length_km": g["network_length_km"],
                "length_ratio_to_rbi": g["length_ratio_to_rbi"],
                "length_diff_km": g["absolute_length_difference_km"],
                "length_diff_percent": g["absolute_length_difference_percent"],
                "stream_cells": g["stream_cells"],
                "headwaters": g["headwater_cells"],
                "outlets": g["outlet_or_truncated_cells"],
                "junctions": g["junction_cells_inflow_ge_2"],
                "components": g["connected_components_8n"],
                "largest_component_fraction": g["largest_component_fraction"],
                "stream_raster": row["stream_raster"],
            }
            for tol in TOLERANCES_M:
                m = row["agreement"][f"{int(tol)}m"]
                suffix = f"{int(tol)}m"
                rec[f"precision_{suffix}"] = m["model_near_rbi_fraction_precision_like"]
                rec[f"recall_{suffix}"] = m["rbi_near_model_fraction_recall_like"]
                rec[f"f1_{suffix}"] = m["f1"]
                rec[f"f2_{suffix}"] = m["f_beta_2_recall_weighted"]
            w.writerow(rec)

    print("=== KURANJI BREACH100 STREAM THRESHOLD CALIBRATION ===")
    print(f"RBI vector length : {rbi_length_km:.3f} km")
    print(f"Cell area         : {cell_area:.6f} m2")
    print()
    print("thr | length (ratio) | heads outlets comps | P100 R100 F1 F2 | len-diff")
    print("----+----------------+---------------------+------------------+---------")
    for row in rows:
        g = row["graph"]
        m = row["agreement"]["100m"]
        print(
            f"{row['threshold_area_km2']:>4.1f} | "
            f"{g['network_length_km']:>6.2f} ({g['length_ratio_to_rbi']:>4.2f}x) | "
            f"{g['headwater_cells']:>5} {g['outlet_or_truncated_cells']:>7} {g['connected_components_8n']:>5} | "
            f"{m['model_near_rbi_fraction_precision_like']:.3f} "
            f"{m['rbi_near_model_fraction_recall_like']:.3f} "
            f"{m['f1']:.3f} {m['f_beta_2_recall_weighted']:.3f} | "
            f"{g['absolute_length_difference_km']:>7.2f} km"
        )

    best_f1 = max(rows, key=lambda r: r["agreement"]["100m"]["f1"])
    best_f2 = max(rows, key=lambda r: r["agreement"]["100m"]["f_beta_2_recall_weighted"])
    best_len = min(rows, key=lambda r: r["graph"]["absolute_length_difference_km"])

    print("\nDiagnostic leaders (not automatic final selection):")
    print(f"  Best F1 @100m : {best_f1['threshold_area_km2']:g} km2")
    print(f"  Best F2 @100m : {best_f2['threshold_area_km2']:g} km2")
    print(f"  Closest length: {best_len['threshold_area_km2']:g} km2")
    print("\nJSON:", OUT_JSON)
    print("CSV :", OUT_CSV)
    print("Candidate rasters:", OUT)


if __name__ == "__main__":
    main()
