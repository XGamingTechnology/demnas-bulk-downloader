#!/usr/bin/env python3
"""Sensitivity analysis for Kuranji normalized GFI flood-prone thresholds.

Purpose
-------
The legacy/manual GFA threshold -0.53 admits many cells with WD = hr - H < 0.
This diagnostic quantifies how threshold selection changes:
- flood-prone area;
- positive/negative WD fractions;
- connected components;
- WD statistics;
- overlap with the physical-consistency domain GFI_raw > 0 (equiv. WD > 0).

This script does NOT automatically declare a final threshold.

Outputs
-------
data/work/kuranji/10_gfi_threshold_sensitivity/
  gfi_threshold_sensitivity.csv
  gfi_threshold_sensitivity.json
  threshold_masks/*.tif
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
OUT = ROOT / "data/work/kuranji/10_gfi_threshold_sensitivity"
MASKDIR = OUT / "threshold_masks"
OUT.mkdir(parents=True, exist_ok=True)
MASKDIR.mkdir(parents=True, exist_ok=True)

GFI_RAW = BASE / "06_GFI_RAW.tif"
GFI_NORM = BASE / "07_GFI_NORMALIZED.tif"
H = BASE / "02_H_CONNECTED_DRAINAGE_M.tif"
HR = BASE / "05_HR_M.tif"
DAS = PREP / "DAS_KURANJI_UTM47S.geojson"

OUT_CSV = OUT / "gfi_threshold_sensitivity.csv"
OUT_JSON = OUT / "gfi_threshold_sensitivity.json"

NODATA = -9999.0
STRUCT8 = np.ones((3, 3), dtype=np.uint8)
MIN_COMPONENT_PIXELS = 8

# Include manual default and dense coverage around the physical zero-WD boundary.
THRESHOLDS = [
    -0.60, -0.55, -0.53, -0.50, -0.45, -0.40, -0.35,
    -0.34, -0.338, -0.3378, -0.335, -0.33, -0.30, -0.25,
    -0.20, -0.10, 0.00, 0.10, 0.20,
]


def load_geojson(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def stat(vals: np.ndarray):
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return {"count": 0}
    return {
        "count": int(vals.size),
        "min": float(np.min(vals)),
        "p05": float(np.percentile(vals, 5)),
        "p25": float(np.percentile(vals, 25)),
        "median": float(np.median(vals)),
        "mean": float(np.mean(vals)),
        "p75": float(np.percentile(vals, 75)),
        "p95": float(np.percentile(vals, 95)),
        "p99": float(np.percentile(vals, 99)),
        "max": float(np.max(vals)),
    }


def clean_components(mask: np.ndarray):
    lab, ncomp = label(mask, structure=STRUCT8)
    counts = np.bincount(lab.ravel())
    keep = np.where(counts >= MIN_COMPONENT_PIXELS)[0]
    keep = keep[keep != 0]
    cleaned = np.isin(lab, keep)
    return cleaned, int(ncomp), int(len(keep)), counts


def write_mask(path: Path, mask: np.ndarray, ref):
    profile = ref.profile.copy()
    profile.update(
        driver="GTiff", dtype="uint8", count=1, nodata=0,
        compress="DEFLATE", tiled=True, blockxsize=512, blockysize=512,
    )
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(mask.astype("uint8"), 1)


def slug(t: float) -> str:
    sign = "M" if t < 0 else "P"
    return f"{sign}{abs(t):.4f}".replace(".", "P")


def main():
    for p in [GFI_RAW, GFI_NORM, H, HR, DAS]:
        if not p.exists():
            raise FileNotFoundError(p)

    fc = load_geojson(DAS)
    geoms = [shape(ft["geometry"]) for ft in fc.get("features", []) if ft.get("geometry")]
    if not geoms:
        raise RuntimeError("No DAS geometry")

    with rasterio.open(GFI_RAW) as rds, rasterio.open(GFI_NORM) as nds, \
         rasterio.open(H) as hds, rasterio.open(HR) as hrds:
        for ds in [nds, hds, hrds]:
            if (
                ds.width != rds.width or ds.height != rds.height or ds.crs != rds.crs
                or not ds.transform.almost_equals(rds.transform)
            ):
                raise RuntimeError("Input Stage-2 rasters are not aligned")

        raw = rds.read(1).astype("float64")
        norm = nds.read(1).astype("float64")
        hh = hds.read(1).astype("float64")
        hr = hrds.read(1).astype("float64")

        for arr, ds in [(raw, rds), (norm, nds), (hh, hds), (hr, hrds)]:
            if ds.nodata is not None and np.isfinite(ds.nodata):
                arr[np.isclose(arr, ds.nodata)] = np.nan

        das_mask = rasterize(
            [(g, 1) for g in geoms], out_shape=(rds.height, rds.width),
            transform=rds.transform, fill=0, all_touched=False, dtype="uint8",
        ).astype(bool)

        valid = das_mask & np.isfinite(raw) & np.isfinite(norm) & np.isfinite(hh) & np.isfinite(hr)
        wd = np.full(raw.shape, np.nan, dtype="float64")
        wd[valid] = hr[valid] - hh[valid]
        phys = valid & (wd > 0)
        raw_gt0 = valid & (raw > 0)

        # Sanity: these should be identical except floating precision at zero.
        phys_xor_raw0 = int(np.count_nonzero(phys ^ raw_gt0))

        raw_min = float(np.nanmin(raw[valid]))
        raw_max = float(np.nanmax(raw[valid]))
        norm_zero_raw = 2.0 * ((0.0 - raw_min) / (raw_max - raw_min) - 0.5)
        cell_area = abs(rds.res[0] * rds.res[1])
        n_valid = int(np.count_nonzero(valid))

        results = []
        for t in THRESHOLDS:
            mask0 = valid & (norm > t)
            mask, comps_before, comps_after, counts = clean_components(mask0)
            mask &= das_mask

            n = int(np.count_nonzero(mask))
            neg = mask & (wd < 0)
            zero = mask & np.isclose(wd, 0.0, atol=1e-12)
            pos = mask & (wd > 0)
            nneg = int(np.count_nonzero(neg))
            nzero = int(np.count_nonzero(zero))
            npos = int(np.count_nonzero(pos))

            inter_phys = int(np.count_nonzero(mask & phys))
            union_phys = int(np.count_nonzero(mask | phys))
            recall_phys = inter_phys / int(np.count_nonzero(phys)) if np.count_nonzero(phys) else 0.0
            precision_phys = inter_phys / n if n else 0.0
            jaccard_phys = inter_phys / union_phys if union_phys else 0.0

            component_areas = []
            lab, _ = label(mask, structure=STRUCT8)
            lab_counts = np.bincount(lab.ravel())
            for cid in range(1, len(lab_counts)):
                if lab_counts[cid] > 0:
                    component_areas.append(lab_counts[cid] * cell_area / 1_000_000.0)
            component_areas.sort(reverse=True)

            rec = {
                "threshold_norm": float(t),
                "area_km2": float(n * cell_area / 1_000_000.0),
                "area_ha": float(n * cell_area / 10_000.0),
                "percent_das_valid": float(100.0 * n / n_valid) if n_valid else 0.0,
                "positive_wd_cells": npos,
                "positive_wd_percent": float(100.0 * npos / n) if n else 0.0,
                "negative_wd_cells": nneg,
                "negative_wd_percent": float(100.0 * nneg / n) if n else 0.0,
                "zero_wd_cells": nzero,
                "components_before_cleanup": comps_before,
                "components_after_cleanup": comps_after,
                "largest_component_km2": float(component_areas[0]) if component_areas else 0.0,
                "physical_precision": float(precision_phys),
                "physical_recall": float(recall_phys),
                "physical_jaccard": float(jaccard_phys),
                "wd_all": stat(wd[mask]),
                "wd_positive": stat(wd[pos]),
            }
            results.append(rec)

            # Save only key masks to avoid unnecessary disk usage.
            if t in (-0.53, -0.40, -0.35, -0.34, -0.3378, -0.33, -0.30, 0.0):
                write_mask(MASKDIR / f"PRONE_{slug(t)}.tif", mask, rds)

        result = {
            "method": {
                "threshold_domain": "GFI normalized [-1,+1]",
                "cleanup": f"8-neighbour connected components >= {MIN_COMPONENT_PIXELS} pixels",
                "physical_consistency_definition": "WD = hr-H > 0, mathematically equivalent to GFI_raw > 0",
                "status": "sensitivity only; no final threshold automatically selected",
            },
            "grid": {
                "crs": str(rds.crs),
                "cell_area_m2": cell_area,
                "valid_das_gfi_cells": n_valid,
            },
            "gfi": {
                "raw_min": raw_min,
                "raw_max": raw_max,
                "normalized_value_at_raw_zero": float(norm_zero_raw),
                "physical_positive_wd_area_km2": float(np.count_nonzero(phys) * cell_area / 1_000_000.0),
                "physical_positive_wd_percent": float(100.0 * np.count_nonzero(phys) / n_valid),
                "wd_positive_vs_raw_gt0_xor_cells": phys_xor_raw0,
            },
            "thresholds": results,
        }

    with OUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    fields = [
        "threshold_norm", "area_km2", "area_ha", "percent_das_valid",
        "positive_wd_cells", "positive_wd_percent",
        "negative_wd_cells", "negative_wd_percent", "zero_wd_cells",
        "components_before_cleanup", "components_after_cleanup",
        "largest_component_km2",
        "physical_precision", "physical_recall", "physical_jaccard",
        "wd_min", "wd_median", "wd_mean", "wd_p95", "wd_p99", "wd_max",
        "wd_positive_median", "wd_positive_mean", "wd_positive_p95", "wd_positive_p99", "wd_positive_max",
    ]
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in results:
            a = r["wd_all"]
            p = r["wd_positive"]
            row = {
                "threshold_norm": r["threshold_norm"],
                "area_km2": r["area_km2"],
                "area_ha": r["area_ha"],
                "percent_das_valid": r["percent_das_valid"],
                "positive_wd_cells": r["positive_wd_cells"],
                "positive_wd_percent": r["positive_wd_percent"],
                "negative_wd_cells": r["negative_wd_cells"],
                "negative_wd_percent": r["negative_wd_percent"],
                "zero_wd_cells": r["zero_wd_cells"],
                "components_before_cleanup": r["components_before_cleanup"],
                "components_after_cleanup": r["components_after_cleanup"],
                "largest_component_km2": r["largest_component_km2"],
                "physical_precision": r["physical_precision"],
                "physical_recall": r["physical_recall"],
                "physical_jaccard": r["physical_jaccard"],
                "wd_min": a.get("min"),
                "wd_median": a.get("median"),
                "wd_mean": a.get("mean"),
                "wd_p95": a.get("p95"),
                "wd_p99": a.get("p99"),
                "wd_max": a.get("max"),
                "wd_positive_median": p.get("median"),
                "wd_positive_mean": p.get("mean"),
                "wd_positive_p95": p.get("p95"),
                "wd_positive_p99": p.get("p99"),
                "wd_positive_max": p.get("max"),
            }
            w.writerow(row)

    print("=== KURANJI GFI THRESHOLD SENSITIVITY ===")
    print(f"Raw GFI range              : {raw_min:.6f} .. {raw_max:.6f}")
    print(f"Norm value at GFI_raw=0    : {norm_zero_raw:.6f}")
    print(f"Positive-WD physical area  : {result['gfi']['physical_positive_wd_area_km2']:.3f} km2 ({result['gfi']['physical_positive_wd_percent']:.2f}%)")
    print(f"WD>0 vs raw>0 XOR cells    : {phys_xor_raw0}")
    print()
    print("thr     area_km2  posWD%  negWD%  comps  physP  physR  Jaccard")
    print("------- ---------- ------- ------- ------ ------ ------ -------")
    for r in results:
        print(
            f"{r['threshold_norm']:>7.4f} {r['area_km2']:>10.3f} "
            f"{r['positive_wd_percent']:>7.2f} {r['negative_wd_percent']:>7.2f} "
            f"{r['components_after_cleanup']:>6} "
            f"{r['physical_precision']:>6.3f} {r['physical_recall']:>6.3f} {r['physical_jaccard']:>7.3f}"
        )
    print("\nJSON:", OUT_JSON)
    print("CSV :", OUT_CSV)
    print("Selected diagnostic masks:", MASKDIR)


if __name__ == "__main__":
    main()
