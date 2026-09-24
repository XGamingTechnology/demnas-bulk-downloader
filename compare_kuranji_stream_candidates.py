#!/usr/bin/env python3
"""Compare plausible Kuranji stream thresholds using hydrologic network structure.

The refined raster-overlap calibration found that 20 km2 maximizes harmonic F1,
but it also prunes a substantial fraction of the RBI reference network. This script
compares a focused set of candidates (4, 5, 6, and 20 km2) using D8 network length,
headwater/outlet counts, connected components, RBI coverage, and F-beta metrics that
can place extra weight on preserving the reference network.

Outputs
-------
data/work/kuranji/05_validation/stream_candidate_comparison.json

No threshold is automatically declared final. The report is intended to support a
scientific choice before outlet snapping and watershed delineation.
"""

from __future__ import annotations

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
HYD = ROOT / "data/work/kuranji/02_hydrology"
VAL = ROOT / "data/work/kuranji/05_validation"
VAL.mkdir(parents=True, exist_ok=True)

DAS = PREP / "DAS_KURANJI_UTM47S.geojson"
RBI = PREP / "SUNGAI_RBI_DAS_KURANJI_UTM47S.geojson"
POINTER = HYD / "02_D8_POINTER.tif"
ACC = HYD / "03_FLOW_ACCUM_CELLS.tif"
OUT_JSON = VAL / "stream_candidate_comparison.json"

CANDIDATES_KM2 = [4.0, 5.0, 6.0, 20.0]
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


def geoms(path: Path):
    data = load_geojson(path)
    out = [shape(ft["geometry"]) for ft in data.get("features", []) if ft.get("geometry")]
    if not out:
        raise RuntimeError(f"No geometries: {path}")
    return out


def harmonic(a, b):
    return 0.0 if a + b == 0 else 2.0 * a * b / (a + b)


def fbeta(precision, recall, beta):
    b2 = beta * beta
    den = b2 * precision + recall
    return 0.0 if den == 0 else (1.0 + b2) * precision * recall / den


def fraction_near(source, distances, tol):
    n = int(np.count_nonzero(source))
    return 0.0 if n == 0 else float(np.count_nonzero(source & (distances <= tol)) / n)


def network_graph_metrics(mask, pointer, rx, ry):
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


def main():
    for p in [DAS, RBI, POINTER, ACC]:
        if not p.exists():
            raise FileNotFoundError(p)

    das_geoms = geoms(DAS)
    rbi_geoms = geoms(RBI)
    rbi_length_km = float(sum(g.length for g in rbi_geoms) / 1000.0)

    with rasterio.open(POINTER) as pds, rasterio.open(ACC) as ads:
        if pds.width != ads.width or pds.height != ads.height or pds.crs != ads.crs or not pds.transform.almost_equals(ads.transform):
            raise RuntimeError("Pointer and accumulation grids differ")

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
        if ads.nodata is not None:
            valid &= ~np.isclose(accum, ads.nodata)

        dist_to_rbi = distance_transform_edt(~rbi_mask, sampling=sampling)
        rows = []

        for area in CANDIDATES_KM2:
            min_cells = int(math.ceil(area * 1_000_000.0 / cell_area))
            model = valid & (accum >= min_cells)
            dist_to_model = distance_transform_edt(~model, sampling=sampling)

            metrics = {}
            for tol in TOLERANCES_M:
                # Treat model->RBI as precision-like and RBI->model as recall-like.
                precision = fraction_near(model, dist_to_rbi, tol)
                recall = fraction_near(rbi_mask, dist_to_model, tol)
                metrics[f"{int(tol)}m"] = {
                    "model_near_rbi_fraction_precision_like": precision,
                    "rbi_near_model_fraction_recall_like": recall,
                    "f1": harmonic(precision, recall),
                    "f_beta_2_recall_weighted": fbeta(precision, recall, 2.0),
                }

            graph = network_graph_metrics(model, pointer, rx, ry)
            graph["length_ratio_to_rbi"] = float(graph["network_length_km"] / rbi_length_km) if rbi_length_km else None

            rows.append({
                "threshold_area_km2": area,
                "minimum_cells": min_cells,
                "graph": graph,
                "agreement": metrics,
            })

    result = {
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
        "interpretation_note": (
            "F1 alone can favour an over-pruned network. F-beta=2 gives more weight to preserving RBI coverage. "
            "Use network length, headwaters, connected components, and map inspection together before selecting the final threshold."
        ),
    }

    with OUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print("=== KURANJI STREAM CANDIDATE COMPARISON ===")
    print(f"RBI vector length: {rbi_length_km:.3f} km")
    for row in rows:
        g = row["graph"]
        m = row["agreement"]["100m"]
        print(
            f"{row['threshold_area_km2']:>4.1f} km2 | "
            f"length={g['network_length_km']:.2f} km ({g['length_ratio_to_rbi']:.2f}x RBI) | "
            f"heads={g['headwater_cells']:,} outlets={g['outlet_or_truncated_cells']:,} comps={g['connected_components_8n']} | "
            f"100m P={m['model_near_rbi_fraction_precision_like']:.3f} "
            f"R={m['rbi_near_model_fraction_recall_like']:.3f} "
            f"F1={m['f1']:.3f} F2={m['f_beta_2_recall_weighted']:.3f}"
        )
    print("JSON:", OUT_JSON)


if __name__ == "__main__":
    main()
