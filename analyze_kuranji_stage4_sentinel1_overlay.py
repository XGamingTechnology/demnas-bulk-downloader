#!/usr/bin/env python3
"""Overlay Kuranji Stage-4 Sentinel-1 change evidence with frozen Stage-3 references.

Purpose
-------
Evaluate whether Sentinel-1 temporal backscatter changes differ spatially within:
- BIG/BRIN observed flood extent dated 2025-12-01
- frozen P175 baseline hazard candidate
- Stage-3 true-positive overlap (Observed & P175)
- Stage-3 false-negative area (Observed & not P175)

This is descriptive evidence analysis only. It does NOT select a Sentinel-1 flood
threshold and does NOT redefine the frozen Stage-3 validation result.

Important interpretation caveat
-------------------------------
Pixels outside the BIG/BRIN observed polygon are labelled NON_OBSERVED_REFERENCE,
not "dry" or "true negative". The 2025-12-01 WorldView-derived extent may not
represent the flood peak during 2025-11-21 to 2025-11-27.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject

ROOT = Path(__file__).resolve().parent
S1_ROOT = ROOT / "data/work/kuranji/19_stage4_sentinel1_change"
CHANGE = S1_ROOT / "change"
ALIGNED = S1_ROOT / "aligned"
OUT = ROOT / "data/work/kuranji/20_stage4_sentinel1_overlay"
OUT.mkdir(parents=True, exist_ok=True)

P175 = ROOT / "data/work/kuranji/14_stage2_admin_final/raster/P175_HAZARD_CLASS.tif"
OBSERVED = ROOT / "data/work/kuranji/15_stage3_validation/results_big_layer3/raster/OBSERVED_BIG_BRIN_20251201.tif"
REFERENCE_GRID = ALIGNED / "EVENT_VV_gamma0_dB_20m_DAS.tif"
NODATA_FLOAT = -9999.0
NODATA_BYTE = 255
PIXEL_AREA_KM2 = 20.0 * 20.0 / 1e6

LAYERS = {
    "EVENT_MINUS_PRE_VV_DB": CHANGE / "EVENT_MINUS_PRE_VV_dB_20m_DAS.tif",
    "EVENT_MINUS_PRE_VH_DB": CHANGE / "EVENT_MINUS_PRE_VH_dB_20m_DAS.tif",
    "EVENT_MINUS_PRE_VHminusVV_DB": CHANGE / "EVENT_MINUS_PRE_VHminusVV_dB_20m_DAS.tif",
    "POST_MINUS_PRE_VV_DB": CHANGE / "POST_MINUS_PRE_VV_dB_20m_DAS.tif",
    "POST_MINUS_PRE_VH_DB": CHANGE / "POST_MINUS_PRE_VH_dB_20m_DAS.tif",
    "POST_MINUS_PRE_VHminusVV_DB": CHANGE / "POST_MINUS_PRE_VHminusVV_dB_20m_DAS.tif",
    "POST_MINUS_EVENT_VV_DB": CHANGE / "POST_MINUS_EVENT_VV_dB_20m_DAS.tif",
    "POST_MINUS_EVENT_VH_DB": CHANGE / "POST_MINUS_EVENT_VH_dB_20m_DAS.tif",
    "POST_MINUS_EVENT_VHminusVV_DB": CHANGE / "POST_MINUS_EVENT_VHminusVV_dB_20m_DAS.tif",
}


def load_reference_grid():
    if not REFERENCE_GRID.exists():
        raise FileNotFoundError(REFERENCE_GRID)
    with rasterio.open(REFERENCE_GRID) as ds:
        arr = ds.read(1, masked=True)
        inside = ~np.ma.getmaskarray(arr)
        return {
            "crs": ds.crs,
            "transform": ds.transform,
            "width": ds.width,
            "height": ds.height,
            "profile": ds.profile.copy(),
            "inside": inside,
        }


def align_positive_mask(src_path: Path, grid, label: str):
    if not src_path.exists():
        raise FileNotFoundError(src_path)

    dst = np.full((grid["height"], grid["width"]), np.nan, dtype="float32")
    with rasterio.open(src_path) as src:
        source = src.read(1, masked=True).astype("float32").filled(np.nan)
        reproject(
            source=source,
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=np.nan,
            dst_transform=grid["transform"],
            dst_crs=grid["crs"],
            dst_nodata=np.nan,
            resampling=Resampling.nearest,
            num_threads=2,
        )

    # Both source products encode their mapped domain/classes using positive values.
    # Outside-source or zero values are not treated as mapped positive.
    positive = np.isfinite(dst) & (dst > 0) & grid["inside"]
    print(f"{label:<10}: pixels={int(positive.sum())} area={positive.sum() * PIXEL_AREA_KM2:.4f} km2")
    return positive


def load_float(path: Path, grid):
    if not path.exists():
        raise FileNotFoundError(path)
    with rasterio.open(path) as ds:
        if (
            ds.crs != grid["crs"]
            or ds.transform != grid["transform"]
            or ds.width != grid["width"]
            or ds.height != grid["height"]
        ):
            raise RuntimeError(f"Layer not on Stage-4 reference grid: {path}")
        return ds.read(1, masked=True).astype("float32").filled(np.nan)


def describe(arr, mask):
    x = arr[mask & np.isfinite(arr)]
    if x.size == 0:
        return {"n": 0}
    q = np.percentile(x, [1, 5, 25, 50, 75, 95, 99])
    return {
        "n": int(x.size),
        "area_km2": float(x.size * PIXEL_AREA_KM2),
        "min": float(np.min(x)),
        "p01": float(q[0]),
        "p05": float(q[1]),
        "p25": float(q[2]),
        "median": float(q[3]),
        "mean": float(np.mean(x)),
        "p75": float(q[4]),
        "p95": float(q[5]),
        "p99": float(q[6]),
        "max": float(np.max(x)),
        "std": float(np.std(x)),
        "negative_pct": float(np.mean(x < 0) * 100.0),
        "positive_pct": float(np.mean(x > 0) * 100.0),
    }


def write_mask(path: Path, mask: np.ndarray, grid, description: str):
    data = np.full(mask.shape, NODATA_BYTE, dtype="uint8")
    data[grid["inside"]] = 0
    data[mask & grid["inside"]] = 1
    profile = grid["profile"].copy()
    profile.update(
        driver="GTiff",
        dtype="uint8",
        count=1,
        nodata=NODATA_BYTE,
        compress="deflate",
        predictor=2,
    )
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)
        dst.set_band_description(1, description)


def main():
    print("=== KURANJI STAGE 4 SENTINEL-1 / BIG-BRIN / P175 OVERLAY ===")
    grid = load_reference_grid()
    print(f"Grid: {grid['width']} x {grid['height']} | {grid['crs']} | 20 m")
    print(f"DAS grid area: {grid['inside'].sum() * PIXEL_AREA_KM2:.4f} km2\n")

    observed = align_positive_mask(OBSERVED, grid, "OBSERVED")
    p175 = align_positive_mask(P175, grid, "P175")

    tp = observed & p175
    fn = observed & (~p175) & grid["inside"]
    p175_only = p175 & (~observed) & grid["inside"]
    non_observed = (~observed) & grid["inside"]

    zones = {
        "DAS_ALL": grid["inside"],
        "OBSERVED_BIG_BRIN": observed,
        "NON_OBSERVED_REFERENCE": non_observed,
        "P175_DOMAIN": p175,
        "STAGE3_TP_OBSERVED_AND_P175": tp,
        "STAGE3_FN_OBSERVED_NOT_P175": fn,
        "P175_ONLY_RELATIVE_TO_20251201_OBSERVED": p175_only,
    }

    print("\n=== ZONE AREAS ON 20 M GRID ===")
    zone_summary = {}
    for name, mask in zones.items():
        px = int(mask.sum())
        area = px * PIXEL_AREA_KM2
        zone_summary[name] = {"pixels": px, "area_km2": area}
        print(f"{name:<42} pixels={px:7d} area={area:9.4f} km2")

    # Aligned evidence masks for map inspection in QGIS.
    write_mask(OUT / "OBSERVED_BIG_BRIN_20251201_20m.tif", observed, grid, "BIG/BRIN observed flood extent 2025-12-01")
    write_mask(OUT / "P175_DOMAIN_20m.tif", p175, grid, "P175 positive hazard domain")
    write_mask(OUT / "STAGE3_TP_20m.tif", tp, grid, "Observed and P175 overlap")
    write_mask(OUT / "STAGE3_FN_20m.tif", fn, grid, "Observed BIG/BRIN but outside P175")

    rows = []
    layer_arrays = {}
    for layer_name, path in LAYERS.items():
        arr = load_float(path, grid)
        layer_arrays[layer_name] = arr
        for zone_name, mask in zones.items():
            st = describe(arr, mask)
            row = {"layer": layer_name, "zone": zone_name}
            row.update(st)
            rows.append(row)

    fields = [
        "layer", "zone", "n", "area_km2", "min", "p01", "p05", "p25",
        "median", "mean", "p75", "p95", "p99", "max", "std",
        "negative_pct", "positive_pct",
    ]
    with (OUT / "SENTINEL1_CHANGE_BY_ZONE.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow(row)

    # Compact comparison focused on the event-date change evidence.
    compact = []
    for layer_name in [
        "EVENT_MINUS_PRE_VV_DB",
        "EVENT_MINUS_PRE_VH_DB",
        "EVENT_MINUS_PRE_VHminusVV_DB",
    ]:
        arr = layer_arrays[layer_name]
        zone_stats = {name: describe(arr, mask) for name, mask in zones.items()}
        obs = zone_stats["OBSERVED_BIG_BRIN"]
        non = zone_stats["NON_OBSERVED_REFERENCE"]
        tp_s = zone_stats["STAGE3_TP_OBSERVED_AND_P175"]
        fn_s = zone_stats["STAGE3_FN_OBSERVED_NOT_P175"]
        compact.append({
            "layer": layer_name,
            "observed_median_db": obs.get("median"),
            "non_observed_median_db": non.get("median"),
            "observed_minus_nonobserved_median_db": (
                obs.get("median") - non.get("median")
                if obs.get("median") is not None and non.get("median") is not None else None
            ),
            "tp_median_db": tp_s.get("median"),
            "fn_median_db": fn_s.get("median"),
            "fn_minus_tp_median_db": (
                fn_s.get("median") - tp_s.get("median")
                if fn_s.get("median") is not None and tp_s.get("median") is not None else None
            ),
            "observed_p05_db": obs.get("p05"),
            "observed_p95_db": obs.get("p95"),
            "fn_p05_db": fn_s.get("p05"),
            "fn_p95_db": fn_s.get("p95"),
        })

    compact_fields = list(compact[0].keys())
    with (OUT / "EVENT_CHANGE_COMPACT_COMPARISON.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=compact_fields)
        w.writeheader()
        w.writerows(compact)

    metadata = {
        "reference_grid": str(REFERENCE_GRID),
        "observed_source": str(OBSERVED),
        "p175_source": str(P175),
        "pixel_area_km2": PIXEL_AREA_KM2,
        "zones": zone_summary,
        "interpretation_caveat": (
            "NON_OBSERVED_REFERENCE means outside the mapped BIG/BRIN 2025-12-01 extent; "
            "it must not be interpreted as confirmed dry or as event-peak true negative."
        ),
        "threshold_policy": "No Sentinel-1 flood/change threshold selected in this script.",
    }
    (OUT / "overlay_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== EVENT - PRE COMPACT COMPARISON ===")
    for r in compact:
        print(f"\n{r['layer']}")
        print(f"  observed median             : {r['observed_median_db']:.3f} dB")
        print(f"  non-observed ref median     : {r['non_observed_median_db']:.3f} dB")
        print(f"  observed - non-observed     : {r['observed_minus_nonobserved_median_db']:+.3f} dB")
        print(f"  Stage3 TP median            : {r['tp_median_db']:.3f} dB")
        print(f"  Stage3 FN median            : {r['fn_median_db']:.3f} dB")
        print(f"  FN - TP median              : {r['fn_minus_tp_median_db']:+.3f} dB")
        print(f"  observed p05..p95           : {r['observed_p05_db']:.3f} .. {r['observed_p95_db']:.3f} dB")
        print(f"  FN p05..p95                 : {r['fn_p05_db']:.3f} .. {r['fn_p95_db']:.3f} dB")

    print("\n=== DONE ===")
    print("Output:", OUT)
    print("Detailed CSV:", OUT / "SENTINEL1_CHANGE_BY_ZONE.csv")
    print("Compact CSV :", OUT / "EVENT_CHANGE_COMPACT_COMPARISON.csv")
    print("NEXT: interpret observed-vs-non-observed and TP-vs-FN distributions before any threshold experiment.")


if __name__ == "__main__":
    main()
