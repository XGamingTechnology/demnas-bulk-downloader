#!/usr/bin/env python3
"""Audit provisional GFI threshold and WD readiness for Kuranji Stage 2.

This script does NOT lock the final flood-prone threshold and does NOT yet create
the final fuzzy hazard index. It checks whether the manual/default GFA threshold
(-0.53 on normalized GFI) produces a physically usable WD = hr - H domain, and
scans ignored local data folders for possible independent flood/genangan datasets
that could be used for GFI threshold calibration.

Inputs
------
data/work/kuranji/08_gfi_baseline/
  02_H_CONNECTED_DRAINAGE_M.tif
  05_HR_M.tif
  07_GFI_NORMALIZED.tif
  08_GFI_MANUAL_PRONE_M053.tif

data/work/kuranji/01_prepared/DAS_KURANJI_UTM47S.geojson

Outputs
-------
data/work/kuranji/09_gfi_threshold_audit/
  01_WD_MANUAL_M053_RAW.tif
  02_WD_MANUAL_M053_NONNEGATIVE.tif
  gfi_threshold_wd_audit.json
  gfi_threshold_wd_audit.csv
  calibration_candidate_files.txt
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from scipy.ndimage import label
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "data/work/kuranji/08_gfi_baseline"
PREP = ROOT / "data/work/kuranji/01_prepared"
OUT = ROOT / "data/work/kuranji/09_gfi_threshold_audit"
OUT.mkdir(parents=True, exist_ok=True)

H_PATH = BASE / "02_H_CONNECTED_DRAINAGE_M.tif"
HR_PATH = BASE / "05_HR_M.tif"
GFI_NORM_PATH = BASE / "07_GFI_NORMALIZED.tif"
PRONE_PATH = BASE / "08_GFI_MANUAL_PRONE_M053.tif"
DAS_PATH = PREP / "DAS_KURANJI_UTM47S.geojson"

OUT_WD_RAW = OUT / "01_WD_MANUAL_M053_RAW.tif"
OUT_WD_NONNEG = OUT / "02_WD_MANUAL_M053_NONNEGATIVE.tif"
OUT_JSON = OUT / "gfi_threshold_wd_audit.json"
OUT_CSV = OUT / "gfi_threshold_wd_audit.csv"
OUT_CAND = OUT / "calibration_candidate_files.txt"

NODATA = -9999.0
STRUCT8 = np.ones((3, 3), dtype=np.uint8)

KEYWORDS = (
    "banjir", "flood", "genangan", "inundation", "hazard", "bahaya",
    "terdampak", "dampak", "kalibrasi", "calibration",
)
EXTENSIONS = {
    ".tif", ".tiff", ".shp", ".geojson", ".json", ".gpkg", ".asc",
    ".txt", ".csv", ".kml", ".kmz", ".zip",
}


def load_geojson(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def write_float(path: Path, arr: np.ndarray, ref):
    out = np.where(np.isfinite(arr), arr, NODATA).astype("float32")
    profile = ref.profile.copy()
    profile.update(
        driver="GTiff", dtype="float32", count=1, nodata=NODATA,
        compress="DEFLATE", tiled=True, blockxsize=512, blockysize=512,
    )
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(out, 1)


def stat(x: np.ndarray):
    x = x[np.isfinite(x)]
    if x.size == 0:
        return {"count": 0}
    return {
        "count": int(x.size),
        "min": float(np.min(x)),
        "p01": float(np.percentile(x, 1)),
        "p05": float(np.percentile(x, 5)),
        "p25": float(np.percentile(x, 25)),
        "median": float(np.median(x)),
        "mean": float(np.mean(x)),
        "p75": float(np.percentile(x, 75)),
        "p95": float(np.percentile(x, 95)),
        "p99": float(np.percentile(x, 99)),
        "max": float(np.max(x)),
    }


def scan_candidates():
    data_root = ROOT / "data"
    found = []
    if not data_root.exists():
        return found
    for p in data_root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in EXTENSIONS:
            continue
        try:
            rel = p.relative_to(ROOT)
        except ValueError:
            rel = p
        # Avoid treating the products we just created as calibration inputs.
        if "08_gfi_baseline" in str(rel) or "09_gfi_threshold_audit" in str(rel):
            continue
        lname = p.name.lower()
        if any(k in lname for k in KEYWORDS):
            found.append({
                "path": str(rel),
                "size_mb": round(p.stat().st_size / 1024 / 1024, 3),
            })
    return sorted(found, key=lambda d: d["path"].lower())


def main():
    for p in [H_PATH, HR_PATH, GFI_NORM_PATH, PRONE_PATH, DAS_PATH]:
        if not p.exists():
            raise FileNotFoundError(p)

    fc = load_geojson(DAS_PATH)
    geoms = [shape(ft["geometry"]) for ft in fc.get("features", []) if ft.get("geometry")]
    if not geoms:
        raise RuntimeError("No DAS geometry")

    with rasterio.open(H_PATH) as hds, rasterio.open(HR_PATH) as rds, \
         rasterio.open(GFI_NORM_PATH) as gds, rasterio.open(PRONE_PATH) as pds:
        for ds in [rds, gds, pds]:
            if (
                ds.width != hds.width or ds.height != hds.height or ds.crs != hds.crs
                or not ds.transform.almost_equals(hds.transform)
            ):
                raise RuntimeError("Stage-2 GFI rasters are not grid-aligned")

        H = hds.read(1).astype("float64")
        hr = rds.read(1).astype("float64")
        gfi = gds.read(1).astype("float64")
        prone = pds.read(1) > 0

        for arr, ds in [(H, hds), (hr, rds), (gfi, gds)]:
            if ds.nodata is not None and np.isfinite(ds.nodata):
                arr[np.isclose(arr, ds.nodata)] = np.nan

        das_mask = rasterize(
            [(g, 1) for g in geoms], out_shape=(hds.height, hds.width),
            transform=hds.transform, fill=0, all_touched=False, dtype="uint8",
        ).astype(bool)

        valid = das_mask & np.isfinite(H) & np.isfinite(hr) & np.isfinite(gfi)
        prone &= valid
        cell_area = abs(hds.res[0] * hds.res[1])

        wd_raw = np.full(H.shape, np.nan, dtype="float64")
        wd_raw[prone] = hr[prone] - H[prone]

        neg = prone & np.isfinite(wd_raw) & (wd_raw < 0)
        zero = prone & np.isfinite(wd_raw) & np.isclose(wd_raw, 0.0, atol=1e-12)
        pos = prone & np.isfinite(wd_raw) & (wd_raw > 0)

        # Diagnostic only. This is NOT silently substituted for the module equation.
        # It is exported to show what the usable non-negative domain would look like
        # if negative WD must later be excluded before ArcGIS-style FuzzyLarge.
        wd_nonneg = np.full(H.shape, np.nan, dtype="float64")
        wd_nonneg[prone] = np.maximum(wd_raw[prone], 0.0)

        write_float(OUT_WD_RAW, wd_raw, hds)
        write_float(OUT_WD_NONNEG, wd_nonneg, hds)

        lab, ncomp = label(prone, structure=STRUCT8)
        counts = np.bincount(lab.ravel())
        comp = []
        for cid in range(1, len(counts)):
            if counts[cid] <= 0:
                continue
            comp.append({
                "component": cid,
                "cells": int(counts[cid]),
                "area_km2": float(counts[cid] * cell_area / 1_000_000.0),
            })
        comp.sort(key=lambda d: d["cells"], reverse=True)

        n_prone = int(np.count_nonzero(prone))
        n_neg = int(np.count_nonzero(neg))
        n_zero = int(np.count_nonzero(zero))
        n_pos = int(np.count_nonzero(pos))

        candidates = scan_candidates()

        result = {
            "status": "pre-final threshold audit",
            "manual_threshold": -0.53,
            "threshold_domain": "GFI normalized [-1,+1]",
            "prone": {
                "cells": n_prone,
                "area_km2": n_prone * cell_area / 1_000_000.0,
                "components": int(ncomp),
                "largest_components": comp[:10],
            },
            "wd_raw": {
                "formula": "hr - H",
                "statistics_all_prone": stat(wd_raw[prone]),
                "negative_cells": n_neg,
                "negative_percent_of_prone": 100.0 * n_neg / n_prone if n_prone else 0.0,
                "zero_cells": n_zero,
                "positive_cells": n_pos,
                "positive_percent_of_prone": 100.0 * n_pos / n_prone if n_prone else 0.0,
                "statistics_positive_only": stat(wd_raw[pos]),
            },
            "fuzzy_readiness": {
                "module_membership": "Large",
                "midpoint_m": 1.125,
                "spread": 1.75,
                "note": "ArcGIS FuzzyLarge expects non-negative input values; negative WD must be resolved methodologically, not silently accepted.",
            },
            "calibration_candidate_files": candidates,
        }

    with OUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    fields = [
        "metric", "value",
    ]
    rows = [
        {"metric": "prone_area_km2", "value": result["prone"]["area_km2"]},
        {"metric": "prone_components", "value": result["prone"]["components"]},
        {"metric": "wd_negative_cells", "value": n_neg},
        {"metric": "wd_negative_percent", "value": result["wd_raw"]["negative_percent_of_prone"]},
        {"metric": "wd_zero_cells", "value": n_zero},
        {"metric": "wd_positive_cells", "value": n_pos},
        {"metric": "wd_positive_percent", "value": result["wd_raw"]["positive_percent_of_prone"]},
        {"metric": "candidate_calibration_files", "value": len(candidates)},
    ]
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    with OUT_CAND.open("w", encoding="utf-8") as f:
        if not candidates:
            f.write("No filename-based flood/genangan calibration candidates detected under data/.\n")
        else:
            for d in candidates:
                f.write(f"{d['path']}\t{d['size_mb']} MB\n")

    print("=== KURANJI GFI THRESHOLD + WD AUDIT ===")
    print(f"Manual -0.53 prone area : {result['prone']['area_km2']:.3f} km2")
    print(f"Prone components        : {result['prone']['components']}")
    for d in result["prone"]["largest_components"][:5]:
        print(f"  component #{d['component']}: {d['area_km2']:.3f} km2")
    print()
    print(f"WD negative cells       : {n_neg:,} ({result['wd_raw']['negative_percent_of_prone']:.3f}%)")
    print(f"WD zero cells           : {n_zero:,}")
    print(f"WD positive cells       : {n_pos:,} ({result['wd_raw']['positive_percent_of_prone']:.3f}%)")
    s = result["wd_raw"]["statistics_all_prone"]
    if s.get("count", 0):
        print(f"WD raw range            : {s['min']:.6f} .. {s['max']:.6f} m")
        print(f"WD median / mean        : {s['median']:.6f} / {s['mean']:.6f} m")
    sp = result["wd_raw"]["statistics_positive_only"]
    if sp.get("count", 0):
        print(f"WD positive p95 / p99   : {sp['p95']:.6f} / {sp['p99']:.6f} m")
    print()
    print(f"Calibration candidates  : {len(candidates)}")
    for d in candidates[:15]:
        print(f"  {d['path']} ({d['size_mb']} MB)")
    if len(candidates) > 15:
        print(f"  ... and {len(candidates)-15} more; see {OUT_CAND}")
    print("\nJSON:", OUT_JSON)
    print("CSV :", OUT_CSV)
    print("Candidates:", OUT_CAND)
    print("WD diagnostic rasters:", OUT)


if __name__ == "__main__":
    main()
