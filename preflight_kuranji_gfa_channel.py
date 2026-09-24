#!/usr/bin/env python3
"""Stage-2 preflight: reproduce GFA channel_ASk logic and compare it to the
locally calibrated 6 km2 stream network and RBI.

This script is intentionally diagnostic. It does NOT compute H/hr/GFI yet.
Its purpose is to verify the drainage-network definition used internally by the
legacy GFA plugin before the research commits to a Stage-2 GFI implementation.

Outputs
-------
data/work/kuranji/07_gfi_preflight/
  01_D8_POINTER_ESRI.tif
  02_SLOPE_DEGREE.tif
  03_CHANNEL_ASK_SEED.tif
  04_CHANNEL_ASK_FULL.tif
  05_CHANNEL_FAT_6KM2.tif
  gfa_channel_preflight.json
  gfa_channel_preflight.csv
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
SENS = ROOT / "data/work/kuranji/05_validation/conditioning_sensitivity"
CAL = ROOT / "data/work/kuranji/05_validation/breach100_stream_calibration"
OUT = ROOT / "data/work/kuranji/07_gfi_preflight"
OUT.mkdir(parents=True, exist_ok=True)

DEM = SENS / "BREACH100_DEM.tif"
PTR = SENS / "BREACH100_D8_POINTER.tif"
ACC = SENS / "BREACH100_FLOW_ACCUM_CELLS.tif"
STREAM6 = CAL / "STREAM_BREACH100_6KM2.tif"
DAS = PREP / "DAS_KURANJI_UTM47S.geojson"
RBI = PREP / "SUNGAI_RBI_DAS_KURANJI_UTM47S.geojson"

OUT_JSON = OUT / "gfa_channel_preflight.json"
OUT_CSV = OUT / "gfa_channel_preflight.csv"

# Whitebox pointer convention from Stage 1.
WBT_D8 = {
    1: (-1, 1),
    2: (0, 1),
    4: (1, 1),
    8: (1, 0),
    16: (1, -1),
    32: (0, -1),
    64: (-1, -1),
    128: (-1, 0),
}

# Conversion to ESRI D8 as expected by GFA if the old plugin were used literally.
WBT_TO_ESRI = {
    1: 128,
    2: 1,
    4: 2,
    8: 4,
    16: 8,
    32: 16,
    64: 32,
    128: 64,
}

TOLS = [25.0, 50.0, 100.0]
STRUCT8 = np.ones((3, 3), dtype=np.uint8)


def load_geojson(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_geoms(path: Path):
    fc = load_geojson(path)
    geoms = [shape(ft["geometry"]) for ft in fc.get("features", []) if ft.get("geometry")]
    if not geoms:
        raise RuntimeError(f"No geometry in {path}")
    return geoms


def write_raster(path: Path, arr: np.ndarray, ref, dtype: str, nodata):
    profile = ref.profile.copy()
    profile.update(
        driver="GTiff",
        dtype=dtype,
        count=1,
        nodata=nodata,
        compress="DEFLATE",
        tiled=True,
        blockxsize=512,
        blockysize=512,
    )
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr.astype(dtype), 1)


def horn_slope_degree(z: np.ndarray, valid: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """Approximate gdaldem/Horn slope in degrees on a regular grid."""
    work = z.astype("float64", copy=True)
    med = float(np.nanmedian(work[valid]))
    work[~valid] = med

    # edge padding permits 3x3 Horn stencil.
    p = np.pad(work, 1, mode="edge")
    z1 = p[:-2, :-2]
    z2 = p[:-2, 1:-1]
    z3 = p[:-2, 2:]
    z4 = p[1:-1, :-2]
    z6 = p[1:-1, 2:]
    z7 = p[2:, :-2]
    z8 = p[2:, 1:-1]
    z9 = p[2:, 2:]

    dzdx = ((z3 + 2*z6 + z9) - (z1 + 2*z4 + z7)) / (8.0 * dx)
    dzdy = ((z7 + 2*z8 + z9) - (z1 + 2*z2 + z3)) / (8.0 * dy)
    slope = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
    slope[~valid] = np.nan
    return slope


def propagate_downstream(seed: np.ndarray, ptr: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Replicate the practical GFA channel_ASk behavior: seed cells plus downstream trace."""
    rows, cols = seed.shape
    channel = seed.astype("uint8")
    rr, cc = np.where(seed)
    for r0, c0 in zip(rr.tolist(), cc.tolist()):
        r, c = r0, c0
        seen = 0
        while 0 <= r < rows and 0 <= c < cols and valid[r, c]:
            code = int(ptr[r, c])
            step = WBT_D8.get(code)
            if step is None:
                break
            nr, nc = r + step[0], c + step[1]
            if nr < 0 or nr >= rows or nc < 0 or nc >= cols or not valid[nr, nc]:
                break
            channel[nr, nc] = 1
            r, c = nr, nc
            seen += 1
            if seen > rows * cols:
                raise RuntimeError("Unexpected D8 loop")
    return channel.astype(bool)


def fraction_near(src: np.ndarray, dist: np.ndarray, tol: float) -> float:
    n = int(np.count_nonzero(src))
    return 0.0 if n == 0 else float(np.count_nonzero(src & (dist <= tol)) / n)


def fbeta(p: float, r: float, beta: float) -> float:
    b2 = beta * beta
    d = b2*p + r
    return 0.0 if d == 0 else (1+b2)*p*r/d


def graph_metrics(mask: np.ndarray, ptr: np.ndarray, rx: float, ry: float):
    rows, cols = mask.shape
    inflow = np.zeros(mask.shape, dtype=np.uint8)
    length = 0.0
    outlets = 0
    rr, cc = np.where(mask)
    for r, c in zip(rr.tolist(), cc.tolist()):
        code = int(ptr[r, c])
        step = WBT_D8.get(code)
        if step is None:
            outlets += 1
            continue
        nr, nc = r + step[0], c + step[1]
        if nr < 0 or nr >= rows or nc < 0 or nc >= cols or not mask[nr, nc]:
            outlets += 1
            continue
        inflow[nr, nc] = min(255, int(inflow[nr, nc]) + 1)
        length += math.hypot(step[1]*rx, step[0]*ry)

    lab, ncomp = label(mask, structure=STRUCT8)
    counts = np.bincount(lab.ravel())
    largest = int(counts[1:].max()) if counts.size > 1 else 0
    n = int(np.count_nonzero(mask))
    return {
        "stream_cells": n,
        "network_length_km": float(length / 1000.0),
        "heads": int(np.count_nonzero(mask & (inflow == 0))),
        "outlets": int(outlets),
        "junctions": int(np.count_nonzero(mask & (inflow >= 2))),
        "components": int(ncomp),
        "largest_component_fraction": float(largest / n) if n else 0.0,
    }


def compare_network(name: str, model: np.ndarray, rbi_mask: np.ndarray, ptr, rx, ry):
    sampling = (ry, rx)
    dist_to_rbi = distance_transform_edt(~rbi_mask, sampling=sampling)
    dist_to_model = distance_transform_edt(~model, sampling=sampling)
    m = graph_metrics(model, ptr, rx, ry)
    for tol in TOLS:
        p = fraction_near(model, dist_to_rbi, tol)
        r = fraction_near(rbi_mask, dist_to_model, tol)
        m[f"precision_{int(tol)}m"] = p
        m[f"recall_{int(tol)}m"] = r
        m[f"f1_{int(tol)}m"] = fbeta(p, r, 1.0)
        m[f"f2_{int(tol)}m"] = fbeta(p, r, 2.0)
    m["name"] = name
    return m


def main():
    for p in [DEM, PTR, ACC, STREAM6, DAS, RBI]:
        if not p.exists():
            raise FileNotFoundError(p)

    das_geoms = load_geoms(DAS)
    rbi_geoms = load_geoms(RBI)
    rbi_length_km = float(sum(g.length for g in rbi_geoms) / 1000.0)

    with rasterio.open(DEM) as dds, rasterio.open(PTR) as pds, rasterio.open(ACC) as ads, rasterio.open(STREAM6) as sds:
        refs = [pds, ads, sds]
        for ds in refs:
            if (
                ds.width != dds.width or ds.height != dds.height or ds.crs != dds.crs
                or not ds.transform.almost_equals(dds.transform)
            ):
                raise RuntimeError("Input grids are not aligned")

        dem = dds.read(1).astype("float64")
        ptr = pds.read(1)
        acc = ads.read(1).astype("float64")
        stream6 = sds.read(1) > 0
        rx, ry = abs(dds.res[0]), abs(dds.res[1])
        cell_area = rx * ry

        valid = np.isfinite(dem)
        if dds.nodata is not None and np.isfinite(dds.nodata):
            valid &= ~np.isclose(dem, dds.nodata)

        das_mask = rasterize(
            [(g, 1) for g in das_geoms], out_shape=(dds.height, dds.width),
            transform=dds.transform, fill=0, all_touched=False, dtype="uint8"
        ).astype(bool)
        valid_das = valid & das_mask

        rbi_mask = rasterize(
            [(g, 1) for g in rbi_geoms], out_shape=(dds.height, dds.width),
            transform=dds.transform, fill=0, all_touched=True, dtype="uint8"
        ).astype(bool) & das_mask

        # ESRI pointer export for compatibility/debugging only.
        esri = np.zeros(ptr.shape, dtype="uint8")
        for wbt, es in WBT_TO_ESRI.items():
            esri[ptr == wbt] = es
        write_raster(OUT / "01_D8_POINTER_ESRI.tif", esri, dds, "uint8", 0)

        slope_deg = horn_slope_degree(dem, valid, rx, ry)
        slope_out = np.where(valid, slope_deg, -9999.0).astype("float32")
        write_raster(OUT / "02_SLOPE_DEGREE.tif", slope_out, dds, "float32", -9999.0)

        slope_rad = np.deg2rad(slope_deg)
        tmp = acc * cell_area * np.power(slope_rad + 0.0001, 1.7)
        seed = valid & np.isfinite(tmp) & (tmp > 100000.0)
        ask_full = propagate_downstream(seed, ptr, valid)

        # Evaluation inside official DAS only.
        seed_das = seed & das_mask
        ask_das = ask_full & das_mask
        stream6_das = stream6 & das_mask

        write_raster(OUT / "03_CHANNEL_ASK_SEED.tif", seed_das.astype("uint8"), dds, "uint8", 0)
        write_raster(OUT / "04_CHANNEL_ASK_FULL.tif", ask_das.astype("uint8"), dds, "uint8", 0)
        write_raster(OUT / "05_CHANNEL_FAT_6KM2.tif", stream6_das.astype("uint8"), dds, "uint8", 0)

        rows = [
            compare_network("GFA_channel_ASk", ask_das, rbi_mask, ptr, rx, ry),
            compare_network("Local_FAt_6km2", stream6_das, rbi_mask, ptr, rx, ry),
        ]

        # Direct overlap between the two modeled network definitions.
        inter = ask_das & stream6_das
        union = ask_das | stream6_das
        direct = {
            "intersection_cells": int(np.count_nonzero(inter)),
            "union_cells": int(np.count_nonzero(union)),
            "jaccard_cell_overlap": float(np.count_nonzero(inter) / np.count_nonzero(union)) if np.count_nonzero(union) else 0.0,
            "ask_cells_near_6km_100m": fraction_near(ask_das, distance_transform_edt(~stream6_das, sampling=(ry, rx)), 100.0),
            "6km_cells_near_ask_100m": fraction_near(stream6_das, distance_transform_edt(~ask_das, sampling=(ry, rx)), 100.0),
        }

        result = {
            "source_algorithm": {
                "plugin": "GeomorphicFloodArea / GeomorphicFloodIndex 2.0",
                "channel_method": "channel_ASk",
                "criterion": "flowacc_cells * cell_area_m2 * (slope_rad + 0.0001)^1.7 > 100000",
                "downstream_propagation": "D8 until valid raster boundary",
                "legacy_gui_threshold_10000_note": "not used as contributing-area threshold in channel_ASk",
            },
            "grid": {
                "crs": str(dds.crs),
                "resolution_m": [rx, ry],
                "cell_area_m2": cell_area,
            },
            "rbi": {
                "feature_count": len(rbi_geoms),
                "length_km": rbi_length_km,
                "raster_cells": int(np.count_nonzero(rbi_mask)),
            },
            "ask_seed_cells_full_valid": int(np.count_nonzero(seed)),
            "ask_seed_cells_inside_das": int(np.count_nonzero(seed_das)),
            "comparisons": rows,
            "ask_vs_6km": direct,
        }

    with OUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    fields = [
        "name", "network_length_km", "stream_cells", "heads", "outlets", "junctions", "components",
        "largest_component_fraction",
        "precision_25m", "recall_25m", "f1_25m", "f2_25m",
        "precision_50m", "recall_50m", "f1_50m", "f2_50m",
        "precision_100m", "recall_100m", "f1_100m", "f2_100m",
    ]
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})

    print("=== KURANJI STAGE 2 GFA CHANNEL PREFLIGHT ===")
    print(f"RBI length      : {rbi_length_km:.3f} km")
    print(f"Cell area       : {cell_area:.6f} m2")
    print(f"ASk seed cells  : {result['ask_seed_cells_inside_das']:,} inside DAS")
    print()
    print("network          | length | heads out comps | P100 R100 F1 F2")
    print("-----------------+--------+----------------+-------------------")
    for r in rows:
        print(
            f"{r['name']:<16} | {r['network_length_km']:>6.2f} | "
            f"{r['heads']:>5} {r['outlets']:>3} {r['components']:>5} | "
            f"{r['precision_100m']:.3f} {r['recall_100m']:.3f} {r['f1_100m']:.3f} {r['f2_100m']:.3f}"
        )
    print()
    print(f"ASk vs 6km cell Jaccard : {direct['jaccard_cell_overlap']:.4f}")
    print(f"ASk -> 6km <=100m       : {direct['ask_cells_near_6km_100m']:.4f}")
    print(f"6km -> ASk <=100m       : {direct['6km_cells_near_ask_100m']:.4f}")
    print("\nJSON:", OUT_JSON)
    print("CSV :", OUT_CSV)
    print("Raster outputs:", OUT)


if __name__ == "__main__":
    main()
